# 🏗️ p2p-michael — Sistema Distribuído P2P com Balanceamento Dinâmico

> Um sistema distribuído autônomo que demonstra balanceamento de carga horizontal através de uma arquitetura P2P, onde Masters negociam dinamicamente o empréstimo de Workers para lidar com excesso de requisições.

---

## 🎯 O Que Este Sistema Faz (em linguagem simples)

Imagine uma **pizzaria com vários fornos**. Cada forno é um "**Master**" — um gerente responsável. Quando chega um pedido, o gerente manda um de seus pizzaiolos ("**Workers**") fazer o trabalho.

Tudo funciona bem... até a festa de 500 pessoas chegar. De repente, aquele forno tem 50 pizzas esperando, e os pizzaiolos estão sobrecarregados!

Aí entra a mágica: o gerente do forno 1 liga para o gerente do forno 2 vizinho e diz: *"Ei, me empresta 2 pizzaiolos?"* O gerente 2 responde: *"Claro!"* Os pizzaiolos vão ajudar. Quando a festa acaba, eles voltam.

**Esse é nosso sistema:** Um P2P autônomo que **distribui trabalho dinamicamente**, sem depender de um servidor central.

---

## 🤔 O Problema que Resolvemos

Sistemas centralizados tradicionais têm dois grandes problemas:

1. **Ponto único de falha:** Se o servidor morre, tudo cai.
2. **Não escalável:** Você não consegue adicionar máquinas novas dinamicamente para lidar com picos de carga.

**Nossa solução** é um sistema distribuído autônomo onde:
- ✅ Cada nó Master gerencia seus próprios Workers
- ✅ Quando fica saturado, **negocia com vizinhos** para pedir ajuda
- ✅ Não precisa de autoridade central — **tudo funciona por consenso**
- ✅ Totalmente interoperável (Masters/Workers de equipes diferentes se comunicam)

---

## 🏛️ Arquitetura — Os Três Personagens

### 🧑‍💼 **MASTER** (O Gerente do Forno)
- Gerencia um conjunto de Workers (sua "Farm")
- Recebe requisições de clientes (simuladas por um `load_generator`)
- Distribui tarefas para seus Workers de forma justa
- Monitora se está sobrecarregado (saturação)
- Quando fica saturado, **negocia com Masters vizinhos** para pedir empréstimo de Workers
- Gerencia Workers próprios E Workers emprestados temporariamente
- Mantém conexões TCP com Workers e com Masters vizinhos
- Escuta em UDP para descoberta automática

### 👷 **WORKER** (O Pizzaioló)
- É quem executa o trabalho real
- Conecta em um Master ao iniciar (descoberta automática ou manual)
- Envia "heartbeat" a cada 30 segundos (verifica se Master está vivo)
- Recebe tarefas da fila do Master
- Processa a tarefa (simula com `sleep` de 3 segundos)
- Reporta o resultado (OK ou NOK)
- Pode ser **emprestado temporariamente** para outro Master quando solicitado
- Lembra quem é seu Master original (para retornar quando a crise passar)

### 📡 **PROTOCOLO** (As Regras de Conversa)
- Baseado em **JSON sobre TCP**
- Cada mensagem termina com **\n** (delimitador)
- Todos os Masters e Workers falam a **mesma língua** — totalmente interoperáveis
- Valores de controle em **CAIXA ALTA** (ALIVE, QUERY, NO_TASK, OK, NOK, ACK)
- Evolui em **3 Sprints** com complexidade crescente

---

## 📅 As Três Sprints Implementadas

### 🏃 **SPRINT 1 — Heartbeat (Mecanismo de Verificação de Atividade)**

**Objetivo:** Master e Worker se verificam mutuamente para detectar falhas.

**Analogia:** É como ligar para sua mãe todo dia à noite e dizer: *"Mãe, tô vivo aqui!"*

**O que acontece:**
1. Worker conecta no Master via TCP
2. A cada **30 segundos**, Worker envia sua "apresentação" (quem ele é)
3. Master recebe e responde: *"Sim, estou aqui! RESPOSTA: ALIVE"*
4. Worker recebe confirmação e fica em paz por mais 30s
5. Se Worker não recebe resposta em **5 segundos**, considera Master offline

**Por que é importante?** Sem heartbeat, você nunca saberia se o Master morreu. Com isso, detecta falhas em segundos.

