@echo off
echo ========================================
echo    SISTEMA DE VENDAS - INSTALADOR
echo ========================================
echo.

REM Verificar se o executável existe
if not exist "dist\SistemaVendas.exe" (
    echo ERRO: Executavel nao encontrado!
    echo Certifique-se de que o arquivo SistemaVendas.exe existe na pasta dist
    pause
    exit /b 1
)

echo Iniciando o Sistema de Vendas...
echo.
echo O sistema sera aberto no seu navegador automaticamente.
echo Para parar o servidor, pressione Ctrl+C
echo.

REM Iniciar o executável
start "" "dist\SistemaVendas.exe"

REM Aguardar um pouco para o servidor inicializar
timeout /t 3 /nobreak >nul

REM Abrir o navegador
start http://127.0.0.1:5000

echo.
echo Sistema iniciado com sucesso!
echo Acesse: http://127.0.0.1:5000
echo.
pause
