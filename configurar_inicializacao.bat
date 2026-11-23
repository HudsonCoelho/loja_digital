@echo off
title Configurar Inicializacao, Rede e Energia - Estilo Unico

echo ========================================================
echo   CONFIGURACAO DE PRODUCAO AUTOMATICA - ESTILO UNICO
echo ========================================================
echo.

:: 1. Desativar suspensao e hibernacao quando conectado na tomada (AC)
echo [1/3] Configurando plano de energia (impedir suspensao do servidor)...
powercfg -change -standby-timeout-ac 0
powercfg -change -hibernate-timeout-ac 0
echo  OK: O computador nao entrara em suspensao enquanto ligado na tomada.
echo.

:: 2. Liberar porta 8000 no Firewall do Windows apenas para Rede Privada
echo [2/3] Liberando a porta 8000 no Firewall do Windows (Rede Privada)...
netsh advfirewall firewall delete rule name="Estilo Unico ERP (Porta 8000)" >nul 2>&1
netsh advfirewall firewall add rule name="Estilo Unico ERP (Porta 8000)" dir=in action=allow protocol=TCP localport=8000 profile=private
echo  OK: Regra de firewall criada para rede privada na porta 8000.
echo.

:: 3. Criar atalho na pasta Inicializar do Windows (shell:startup)
echo [3/3] Configurando inicializacao automatica com o Windows...
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "BAT_PATH=%~dp0iniciar_sistema.bat"
set "VBS_SCRIPT=%TEMP%\criar_atalho.vbs"

echo Set oWS = WScript.CreateObject("WScript.Shell") > "%VBS_SCRIPT%"
echo sLinkFile = "%STARTUP_FOLDER%\EstiloUnico_ERP.lnk" >> "%VBS_SCRIPT%"
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%VBS_SCRIPT%"
echo oLink.TargetPath = "%BAT_PATH%" >> "%VBS_SCRIPT%"
echo oLink.WorkingDirectory = "%~dp0" >> "%VBS_SCRIPT%"
echo oLink.Description = "Iniciar Estilo Unico ERP" >> "%VBS_SCRIPT%"
echo oLink.Save >> "%VBS_SCRIPT%"

cscript /nologo "%VBS_SCRIPT%"
del "%VBS_SCRIPT%" >nul 2>&1
echo  OK: Atalho criado em %STARTUP_FOLDER%.
echo.
echo ========================================================
echo  Configuracoes concluidas com sucesso!
echo ========================================================
pause