**Formato JSON (com \n no final):**
```json
Worker → Master:
{"WORKER": "ALIVE", "WORKER_UUID": "abc123..."}

Master → Worker:
{"SERVER_UUID": "xyz789...", "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"}
```

**Status de Implementação:** ✅ **90% COMPLETO**
- ✅ Loop a cada 30 segundos
- ✅ Timeout de 5 segundos
- ✅ Master usa threads para não bloquear
- ⚠️ Primeira mensagem é de "apresentação" (Sprint 2), não heartbeat puro (detalhe arquitetural)

---

### 🏃‍♀️ **SPRINT 2 — Ciclo de Tarefas (Apresentação, Distribuição, Status, ACK)**

**Objetivo:** Implementar o fluxo completo de distribuição de trabalho (fila de atendimento).

**Analogia:** É como uma fila de banco:
1. Cliente chega: *"Oi, sou eu!"*
2. Caixa vê se tem fila
3. Se tem: *"Você vai fazer essa transferência"*
4. Cliente processa: *"Pronto!"*
5. Caixa confirma: *"OK, próximo!"*

**O que acontece (6 passos):**

1. **Apresentação:** Worker diz "Oi Master, sou eu, worker-123"
   - Se for **emprestado**, também diz quem é seu Master original

2. **Requisição:** Worker pergunta "Tem trabalho?"

3. **Resposta Master:**
   - Se tem tarefa na fila: *"Sim! Calcule isso para o User1"*
   - Se não tem: *"Não, fila vazia"*

4. **Processamento:** Worker processa (aguarda 3 segundos por tarefa)

5. **Reporte:** Worker diz *"Pronto! Status: OK"* (ou NOK se falhou)

6. **ACK:** Master confirma *"Recebi! Pode pedir outra"*

**Por que é importante?** Agora o sistema realmente **processa trabalho**, rastreia qual Worker faz qual tarefa, e garante entrega (ACK).

**Formato JSON (com \n no final):**
```json
Worker apresenta (local):
{"WORKER": "ALIVE", "WORKER_UUID": "w1"}

Worker apresenta (emprestado):
{"WORKER": "ALIVE", "WORKER_UUID": "w1", "SERVER_UUID": "master_original_id"}

Master entrega tarefa:
{"TASK": "QUERY", "USER": "User1"}

Master sem tarefa na fila:
{"TASK": "NO_TASK"}

Worker reporta sucesso:
{"STATUS": "OK", "TASK": "QUERY", "WORKER_UUID": "w1"}

Worker reporta falha:
{"STATUS": "NOK", "TASK": "QUERY", "WORKER_UUID": "w1"}

Master confirma (ACK):
{"STATUS": "ACK", "WORKER_UUID": "w1"}
```

**Status de Implementação:** ✅ **90% COMPLETO**
- ✅ Fila de tarefas funcionando
- ✅ Apresentação de Workers local e emprestados
- ✅ Distribuição de tarefas (QUERY/NO_TASK)
- ✅ Reporte de status (OK/NOK)
- ✅ ACK de confirmação
- ✅ Timeout de 5 segundos no Worker
- ⚠️ Alguns campos extras adicionados (TASK_ID, FORCE_NOK) que não quebram compatibilidade

---

### 🏃‍♂️ **SPRINT 3 — Negociação Master-to-Master (Pedir Reforço)**

**Objetivo:** Masters conversam entre si para emprestar Workers quando um deles fica saturado e devolver esses Workers quando a carga volta ao normal.

**Analogia:** É como dois gerentes de cozinha.
- Se a cozinha A lota, o gerente A pede reforço ao gerente B.
- O gerente B vê se tem gente livre e empresta um ou mais cozinheiros.
- Esses cozinheiros trabalham temporariamente na cozinha A.
- Quando a fila de A baixa, os cozinheiros voltam para a cozinha B.

**Fluxo implementado:**

1. O Master A detecta saturação quando `pending > LOAD_THRESHOLD`.
2. O Master A envia para um vizinho um envelope JSON com `type`, `request_id` e `payload`.
3. O Master B responde com `response_accepted` ou `response_rejected`, usando o mesmo `request_id`.
4. Se aceitar, o Master B envia `command_redirect` para os Workers escolhidos.
5. O Worker redirecionado conecta no Master A e envia `register_temporary_worker`.
6. O Worker temporário continua o ciclo da Sprint 2 normalmente.
7. Quando `pending <= RELEASE_THRESHOLD`, o Master A envia `command_release`.
8. O Worker volta ao Master original e o Master A emite `notify_worker_returned`.

