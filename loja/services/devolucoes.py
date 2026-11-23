import secrets
import string
from datetime import datetime, timedelta
from ..db import transaction
from ..utils import ErroNegocio, agora, to_float, money
from .estoque import movimentar
from .caixa import exigir_caixa_aberto

_ALFABETO = string.ascii_uppercase + string.digits

def _novo_codigo_vale(conn) -> str:
    while True:
        codigo = "VT-" + "".join(secrets.choice(_ALFABETO) for _ in range(6))
        if not conn.execute("SELECT 1 FROM vales_troca WHERE codigo = ?", (codigo,)).fetchone():
            return codigo

def processar_devolucao(conn, usuario: dict, venda_id: int, tipo: str, itens_devolvidos: list[dict], obs: str) -> dict:
    """
    itens_devolvidos = [{"venda_item_id": 1, "quantidade": 2}, ...]
    tipo = 'vale' ou 'dinheiro'
    """
    if tipo not in ('vale', 'dinheiro'):
        raise ErroNegocio("Tipo de devolução inválido")
        
    if not itens_devolvidos:
        raise ErroNegocio("Nenhum item selecionado para devolução")

    with transaction(conn):
        venda = conn.execute("SELECT * FROM vendas WHERE id = ?", (venda_id,)).fetchone()
        if not venda:
            raise ErroNegocio("Venda não encontrada")
        if venda["status"] == "cancelada":
            raise ErroNegocio("Venda cancelada não pode ter itens devolvidos")
        if usuario.get("perfil") != "admin" and venda["vendedor_id"] != usuario.get("id"):
            raise ErroNegocio("Devolução de venda de outro vendedor exige perfil de administrador", 403)
            
        caixa = exigir_caixa_aberto(conn)

        valor_total_devolucao = money(0)
        itens_para_gravar = []
        
        for dev in itens_devolvidos:
            item_id = dev.get("venda_item_id")
            qtd_dev = int(dev.get("quantidade", 0))
            if qtd_dev <= 0:
                continue
                
            item = conn.execute("SELECT * FROM venda_itens WHERE id = ? AND venda_id = ?", (item_id, venda_id)).fetchone()
            if not item:
                raise ErroNegocio(f"Item da venda {item_id} não encontrado")
                
            qtd_disp = item["quantidade"] - item["qtd_devolvida"]
            if qtd_dev > qtd_disp:
                raise ErroNegocio(f"Quantidade a devolver maior que a disponível no item {item['nome']}")
                
            # O valor do item na venda já está com desconto rateado, então (total / quantidade) é o valor unitário real pago
            valor_unitario_real = money(item["total"] / item["quantidade"])
            valor_devolver = valor_unitario_real * qtd_dev
            
            valor_total_devolucao += valor_devolver
            itens_para_gravar.append({
                "item_id": item["id"],
                "variacao_id": item["variacao_id"],
                "nome": item["nome"],
                "quantidade": qtd_dev,
                "valor": valor_devolver
            })
            
            # Atualiza qtd devolvida
            conn.execute("UPDATE venda_itens SET qtd_devolvida = qtd_devolvida + ? WHERE id = ?", (qtd_dev, item_id))
            
            # Devolve pro estoque
            if item["variacao_id"]:
                movimentar(conn, item["variacao_id"], qtd_dev, "devolucao", usuario["id"], "venda", venda_id)
                
        if not itens_para_gravar:
            raise ErroNegocio("Nenhum item válido para devolver")
            
        vale_id = None
        vale_codigo = None
        
        if tipo == 'vale':
            vale_codigo = _novo_codigo_vale(conn)
            validade = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")
            vale_id = conn.execute(
                """INSERT INTO vales_troca (codigo, cliente_id, valor_original, saldo, status, validade) 
                   VALUES (?, ?, ?, ?, 'ativo', ?)""",
                (vale_codigo, venda["cliente_id"], to_float(valor_total_devolucao), to_float(valor_total_devolucao), validade)
            ).lastrowid
            
        dev_id = conn.execute(
            """INSERT INTO devolucoes (venda_id, data, usuario_id, caixa_id, tipo, valor, vale_id, obs)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (venda_id, agora(), usuario["id"], caixa["id"], tipo, to_float(valor_total_devolucao), vale_id, obs)
        ).lastrowid

        if tipo == 'dinheiro':
            conn.execute(
                """INSERT INTO caixa_movimentos (caixa_id, tipo, valor, motivo, usuario_id, data)
                   VALUES (?, 'sangria', ?, ?, ?, ?)""",
                (caixa["id"], to_float(valor_total_devolucao), f"Devolução em dinheiro - Venda #{venda['codigo']}", usuario["id"], agora())
            )
        
        for it in itens_para_gravar:
            conn.execute(
                "INSERT INTO devolucao_itens (devolucao_id, venda_item_id, quantidade, valor) VALUES (?, ?, ?, ?)",
                (dev_id, it["item_id"], it["quantidade"], to_float(it["valor"]))
            )
            
        return {
            "success": True,
            "devolucao_id": dev_id,
            "valor": to_float(valor_total_devolucao),
            "tipo": tipo,
            "vale_codigo": vale_codigo
        }
