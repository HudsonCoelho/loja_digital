import json
from decimal import Decimal

from ..db import one, rows, transaction
from ..utils import ErroNegocio, agora, money, to_float

def caixa_aberto_da_loja(conn) -> dict | None:
    return one(conn.execute("SELECT * FROM caixas WHERE status = 'aberto'"))

def exigir_caixa_aberto(conn) -> dict:
    caixa = caixa_aberto_da_loja(conn)
    if not caixa:
        raise ErroNegocio("Nenhum caixa aberto.", 409)
    return caixa

def abrir_caixa(conn, usuario_id: int, valor_abertura: float) -> dict:
    valor = to_float(money(valor_abertura))
    if valor < 0:
        raise ErroNegocio("Valor de abertura não pode ser negativo.")
    with transaction(conn):
        if caixa_aberto_da_loja(conn):
            raise ErroNegocio("Já existe um caixa aberto.", 409)
        conn.execute(
            "INSERT INTO caixas (aberto_por, aberto_em, valor_abertura) VALUES (?, ?, ?)",
            (usuario_id, agora(), valor)
        )
        return caixa_aberto_da_loja(conn)

def registrar_movimento(conn, caixa_id: int, tipo: str, valor: float, motivo: str, usuario_id: int):
    valor_dec = money(valor)
    if valor_dec <= 0:
        raise ErroNegocio("O valor deve ser maior que zero.")
    if tipo not in ('sangria', 'suprimento'):
        raise ErroNegocio("Tipo de movimento inválido.")
    if not motivo:
        raise ErroNegocio("Informe o motivo.")
    with transaction(conn):
        caixa = one(conn.execute("SELECT status FROM caixas WHERE id = ?", (caixa_id,)))
        if not caixa or caixa["status"] != "aberto":
            raise ErroNegocio("O caixa não está aberto.")
        conn.execute(
            "INSERT INTO caixa_movimentos (caixa_id, tipo, valor, motivo, usuario_id, data) VALUES (?, ?, ?, ?, ?, ?)",
            (caixa_id, tipo, to_float(valor_dec), motivo, usuario_id, agora())
        )

