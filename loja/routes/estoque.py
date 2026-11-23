from flask import Blueprint, jsonify, request, g
from ..db import get_db, rows, one, transaction
from ..security import login_required, admin_required
from ..services.estoque import movimentar
from ..utils import ErroNegocio, agora, to_float, parse_int

bp = Blueprint("estoque", __name__)

MOTIVOS_AJUSTE = {
    "Avaria": {"tipo": "ajuste_avaria", "obs_obrigatoria": False},
    "Perda / extravio": {"tipo": "ajuste_perda", "obs_obrigatoria": False},
    "Furto": {"tipo": "ajuste_furto", "obs_obrigatoria": True},
    "Brinde / doação": {"tipo": "ajuste_brinde", "obs_obrigatoria": False},
    "Uso da loja": {"tipo": "ajuste_uso_loja", "obs_obrigatoria": False},
    "Devolução ao fornecedor": {"tipo": "ajuste_devolucao_fornecedor", "obs_obrigatoria": True},
    "Inventário (contagem)": {"tipo": "ajuste_inventario", "obs_obrigatoria": False},
    "Outro": {"tipo": "ajuste", "obs_obrigatoria": True},
}

_MAPA_MOTIVOS = {}
for rotulo, cfg in MOTIVOS_AJUSTE.items():
    _MAPA_MOTIVOS[rotulo.lower()] = (rotulo, cfg["tipo"], cfg["obs_obrigatoria"])
    _MAPA_MOTIVOS[cfg["tipo"]] = (rotulo, cfg["tipo"], cfg["obs_obrigatoria"])
_MAPA_MOTIVOS["perda"] = _MAPA_MOTIVOS["perda / extravio"]
_MAPA_MOTIVOS["brinde"] = _MAPA_MOTIVOS["brinde / doação"]
_MAPA_MOTIVOS["inventario"] = _MAPA_MOTIVOS["inventário (contagem)"]
_MAPA_MOTIVOS["contagem"] = _MAPA_MOTIVOS["inventário (contagem)"]
_MAPA_MOTIVOS["devolucao_fornecedor"] = _MAPA_MOTIVOS["devolução ao fornecedor"]
_MAPA_MOTIVOS["uso_loja"] = _MAPA_MOTIVOS["uso da loja"]


# ---------------- Movimentações de Estoque ----------------
@bp.get("/api/estoque/movimentacoes")
@admin_required
def listar_movimentacoes():
    """Histórico de movimentações de estoque (venda, entrada, ajuste, devolução, etc.)."""
    conn = get_db()
    tipo = request.args.get("tipo")
    variacao_id = request.args.get("variacao_id")
    busca = (request.args.get("q") or "").strip()
    de = request.args.get("de")
    ate = request.args.get("ate")
    try:
        limite = max(1, min(int(request.args.get("limite", 200)), 1000))
    except ValueError:
        limite = 200
    
    where = []
    params = []
    if tipo:
        if tipo == "ajuste" or tipo.startswith("ajuste"):
            where.append("(m.tipo = 'ajuste' OR m.tipo LIKE 'ajuste_%')")
        else:
            where.append("m.tipo = ?")
            params.append(tipo)
    if variacao_id:
        where.append("m.variacao_id = ?")
        params.append(variacao_id)
    if busca:
        where.append("(p.nome LIKE ? OR v.codigo_barras = ? OR v.sku = ?)")
        params.extend([f"%{busca}%", busca, busca])
    if de:
        where.append("m.data >= ?")
        params.append(de + " 00:00:00")
    if ate:
        where.append("m.data <= ?")
        params.append(ate + " 23:59:59")
        
    clausula = "WHERE " + " AND ".join(where) if where else ""
    
    movs = rows(conn.execute(f"""
        SELECT m.id, m.data, m.tipo, m.quantidade, m.saldo_apos, m.obs, m.ref_tipo, m.ref_id,
               v.tamanho, v.cor, p.nome as produto_nome, p.id as produto_id,
               u.nome as usuario_nome
        FROM movimentacoes_estoque m
        JOIN variacoes v ON v.id = m.variacao_id
        JOIN produtos p ON p.id = v.produto_id
        LEFT JOIN usuarios u ON u.id = m.usuario_id
        {clausula}
        ORDER BY m.id DESC
        LIMIT ?
    """, params + [limite]))
    return jsonify(movs)


