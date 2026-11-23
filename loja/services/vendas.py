"""Checkout: o navegador envia só variação + quantidade; preço, custo, desconto e
pagamentos são calculados e validados aqui, dentro de uma transação."""
import secrets
import string
from decimal import Decimal

from ..db import transaction
from ..utils import ErroNegocio, agora, money, parse_int, to_float
from .caixa import exigir_caixa_aberto
from .estoque import movimentar

FORMAS_PAGAMENTO = {"Pix", "Débito", "Crédito", "Dinheiro", "Vale-Troca", "Vale"}
_ALFABETO = string.ascii_uppercase + string.digits


def _novo_codigo(conn) -> str:
    while True:
        codigo = "".join(secrets.choice(_ALFABETO) for _ in range(8))
        if not conn.execute("SELECT 1 FROM vendas WHERE codigo = ?", (codigo,)).fetchone():
            return codigo


def _agrupar_itens(itens_payload) -> dict[int, int]:
    if not isinstance(itens_payload, list) or not itens_payload:
        raise ErroNegocio("Carrinho vazio")
    agrupado: dict[int, int] = {}
    for it in itens_payload:
        if not isinstance(it, dict):
            raise ErroNegocio("Item inválido no carrinho")
        vid = parse_int(it.get("variacao_id"), "Item", 1)
        qtd = parse_int(it.get("quantidade"), "Quantidade", 1)
        agrupado[vid] = agrupado.get(vid, 0) + qtd
    return agrupado


def calcular_desconto(subtotal: Decimal, desconto_payload) -> Decimal:
    if not desconto_payload:
        return Decimal("0.00")
    tipo = (desconto_payload or {}).get("tipo", "valor")
    valor = money((desconto_payload or {}).get("valor") or 0)
    if valor < 0:
        raise ErroNegocio("Desconto não pode ser negativo")
    if tipo in ("pct", "percentual"):
        if valor > 100:
            raise ErroNegocio("Desconto percentual não pode passar de 100%")
        desconto = money(subtotal * valor / Decimal(100))
    elif tipo == "valor":
        desconto = valor
    else:
        raise ErroNegocio("Tipo de desconto inválido")
    if desconto > subtotal:
        raise ErroNegocio("Desconto maior que o valor da venda")
    return desconto


def ratear(valores: list[Decimal], total_rateio: Decimal) -> list[Decimal]:
    """Distribui o desconto proporcionalmente; a sobra de centavos vai para o último item."""
    soma = sum(valores, Decimal("0"))
    if total_rateio == 0 or soma == 0:
        return [Decimal("0.00") for _ in valores]
    partes = [money(v * total_rateio / soma) for v in valores[:-1]]
    partes.append(total_rateio - sum(partes, Decimal("0")))
    return partes


