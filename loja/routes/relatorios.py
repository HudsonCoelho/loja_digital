import calendar
import re
from datetime import datetime

from flask import Blueprint, g, jsonify, request
from ..db import get_db, rows, one, transaction
from ..security import login_required, admin_required, usuario_atual
from ..utils import ErroNegocio, to_float, parse_int

bp = Blueprint("relatorios", __name__)

@bp.get("/api/relatorios")
@admin_required
def dashboard_relatorios():
    """Retorna dados completos para o dashboard de relatórios."""
    conn = get_db()
    
    # 1. KPIs
    # Faturamento do dia
    dia_row = conn.execute("""
        SELECT COALESCE(SUM(total), 0) as total, COUNT(*) as qtd
        FROM vendas 
        WHERE status = 'concluida' AND date(data) = date('now', 'localtime')
    """).fetchone()
    total_dia = float(dia_row["total"] or 0)

    # Faturamento e métricas do mês
    mes_row = conn.execute("""
        SELECT COALESCE(SUM(total), 0) as total, COUNT(*) as qtd
        FROM vendas 
        WHERE status = 'concluida' AND strftime('%Y-%m', data) = strftime('%Y-%m', 'now', 'localtime')
    """).fetchone()
    total_mes = float(mes_row["total"] or 0)
    qtd_mes = int(mes_row["qtd"] or 0)
    ticket_medio = round(total_mes / qtd_mes, 2) if qtd_mes > 0 else 0.0

    # Peças vendidas no mês
    pecas_row = conn.execute("""
        SELECT COALESCE(SUM(vi.quantidade - vi.qtd_devolvida), 0) as pecas
        FROM venda_itens vi
        JOIN vendas v ON v.id = vi.venda_id
        WHERE v.status = 'concluida' AND strftime('%Y-%m', v.data) = strftime('%Y-%m', 'now', 'localtime')
    """).fetchone()
    pecas_mes = int(pecas_row["pecas"] or 0)

    # 2. Últimas vendas (para tabela resumo)
    ultimas = rows(conn.execute("""
        SELECT v.id, v.codigo, v.data as date, v.total,
               (SELECT COALESCE(SUM(quantidade), 0) FROM venda_itens WHERE venda_id = v.id) as items,
               (SELECT GROUP_CONCAT(DISTINCT forma) FROM venda_pagamentos WHERE venda_id = v.id) as payment
        FROM vendas v
        WHERE v.status = 'concluida'
        ORDER BY v.data DESC LIMIT 15
    """))

    # 3. Gráfico de Faturamento Mensal (últimos 12 meses)
    # Gera lista dos últimos 12 meses para garantir que mesmo meses sem venda apareçam
    grafico_mensal_rows = rows(conn.execute("""
        SELECT strftime('%m/%Y', data) as mes,
               strftime('%Y-%m', data) as ordenacao,
               COALESCE(SUM(total), 0) as total
        FROM vendas
        WHERE status = 'concluida' AND data >= datetime('now', 'localtime', '-12 months')
        GROUP BY strftime('%Y-%m', data)
        ORDER BY ordenacao DESC
        LIMIT 12
    """))
    grafico_mensal = [{"mes": r["mes"], "total": float(r["total"])} for r in grafico_mensal_rows]
    if not grafico_mensal:
        # Pelo menos mês atual com 0
        mes_atual = conn.execute("SELECT strftime('%m/%Y', 'now', 'localtime')").fetchone()[0]
        grafico_mensal = [{"mes": mes_atual, "total": 0.0}]

    # 4. Gráfico de Categorias / Produtos mais vendidos
    cat_rows = rows(conn.execute("""
        SELECT COALESCE(c.nome, 'Diversos') as label,
               ROUND(SUM(vi.total), 2) as valor
        FROM venda_itens vi
        JOIN vendas v ON v.id = vi.venda_id
        LEFT JOIN produtos p ON p.id = vi.produto_id
        LEFT JOIN categorias c ON c.id = p.categoria_id
        WHERE v.status = 'concluida'
        GROUP BY c.nome
        ORDER BY valor DESC
        LIMIT 6
    """))
    grafico_categorias = [{"label": r["label"] or "Diversos", "valor": float(r["valor"])} for r in cat_rows]
    if not grafico_categorias:
        grafico_categorias = [{"label": "Sem vendas", "valor": 0.0}]

    # 5. Gráfico de Formas de Pagamento
    pag_rows = rows(conn.execute("""
        SELECT vp.forma as label, ROUND(SUM(vp.valor), 2) as valor
        FROM venda_pagamentos vp
        JOIN vendas v ON v.id = vp.venda_id
        WHERE v.status = 'concluida'
        GROUP BY vp.forma
        ORDER BY valor DESC
    """))
    grafico_pagamentos = [{"label": r["label"], "valor": float(r["valor"])} for r in pag_rows]
    if not grafico_pagamentos:
        grafico_pagamentos = [{"label": "Sem vendas", "valor": 0.0}]

    return jsonify({
        "kpis": {
            "dia": total_dia,
            "mes": total_mes,
            "ticket": ticket_medio,
            "pecas": pecas_mes
        },
        "ultimas_vendas": ultimas,
        "grafico_mensal": grafico_mensal,
        "grafico_categorias": grafico_categorias,
        "grafico_pagamentos": grafico_pagamentos
    })