# ---------------- Ajuste de Estoque & Inventário (Admin) ----------------
@bp.post("/api/estoque/ajuste")
@admin_required
def ajuste_estoque():
    """Ajuste avulso de estoque (baixa ou contagem física de inventário). Apenas administradores."""
    conn = get_db()
    dados = request.json or {}
    vid = parse_int(dados.get("variacao_id"), "Variação", 1)
    modo = (dados.get("modo") or "").strip().lower()
    if modo not in ("baixa", "contagem"):
        raise ErroNegocio("Modo de ajuste inválido (use 'baixa' ou 'contagem')", 400)

    motivo_raw = (dados.get("motivo") or "").strip()
    chave_norm = motivo_raw.lower()
    if chave_norm not in _MAPA_MOTIVOS:
        raise ErroNegocio(f"Motivo de ajuste inválido: '{motivo_raw}'", 400)

    rotulo_motivo, tipo_gravado, obs_obrigatoria = _MAPA_MOTIVOS[chave_norm]
    obs = (dados.get("obs") or "").strip() or None
    if obs_obrigatoria and not obs:
        raise ErroNegocio(f"Observação é obrigatória para o motivo '{rotulo_motivo}'", 400)

    usuario = getattr(g, "usuario", None) or {}
    uid = usuario.get("id")

    with transaction(conn):
        var = conn.execute("SELECT id, estoque FROM variacoes WHERE id = ?", (vid,)).fetchone()
        if not var:
            raise ErroNegocio(f"Variação {vid} não encontrada", 404)
        estoque_atual = int(var["estoque"])

        if modo == "baixa":
            qtd = parse_int(dados.get("quantidade"), "Quantidade", 1)
            delta = -qtd
        else:
            qtd = parse_int(dados.get("quantidade"), "Quantidade", 0)
            delta = qtd - estoque_atual

        if delta == 0:
            return jsonify({
                "success": True,
                "variacao_id": vid,
                "delta": 0,
                "saldo_anterior": estoque_atual,
                "saldo_apos": estoque_atual,
                "mensagem": "Nenhuma alteração necessária (estoque já coincide com a contagem)"
            })

        saldo = movimentar(conn, vid, delta, tipo_gravado, uid, "ajuste", None, obs)

    return jsonify({
        "success": True,
        "variacao_id": vid,
        "modo": modo,
        "motivo": rotulo_motivo,
        "tipo": tipo_gravado,
        "delta": delta,
        "saldo_anterior": estoque_atual,
        "saldo_apos": saldo
    })


@bp.post("/api/estoque/inventario")
@admin_required
def inventario_lote():
    """Contagem de inventário em lote para múltiplas variações simultâneas (atômico)."""
    conn = get_db()
    dados = request.json or {}
    itens = dados.get("itens")
    if not itens or not isinstance(itens, list):
        raise ErroNegocio("Lista de itens de inventário é obrigatória", 400)

    obs_geral = (dados.get("obs") or "").strip() or "Inventário físico geral"
    usuario = getattr(g, "usuario", None) or {}
    uid = usuario.get("id")

    resultados = []
    with transaction(conn):
        for it in itens:
            vid = parse_int(it.get("variacao_id"), "Variação", 1)
            contado = parse_int(it.get("quantidade"), "Quantidade contada", 0)
            var = conn.execute("SELECT id, estoque FROM variacoes WHERE id = ?", (vid,)).fetchone()
            if not var:
                raise ErroNegocio(f"Variação {vid} não encontrada", 404)
            estoque_atual = int(var["estoque"])
            delta = contado - estoque_atual
            item_obs = (it.get("obs") or "").strip() or obs_geral

            saldo = estoque_atual
            if delta != 0:
                saldo = movimentar(conn, vid, delta, "ajuste_inventario", uid, "ajuste", None, item_obs)

            resultados.append({
                "variacao_id": vid,
                "estoque_anterior": estoque_atual,
                "contado": contado,
                "delta": delta,
                "saldo_apos": saldo
            })

    return jsonify({
        "success": True,
        "itens_processados": len(resultados),
        "ajustes_aplicados": len([r for r in resultados if r["delta"] != 0]),
        "detalhes": resultados
    })

