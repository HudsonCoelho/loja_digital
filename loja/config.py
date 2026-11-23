"""Configuração e caminhos da aplicação.

Separa dois tipos de diretório:
- RESOURCE_DIR: arquivos empacotados (HTML/CSS/JS). No .exe do PyInstaller fica em _MEIPASS.
- DATA_DIR: dados persistentes (banco, uploads, backups, secret key). Sempre ao lado do
  executável (ou na raiz do projeto em desenvolvimento), nunca na pasta temporária.
"""
import os
import secrets
import sys
from datetime import timedelta
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return _project_root()


def data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _project_root()


def _load_or_create_secret(instance_dir: Path) -> str:
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    instance_dir.mkdir(parents=True, exist_ok=True)
    key_file = instance_dir / "secret_key"
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = secrets.token_hex(32)
    key_file.write_text(key, encoding="utf-8")
    return key


def build_config(overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    base = Path(overrides.get("DATA_DIR") or data_dir())
    instance = base / "instance"
    cfg = {
        "DATA_DIR": base,
        "RESOURCE_DIR": resource_dir(),
        "DATABASE": str(base / "estoque.db"),
        "UPLOAD_DIR": str(base / "static" / "images"),
        "BACKUP_DIR": str(base / "backups"),
        "MAX_CONTENT_LENGTH": 5 * 1024 * 1024,  # 5 MB por upload
        "ALLOWED_EXTENSIONS": {"png", "jpg", "jpeg", "gif", "webp"},
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=12),
        "LOGIN_MAX_TENTATIVAS": 5,
        "LOGIN_BLOQUEIO_SEGUNDOS": 300,
    }
    cfg.update(overrides)
    if "SECRET_KEY" not in cfg:
        cfg["SECRET_KEY"] = _load_or_create_secret(instance)
    return cfg
