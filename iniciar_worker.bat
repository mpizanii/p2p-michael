@echo off
title WORKER - P2P Farm

:: ============================================================
::  Inicia um Worker conectado ao Master local
:: ============================================================

set MASTER_HOST=10.62.206.49
set MASTER_PORT=5000

echo.
echo ============================================================
echo  WORKER iniciando...
echo  Conectando em: %MASTER_HOST%:%MASTER_PORT%
echo ============================================================
echo.

python worker.py %MASTER_HOST% %MASTER_PORT%
pause
