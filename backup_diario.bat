@echo off
title Backup do Banco de Dados - Estilo Unico
cd /d "%~dp0"

echo ========================================================
echo      BACKUP DO BANCO DE DADOS - ESTILO UNICO
echo ========================================================
echo.

python -c "from loja.services.backup import fazer_backup; from loja.config import build_config; cfg = build_config(); res = fazer_backup(cfg['DATABASE'], cfg['BACKUP_DIR']); print('Backup realizado com sucesso:', res['arquivo'])"

echo.
pause
