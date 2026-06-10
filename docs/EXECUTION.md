# Instruções de Execução

## Pré-requisitos

- Python 3.8 ou superior
- Sem dependências externas — apenas stdlib
- Windows, Linux ou macOS

Verificar versão:
```powershell
python --version
```

---

## Cenário 1: Sprint 1 — Heartbeat Simples

Demonstra conectividade básica Worker → Master com heartbeat periódico.

### Passo 1: Ativar modo Sprint 1

Editar `config.py`, linha 25:
```python
SPRINT1_HEARTBEAT_ONLY = True
```

### Passo 2: Terminal A — Iniciar o Master

```powershell
python master.py
```

Saída esperada:
```
[MASTER] Iniciando | UUID: <uuid> | nome: MASTER_1
[MASTER] Modo Sprint 1 ativo: apenas HEARTBEAT para demonstracao.
[MASTER] Escutando em 0.0.0.0:5000 | anunciado como 127.0.0.1:5000
```

### Passo 3: Terminal B — Iniciar o Worker

```powershell
python worker.py 127.0.0.1 5000
```

Saída esperada (Worker):
```
[WORKER] Conectando em 127.0.0.1:5000
[WORKER] Conectado. Enviando apresentacao...
[WORKER] ALIVE enviado.
[WORKER] Resposta: {'SERVER_UUID': '...', 'TASK': 'HEARTBEAT', 'RESPONSE': 'ALIVE'}
```

---

## Cenário 2: Sprint 2 — Ciclo Completo de Tarefas

### Passo 1: Garantir modo completo

Editar `config.py`:
```python
SPRINT1_HEARTBEAT_ONLY = False
```

### Passo 2: Terminal A — Master

```powershell
python master.py
```

### Passo 3: Terminais B, C, D — Workers

```powershell
# Terminal B
python worker.py 127.0.0.1 5000

# Terminal C
python worker.py 127.0.0.1 5000

# Terminal D (opcional, terceiro worker)
python worker.py 127.0.0.1 5000
```

### O que observar

No Master:
```
[MASTER] Tarefa TASK-0001 enfileirada para User1. Pendentes: 1
[MASTER] Worker proprio abc12345 apresentou-se de ('127.0.0.1', ...)
[MASTER] Enviando TASK-0001 para Worker abc12345 | USER=User1
[MASTER] Tarefa TASK-0001 concluida por abc12345 com status OK. Pendentes: 0
```

No Worker:
```
[WORKER] Tarefa recebida: TASK-0001 para User1
[WORKER] Processando... (3s)
[WORKER] Tarefa TASK-0001 concluida com status OK
[WORKER] ACK recebido para TASK-0001
```

---

## Cenário 3: Sprint 2.1 — Descoberta UDP e Eleição

### Configuração (múltiplos Masters na mesma máquina)

**Terminal A — Master 1 (eleito)**
```powershell
$env:MASTER_NAME="MASTER_1"; $env:MASTER_PORT="5000"; $env:MASTER_HOST="127.0.0.1"; python master.py
```

**Terminal B — Master 2**
```powershell
$env:MASTER_NAME="MASTER_2"; $env:MASTER_PORT="5001"; $env:MASTER_HOST="127.0.0.1"; python master.py
```

**Terminal C — Worker (modo descoberta — sem argumentos)**
```powershell
python worker.py
```

### O que observar

Worker descobre dois Masters via UDP broadcast, elege `MASTER_1` (menor nome), conecta via TCP, executa handshake `ELECTION_ACK`:
```
[WORKER] Iniciando descoberta UDP em 255.255.255.255:5000
[WORKER] Masters encontrados: ['MASTER_1', 'MASTER_2']
[WORKER] Master eleito: MASTER_1
[WORKER] Handshake de eleicao com MASTER_1...
[WORKER] Handshake aceito. Conectado ao MASTER_1.
```

---

## Cenário 4: Sprint 3 — Negociação Master-to-Master

Este é o cenário principal da Sprint 3. Requer dois Masters configurados como vizinhos.

### Diagrama do Cenário

