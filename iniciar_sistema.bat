@echo off
title Estilo Unico ERP - Servidor de Producao
cd /d "%~dp0"

echo ========================================================
echo         ESTILO UNICO - SISTEMA DE GESTAO ERP / PDV
echo               "Vista-se com estilo!"
echo ========================================================
echo.
echo Iniciando servidor Waitress em 0.0.0.0:8000...
echo O sistema estara acessivel neste computador e em outros
echo dispositivos conectados no mesmo Wi-Fi / rede local.
echo.

:: Abre o navegador padrao apos 2 segundos em segundo plano
start "" /b cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:8000"

:: Executa o servidor de producao (Waitress escutando em 0.0.0.0:8000)
python app.py

pause
