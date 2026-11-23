from flask import Blueprint, request, jsonify, g
from ..db import get_db, rows, one
from ..security import login_required, admin_required, usuario_atual, is_admin
from ..services.vendas import finalizar_venda, cancelar_venda
from ..utils import ErroNegocio, parse_int, agora

bp = Blueprint("vendas", __name__)

@bp.post("/api/vendas")
@login_required
def criar_venda():
    """Realiza o checkout de uma venda."""
    conn = get_db()
    resultado = finalizar_venda(conn, getattr(g, "usuario"), request.json)
    return jsonify(resultado), 201

@bp.get("/api/vendas")
@login_required
def listar_vendas():
    """Lista as vendas recentes (vendedor vê apenas as próprias)."""
    conn = get_db()
    usuario = getattr(g, "usuario", None) or usuario_atual()
    eh_admin = usuario and usuario.get("perfil") == "admin"
    
    where_clauses = []
    params = []
    
    # Vendedor só vê as próprias vendas
    if not eh_admin:
        where_clauses.append("v.vendedor_id = ?")
        params.append(usuario["id"])
    
    # Filtros
    dt_ini = request.args.get("de")
    if dt_ini:
        where_clauses.append("v.data >= ?")
        params.append(dt_ini + " 00:00:00")
        
    dt_fim = request.args.get("ate")
    if dt_fim:
        where_clauses.append("v.data <= ?")
        params.append(dt_fim + " 23:59:59")
        
    status = request.args.get("status")
    if status:
        where_clauses.append("v.status = ?")
        params.append(status)
        
    where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    res = rows(conn.execute(f"""
        SELECT v.id, v.codigo, v.data, v.total, v.status, u.nome as vendedor_nome
        FROM vendas v
        LEFT JOIN usuarios u ON u.id = v.vendedor_id
        {where}
        ORDER BY v.data DESC LIMIT 100
    """, params))
    return jsonify(res)

@bp.get("/api/vendas/<int:vid>")
@login_required
def detalhe_venda(vid):
    """Retorna os detalhes de uma venda e seus itens (vendedor só acessa as suas)."""
    conn = get_db()
    usuario = getattr(g, "usuario", None) or usuario_atual()
    eh_admin = usuario and usuario.get("perfil") == "admin"

    venda = one(conn.execute("""
        SELECT v.*, u.nome as vendedor_nome, c.nome as cliente_nome
        FROM vendas v
        LEFT JOIN usuarios u ON u.id = v.vendedor_id
        LEFT JOIN clientes c ON c.id = v.cliente_id
        WHERE v.id = ?
    """, (vid,)))
    if not venda:
        raise ErroNegocio("Venda não encontrada", 404)
    if not eh_admin and venda["vendedor_id"] != usuario["id"]:
        raise ErroNegocio("Venda não encontrada", 404)
    itens = rows(conn.execute("SELECT * FROM venda_itens WHERE venda_id = ?", (vid,)))
    pagamentos = rows(conn.execute("SELECT * FROM venda_pagamentos WHERE venda_id = ?", (vid,)))
    devolucoes = rows(conn.execute("""
        SELECT d.*, v.codigo as vale_codigo 
        FROM devolucoes d 
        LEFT JOIN vales_troca v ON v.id = d.vale_id 
        WHERE d.venda_id = ?
    """, (vid,)))
    
    if not eh_admin:
        venda.pop("custo_total", None)
        for item in itens:
            item.pop("custo_unit", None)

    venda["itens"] = itens
    venda["pagamentos"] = pagamentos
    venda["devolucoes"] = devolucoes
    return jsonify(venda)

@bp.get("/api/vales/<string:codigo>")
@login_required
def consultar_vale(codigo):
    """Consulta informações e saldo de um vale-troca."""
    conn = get_db()
    codigo_limpo = codigo.strip().upper()
    vale = one(conn.execute("""
        SELECT v.*, c.nome as cliente_nome
        FROM vales_troca v
        LEFT JOIN clientes c ON c.id = v.cliente_id
        WHERE v.codigo = ?
    """, (codigo_limpo,)))
    if not vale:
        raise ErroNegocio("Vale-Troca não encontrado", 404)
    v_dict = dict(vale)
    agora_str = agora()
    if vale["validade"]:
        val_limite = str(vale["validade"]).strip()
        v_dict["expirado"] = bool(val_limite and agora_str[:len(val_limite)] > val_limite)
    else:
        v_dict["expirado"] = False
    return jsonify(v_dict)

@bp.post("/api/vendas/<int:vid>/cancelar")
@login_required
def cancelar(vid):
    user = getattr(g, "usuario")
    if user.get("perfil") != "admin":
        raise ErroNegocio("Cancelamento de venda exige perfil de administrador", 403)
    conn = get_db()
    motivo = (request.json or {}).get("motivo", "")
    cancelar_venda(conn, vid, user, motivo)
    return jsonify({"success": True})

@bp.post("/api/vendas/<int:vid>/devolver")
@login_required
def devolver(vid):
    user = getattr(g, "usuario")
    req = request.json or {}
    tipo = req.get("tipo")
    if tipo == "dinheiro" and user.get("perfil") != "admin":
        raise ErroNegocio("Devolução com estorno em dinheiro exige perfil de administrador", 403)
    conn = get_db()
    venda = one(conn.execute("SELECT vendedor_id FROM vendas WHERE id = ?", (vid,)))
    if not venda:
        raise ErroNegocio("Venda não encontrada", 404)
    if user.get("perfil") != "admin" and venda["vendedor_id"] != user.get("id"):
        raise ErroNegocio("Devolução de venda de outro vendedor exige perfil de administrador", 403)
    from ..services.devolucoes import processar_devolucao
    resultado = processar_devolucao(
        conn, 
        user, 
        vid, 
        tipo, 
        req.get("itens"), 
        req.get("obs", "")
    )
    return jsonify(resultado)