```
MASTER_1 (porta 5000) ──── conhece ────► MASTER_2 (porta 5001)
    │                                         │
    │◄── W1, W2, W3 (workers locais)          │◄── W4 (worker local)
    │
    (satura com >5 pendentes)
    ──── request_help ────────────────────────►
    ◄─── response_accepted ──────────────────
                           ─── command_redirect ──► W4
                                                    │
    ◄── register_temporary_worker ──────────────────
    (processa com 4 workers)
    (carga cai ≤ 3)
    ─── command_release ──────────────────────────► W4
                                                    │
    ◄── notify_worker_returned (de W4 para MASTER_2)
```

### Terminal A — Master 1 (solicitante de ajuda)

```powershell
$env:MASTER_NAME="MASTER_1"
$env:MASTER_PORT="5000"
$env:MASTER_HOST="127.0.0.1"
$env:NEIGHBOR_MASTERS="127.0.0.1:5001"
python master.py
```

### Terminal B — Master 2 (auxiliar)

```powershell
$env:MASTER_NAME="MASTER_2"
$env:MASTER_PORT="5001"
$env:MASTER_HOST="127.0.0.1"
python master.py
```

### Terminais C, D, E — Workers para Master 1

```powershell
python worker.py   # descobre e conecta no MASTER_1 (menor nome)
```

### Terminal F — Worker para Master 2

Para forçar um worker no Master 2 (para que ele possa emprestar):
```powershell
# Conectar diretamente ao MASTER_2 (sem eleição)
python worker.py 127.0.0.1 5001
```

### O que observar durante a demo

**Saturação (≈5s após iniciar):**
```
[MASTER] SATURADO! (6 pendentes). Pedindo ajuda...
[MASTER] Vizinho 127.0.0.1:5001 aceitou ajudar com 1 worker(s).
[MASTER] Worker <uuid> redirecionado para MASTER_2 (127.0.0.1:5001).
```

**Worker redirecionado:**
```
[WORKER] Recebido command_redirect: MASTER_1 -> MASTER_2
[WORKER] Conectando ao novo Master MASTER_2 em 127.0.0.1:5001
[WORKER] Registrado como worker temporario em MASTER_2
```

**Liberação (quando fila drena):**
```
[MASTER] Carga normalizada (2 pendentes). Liberando 1 worker(s) emprestado(s)...
[MASTER] Worker <uuid> liberado e redirecionado de volta ao Master original.
[MASTER] notify_worker_returned enviado para 127.0.0.1:5001 sobre <uuid>.
```

---

## Variáveis de Ambiente — Referência Rápida

```powershell
# Identidade do Master
$env:MASTER_NAME="MASTER_1"          # nome único (usado na eleição)
$env:MASTER_PORT="5000"              # porta TCP e UDP
$env:MASTER_HOST="127.0.0.1"         # IP anunciado para workers
$env:MASTER_BIND_HOST="0.0.0.0"      # IP de escuta (bind)

# Vizinhos M2M
$env:NEIGHBOR_MASTERS="127.0.0.1:5001,192.168.1.10:5000"

# Ajuste de comportamento
$env:RELEASE_THRESHOLD="3"           # carga para liberar workers emprestados
$env:SPRINT3_HELP_TIMEOUT="5.0"      # timeout da negociação M2M (segundos)
$env:SPRINT3_DEFAULT_WORKERS_TO_BORROW="1"   # workers solicitados por padrão
```

---

## Executar os Testes

```powershell
# Testes unitários (sem rede, rápido)
python -m pytest test_sprint3.py -v

# Com relatório de cobertura (requer pytest-cov)
python -m pytest test_sprint3.py -v --tb=short

# Diretamente
python test_sprint3.py
```

Resultado esperado:
```
60 passed in 0.045s
```

---

## Solução de Problemas

| Sintoma                                    | Causa provável                          | Solução                                  |
|--------------------------------------------|-----------------------------------------|------------------------------------------|
| Worker não descobre Masters                | Broadcast bloqueado pelo firewall       | Usar `python worker.py 127.0.0.1 5000`  |
| Master 2 nunca empresta workers            | Nenhum worker local no Master 2         | Conectar um worker diretamente ao Master 2 |
| `OSError: [WinError 10048]` ao iniciar     | Porta já em uso                         | Mudar `MASTER_PORT` ou encerrar o processo anterior |
| Fila nunca drena                           | Workers insuficientes para a taxa de geração | Adicionar mais workers (mínimo 2)    |
| `NEIGHBOR_MASTERS` não funciona             | Formato errado                          | Usar exatamente `host:porta` sem espaços |
