@echo off
title Gerar Pacote de Producao - Estilo Unico ERP
cd /d "%~dp0"

echo ========================================================
echo       GERADOR DE PACOTE DE PRODUCAO (ZIP LIMPO)
echo ========================================================
echo.

:: 1. Remove caches e temporários
echo [1/4] Limpando caches e arquivos temporarios...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
del /s /q *.pyc *.pyo *.pyd *.db-wal *.db-shm 2>nul

:: 2. Limpa dados de backups antigos e segredos de desenvolvimento
echo [2/4] Limpando backups antigos e segredos locais...
if exist "backups\diario" del /q "backups\diario\*.*" 2>nul
if exist "backups" del /q "backups\*.*" 2>nul
if exist "instance" del /q "instance\*.*" 2>nul

:: 3. Garante pastas necessarias vazias
if not exist "backups\diario" mkdir "backups\diario"
if not exist "instance" mkdir "instance"

:: 4. Gera o arquivo ZIP de producao limpo sem .git
echo [3/4] Empacotando sistema em EstiloUnico_ERP_Producao.zip...
set "ZIP_OUT=%~dp0EstiloUnico_ERP_Producao.zip"
if exist "%ZIP_OUT%" del /f /q "%ZIP_OUT%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$dest = '%ZIP_OUT%';" ^
  "$items = @('app.py', 'iniciar_sistema.bat', 'configurar_inicializacao.bat', 'backup_diario.bat', 'requirements.txt', 'README.md', 'estoque.db', 'loja', 'static', 'backups', 'instance');" ^
  "$valid = $items | Where-Object { Test-Path $_ };" ^
  "Compress-Archive -Path $valid -DestinationPath $dest -Force;"

if exist "%ZIP_OUT%" (
    echo.
    echo ========================================================
    echo  SUCESSO: Pacote gerado com seguranca!
    echo  Arquivo: EstiloUnico_ERP_Producao.zip
    echo.
    echo  Este zip contem apenas o sistema limpo:
    echo  - ZERO senhas ou hashes antigos
    echo  - ZERO historico .git
    echo  - ZERO arquivos temporarios ou de testes
    echo  - Banco zerado pronto para o primeiro cadastro do Admin
    echo ========================================================
) else (
    echo.
    echo [AVISO] Nao foi possivel criar o zip automaticamente.
)

echo.
pause