@bp.get("/api/relatorios/abc")
@admin_required
def curva_abc():
    """Classificação Curva ABC de produtos por receita acumulada."""
    conn = get_db()
    total_receita_row = conn.execute("""
        SELECT COALESCE(SUM(vi.total), 0) as total_geral
        FROM venda_itens vi
        JOIN vendas v ON v.id = vi.venda_id
        WHERE v.status = 'concluida'
    """).fetchone()
    total_geral = float(total_receita_row["total_geral"] or 0)

    produtos = rows(conn.execute("""
        SELECT vi.produto_id, vi.nome,
               SUM(vi.quantidade - vi.qtd_devolvida) as total_qtd,
               ROUND(SUM(vi.total), 2) as total_receita
        FROM venda_itens vi
        JOIN vendas v ON v.id = vi.venda_id
        WHERE v.status = 'concluida'
        GROUP BY vi.produto_id, vi.nome
        ORDER BY total_receita DESC
    """))

    acumulado = 0.0
    anterior_pct = 0.0
    resultado = []
    for i, p in enumerate(produtos):
        receita = float(p["total_receita"])
        acumulado += receita
        pct_acumulado = (acumulado / total_geral * 100) if total_geral > 0 else 0
        if i == 0 or anterior_pct < 80:
            classe = "A"
        elif anterior_pct < 95:
            classe = "B"
        else:
            classe = "C"
        anterior_pct = pct_acumulado
        resultado.append({
            "produto_id": p["produto_id"],
            "nome": p["nome"],
            "quantidade": p["total_qtd"],
            "receita": receita,
            "pct_acumulado": round(pct_acumulado, 2),
            "classe": classe
        })

    return jsonify({"total_geral": total_geral, "itens": resultado})

@bp.get("/api/relatorios/vendas")
@admin_required
def relatorio_vendas():
    """Extrato completo de vendas para listagem e exportação."""
    conn = get_db()
    where = ["v.status = 'concluida'"]
    params = []
    de = request.args.get("de")
    ate = request.args.get("ate")
    if de:
        where.append("v.data >= ?")
        params.append(de + " 00:00:00")
    if ate:
        where.append("v.data <= ?")
        params.append(ate + " 23:59:59")
    
    clausula = "WHERE " + " AND ".join(where)
    vendas = rows(conn.execute(f"""
        SELECT v.id, v.codigo, v.data, v.total, v.desconto, v.subtotal,
               u.nome as vendedor, c.nome as cliente
        FROM vendas v
        LEFT JOIN usuarios u ON u.id = v.vendedor_id
        LEFT JOIN clientes c ON c.id = v.cliente_id
        {clausula}
        ORDER BY v.data DESC
    """, params))
    return jsonify(vendas)