**Formato JSON da Sprint 3:**
```json
request_help:
{"type": "request_help", "request_id": "uuid", "payload": {"master_uuid": "...", "master_name": "...", "current_load": 6, "workers_needed": 2}}

response_accepted:
{"type": "response_accepted", "request_id": "uuid", "payload": {"master_uuid": "...", "workers_offered": 2, "worker_details": [{"worker_uuid": "..."}]}}

command_redirect:
{"type": "command_redirect", "request_id": "uuid", "payload": {"new_master_uuid": "...", "new_master_host": "...", "new_master_port": 5000}}

register_temporary_worker:
{"type": "register_temporary_worker", "request_id": "uuid", "payload": {"WORKER_UUID": "...", "ORIGINAL_MASTER_UUID": "...", "ORIGINAL_MASTER_HOST": "...", "ORIGINAL_MASTER_PORT": 5001}}

command_release:
{"type": "command_release", "request_id": "uuid", "payload": {"return_to_master_uuid": "...", "return_to_master_host": "...", "return_to_master_port": 5001}}

notify_worker_returned:
{"type": "notify_worker_returned", "request_id": "uuid", "payload": {"worker_uuid": "...", "owner_master_uuid": "..."}}
```

**Status de Implementação:** ✅ **COMPLETO**
- ✅ Envelope padrão `type` / `request_id` / `payload`
- ✅ `request_id` igual no pedido e na resposta
- ✅ `response_accepted` e `response_rejected`
- ✅ `command_redirect` e `register_temporary_worker`
- ✅ `command_release` e `notify_worker_returned`
- ✅ Timeout de 5 segundos para resposta de vizinho
- ✅ Histerese com `LOAD_THRESHOLD` e `RELEASE_THRESHOLD`

**Recomendação:** Sprint 3 agora está pronta para demonstração ao vivo com dois Masters e Workers sendo emprestados em tempo real.

---

## 🚀 Como Executar

### Pré-requisitos
- Python 3.7+
- Nenhuma dependência externa (apenas biblioteca padrão)

### Opção 1: Teste Local (Recomendado para Apresentação)

**Terminal 1 — Inicie o Master:**
```bash
python master.py
```
Você verá:
```
[MASTER] Iniciando | UUID: xxxxx | nome: MASTER_1
[MASTER] Descoberta UDP ativa em 0.0.0.0:5000 | nome=MASTER_1
[MASTER] Escutando em 0.0.0.0:5000 | anunciado como 127.0.0.1:5000
[MASTER] Modo Sprint 1 ativo: apenas HEARTBEAT para demonstracao.
```

**Terminal 2 — Inicie o Worker 1 (descobe​rta automática):**
```bash
python worker.py
```
Você verá:
```
[WORKER] UUID: yyyyy
[WORKER][DISCOVERY] Iniciando sem host/porta configurados...
[WORKER][DISCOVERY] Probe enviado para 255.255.255.255:5000
[WORKER][DISCOVERY] Resposta valida de MASTER_1 em 127.0.0.1:5000
[WORKER] Conectado em 127.0.0.1:5000
[WORKER] Apresentacao enviada: {'WORKER': 'ALIVE', 'WORKER_UUID': 'yyyyy'}
```

**Terminal 3 — Inicie o Worker 2:**
```bash
python worker.py
```

Agora você verá a conversação:
- Workers enviando apresentação a cada 30 segundos
- Master respondendo com "HEARTBEAT" + "RESPONSE": "ALIVE"
- Tarefas sendo geradas, distribuídas e completadas

### Opção 2: Teste com Hosts/Portas Explícitas

Se você quer rodar Masters em máquinas diferentes:

**Terminal 1 — Master em localhost:5000:**
```bash
MASTER_NAME=MASTER_1 MASTER_PORT=5000 python master.py
```

**Terminal 2 — Worker conectando manualmente:**
```bash
python worker.py 127.0.0.1 5000
```

### Opção 3: Múltiplos Masters (Sprint 3)

Para demonstrar a negociação Master-to-Master com empréstimo de Workers:

> **Pré-requisito:** `NEIGHBOR_MASTERS` deve apontar para o Master que irá emprestar Workers.
> O Master que possui `NEIGHBOR_MASTERS` configurado é quem faz o pedido de ajuda quando satura.

**Terminal 1 — Master B (helper — apenas aceita workers, não pede ajuda):**
```bash
MASTER_NAME=MASTER_B MASTER_PORT=5001 python master.py
```