def preview_fechamento(conn, caixa_id: int) -> dict:
    caixa = one(conn.execute("SELECT * FROM caixas WHERE id = ?", (caixa_id,)))
    if not caixa or caixa["status"] != "aberto":
        raise ErroNegocio("O caixa não está aberto.")
        
    vendas = rows(conn.execute(
        "SELECT forma, SUM(valor) as total FROM venda_pagamentos vp JOIN vendas v ON v.id = vp.venda_id WHERE v.caixa_id = ? AND v.status = 'concluida' GROUP BY forma",
        (caixa_id,)
    ))
    
    # Devs em dinheiro (trocas/devoluções)
    devs = one(conn.execute(
        "SELECT SUM(valor) as total FROM devolucoes WHERE caixa_id = ? AND tipo = 'dinheiro'",
        (caixa_id,)
    ))
    
    movs = rows(conn.execute(
        "SELECT tipo, SUM(valor) as total FROM caixa_movimentos WHERE caixa_id = ? GROUP BY tipo",
        (caixa_id,)
    ))

    tot_vendas = {v["forma"]: money(v["total"] or 0) for v in vendas}
    dev_dinheiro = money((devs or {}).get("total") or 0)
    
    suprimentos = money(sum((m["total"] for m in movs if m["tipo"] == "suprimento"), 0))
    sangrias = money(sum((m["total"] for m in movs if m["tipo"] == "sangria"), 0))
    
    # Vendas e troco em dinheiro
    vendas_din = tot_vendas.get("Dinheiro", Decimal("0"))
    troco = money(one(conn.execute("SELECT SUM(troco) as t FROM vendas WHERE caixa_id = ? AND status = 'concluida'", (caixa_id,)))["t"] or 0)
    
    abertura = money(caixa["valor_abertura"])
    
    # Esperado em dinheiro:
    # Como as devoluções em dinheiro já geram sangria automática no caixa_movimentos,
    # 'sangrias' já contempla as devoluções em espécie. Não subtrair dev_dinheiro novamente!
    # Além disso, 'vendas_din' (venda_pagamentos) já grava o valor líquido recebido (troco deduzido na finalização).
    # Portanto, não subtrair 'troco' novamente.
    esperado_dinheiro = abertura + vendas_din + suprimentos - sangrias

    vendas_vale = tot_vendas.get("Vale-Troca", Decimal("0")) + tot_vendas.get("Vale-troca", Decimal("0")) + tot_vendas.get("Vale", Decimal("0"))

    esperado = {
        "Dinheiro": to_float(esperado_dinheiro),
        "Pix": to_float(tot_vendas.get("Pix", Decimal("0"))),
        "Débito": to_float(tot_vendas.get("Débito", Decimal("0"))),
        "Crédito": to_float(tot_vendas.get("Crédito", Decimal("0"))),
        "Vale-Troca": to_float(vendas_vale)
    }
    
    resumo = {
        "abertura": to_float(abertura),
        "vendas_dinheiro": to_float(vendas_din),
        "troco": to_float(troco),
        "suprimentos": to_float(suprimentos),
        "sangrias": to_float(sangrias),
        "devolucoes": to_float(dev_dinheiro),
        "vendas_pix": to_float(tot_vendas.get("Pix", Decimal("0"))),
        "vendas_debito": to_float(tot_vendas.get("Débito", Decimal("0"))),
        "vendas_credito": to_float(tot_vendas.get("Crédito", Decimal("0"))),
        "vendas_vale": to_float(vendas_vale)
    }

    # Resumo por vendedor no turno
    vendas_totais = rows(conn.execute("""
        SELECT 
            v.vendedor_id,
            COALESCE(u.nome, 'Não informado') as vendedor_nome,
            SUM(v.total) as total_vendas
        FROM vendas v
        LEFT JOIN usuarios u ON u.id = v.vendedor_id
        WHERE v.caixa_id = ? AND v.status = 'concluida'
        GROUP BY v.vendedor_id, u.nome
        ORDER BY u.nome
    """, (caixa_id,)))

    linhas_vendedor = rows(conn.execute("""
        SELECT 
            v.vendedor_id,
            COALESCE(u.nome, 'Não informado') as vendedor_nome,
            vp.forma,
            SUM(vp.valor) as total_forma
        FROM vendas v
        JOIN venda_pagamentos vp ON vp.venda_id = v.id
        LEFT JOIN usuarios u ON u.id = v.vendedor_id
        WHERE v.caixa_id = ? AND v.status = 'concluida'
        GROUP BY v.vendedor_id, u.nome, vp.forma
        ORDER BY u.nome
    """, (caixa_id,)))

    vendedores_dados = {}
    for vt in vendas_totais:
        vid = vt["vendedor_id"]
        vendedores_dados[vid] = {
            "vendedor_id": vid,
            "vendedor_nome": vt["vendedor_nome"],
            "total": money(vt["total_vendas"] or 0),
            "dinheiro": Decimal("0"),
            "pix": Decimal("0"),
            "debito": Decimal("0"),
            "credito": Decimal("0"),
            "vale_troca": Decimal("0"),
        }

    for r in linhas_vendedor:
        vid = r["vendedor_id"]
        if vid not in vendedores_dados:
            vendedores_dados[vid] = {
                "vendedor_id": vid,
                "vendedor_nome": r["vendedor_nome"],
                "total": Decimal("0"),
                "dinheiro": Decimal("0"),
                "pix": Decimal("0"),
                "debito": Decimal("0"),
                "credito": Decimal("0"),
                "vale_troca": Decimal("0"),
            }
        val = money(r["total_forma"] or 0)
        forma = (r["forma"] or "").strip()
        if forma == "Dinheiro":
            vendedores_dados[vid]["dinheiro"] += val
        elif forma == "Pix":
            vendedores_dados[vid]["pix"] += val
        elif forma in ("Débito", "Debito"):
            vendedores_dados[vid]["debito"] += val
        elif forma in ("Crédito", "Credito"):
            vendedores_dados[vid]["credito"] += val
        elif forma in ("Vale-Troca", "Vale-troca", "Vale"):
            vendedores_dados[vid]["vale_troca"] += val

    por_vendedor = [
        {
            "vendedor_id": d["vendedor_id"],
            "vendedor_nome": d["vendedor_nome"],
            "total": to_float(d["total"]),
            "dinheiro": to_float(d["dinheiro"]),
            "pix": to_float(d["pix"]),
            "debito": to_float(d["debito"]),
            "credito": to_float(d["credito"]),
            "vale_troca": to_float(d["vale_troca"]),
        }
        for d in vendedores_dados.values()
    ]

    return {"esperado": esperado, "resumo": resumo, "por_vendedor": por_vendedor}

def fechar_caixa(conn, caixa_id: int, usuario_id: int, contagem: dict) -> dict:
    preview = preview_fechamento(conn, caixa_id)
    esperado = preview["esperado"]
    
    # Formas de vale não são dinheiro físico ou maquininha a contar na gaveta
    VALE_KEYS = {"Vale-Troca", "Vale-troca", "Vale"}
    tot_esp = sum(money(v) for k, v in esperado.items() if k not in VALE_KEYS)
    tot_cont = sum(money(contagem.get(k, 0)) for k in esperado.keys() if k not in VALE_KEYS)
    
    diferenca = tot_cont - tot_esp
    
    with transaction(conn):
        conn.execute(
            "UPDATE caixas SET fechado_por = ?, fechado_em = ?, contagem = ?, esperado = ?, diferenca = ?, status = 'fechado' WHERE id = ?",
            (usuario_id, agora(), json.dumps(contagem), json.dumps(esperado), to_float(diferenca), caixa_id)
        )

    # Dispara backup automático de segurança no fechamento de caixa
    try:
        from flask import current_app
        from .backup import backup_com_configuracao
        backup_com_configuracao(conn, current_app.config["DATABASE"], current_app.config["BACKUP_DIR"], "fechamento_caixa")
    except Exception as e:
        try:
            current_app.logger.warning(f"Backup no fechamento de caixa falhou: {e}")
        except Exception:
            pass

    return {"esperado": esperado, "contagem": contagem, "diferenca": to_float(diferenca)}