# ---------------- Metas por Vendedor ----------------
@bp.get("/api/metas")
@login_required
def listar_metas():
    """Lista metas de vendedores para o período especificado (YYYY-MM).
    Admin vê todos os usuários ativos; Vendedor vê apenas a própria meta.
    """
    conn = get_db()
    agora_dt = datetime.now()
    periodo_padrao = agora_dt.strftime("%Y-%m")
    periodo = (request.args.get("periodo") or periodo_padrao).strip()

    if not re.match(r"^\d{4}-\d{2}$", periodo):
        raise ErroNegocio("Formato de período inválido. Use YYYY-MM", 400)

    usuario = getattr(g, "usuario", None) or usuario_atual()
    eh_admin = usuario.get("perfil") == "admin"

    if eh_admin:
        usuarios = rows(conn.execute("""
            SELECT id, nome, login, perfil 
            FROM usuarios 
            WHERE ativo = 1 AND perfil = 'vendedor'
            ORDER BY nome
        """))
    else:
        if usuario.get("perfil") != "vendedor":
            return jsonify([])
        usuarios = rows(conn.execute("""
            SELECT id, nome, login, perfil 
            FROM usuarios 
            WHERE id = ? AND ativo = 1 AND perfil = 'vendedor'
        """, (usuario["id"],)))

    eh_mes_corrente = (periodo == agora_dt.strftime("%Y-%m"))
    if eh_mes_corrente:
        dias_no_mes = calendar.monthrange(agora_dt.year, agora_dt.month)[1]
        dias_restantes = max(1, dias_no_mes - agora_dt.day + 1)
    else:
        dias_restantes = 0

    metas_resultado = []
    for u in usuarios:
        uid = u["id"]
        meta_row = conn.execute("""
            SELECT id, valor_meta, criado_por, atualizado_em
            FROM metas_vendedor
            WHERE vendedor_id = ? AND periodo = ?
        """, (uid, periodo)).fetchone()

        valor_meta = round(float(meta_row["valor_meta"]), 2) if meta_row else 0.0

        # Total de vendas concluídas no período
        vendas_tot = conn.execute("""
            SELECT COALESCE(SUM(total), 0)
            FROM vendas
            WHERE vendedor_id = ? AND status = 'concluida' AND strftime('%Y-%m', data) = ?
        """, (uid, periodo)).fetchone()[0]

        # Devoluções de vendas concluídas do vendedor no período
        devs_tot = conn.execute("""
            SELECT COALESCE(SUM(d.valor), 0)
            FROM devolucoes d
            JOIN vendas v ON v.id = d.venda_id
            WHERE v.vendedor_id = ? AND v.status = 'concluida' AND strftime('%Y-%m', v.data) = ?
        """, (uid, periodo)).fetchone()[0]

        vendido = max(0.0, round(float(vendas_tot) - float(devs_tot), 2))
        percentual = round((vendido / valor_meta * 100), 1) if valor_meta > 0 else 0.0
        falta = max(0.0, round(valor_meta - vendido, 2)) if valor_meta > 0 else 0.0

        if eh_mes_corrente and dias_restantes > 0 and falta > 0:
            ritmo_diario = round(falta / dias_restantes, 2)
        else:
            ritmo_diario = 0.0

        metas_resultado.append({
            "id": meta_row["id"] if meta_row else None,
            "vendedor_id": uid,
            "vendedor_nome": u["nome"],
            "periodo": periodo,
            "valor_meta": valor_meta,
            "vendido": vendido,
            "percentual": percentual,
            "falta": falta,
            "ritmo_diario": ritmo_diario,
            "tem_meta": valor_meta > 0
        })

    return jsonify(metas_resultado)


