@echo off
title P2P Farm - Inicializando...

:: ============================================================
::  CONFIGURACOES — edite aqui antes de rodar
:: ============================================================
set MASTER_NAME=master_6
set MASTER_HOST=10.62.206.49
set MASTER_PORT=5000
set MASTER_BIND_HOST=0.0.0.0
set FARM_ID=%MASTER_NAME%
set LOAD_THRESHOLD=5
set RELEASE_THRESHOLD=3
set NEIGHBOR_MASTERS=

:: Supervisor
set SUPERVISOR_HOST=10.62.206.206
set SUPERVISOR_PORT=8000
set SUPERVISOR_TLS=false
set SUPERVISOR_INTERVAL=10.0

:: ============================================================
::  INICIALIZACAO
:: ============================================================
echo.
echo ============================================================
echo   P2P Farm - %MASTER_NAME%
echo   Master    : %MASTER_HOST%:%MASTER_PORT%
echo   Supervisor: %SUPERVISOR_HOST%:%SUPERVISOR_PORT%
echo   Vizinhos  : %NEIGHBOR_MASTERS%
echo ============================================================
echo.

:: --- MASTER ---
echo [1/4] Abrindo MASTER...
start "MASTER [%MASTER_NAME%]" cmd /k python master.py

:: Aguarda master subir
echo Aguardando Master estabilizar (3s)...
timeout /t 3 /nobreak > nul

:: --- WORKERS ---
echo [2/4] Abrindo WORKER 1...
start "WORKER-1" cmd /k python worker.py %MASTER_HOST% %MASTER_PORT%
timeout /t 1 /nobreak > nul

echo [3/4] Abrindo WORKER 2...
start "WORKER-2" cmd /k python worker.py %MASTER_HOST% %MASTER_PORT%
timeout /t 1 /nobreak > nul

echo [4/4] Abrindo WORKER 3...
start "WORKER-3" cmd /k python worker.py %MASTER_HOST% %MASTER_PORT%

echo.
echo Sistema iniciado! Verifique as janelas abertas.
echo Supervisor: %SUPERVISOR_HOST%:%SUPERVISOR_PORT%
echo.
pause