def validar_pagamentos(conn, pagamentos_payload, total: Decimal) -> tuple[list[dict], Decimal]:
    if not isinstance(pagamentos_payload, list) or not pagamentos_payload:
        raise ErroNegocio("Informe a forma de pagamento")

    # 1. Agrega e valida total solicitado por código de vale (impede usar o mesmo vale 2x sem saldo)
    vales_solicitados = {}
    for p in pagamentos_payload:
        forma = (p or {}).get("forma")
        if forma in ("Vale-Troca", "Vale"):
            codigo = (p.get("vale_codigo") or "").strip().upper()
            if not codigo:
                raise ErroNegocio("Informe o código do Vale-Troca")
            v_val = money(p.get("valor"))
            if v_val <= 0:
                raise ErroNegocio("Valor do Vale-Troca deve ser maior que zero")
            vales_solicitados[codigo] = vales_solicitados.get(codigo, Decimal("0")) + v_val

    vales_info = {}
    agora_str = agora()
    for codigo, total_solicitado in vales_solicitados.items():
        vale = conn.execute("SELECT * FROM vales_troca WHERE codigo = ?", (codigo,)).fetchone()
        if not vale:
            raise ErroNegocio(f"Vale-Troca {codigo} não encontrado")
        if vale["status"] != "ativo" or vale["saldo"] <= 0:
            raise ErroNegocio(f"Vale-Troca {codigo} não está ativo ou não possui saldo")
        if vale["validade"]:
            val_limite = str(vale["validade"]).strip()
            if val_limite and agora_str[:len(val_limite)] > val_limite:
                raise ErroNegocio(f"Vale-Troca {codigo} expirou em {val_limite}")
        saldo = money(vale["saldo"])
        if total_solicitado > saldo:
            raise ErroNegocio(
                f"Saldo insuficiente no Vale-Troca {codigo}: total utilizado R$ {to_float(total_solicitado):.2f}, disponível R$ {to_float(saldo):.2f}"
            )
        vales_info[codigo] = vale

    pagamentos = []
    for p in pagamentos_payload:
        forma = (p or {}).get("forma")
        if forma not in FORMAS_PAGAMENTO:
            raise ErroNegocio(f"Forma de pagamento inválida: {forma}")
        valor = money(p.get("valor"))
        if valor <= 0:
            raise ErroNegocio("Valor de pagamento deve ser maior que zero")
        parcelas = parse_int(p.get("parcelas") or 1, "Parcelas", 1)
        if forma != "Crédito":
            parcelas = 1
        elif parcelas > 12:
            raise ErroNegocio("Máximo de 12 parcelas")

        vale_id = None
        if forma in ("Vale-Troca", "Vale"):
            codigo = (p.get("vale_codigo") or "").strip().upper()
            vale_id = vales_info[codigo]["id"]

        pagamentos.append({
            "forma": forma, 
            "valor": valor, 
            "parcelas": parcelas, 
            "vale_id": vale_id
        })

    pago = sum((p["valor"] for p in pagamentos), Decimal("0"))
    if pago < total:
        raise ErroNegocio(f"Pagamento insuficiente: faltam R$ {to_float(total - pago):.2f}".replace(".", ","),
                          total=to_float(total))
    troco = pago - total
    dinheiro = sum((p["valor"] for p in pagamentos if p["forma"] == "Dinheiro"), Decimal("0"))
    if troco > 0 and troco > dinheiro:
        raise ErroNegocio("Troco só é permitido para pagamento em dinheiro", total=to_float(total))
    # Grava o líquido: abate o troco dos pagamentos em dinheiro
    restante_troco = troco
    for p in pagamentos:
        if restante_troco > 0 and p["forma"] == "Dinheiro":
            abatido = min(p["valor"], restante_troco)
            p["valor"] -= abatido
            restante_troco -= abatido
    return [p for p in pagamentos if p["valor"] > 0], troco