@bp.put("/api/metas")
@admin_required
def definir_meta():
    """Define ou atualiza meta mensal de um vendedor. Apenas administradores."""
    conn = get_db()
    dados = request.json or {}
    vid = parse_int(dados.get("vendedor_id"), "Vendedor", 1)
    periodo = (dados.get("periodo") or "").strip()
    if not re.match(r"^\d{4}-\d{2}$", periodo):
        raise ErroNegocio("Formato de período inválido. Use YYYY-MM", 400)

    try:
        valor_meta = float(dados.get("valor_meta", 0))
    except (ValueError, TypeError):
        raise ErroNegocio("Valor da meta inválido", 400)

    if valor_meta < 0:
        raise ErroNegocio("Valor da meta deve ser maior ou igual a zero", 400)

    vendedor = conn.execute("SELECT id, nome, perfil FROM usuarios WHERE id = ?", (vid,)).fetchone()
    if not vendedor:
        raise ErroNegocio(f"Usuário {vid} não encontrado", 404)
    if vendedor["perfil"] != "vendedor":
        raise ErroNegocio("Apenas usuários com perfil vendedor podem ter metas definidas", 400)

    usuario = getattr(g, "usuario", None) or usuario_atual()
    uid = usuario.get("id")

    with transaction(conn):
        conn.execute("""
            INSERT INTO metas_vendedor (vendedor_id, periodo, valor_meta, criado_por, atualizado_em)
            VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(vendedor_id, periodo) DO UPDATE SET
                valor_meta = excluded.valor_meta,
                criado_por = excluded.criado_por,
                atualizado_em = excluded.atualizado_em
        """, (vid, periodo, round(valor_meta, 2), uid))

    return jsonify({
        "success": True,
        "vendedor_id": vid,
        "periodo": periodo,
        "valor_meta": round(valor_meta, 2)
    })


@bp.post("/api/metas/copiar-mes-anterior")
@admin_required
def copiar_metas_mes_anterior():
    """Copia metas do mês anterior para o mês indicado, sem sobrescrever metas já definidas."""
    conn = get_db()
    dados = request.json or {}
    periodo = (dados.get("periodo") or "").strip()
    if not re.match(r"^\d{4}-\d{2}$", periodo):
        raise ErroNegocio("Formato de período inválido. Use YYYY-MM", 400)

    ano, mes = map(int, periodo.split("-"))
    if mes == 1:
        origem = f"{ano - 1:04d}-12"
    else:
        origem = f"{ano:04d}-{mes - 1:02d}"

    origem = (dados.get("origem") or origem).strip()

    usuario = getattr(g, "usuario", None) or usuario_atual()
    uid = usuario.get("id")

    metas_origem = rows(conn.execute("""
        SELECT mv.vendedor_id, mv.valor_meta
        FROM metas_vendedor mv
        JOIN usuarios u ON u.id = mv.vendedor_id
        WHERE mv.periodo = ? AND mv.valor_meta > 0 AND u.perfil = 'vendedor' AND u.ativo = 1
    """, (origem,)))

    copiadas = 0
    with transaction(conn):
        for m in metas_origem:
            ja_existe = conn.execute("""
                SELECT 1 FROM metas_vendedor
                WHERE vendedor_id = ? AND periodo = ?
            """, (m["vendedor_id"], periodo)).fetchone()
            if not ja_existe:
                conn.execute("""
                    INSERT INTO metas_vendedor (vendedor_id, periodo, valor_meta, criado_por, atualizado_em)
                    VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
                """, (m["vendedor_id"], periodo, m["valor_meta"], uid))
                copiadas += 1

    return jsonify({
        "success": True,
        "copiadas": copiadas,
        "origem": origem,
        "destino": periodo
    })
