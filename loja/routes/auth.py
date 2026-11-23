from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_db, one, transaction
from ..security import csrf_token, iniciar_sessao, limite_login, login_required, usuario_atual
from ..utils import ErroNegocio, limpar

bp = Blueprint("auth", __name__)

SENHA_MIN = 6


def validar_senha(senha: str):
    if not senha or len(senha) < SENHA_MIN:
        raise ErroNegocio(f"A senha deve ter pelo menos {SENHA_MIN} caracteres")


def hash_senha(senha: str) -> str:
    return generate_password_hash(senha)


def _json():
    return request.get_json(silent=True) or {}


def _usuario_publico(u: dict) -> dict:
    return {"id": u["id"], "nome": u["nome"], "login": u["login"], "perfil": u["perfil"],
            "comissao_pct": u["comissao_pct"],
            "desconto_max_pct": u.get("desconto_max_pct") if "desconto_max_pct" in u.keys() else None}


@bp.get("/api/auth/estado")
def estado():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    u = usuario_atual()
    return jsonify({
        "precisa_setup": total == 0,
        "usuario": _usuario_publico(u) if u else None,
        "csrf": csrf_token(),
    })


@bp.post("/api/auth/setup")
def setup():
    """Cria o primeiro administrador. Só funciona enquanto não existir nenhum usuário."""
    dados = _json()
    nome = limpar(dados.get("nome"), 80)
    login = limpar(dados.get("login") or dados.get("usuario"), 40)
    senha = dados.get("senha") or ""
    if not nome or not login:
        raise ErroNegocio("Informe nome e login")
    validar_senha(senha)
    db = get_db()
    with transaction(db):
        if db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] > 0:
            raise ErroNegocio("O sistema já foi configurado", 409)
        uid = db.execute(
            "INSERT INTO usuarios (nome, login, senha_hash, perfil) VALUES (?, ?, ?, 'admin')",
            (nome, login, hash_senha(senha))).lastrowid
    user = one(db.execute("SELECT * FROM usuarios WHERE id = ?", (uid,)))
    iniciar_sessao(user)
    return jsonify({"success": True, "usuario": _usuario_publico(user), "csrf": session["csrf"]})


@bp.post("/api/auth/login")
def login():
    dados = _json()
    login_raw = dados.get("login") or dados.get("usuario")
    login_ = limpar(login_raw, 40)
    if not login_:
        raise ErroNegocio("Informe o usuário", 400)
    login_key = login_.lower()
    senha = dados.get("senha") or ""
    espera = limite_login.bloqueado_por(login_key)
    if espera:
        minutos = max(1, round(espera / 60))
        raise ErroNegocio(f"Muitas tentativas. Tente novamente em {minutos} min.", 429)
    user = one(get_db().execute("SELECT * FROM usuarios WHERE LOWER(login) = LOWER(?)", (login_,)))
    if not user or not check_password_hash(user["senha_hash"], senha):
        limite_login.falhou(login_key)
        raise ErroNegocio("Login ou senha incorretos", 401)
    if not user["ativo"]:
        raise ErroNegocio("Usuário desativado. Fale com o administrador.", 403)
    limite_login.sucesso(login_key)
    iniciar_sessao(user)
    current_app.logger.info("Login: %s", login_)
    return jsonify({"success": True, "usuario": _usuario_publico(user), "csrf": session["csrf"]})


@bp.post("/api/auth/logout")
def logout():
    session.clear()
    from flask import g
    g.pop("usuario", None)
    return jsonify({"success": True})


@bp.post("/api/auth/senha")
@login_required
def trocar_senha():
    dados = _json()
    db = get_db()
    u = usuario_atual()
    atual = one(db.execute("SELECT senha_hash FROM usuarios WHERE id = ?", (u["id"],)))
    if not check_password_hash(atual["senha_hash"], dados.get("atual") or ""):
        raise ErroNegocio("Senha atual incorreta", 400)
    validar_senha(dados.get("nova") or "")
    novo_hash = hash_senha(dados["nova"])
    with transaction(db):
        db.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (novo_hash, u["id"]))
    session["sh"] = novo_hash[-16:]
    return jsonify({"success": True})