def finalizar_venda(conn, usuario: dict, payload: dict) -> dict:
    itens_req = _agrupar_itens(payload.get("itens"))

    with transaction(conn):
        caixa = exigir_caixa_aberto(conn)
        itens = []
        for vid, qtd in itens_req.items():
            row = conn.execute(
                """SELECT v.id, v.tamanho, v.cor, v.estoque, v.ativo AS v_ativo, p.id AS produto_id,
                          p.nome, p.preco_venda, p.preco_custo, p.ativo AS p_ativo
                   FROM variacoes v JOIN produtos p ON p.id = v.produto_id WHERE v.id = ?""", (vid,)).fetchone()
            if not row or not row["v_ativo"] or not row["p_ativo"]:
                raise ErroNegocio("Um dos produtos do carrinho não está mais disponível", 409, variacao_id=vid)
            if qtd > row["estoque"]:
                raise ErroNegocio(
                    f"Estoque insuficiente: {row['nome']} ({row['tamanho']} / {row['cor']}) — disponível: {row['estoque']}",
                    409, variacao_id=vid, disponivel=row["estoque"])
            preco = money(row["preco_venda"])
            itens.append({"row": row, "qtd": qtd, "preco": preco, "custo": money(row["preco_custo"]),
                          "bruto": preco * qtd})

        subtotal = sum((i["bruto"] for i in itens), Decimal("0"))
        desconto = calcular_desconto(subtotal, payload.get("desconto"))

        # Validação de alçada de desconto para vendedor
        if usuario.get("perfil") != "admin" and subtotal > 0 and desconto > 0:
            limite_pct = None
            if usuario.get("id"):
                u_row = conn.execute("SELECT desconto_max_pct FROM usuarios WHERE id = ?", (usuario["id"],)).fetchone()
                if u_row and u_row["desconto_max_pct"] is not None:
                    try:
                        limite_pct = Decimal(str(u_row["desconto_max_pct"]))
                    except Exception:
                        limite_pct = None

            if limite_pct is None:
                cfg_row = conn.execute("SELECT valor FROM configuracoes WHERE chave = 'desconto_maximo_vendedor'").fetchone()
                limite_str = cfg_row["valor"] if (cfg_row and cfg_row["valor"]) else "10"
                try:
                    limite_pct = Decimal(limite_str)
                except Exception:
                    limite_pct = Decimal("10")

            max_desconto = (subtotal * limite_pct / Decimal("100")).quantize(Decimal("0.01"))
            if desconto > max_desconto:
                raise ErroNegocio(
                    f"Desconto de R$ {to_float(desconto):.2f} excede o limite permitido para vendedores ({limite_pct}% = R$ {to_float(max_desconto):.2f}). Exige aprovação de administrador.",
                    403
                )

        total = subtotal - desconto
        pagamentos, troco = validar_pagamentos(conn, payload.get("pagamentos"), total)
        descontos = ratear([i["bruto"] for i in itens], desconto)
        custo_total = sum((i["custo"] * i["qtd"] for i in itens), Decimal("0"))

        cliente_id = payload.get("cliente_id")
        if cliente_id not in (None, "", 0):
            cliente_id = parse_int(cliente_id, "Cliente", 1)
            if not conn.execute("SELECT 1 FROM clientes WHERE id = ?", (cliente_id,)).fetchone():
                raise ErroNegocio("Cliente não encontrado", 404)
        else:
            cliente_id = None

        codigo = _novo_codigo(conn)
        venda_id = conn.execute(
            """INSERT INTO vendas (codigo, data, cliente_id, vendedor_id, caixa_id, subtotal, desconto, total,
                   custo_total, troco, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'concluida')""",
            (codigo, agora(), cliente_id, usuario["id"], caixa["id"], to_float(subtotal),
             to_float(desconto), to_float(total), to_float(custo_total), to_float(troco)),
        ).lastrowid

        for item, desc in zip(itens, descontos):
            r = item["row"]
            conn.execute(
                """INSERT INTO venda_itens (venda_id, variacao_id, produto_id, nome, tamanho, cor, quantidade,
                       preco_unit, custo_unit, desconto, total) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (venda_id, r["id"], r["produto_id"], r["nome"], r["tamanho"], r["cor"], item["qtd"],
                 to_float(item["preco"]), to_float(item["custo"]), to_float(desc), to_float(item["bruto"] - desc)),
            )
            movimentar(conn, r["id"], -item["qtd"], "venda", usuario["id"], "venda", venda_id)

        for p in pagamentos:
            conn.execute(
                "INSERT INTO venda_pagamentos (venda_id, forma, valor, parcelas, vale_id) VALUES (?, ?, ?, ?, ?)",
                (venda_id, p["forma"], to_float(p["valor"]), p["parcelas"], p.get("vale_id")),
            )

        # Abate saldo dos vales agrupando por vale_id para suportar múltiplas linhas de pagamento com exatidão
        vales_deduzir = {}
        for p in pagamentos:
            if p.get("vale_id"):
                vid = p["vale_id"]
                vales_deduzir[vid] = vales_deduzir.get(vid, Decimal("0")) + p["valor"]

        for vid, total_abater in vales_deduzir.items():
            vale = conn.execute("SELECT saldo FROM vales_troca WHERE id = ?", (vid,)).fetchone()
            novo_saldo = money(vale["saldo"]) - total_abater
            novo_status = "usado" if novo_saldo <= 0 else "ativo"
            conn.execute(
                "UPDATE vales_troca SET saldo = ?, status = ? WHERE id = ?",
                (to_float(novo_saldo), novo_status, vid)
            )

    return {
        "id": venda_id,
        "codigo": codigo,
        "subtotal": to_float(subtotal),
        "desconto": to_float(desconto),
        "total": to_float(total),
        "troco": to_float(troco),
        "itens": sum(itens_req.values()),
        "pagamentos": [{"forma": p["forma"], "valor": to_float(p["valor"]), "parcelas": p["parcelas"]}
                       for p in pagamentos],
    }

def cancelar_venda(conn, venda_id: int, usuario: dict, motivo: str):
    if not motivo or len(motivo.strip()) < 5:
        raise ErroNegocio("Motivo do cancelamento deve ter pelo menos 5 caracteres")
        
    with transaction(conn):
        venda = conn.execute("SELECT * FROM vendas WHERE id = ?", (venda_id,)).fetchone()
        if not venda:
            raise ErroNegocio("Venda não encontrada", 404)
        if venda["status"] == "cancelada":
            raise ErroNegocio("Venda já está cancelada")
            
        # Verifica se já houve alguma devolução
        tem_devolucao = conn.execute("SELECT 1 FROM devolucoes WHERE venda_id = ?", (venda_id,)).fetchone()
        if tem_devolucao:
            raise ErroNegocio("Não é possível cancelar uma venda que já possui itens devolvidos/trocados.")

        # 1. Atualizar status da venda
        conn.execute(
            """UPDATE vendas SET status = 'cancelada', cancelada_em = ?, 
               cancelada_por = ?, motivo_cancelamento = ? WHERE id = ?""",
            (agora(), usuario["id"], motivo.strip(), venda_id)
        )
        
        # 2. Devolver itens para o estoque e registrar movimentação
        itens = conn.execute("SELECT variacao_id, quantidade FROM venda_itens WHERE venda_id = ?", (venda_id,)).fetchall()
        for it in itens:
            if it["variacao_id"]:
                movimentar(conn, it["variacao_id"], it["quantidade"], "cancelamento", 
                          usuario["id"], "venda", venda_id)

        # 3. Restaurar saldo de vales-troca usados no pagamento
        vales_usados = conn.execute(
            "SELECT vale_id, valor FROM venda_pagamentos WHERE venda_id = ? AND vale_id IS NOT NULL", 
            (venda_id,)
        ).fetchall()
        for vu in vales_usados:
            conn.execute(
                "UPDATE vales_troca SET saldo = saldo + ?, status = 'ativo' WHERE id = ?",
                (vu["valor"], vu["vale_id"])
            )

        # 4. Estorno em dinheiro para vendas de turno anterior
        pag_din = conn.execute(
            "SELECT SUM(valor) as total FROM venda_pagamentos WHERE venda_id = ? AND forma = 'Dinheiro'", 
            (venda_id,)
        ).fetchone()
        total_dinheiro = money(pag_din["total"] if pag_din and pag_din["total"] is not None else 0)
        
        caixa_venda = conn.execute("SELECT status FROM caixas WHERE id = ?", (venda["caixa_id"],)).fetchone()
        caixa_venda_fechado = not caixa_venda or caixa_venda["status"] != "aberto"
        
        if total_dinheiro > 0 and caixa_venda_fechado:
            caixa_aberto = conn.execute("SELECT id FROM caixas WHERE status = 'aberto'").fetchone()
            if not caixa_aberto:
                raise ErroNegocio(
                    "Cancelamento com estorno em dinheiro de venda de turno anterior exige que o caixa atual esteja aberto.",
                    409
                )
            conn.execute(
                """INSERT INTO caixa_movimentos (caixa_id, tipo, valor, motivo, usuario_id, data)
                   VALUES (?, 'sangria', ?, ?, ?, ?)""",
                (
                    caixa_aberto["id"],
                    to_float(total_dinheiro),
                    f"Estorno/Cancelamento de venda #{venda['codigo']} (Turno anterior)",
                    usuario["id"],
                    agora()
                )
            )