**Terminal 2 — Master A (saturado — pede ajuda ao B):**
```bash
MASTER_NAME=MASTER_A MASTER_PORT=5000 NEIGHBOR_MASTERS=127.0.0.1:5001 python master.py
```

**Terminal 3–4 — Workers ociosos no Master B (serão emprestados):**
```bash
python worker.py 127.0.0.1 5001
python worker.py 127.0.0.1 5001
```

**Terminal 5–6 — Workers no Master A (insuficientes para a carga):**
```bash
python worker.py 127.0.0.1 5000
```

**O que observar:**
1. Master A satura (`pending > 5`) → envia `request_help` ao Master B
2. Master B responde `response_accepted` e manda `command_redirect` aos seus Workers
3. Workers enviam `register_temporary_worker` ao Master A e processam tarefas
4. Quando `pending <= 3`, Master A envia `command_release` → Workers voltam ao Master B

---

## 📊 Casos de Teste Principais

### SPRINT 1 — Heartbeat

| Caso | Ação | Resultado Esperado |
|------|------|-------------------|
| **CT1.1** | Iniciar Worker e deixar rodando | Worker envia apresentação a cada 30s; Master responde ALIVE |
| **CT1.2** | Matar Master enquanto Worker roda | Worker detecta falha em até 5s; tenta reconectar |
| **CT1.3** | Matar Worker enquanto Master roda | Master log: "Worker desconectou"; continua aceitando outros |
| **CT1.4** | Dois Workers simultaneamente | Master trata ambos em threads separadas; sem bloqueio |

### SPRINT 2 — Tarefas

| Caso | Ação | Resultado Esperado |
|------|------|-------------------|
| **CT2.1** | Worker inicia sem tarefas enfileiradas | Master responde com {"TASK": "NO_TASK"} |
| **CT2.2** | Load generator cria 3 tarefas; 1 Worker pega | Worker recebe QUERY, processa 3s, reporta OK; Master envia ACK |
| **CT2.3** | 2 Workers, 10 tarefas | Ambos pegam tarefas; nenhuma é executada 2x |
| **CT2.4** | Worker reporta NOK (força falha) | Master recebe NOK; ainda envia ACK; registra em log |
| **CT2.5** | Worker não responde em 5s | Master timeout; Worker tenta reconectar |

### SPRINT 3 — Negociação entre Masters

| Caso | Ação | Resultado Esperado |
|------|------|-------------------|
| **CT3.1** | Master A fica saturado (`pending > LOAD_THRESHOLD`) | Master A envia `request_help` com `request_id` e `payload` |
| **CT3.2** | Master B tem Workers ociosos | Master B responde `response_accepted` com `worker_details` |
| **CT3.3** | Master B sem capacidade | Master B responde `response_rejected` com `reason` |
| **CT3.4** | Worker redirecionado em operação | Worker envia `register_temporary_worker` e continua Sprint 2 |
| **CT3.5** | Master A normaliza (`pending <= RELEASE_THRESHOLD`) | Master A envia `command_release` e `notify_worker_returned` |

---

## 🔧 Arquivos Principais

| Arquivo | Responsabilidade |
|---------|-----------------|
| **config.py** | Constantes compartilhadas (portas, thresholds, timeouts, nomes dos Masters) |
| **master.py** | Servidor Master — escuta Workers, distribui tarefas, negocia com vizinhos |
| **worker.py** | Cliente Worker — conecta em Master, recebe tarefas, processa, reporta |

### Variáveis de Ambiente (Opcionais)

```bash
# Master
MASTER_NAME=MASTER_A          # Nome único do Master
MASTER_HOST=127.0.0.1         # IP anunciado para Workers
MASTER_BIND_HOST=0.0.0.0      # Interface de escuta
MASTER_PORT=5000              # Porta TCP
DISCOVERY_PORT=5000           # Porta UDP (geralmente igual a MASTER_PORT)
NEIGHBOR_MASTERS=ip:port      # Masters vizinhos (para negociação)
LOAD_THRESHOLD=5              # Limite de tarefas pendentes para saturação
REQUEST_INTERVAL=1.0          # Intervalo entre geração de tarefas (segundos)
HEARTBEAT_INTERVAL=30.0       # Intervalo de heartbeat (segundos)

# Worker
# Nenhuma variável de ambiente específica; usa defaults de config.py
```

---

## 🎬 Como Funciona na Prática (Fluxo Completo)

