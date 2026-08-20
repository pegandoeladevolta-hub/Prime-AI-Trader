@echo off
setlocal EnableExtensions
chcp 65001 >nul
title PRIME AI TRADER - Limpeza segura

echo ============================================================
echo        PRIME AI TRADER - LIMPEZA SEGURA DE CACHE
echo ============================================================
echo.
echo Esta ferramenta remove somente arquivos regeneraveis:
echo - cache temporario;
echo - modelos de IA de versoes antigas;
echo - restos de atualizacoes anteriores.
echo.
echo Serao preservados:
echo - chaves de API;
echo - configuracoes;
echo - banco de sinais e historico de operacoes.
echo.

tasklist /FI "IMAGENAME eq PrimeAITrader.exe" 2>NUL | find /I "PrimeAITrader.exe" >NUL
if not errorlevel 1 (
    echo Feche o PRIME AI TRADER antes de executar a limpeza.
    echo Nenhum arquivo foi alterado.
    echo.
    pause
    exit /b 2
)

choice /C SN /N /M "Deseja continuar? [S/N]: "
if errorlevel 2 exit /b 0

call :RemoveDir "%APPDATA%\PrimeAITrader\models"
call :RemoveDir "%APPDATA%\PrimeAITrader\cache"
call :RemoveDir "%APPDATA%\PrimeAITrader\temp"
call :RemoveDir "%APPDATA%\PrimeAITrader\old_versions"
call :RemoveDir "%APPDATA%\PrimeAITrader\updates"

call :RemoveDir "%LOCALAPPDATA%\PrimeAITrader\models"
call :RemoveDir "%LOCALAPPDATA%\PrimeAITrader\cache"
call :RemoveDir "%LOCALAPPDATA%\PrimeAITrader\temp"
call :RemoveDir "%LOCALAPPDATA%\PrimeAITrader\old_versions"

call :RemoveDir "%LOCALAPPDATA%\Programs\PrimeAITrader-old"
call :RemoveDir "%LOCALAPPDATA%\Programs\PrimeAITrader-legacy"
call :RemoveDir "%LOCALAPPDATA%\Programs\PrimeAITrader-0.1.0"
call :RemoveDir "%LOCALAPPDATA%\Programs\PrimeAITrader-0.2.0"
call :RemoveDir "%LOCALAPPDATA%\Programs\PrimeAITrader-0.3.0"

call :RemoveDir "%TEMP%\PrimeAITrader"
for /d %%D in ("%TEMP%\PrimeAITrader-*") do if exist "%%~fD" rd /s /q "%%~fD" 2>nul

echo.
echo Limpeza concluida com seguranca.
echo Abra o PRIME AI TRADER, inicie uma nova analise e treine novamente o ativo.
echo.
pause
exit /b 0

:RemoveDir
if exist "%~1" (
    echo Removendo: %~1
    rd /s /q "%~1" 2>nul
)
exit /b 0
