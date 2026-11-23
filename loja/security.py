"""Autenticação, autorização por perfil, CSRF e limite de tentativas de login."""
import secrets
import threading
import time
from functools import wraps

from flask import current_app, g, jsonify, redirect, request, session

from .db import get_db, one

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_ISENTOS = {"/api/auth/estado"}


# ---------------- Usuário atual ----------------
def usuario_atual() -> dict | None:
    uid = session.get("uid")
    if not uid:
        g.pop("usuario", None)
        return None
    if "usuario" in g and g.usuario and g.usuario.get("id") == uid:
        return g.usuario
    user = None
    if uid:
        user = one(get_db().execute(
            "SELECT id, nome, login, perfil, comissao_pct, desconto_max_pct, ativo, senha_hash FROM usuarios WHERE id = ?", (uid,)))
        if not user or not user["ativo"]:
            session.clear()
            user = None
        elif session.get("sh") and user.get("senha_hash") and session.get("sh") != user["senha_hash"][-16:]:
            session.clear()
            user = None
    g.usuario = user
    return user


def is_admin() -> bool:
    u = usuario_atual()
    return bool(u and u["perfil"] == "admin")


def _negado(status: int, msg: str):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": msg}), status
    return redirect("/login")


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not usuario_atual():
            return _negado(401, "Sessão expirada. Faça login novamente.")
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not usuario_atual():
            return _negado(401, "Sessão expirada. Faça login novamente.")
        if not is_admin():
            return _negado(403, "Apenas administradores podem fazer isso.")
        return fn(*args, **kwargs)
    return wrapper


def iniciar_sessao(user: dict):
    session.clear()  # evita fixação de sessão
    session.permanent = True
    session["uid"] = user["id"]
    session["sh"] = (user.get("senha_hash") or "")[-16:]
    session["csrf"] = secrets.token_urlsafe(32)
    g.usuario = user


# ---------------- CSRF ----------------
def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def verificar_csrf():
    """Executado antes de cada request: toda escrita na API exige o header X-CSRF-Token."""
    if request.method in SAFE_METHODS or not request.path.startswith("/api/"):
        return None
    if request.path in CSRF_ISENTOS or current_app.config.get("CSRF_DISABLED"):
        return None
    enviado = request.headers.get("X-CSRF-Token", "")
    esperado = session.get("csrf", "")
    if not esperado or not secrets.compare_digest(enviado, esperado):
        return jsonify({"success": False, "error": "Token de segurança inválido. Recarregue a página."}), 403
    return None


# ---------------- Rate limit de login ----------------
class LimiteLogin:
    def __init__(self):
        self._lock = threading.Lock()
        self._falhas: dict[str, tuple[int, float]] = {}

    def _chave(self, login: str) -> str:
        return f"{(login or '').lower()}|{request.remote_addr}"

    def bloqueado_por(self, login: str) -> int:
        with self._lock:
            n, ate = self._falhas.get(self._chave(login), (0, 0))
            restante = int(ate - time.time())
            return restante if restante > 0 else 0

    def falhou(self, login: str):
        maximo = current_app.config["LOGIN_MAX_TENTATIVAS"]
        bloqueio = current_app.config["LOGIN_BLOQUEIO_SEGUNDOS"]
        with self._lock:
            chave = self._chave(login)
            n, ate = self._falhas.get(chave, (0, 0))
            if ate and ate < time.time():
                n = 0
            n += 1
            self._falhas[chave] = (n, time.time() + bloqueio if n >= maximo else 0)

    def sucesso(self, login: str):
        with self._lock:
            self._falhas.pop(self._chave(login), None)


limite_login = LimiteLogin()
