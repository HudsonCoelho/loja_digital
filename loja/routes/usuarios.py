from flask import Blueprint, jsonify, request, session

from ..db import get_db, one, rows, transaction
from ..security import admin_required, usuario_atual
from ..utils import ErroNegocio, limpar, money, to_float
from .auth import hash_senha, validar_senha

bp = Blueprint("usuarios", __name__)

CAMPOS = "id, nome, login, perfil, comissao_pct, desconto_max_pct, ativo, criado_em"


def _dados_validos(dados: dict, criando: bool) -> dict:
    nome = limpar(dados.get("nome"), 80)
    login = limpar(dados.get("login"), 40).lower()
    perfil = dados.get("perfil", "vendedor")
    if not nome:
        raise ErroNegocio("Informe o nome")
    if criando and not login:
        raise ErroNegocio("Informe o login")
    if login and not login.replace(".", "").replace("_", "").replace("-", "").isalnum():
        raise ErroNegocio("Login deve ter apenas letras, números, ponto, hífen ou sublinhado")
    if perfil not in ("admin", "vendedor"):
        raise ErroNegocio("Perfil inválido")
    comissao = money(dados.get("comissao_pct") or 0)
    if comissao < 0 or comissao > 100:
        raise ErroNegocio("Comissão deve estar entre 0 e 100%")
    desc_raw = dados.get("desconto_max_pct")
    if desc_raw is not None and str(desc_raw).strip() != "":
        desc_val = money(desc_raw)
        if desc_val < 0 or desc_val > 100:
            raise ErroNegocio("Desconto máximo deve estar entre 0 e 100%")
        desc_max = to_float(desc_val)
    else:
        desc_max = None
    return {"nome": nome, "login": login, "perfil": perfil, "comissao_pct": to_float(comissao),
            "desconto_max_pct": desc_max,
            "ativo": 1 if dados.get("ativo", True) in (True, 1, "1", "true") else 0}


def _restaria_admin(db, excluindo_id: int) -> bool:
    return db.execute(
        "SELECT COUNT(*) FROM usuarios WHERE perfil = 'admin' AND ativo = 1 AND id != ?",
        (excluindo_id,)).fetchone()[0] > 0


@bp.get("/api/usuarios")
@admin_required
def listar():
    return jsonify(rows(get_db().execute(f"SELECT {CAMPOS} FROM usuarios ORDER BY ativo DESC, nome")))


@bp.post("/api/usuarios")
@admin_required
def criar():
    dados = request.get_json(silent=True) or {}
    d = _dados_validos(dados, criando=True)
    validar_senha(dados.get("senha") or "")
    db = get_db()
    with transaction(db):
        if db.execute("SELECT 1 FROM usuarios WHERE login = ?", (d["login"],)).fetchone():
            raise ErroNegocio("Já existe um usuário com esse login", 409)
        uid = db.execute(
            """INSERT INTO usuarios (nome, login, senha_hash, perfil, comissao_pct, desconto_max_pct, ativo)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (d["nome"], d["login"], hash_senha(dados["senha"]), d["perfil"], d["comissao_pct"], d["desconto_max_pct"], d["ativo"]),
        ).lastrowid
    return jsonify({"success": True, "usuario": one(db.execute(f"SELECT {CAMPOS} FROM usuarios WHERE id = ?", (uid,)))})


@bp.put("/api/usuarios/<int:uid>")
@admin_required
def editar(uid: int):
    dados = request.get_json(silent=True) or {}
    d = _dados_validos(dados, criando=False)
    db = get_db()
    eu = usuario_atual()
    with transaction(db):
        atual = one(db.execute("SELECT * FROM usuarios WHERE id = ?", (uid,)))
        if not atual:
            raise ErroNegocio("Usuário não encontrado", 404)
        perde_admin = atual["perfil"] == "admin" and atual["ativo"] and (d["perfil"] != "admin" or not d["ativo"])
        if perde_admin and not _restaria_admin(db, uid):
            raise ErroNegocio("É preciso manter pelo menos um administrador ativo")
        if uid == eu["id"] and not d["ativo"]:
            raise ErroNegocio("Você não pode desativar o próprio usuário")
        if d["login"] and d["login"] != atual["login"]:
            if db.execute("SELECT 1 FROM usuarios WHERE login = ? AND id != ?", (d["login"], uid)).fetchone():
                raise ErroNegocio("Já existe um usuário com esse login", 409)
        db.execute(
            "UPDATE usuarios SET nome = ?, login = ?, perfil = ?, comissao_pct = ?, desconto_max_pct = ?, ativo = ? WHERE id = ?",
            (d["nome"], d["login"] or atual["login"], d["perfil"], d["comissao_pct"], d["desconto_max_pct"], d["ativo"], uid))
        if dados.get("senha"):
            validar_senha(dados["senha"])
            n_hash = hash_senha(dados["senha"])
            db.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (n_hash, uid))
            if uid == eu["id"]:
                session["sh"] = n_hash[-16:]
    return jsonify({"success": True, "usuario": one(db.execute(f"SELECT {CAMPOS} FROM usuarios WHERE id = ?", (uid,)))})