### Cenário: Uma festa chega (pico de carga)

**Tempo 0:00 — Sistema em repouso**
```
Master A:  10 Workers, 0 tarefas pendentes (relaxado)
```

**Tempo 0:05 — Chegam requisições**
```
Load Generator cria: TASK-0000, TASK-0001, TASK-0002 (tarefas chegam a cada 1s)
Master A fila:      [TASK-0000, TASK-0001, TASK-0002] (3 pendentes)
Workers pegam:      W1 pega TASK-0000, W2 pega TASK-0001, W3 pega TASK-0002
Workers processam:  (3 segundos cada)
```

**Tempo 0:10 — Mais requisições chegam rápido**
```
Load Generator continua: TASK-0003, TASK-0004, TASK-0005, TASK-0006
Master A fila:  [TASK-0003, TASK-0004, TASK-0005, TASK-0006] (4 pendentes)
(Tarefas completam a 3 em 3 segundos, mas chegam a cada 1s = FILA CRESCE)
```

**Tempo 0:15 — SATURAÇÃO! (pending = 6 > LOAD_THRESHOLD = 5)**
```
[MASTER] SATURADO! (6 pendentes). Pedindo ajuda...
Master A conecta em Master B vizinho
Master A envia: {"type": "request_help", "request_id": "...", "payload": {...}}
```

**Tempo 0:16 — Master B responde**
```
Master B analisa sua carga e responde com o mesmo request_id
Master B responde: {"type": "response_accepted", "request_id": "...", "payload": {...}}
Master B envia comando: {"type": "command_redirect", "request_id": "...", "payload": {...}}
W7 e W8 desconectam de Master B, conectam em Master A
W7 e W8 enviam: {"type": "register_temporary_worker", "request_id": "...", "payload": {...}}
```

**Tempo 0:17 — Workers emprestados em operação**
```
Master A agora tem: 12 Workers (10 próprios + 2 emprestados)
W7 e W8 puxam tarefas: TASK-0007, TASK-0008
Master A fila: [TASK-0009, TASK-0010] (reduz a fila!)
```

**Tempo 0:30 — Festa termina (requisições param)**
```
Load Generator para de criar tarefas
Workers continuam processando o que sobrou
Fila: 0 pendentes
```

**Tempo 0:35 — Normalização**
```
Master A carga <= RELEASE_THRESHOLD (liberação)
Master A ordena: {"type": "command_release", "request_id": "...", "payload": {...}}
W7 e W8 desconectam de Master A, reconectam em Master B
Master A notifica: {"type": "notify_worker_returned", "request_id": "...", "payload": {...}}
Master B registra que os Workers voltaram
```

**Tempo 0:36 — Volta ao normal**
```
Master A:  10 Workers, 0 tarefas (relaxado)
Master B:  10 Workers, 0 tarefas (relaxado)
Ninguém se importa que houve uma crise 30 segundos atrás!
```

---

## 📈 Observabilidade — O Que Você Verá nos Logs

### Master Log (Exemplo)
```
[MASTER] Iniciando | UUID: a1b2c3d4 | nome: MASTER_1
[MASTER] Descoberta UDP ativa em 0.0.0.0:5000 | nome=MASTER_1
[MASTER] Escutando em 0.0.0.0:5000 | anunciado como 127.0.0.1:5000
[MASTER] Worker proprio w1 apresentou-se de 127.0.0.1:54321
[MASTER] Tarefa TASK-0000 enfileirada para User1. Pendentes: 1
[MASTER] Enviando TASK-0000 para Worker w1 | USER=User1
[MASTER] Tarefa TASK-0000 concluida por w1 com status OK. Pendentes: 0
[MASTER] Discovery reply enviado para w2 em 127.0.0.1:54322
[MASTER] SATURADO! (6 pendentes). Pedindo ajuda...
[MASTER] Vizinho 127.0.0.1:5001 aceitou ajudar!  # Sprint 3
```

### Worker Log (Exemplo)
```
[WORKER] UUID: w1
[WORKER] Conectado em 127.0.0.1:5000
[WORKER] Apresentacao enviada: {'WORKER': 'ALIVE', 'WORKER_UUID': 'w1'}
[WORKER] Processando tarefa TASK-0000 para User1...
[WORKER] ACK recebido da tarefa TASK-0000
[WORKER] Heartbeat confirmado pelo Master
[WORKER] Status: OFFLINE - Tentando Reconectar (1/4)
[WORKER] Conectado em 127.0.0.1:5000  # Reconectado!
```

