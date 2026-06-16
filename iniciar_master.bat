@echo off
title MASTER - P2P Farm

:: ============================================================
::  Configuracoes do Master
::  Edite as variaveis abaixo conforme necessario
:: ============================================================

:: Identificador unico da sua farm no dashboard do supervisor
set MASTER_NAME=master_6

:: IP desta maquina (usado pelos workers para conectar)
set MASTER_HOST=10.62.206.49

:: Porta TCP do Master
set MASTER_PORT=5000

:: Aceita conexoes de qualquer IP
set MASTER_BIND_HOST=0.0.0.0

:: Identificador do supervisor (mesmo valor de MASTER_NAME)
set FARM_ID=%MASTER_NAME%

:: Supervisor de metricas
set SUPERVISOR_HOST=10.62.206.206
set SUPERVISOR_PORT=8000
set SUPERVISOR_TLS=false
set SUPERVISOR_INTERVAL=10.0

:: Masters vizinhos para negociacao P2P (host:porta,host:porta)
:: Exemplo: set NEIGHBOR_MASTERS=10.62.206.50:5000
set NEIGHBOR_MASTERS=

:: false = modo passivo (sem gerador de tarefas), true = gera carga
set GENERATE_TASKS=false

:: Threshold de saturacao e liberacao
set LOAD_THRESHOLD=5
set RELEASE_THRESHOLD=3

echo.
echo ============================================================
echo  MASTER iniciando...
echo  Nome     : %MASTER_NAME%
echo  IP       : %MASTER_HOST%:%MASTER_PORT%
echo  Supervisor: %SUPERVISOR_HOST%:%SUPERVISOR_PORT%
echo  Vizinhos : %NEIGHBOR_MASTERS%
echo ============================================================
echo.

python master.py
pause
