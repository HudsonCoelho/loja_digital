"""Serviço de backup automático do banco de dados (SQLite online backup).
Garante cópias consistentes sem travar o sistema ou corromper o banco.

Destinos:
- Principal: backups/diario/ (mesmo disco do sistema; protege contra erro humano/corrupção).
- Extra: pasta configurada em `backup_destino_extra` (pendrive, HD externo ou pasta de nuvem).
  Se o campo estiver vazio, usa automaticamente a pasta do Google Drive para computador
  (ex.: G:\\Meu Drive), quando instalada. É o destino extra que protege contra falha do HD.
"""
import json
import shutil
import sqlite3
import string
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

PASTA_NUVEM = "backups_estilo_unico"
DIAS_RETENCAO_LOCAL = 30
DIAS_RETENCAO_EXTRA = 90
_lock_backup = threading.Lock()


# ---------------- Destino extra ----------------
def detectar_google_drive() -> str | None:
    """Procura a pasta do Google Drive para computador (Drive for Desktop / Backup and Sync)."""
    candidatos = []
    for letra in string.ascii_uppercase:
        for sub in ("Meu Drive", "My Drive"):
            candidatos.append(Path(f"{letra}:\\") / sub)
    home = Path.home()
    for sub in ("Google Drive/Meu Drive", "Google Drive/My Drive", "Google Drive", "My Drive", "Meu Drive"):
        candidatos.append(home / sub)
    for p in candidatos:
        try:
            if p.is_dir():
                return str(p)
        except OSError:
            continue
    return None


def resolver_destino_extra(configurado: str | None) -> tuple[str | None, str | None]:
    """Retorna (caminho, origem). origem: 'configurado', 'google_drive_auto' ou None."""
    if configurado and str(configurado).strip():
        return str(configurado).strip(), "configurado"
    drive = detectar_google_drive()
    if drive:
        return drive, "google_drive_auto"
    return None, None


def _ler_destino_configurado(conn) -> str | None:
    row = conn.execute("SELECT valor FROM configuracoes WHERE chave = 'backup_destino_extra'").fetchone()
    return row["valor"] if row else None


# ---------------- Backup ----------------
def fazer_backup(db_path: str, backup_dir: str, destino_extra: str | None = None, motivo: str = "manual") -> dict:
    """Realiza cópia de segurança usando o SQLite Online Backup API."""
    db_file = Path(db_path)
    if not db_file.exists():
        raise FileNotFoundError(f"Banco de dados não encontrado em {db_path}")

    with _lock_backup:
        agora = datetime.now()
        timestamp = agora.strftime("%Y-%m-%d_%H%M%S")
        pasta_diaria = Path(backup_dir) / "diario"
        pasta_diaria.mkdir(parents=True, exist_ok=True)

        nome_arquivo = f"estoque_backup_{timestamp}.db"
        destino_principal = pasta_diaria / nome_arquivo

        src_conn = sqlite3.connect(str(db_file), timeout=30)
        try:
            dst_conn = sqlite3.connect(str(destino_principal), timeout=30)
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
        finally:
            src_conn.close()

        # Confere se a cópia abre e está íntegra
        integro = verificar_integridade(destino_principal)
        tamanho = destino_principal.stat().st_size

        copiado_extra = False
        erro_extra = None
        caminho_extra_final = None
        if destino_extra and str(destino_extra).strip():
            caminho_extra = Path(str(destino_extra).strip())
            if not caminho_extra.is_dir():
                erro_extra = (f"Pasta de destino extra não encontrada: {caminho_extra}. "
                              "Pendrive desconectado ou Google Drive fechado?")
            else:
                try:
                    pasta_alvo = caminho_extra / PASTA_NUVEM
                    pasta_alvo.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(destino_principal), str(pasta_alvo / nome_arquivo))
                    copiado_extra = True
                    caminho_extra_final = str(pasta_alvo / nome_arquivo)
                    limpar_backups_antigos(pasta_alvo, DIAS_RETENCAO_EXTRA)
                except Exception as e:
                    erro_extra = str(e)

        limpar_backups_antigos(pasta_diaria, DIAS_RETENCAO_LOCAL)

        # Remove eventuais arquivos temporários do SQLite (.db-wal / .db-shm) gerados no backup
        for ext in ("-wal", "-shm"):
            t_file = destino_principal.with_name(destino_principal.name + ext)
            if t_file.exists():
                try:
                    t_file.unlink()
                except OSError:
                    pass

        resultado = {
            "success": True,
            "arquivo": nome_arquivo,
            "caminho": str(destino_principal),
            "tamanho_bytes": tamanho,
            "criado_em": agora.strftime("%Y-%m-%d %H:%M:%S"),
            "integro": integro,
            "motivo": motivo,
            "destino_extra": str(destino_extra).strip() if destino_extra else None,
            "copiado_extra": copiado_extra,
            "caminho_extra": caminho_extra_final,
            "erro_extra": erro_extra,
        }
        _salvar_status(backup_dir, resultado)
        return resultado


