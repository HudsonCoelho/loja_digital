from pathlib import Path

from flask import Blueprint, jsonify, request, current_app, send_from_directory
from ..db import get_db, rows, transaction
from ..security import admin_required, usuario_atual
from ..utils import ErroNegocio

bp = Blueprint("config", __name__)

# Quem não está logado (tela de login) só vê o nome da loja e o rodapé.
CHAVES_PUBLICAS = {"loja_nome", "cupom_rodape"}
# Usuário logado (vendedor) vê os dados da loja necessários para imprimir o cupom e limites operacionais.
CHAVES_LOJA = CHAVES_PUBLICAS | {"loja_documento", "loja_endereco", "loja_telefone", "dias_produto_parado", "desconto_maximo_vendedor"}
# Somente administrador vê/edita configurações operacionais (ex.: caminho do backup).
CHAVES_ADMIN = CHAVES_LOJA | {"backup_destino_extra"}


def _todas_configuracoes(conn) -> dict:
    return {i["chave"]: i["valor"] for i in rows(conn.execute("SELECT chave, valor FROM configuracoes"))}


@bp.get("/api/configuracoes")
def listar_configuracoes():
    """Configurações da loja, filtradas pelo nível de acesso de quem pede."""
    cfg = _todas_configuracoes(get_db())
    usuario = usuario_atual()
    if not usuario:
        permitidas = CHAVES_PUBLICAS
    elif usuario["perfil"] == "admin":
        permitidas = CHAVES_ADMIN
    else:
        permitidas = CHAVES_LOJA
    return jsonify({k: v for k, v in cfg.items() if k in permitidas})


@bp.post("/api/configuracoes")
@admin_required
def salvar_configuracoes():
    """Salva/atualiza configurações da loja (somente chaves conhecidas)."""
    conn = get_db()
    dados = request.json or {}
    desconhecidas = [k for k in dados if k not in CHAVES_ADMIN]
    if desconhecidas:
        raise ErroNegocio(f"Configuração desconhecida: {', '.join(desconhecidas)}")

    if "loja_nome" in dados and not str(dados["loja_nome"] or "").strip():
        raise ErroNegocio("O nome da loja é obrigatório")
    if "dias_produto_parado" in dados:
        try:
            dias = int(str(dados["dias_produto_parado"]).strip() or "60")
        except ValueError:
            raise ErroNegocio("Dias de produto parado deve ser um número")
        if not 1 <= dias <= 365:
            raise ErroNegocio("Dias de produto parado deve estar entre 1 e 365")
        dados["dias_produto_parado"] = dias
    destino = str(dados.get("backup_destino_extra") or "").strip()
    if destino and not Path(destino).is_dir():
        raise ErroNegocio(f"A pasta de backup extra não existe: {destino}")

    with transaction(conn):
        for chave, valor in dados.items():
            conn.execute("""
                INSERT INTO configuracoes (chave, valor) VALUES (?, ?)
                ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor
            """, (chave, str(valor).strip()))

    cfg = _todas_configuracoes(conn)
    return jsonify({"success": True, "configuracoes": {k: v for k, v in cfg.items() if k in CHAVES_ADMIN}})


# ---------------- Rotas de Backup ----------------
@bp.get("/api/backup/historico")
@admin_required
def historico_backups():
    """Retorna lista de backups diários realizados."""
    from ..services.backup import listar_backups
    return jsonify(listar_backups(current_app.config["BACKUP_DIR"]))


@bp.get("/api/backup/status")
@admin_required
def status_backups():
    """Destino extra efetivo, Google Drive detectado e resultado do último backup."""
    from ..services.backup import status_backup
    return jsonify(status_backup(get_db(), current_app.config["BACKUP_DIR"]))


@bp.post("/api/backup/executar")
@admin_required
def executar_backup_manual():
    """Gera um backup imediato do banco de dados."""
    from ..services.backup import backup_com_configuracao
    res = backup_com_configuracao(get_db(), current_app.config["DATABASE"],
                                  current_app.config["BACKUP_DIR"], "manual")
    return jsonify(res)


@bp.get("/api/backup/download/<string:arquivo>")
@admin_required
def download_backup(arquivo):
    """Permite baixar um arquivo de backup."""
    from werkzeug.utils import secure_filename
    nome = secure_filename(arquivo)
    pasta = Path(current_app.config["BACKUP_DIR"]) / "diario"
    return send_from_directory(str(pasta), nome, as_attachment=True)