---

## 🏆 Resumo Visual da Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                    Internet/LAN                         │
└──────────────────┬──────────────────────────────────────┘
                   │
       ┌───────────┼───────────┐
       │           │           │
    ┌──▼──┐     ┌──▼──┐    ┌──▼──┐
    │Master A    │Master B    │Master C
    │(Port 5000) │(Port 5001) │(Port 5002)
    └──┬──┘     └──┬──┘    └──┬──┘
       │           │           │
   ┌───┴───────┐   │      ┌────┴──┐
   │           │   │      │       │
  Worker   Worker  │    Worker  Worker
   W1    W2-W10   │     W11-W20  W21-W30
              │   │
              │   │
          (vizinhos — Sprint 3)
```

---

## 🧪 Teste de Stress (Opcional)

Se você quer testar com mais Workers:

```bash
# Terminal 1 — Master
python master.py

# Terminal 2-11 — 10 Workers
for i in {1..10}; do
  python worker.py 127.0.0.1 5000 &
done

# Monitorar a saída do Master
# Você verá: Tarefas sendo distribuídas, completadas, nova tarefa gerada a cada 1s
```

---

## 📚 Referências e Documentação

### Documentação Técnica (pasta `docs/`)

| Documento | Conteúdo |
|-----------|----------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Arquitetura, diagramas Mermaid, modelo de threads |
| [`docs/PROTOCOL.md`](docs/PROTOCOL.md) | Todos os formatos de mensagem e fluxos de comunicação |
| [`docs/SPRINTS.md`](docs/SPRINTS.md) | Descrição detalhada de cada sprint |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Decisões arquiteturais (ADR-001 a ADR-009) |
| [`docs/TESTING.md`](docs/TESTING.md) | 99 casos de teste (Sprint 3 + Sprint 4) e cobertura de requisitos |
| [`docs/EXECUTION.md`](docs/EXECUTION.md) | Instruções passo a passo para cada cenário |

### Especificações Oficiais

- **Plano Geral do Projeto:** `plano_proj_SD-26_1.pdf`
- **Especificação Sprint 2.1 (Descoberta/Eleição):** `discovery.pdf`
- **Design Spec Sprint 2.1:** `docs/superpowers/specs/2026-05-08-p2p-discovery-election-design.md`
- **Plan Sprint 2.1:** `docs/superpowers/plans/2026-05-08-p2p-discovery-election.md`

---

## ✅ Status da Implementação

| Sprint | Feature | Status |
|--------|---------|--------|
| 1 | Heartbeat básico | ✅ Completo |
| 2.1 | Descoberta UDP (broadcast/unicast) | ✅ Completo |
| 2.1 | Eleição determinística (menor nome) | ✅ Completo |
| 2.1 | Handshake TCP pós-eleição | ✅ Completo |
| 2.1 | Fallback/retry sem Master | ✅ Completo |
| 2 | Ciclo de tarefas (apresentação) | ✅ Completo |
| 2 | Fila e distribuição | ✅ Completo |
| 2 | Reporte de status (OK/NOK) | ✅ Completo |
| 2 | ACK de confirmação | ✅ Completo |
| 3 | Detecção de saturação | ✅ Completo |
| 3 | request_help + response_accepted/rejected | ✅ Completo |
| 3 | request_id correlacionado | ✅ Completo |
| 3 | command_redirect → register_temporary_worker | ✅ Completo |
| 3 | ORIGINAL_MASTER_NAME no registro temporário | ✅ Completo |
| 3 | Dispatch contínuo de tarefas após ACK | ✅ Completo |
| 3 | command_release + retorno do Worker | ✅ Completo |
| 3 | notify_worker_returned | ✅ Completo |
| 3 | Histerese (LOAD_THRESHOLD / RELEASE_THRESHOLD) | ✅ Completo |
| 4 | Monitor de métricas (thread daemon) | ✅ Completo |
| 4 | Coleta via psutil (CPU, memória, disco) | ✅ Completo |
| 4 | Envio TLS TCP fire-and-forget ao supervisor | ✅ Completo |
| 4 | Schema `sprint4-monitor` com todos os campos | ✅ Completo |
| 4 | Fallback sem psutil (zeros) | ✅ Completo |
| 4 | Resiliência: falha de envio não para o Master | ✅ Completo |

---

## 📝 Licença

Projeto acadêmico — Arquitetura de Sistemas Distribuídos, CEUBr 2026