def backup_com_configuracao(conn, db_path: str, backup_dir: str, motivo: str = "manual") -> dict:
    """Faz backup lendo o destino extra configurado (ou o Google Drive detectado)."""
    destino, origem = resolver_destino_extra(_ler_destino_configurado(conn))
    res = fazer_backup(db_path, backup_dir, destino, motivo)
    res["origem_destino_extra"] = origem
    return res


def verificar_integridade(arquivo: Path | str) -> bool:
    try:
        c = sqlite3.connect(f"file:{Path(arquivo).as_posix()}?mode=ro", uri=True, timeout=10)
        try:
            return c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            c.close()
    except sqlite3.Error:
        return False


def limpar_backups_antigos(pasta: Path, dias_retencao: int = DIAS_RETENCAO_LOCAL):
    """Remove backups que ultrapassaram o período de retenção e limpa temporários (.db-wal / .db-shm)."""
    limite = datetime.now() - timedelta(days=dias_retencao)
    try:
        p = Path(pasta)
        for f in p.glob("estoque_backup_*.db"):
            if f.is_file() and datetime.fromtimestamp(f.stat().st_mtime) < limite:
                try:
                    f.unlink()
                except OSError:
                    pass
        for f in list(p.glob("*.db-wal")) + list(p.glob("*.db-shm")):
            if f.is_file():
                try:
                    f.unlink()
                except OSError:
                    pass
    except Exception:
        pass


def listar_backups(backup_dir: str) -> list[dict]:
    """Lista todos os arquivos de backup ordenados do mais recente ao mais antigo."""
    pasta_diaria = Path(backup_dir) / "diario"
    if not pasta_diaria.exists():
        return []

    arquivos = []
    for f in pasta_diaria.glob("estoque_backup_*.db"):
        if f.is_file():
            stat = f.stat()
            arquivos.append({
                "nome": f.name,
                "tamanho_bytes": stat.st_size,
                "tamanho_fmt": f"{stat.st_size / (1024 * 1024):.2f} MB" if stat.st_size > 1024 * 1024 else f"{stat.st_size / 1024:.1f} KB",
                "criado_em": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M:%S"),
                "timestamp": stat.st_mtime,
            })

    arquivos.sort(key=lambda x: x["timestamp"], reverse=True)
    return arquivos


# ---------------- Status ----------------
def _arquivo_status(backup_dir: str) -> Path:
    return Path(backup_dir) / "ultimo_backup.json"


def _salvar_status(backup_dir: str, resultado: dict):
    try:
        caminho = _arquivo_status(backup_dir)
        anterior = {}
        if caminho.exists():
            anterior = json.loads(caminho.read_text(encoding="utf-8"))
        status = {"ultimo": resultado}
        # Guarda a última cópia extra bem-sucedida mesmo que a atual falhe
        status["ultimo_extra_ok"] = resultado if resultado.get("copiado_extra") else anterior.get("ultimo_extra_ok")
        caminho.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def status_backup(conn, backup_dir: str) -> dict:
    configurado = (_ler_destino_configurado(conn) or "").strip()
    destino, origem = resolver_destino_extra(configurado)
    salvo = {}
    try:
        caminho = _arquivo_status(backup_dir)
        if caminho.exists():
            salvo = json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "destino_configurado": configurado,
        "destino_efetivo": destino,
        "origem_destino": origem,
        "destino_acessivel": bool(destino and Path(destino).is_dir()),
        "google_drive_detectado": detectar_google_drive(),
        "ultimo": salvo.get("ultimo"),
        "ultimo_extra_ok": salvo.get("ultimo_extra_ok"),
    }


# ---------------- Agendador ----------------
_daemon_iniciado = False


def iniciar_agendador_backup(app):
    """Inicia thread de verificação para garantir backup diário automático."""
    global _daemon_iniciado
    if _daemon_iniciado:
        return
    _daemon_iniciado = True

    def _loop_backup():
        time.sleep(10)  # Aguarda inicialização da aplicação
        while True:
            try:
                with app.app_context():
                    db_path = app.config.get("DATABASE")
                    backup_dir = app.config.get("BACKUP_DIR")
                    if db_path and backup_dir and Path(db_path).exists():
                        pasta = Path(backup_dir) / "diario"
                        hoje_str = datetime.now().strftime("%Y-%m-%d")
                        ja_fez_hoje = pasta.exists() and any(pasta.glob(f"estoque_backup_{hoje_str}_*.db"))
                        if not ja_fez_hoje:
                            from ..db import get_db
                            app.logger.info("Executando backup diário automático...")
                            res = backup_com_configuracao(get_db(), db_path, backup_dir, "diario")
                            if res.get("erro_extra"):
                                app.logger.warning(f"Backup local OK, mas cópia extra falhou: {res['erro_extra']}")
                            app.logger.info("Backup diário automático concluído.")
            except Exception as e:
                app.logger.warning(f"Erro no backup automático: {e}")

            time.sleep(3600)  # Verifica a cada 1 hora

    t = threading.Thread(target=_loop_backup, daemon=True, name="BackupAutomaticoThread")
    t.start()