# ---------------- Fornecedores ----------------
@bp.get("/api/fornecedores")
@admin_required
def listar_fornecedores():
    conn = get_db()
    fornecedores = rows(conn.execute("""
        SELECT f.*,
               (SELECT COUNT(*) FROM entradas WHERE fornecedor_id = f.id) as total_entradas,
               (SELECT MAX(data) FROM entradas WHERE fornecedor_id = f.id) as ultima_entrada
        FROM fornecedores f WHERE f.ativo = 1 ORDER BY f.nome
    """))
    return jsonify(fornecedores)

@bp.post("/api/fornecedores")
@admin_required
def criar_fornecedor():
    conn = get_db()
    dados = request.json or {}
    nome = (dados.get("nome") or "").strip()
    if not nome:
        raise ErroNegocio("Nome do fornecedor é obrigatório")
    
    with transaction(conn):
        fid = conn.execute("""
            INSERT INTO fornecedores (nome, cnpj, telefone, email, contato, obs, ativo)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (
            nome,
            (dados.get("cnpj") or "").strip(),
            (dados.get("telefone") or "").strip(),
            (dados.get("email") or "").strip(),
            (dados.get("contato") or "").strip(),
            (dados.get("obs") or "").strip()
        )).lastrowid
        
    forn = one(conn.execute("SELECT * FROM fornecedores WHERE id = ?", (fid,)))
    return jsonify(forn), 201

@bp.put("/api/fornecedores/<int:fid>")
@admin_required
def editar_fornecedor(fid):
    conn = get_db()
    if not one(conn.execute("SELECT id FROM fornecedores WHERE id = ?", (fid,))):
        raise ErroNegocio("Fornecedor não encontrado", 404)
    dados = request.json or {}
    nome = (dados.get("nome") or "").strip()
    if not nome:
        raise ErroNegocio("Nome do fornecedor é obrigatório")
    with transaction(conn):
        conn.execute("""
            UPDATE fornecedores SET nome = ?, cnpj = ?, telefone = ?, email = ?, contato = ?, obs = ?, ativo = ?
            WHERE id = ?
        """, (
            nome,
            (dados.get("cnpj") or "").strip(),
            (dados.get("telefone") or "").strip(),
            (dados.get("email") or "").strip(),
            (dados.get("contato") or "").strip(),
            (dados.get("obs") or "").strip(),
            0 if dados.get("ativo") is False else 1,
            fid,
        ))
    return jsonify(one(conn.execute("SELECT * FROM fornecedores WHERE id = ?", (fid,))))

# ---------------- Entradas de Mercadoria ----------------
@bp.get("/api/entradas")
@admin_required
def listar_entradas():
    """Lista as entradas de mercadorias realizadas."""
    conn = get_db()
    entradas = rows(conn.execute("""
        SELECT e.id, e.numero_nota, e.data, e.total, e.obs,
               f.nome as fornecedor_nome, u.nome as usuario_nome,
               (SELECT COUNT(*) FROM entrada_itens WHERE entrada_id = e.id) as total_itens,
               (SELECT COALESCE(SUM(quantidade), 0) FROM entrada_itens WHERE entrada_id = e.id) as total_pecas
        FROM entradas e
        LEFT JOIN fornecedores f ON f.id = e.fornecedor_id
        LEFT JOIN usuarios u ON u.id = e.usuario_id
        ORDER BY e.id DESC
        LIMIT 50
    """))
    return jsonify(entradas)

@bp.get("/api/entradas/<int:eid>")
@admin_required
def detalhe_entrada(eid):
    """Detalhes de uma entrada com seus itens recebidos."""
    conn = get_db()
    entrada = one(conn.execute("""
        SELECT e.*, f.nome as fornecedor_nome, u.nome as usuario_nome
        FROM entradas e
        LEFT JOIN fornecedores f ON f.id = e.fornecedor_id
        LEFT JOIN usuarios u ON u.id = e.usuario_id
        WHERE e.id = ?
    """, (eid,)))
    if not entrada:
        raise ErroNegocio("Entrada não encontrada", 404)
        
    itens = rows(conn.execute("""
        SELECT ei.*, v.tamanho, v.cor, p.nome as produto_nome, p.id as produto_id
        FROM entrada_itens ei
        JOIN variacoes v ON v.id = ei.variacao_id
        JOIN produtos p ON p.id = v.produto_id
        WHERE ei.entrada_id = ?
    """, (eid,)))
    entrada["itens"] = itens
    return jsonify(entrada)

@bp.post("/api/entradas")
@admin_required
def registrar_entrada():
    """Registra uma entrada de mercadoria com fornecedor, itens e custo, atualizando o estoque."""
    conn = get_db()
    dados = request.json or {}
    itens = dados.get("itens")
    if not itens or not isinstance(itens, list):
        raise ErroNegocio("Informe ao menos um item para entrada de mercadoria")
        
    usuario = getattr(g, "usuario")
    fornecedor_id = dados.get("fornecedor_id") or None
    if fornecedor_id is not None:
        fornecedor_id = parse_int(fornecedor_id, "Fornecedor", 1)
        if not one(conn.execute("SELECT id FROM fornecedores WHERE id = ? AND ativo = 1", (fornecedor_id,))):
            raise ErroNegocio("Fornecedor não encontrado")
    numero_nota = (dados.get("numero_nota") or "").strip()
    obs = (dados.get("obs") or "").strip()
    
    with transaction(conn):
        total_entrada = 0.0
        
        # 1. Cria cabeçalho da entrada
        eid = conn.execute("""
            INSERT INTO entradas (fornecedor_id, numero_nota, data, total, usuario_id, obs)
            VALUES (?, ?, ?, 0, ?, ?)
        """, (fornecedor_id, numero_nota, agora(), usuario["id"], obs)).lastrowid
        
        # 2. Processa cada item
        for it in itens:
            vid = parse_int(it.get("variacao_id"), "Variação", 1)
            qtd = parse_int(it.get("quantidade"), "Quantidade", 1)
            custo_unit = to_float(it.get("custo_unit", 0))
            if custo_unit < 0:
                raise ErroNegocio("Custo unitário não pode ser negativo")
                
            var = one(conn.execute("SELECT id, produto_id, estoque FROM variacoes WHERE id = ?", (vid,)))
            if not var:
                raise ErroNegocio(f"Variação {vid} não encontrada")
                
            subtotal_item = round(qtd * custo_unit, 2)
            total_entrada += subtotal_item
            
            # Grava item da entrada
            conn.execute("""
                INSERT INTO entrada_itens (entrada_id, variacao_id, quantidade, custo_unit)
                VALUES (?, ?, ?, ?)
            """, (eid, vid, qtd, custo_unit))
            
            # Movimenta estoque da variação (tipo = entrada)
            movimentar(conn, vid, qtd, "entrada", usuario["id"], "entrada", eid, f"Nota: {numero_nota or 'S/N'}")
            
            # Atualiza o preço de custo no produto se fornecido
            if custo_unit > 0:
                conn.execute("UPDATE produtos SET preco_custo = ? WHERE id = ?", (custo_unit, var["produto_id"]))
                
        # Atualiza total na entrada
        conn.execute("UPDATE entradas SET total = ? WHERE id = ?", (round(total_entrada, 2), eid))
        
    return jsonify({
        "success": True,
        "entrada_id": eid,
        "total": round(total_entrada, 2),
        "itens_processados": len(itens)
    }), 201
