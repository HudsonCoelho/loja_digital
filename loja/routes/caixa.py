from flask import Blueprint, jsonify, request
from ..db import get_db, rows
from ..security import login_required, usuario_atual, is_admin
from ..services.caixa import (
    caixa_aberto_da_loja, abrir_caixa, registrar_movimento,
    preview_fechamento, fechar_caixa
)
from ..utils import ErroNegocio, parse_int

bp = Blueprint("caixa", __name__)

def _json():
    return request.get_json(silent=True) or {}

@bp.get("/api/caixa/status")
@login_required
def status_caixa():
    db = get_db()
    caixa = caixa_aberto_da_loja(db)
    if not caixa:
        return jsonify({"status": "fechado", "caixa": None})
    return jsonify({
        "status": "aberto",
        "caixa": dict(caixa)
    })

@bp.post("/api/caixa/abrir")
@login_required
def abrir():
    db = get_db()
    dados = _json()
    valor = float(dados.get("valor_abertura", 0))
    usuario = usuario_atual()
    caixa = abrir_caixa(db, usuario["id"], valor)
    return jsonify({"success": True, "caixa": dict(caixa)})

@bp.post("/api/caixa/movimento")
@login_required
def movimento():
    db = get_db()
    dados = _json()
    caixa = caixa_aberto_da_loja(db)
    if not caixa:
        raise ErroNegocio("Nenhum caixa aberto.", 409)
        
    tipo = dados.get("tipo")
    valor = float(dados.get("valor", 0))
    motivo = dados.get("motivo")
    usuario = usuario_atual()
    
    registrar_movimento(db, caixa["id"], tipo, valor, motivo, usuario["id"])
    return jsonify({"success": True})

@bp.get("/api/caixa/fechamento-preview")
@login_required
def fechamento_preview():
    db = get_db()
    caixa = caixa_aberto_da_loja(db)
    if not caixa:
        raise ErroNegocio("Nenhum caixa aberto.", 409)
        
    preview = preview_fechamento(db, caixa["id"])
    if not is_admin():
        preview.pop("por_vendedor", None)
    return jsonify(preview)

@bp.post("/api/caixa/fechar")
@login_required
def fechar():
    db = get_db()
    dados = _json()
    caixa = caixa_aberto_da_loja(db)
    if not caixa:
        raise ErroNegocio("Nenhum caixa aberto.", 409)
        
    usuario = usuario_atual()
    contagem = dados.get("contagem", {})
    
    resultado = fechar_caixa(db, caixa["id"], usuario["id"], contagem)
    return jsonify({"success": True, "fechamento": resultado})

@bp.get("/api/caixa/movimentos")
@login_required
def movimentos():
    db = get_db()
    caixa = caixa_aberto_da_loja(db)
    if not caixa:
        return jsonify([])
    movs = rows(db.execute(
        "SELECT m.*, u.nome as usuario FROM caixa_movimentos m LEFT JOIN usuarios u ON u.id = m.usuario_id WHERE m.caixa_id = ? ORDER BY m.id DESC",
        (caixa["id"],)
    ))
    return jsonify([dict(m) for m in movs])
