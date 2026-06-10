# Descrição das Sprints

Evolução incremental do sistema distribuído P2P ao longo de quatro sprints.
Cada sprint adiciona uma camada de funcionalidade sobre as anteriores, sem remover compatibilidade.

---

## Sprint 1 — Heartbeat TCP

**Objetivo:** Estabelecer conectividade básica e prova de vida entre Worker e Master.

### O que foi implementado

- Worker conecta ao Master via TCP em endereço fixo (host + porta por parâmetro de linha de comando)
- Worker envia mensagem de apresentação `{"WORKER":"ALIVE","WORKER_UUID":"..."}`
- Master responde com `{"SERVER_UUID":"...","TASK":"HEARTBEAT","RESPONSE":"ALIVE"}`
- Worker envia heartbeat periódico a cada `HEARTBEAT_INTERVAL=30s`
- Master responde ao heartbeat com a mesma estrutura de resposta

### Limitações intencionais

- Nenhuma tarefa real é distribuída
- Sem fila, sem estado além da conexão TCP ativa
- Controlado por `SPRINT1_HEARTBEAT_ONLY=True` em `config.py`

### Fluxo

```
Worker                     Master
  |── WORKER:ALIVE ──────►|
  |◄── HEARTBEAT:ALIVE ───|
  |  ... (30s) ...        |
  |── HEARTBEAT ─────────►|
  |◄── HEARTBEAT:ALIVE ───|
```

---

## Sprint 2 — Ciclo Completo de Tarefas

**Objetivo:** Implementar geração, distribuição, execução e confirmação de tarefas.

### O que foi implementado

- Master gera tarefas a cada `REQUEST_INTERVAL=1.0s` com IDs sequenciais (`TASK-0001`, ...)
- Fila interna de tarefas (`task_queue`) protegida por lock
- Worker recebe `QUERY` após apresentação e após cada ACK
- Worker simula execução por `TASK_DURATION=3s`
- Worker envia relatório `STATUS: OK` ou `STATUS: NOK` (simulado via `FORCE_NOK`)
- Master envia `ACK` confirmando recebimento do status
- `FORCE_NOK=True` a cada 5ª tarefa simula falhas reais no sistema
- Se não há tarefa disponível, Master responde `TASK: NO_TASK`

### Fluxo

```
Worker                       Master
  |── WORKER:ALIVE ────────►|
  |                          |── (verifica fila)
  |◄── QUERY:TASK-0001 ─────|
  |  ... (3s execução) ...   |
  |── STATUS:OK ────────────►|
  |◄── ACK ─────────────────|
  |◄── QUERY:TASK-0002 ─────|  ← despacho imediato (Sprint 3 fix)
```

### Contador de pendentes

`pending` é incrementado quando uma tarefa é enfileirada e decrementado quando o STATUS chega.
Esse contador alimenta a lógica de saturação da Sprint 3.

---

## Sprint 2.1 — Descoberta UDP e Eleição Determinística

**Objetivo:** Workers não precisam mais conhecer o IP do Master antecipadamente.
Múltiplos Masters podem coexistir na rede; o Worker escolhe o melhor de forma autônoma.

### O que foi implementado

**Descoberta UDP:**
- Worker envia broadcast UDP para `255.255.255.255` na porta `DISCOVERY_PORT`
- Todos os Masters na rede respondem com unicast UDP contendo nome, IP, porta e UUID
- Worker coleta respostas durante `DISCOVERY_TIMEOUT=3.0s`

**Eleição determinística:**
- Worker ordena Masters respondentes por nome lexicográfico
- Menor nome vence a eleição (ex: `MASTER_1` < `MASTER_2`)
- Critério determinístico: todos os Workers escolhem o mesmo Master dado o mesmo conjunto de respostas

**Handshake TCP de eleição:**
- Worker conecta ao Master eleito via TCP
- Envia `ELECTION_ACK` com o nome do Master escolhido
- Master verifica se o Worker escolheu corretamente este próprio Master
- Se correto: responde com `STATUS: ACCEPTED`
- Se incorreto: responde com `STATUS: REJECTED` e fecha a conexão

### Por que eleição determinística?

Garantia de que todos os Workers novos convergem para o mesmo Master, evitando balanceamento acidental entre Masters. A carga nos Masters é controlada apenas pela negociação M2M (Sprint 3).

### Fluxo

```
Worker          Rede UDP        MASTER_1     MASTER_2
  |── DISCOVERY broadcast ────►|──────────►|
  |◄──────────────────── DISCOVERY_REPLY ──|
  |◄── DISCOVERY_REPLY ────────|
  |  (elege MASTER_1 por ser menor)
  |── ELECTION_ACK TCP ────────►|
  |◄── ELECTION_ACK:ACCEPTED ──|
  |── WORKER:ALIVE ─────────── ►|
```

---

## Sprint 3 — Negociação Master-to-Master

**Objetivo:** Masters saturados pedem workers emprestados a Masters vizinhos.
O sistema se auto-regula: workers são devolvidos quando a carga normaliza.

### O que foi implementado

**Detecção de saturação:**
- `pending > LOAD_THRESHOLD (5)` → Master A pede ajuda a cada vizinho em `NEIGHBOR_MASTERS`
- Flag `help_request_in_progress` evita pedidos duplicados simultâneos

**Negociação M2M:**
- Master A envia `request_help` com carga atual e quantidade de workers necessários
- Master B verifica disponibilidade de workers locais
- Se disponível: responde `response_accepted` e envia `command_redirect` ao worker selecionado
- Se indisponível: responde `response_rejected` com motivo

**Redirecionamento do Worker:**
- Worker recebe `command_redirect` com endereço do novo Master (A) e do original (B)
- Worker fecha conexão com B, conecta em A
- Worker envia `register_temporary_worker` a A com metadados do Master original

**Liberação:**
- `pending <= RELEASE_THRESHOLD (3)` → Master A envia `command_release` ao worker emprestado
- Worker reconecta ao Master original (B) com apresentação normal `WORKER:ALIVE`
- Master A notifica B via `notify_worker_returned`

**Correção crítica (aplicada em 2026-06-10):**
Após receber `STATUS: OK/NOK` e enviar `ACK`, o Master chama imediatamente `dispatch_next_task`.
Sem isso, workers ficavam ociosos 30s entre tarefas (aguardando o próximo heartbeat),
impedindo que a fila drenasse e o `RELEASE_THRESHOLD` nunca era atingido.

### Invariantes do protocolo M2M

1. `request_id` é UUID único por sessão de empréstimo — correlaciona todos os 7 tipos de mensagem
2. Worker guarda `original_master_name/uuid/host/port` para poder retornar corretamente
3. Master rastreia workers emprestados em `borrowed_outgoing_workers` para aceitar `notify_worker_returned`
4. Worker temporário é marcado como `role: temporary` — nunca é eleito para novos empréstimos

### Linha do tempo do empréstimo

```
MA satura → request_help → response_accepted → command_redirect →
Worker re-conecta em MA → register_temporary_worker → 
MA processa carga → carga cai → command_release →
Worker reconecta em MB → notify_worker_returned → 
MA remove worker de borrowed_outgoing_workers
```

---

## Sprint 4 — Monitor de Métricas via TLS TCP

**Objetivo:** Coletar métricas do sistema e da farm a cada 10 segundos e enviá-las ao supervisor externo `nuted-ia.dev:443` via TLS TCP (fire-and-forget).

### O que foi implementado

**Novo arquivo `monitor.py`:**
- Thread daemon iniciada junto com o Master
- Coleta métricas do SO com `psutil` (CPU%, memória, disco, load average)
- Monta payload JSON completo conforme schema `sprint4-monitor`
- Conecta ao supervisor via TLS, envia JSON + `\n`, fecha sem receber resposta
- Captura todas as exceções silenciosamente — falha de envio nunca para o Master

**Métricas coletadas:**

| Categoria     | Campo                | Fonte                          |
|---------------|----------------------|--------------------------------|
| Sistema       | `uptime_seconds`     | `time.time() - start_time`     |
| Sistema       | `load_average_1m/5m` | `os.getloadavg()` (0.0 no Win) |
| Sistema       | `cpu.usage_percent`  | `psutil.cpu_percent()`         |
| Sistema       | `cpu.count_logical`  | `psutil.cpu_count(logical=True)`|
| Sistema       | `memory.total_mb`    | `psutil.virtual_memory().total`|
| Sistema       | `disk.total_gb`      | `shutil.disk_usage(".")`       |
| Farm          | `workers.*`          | `get_farm_state()["workers"]`  |
| Farm          | `tasks.*`            | `get_farm_state()["tasks"]`    |
| Farm          | `config_thresholds`  | `LOAD_THRESHOLD`, `RELEASE_THRESHOLD` |
| Farm          | `neighbors`          | `s4_neighbor_status` (M2M)     |

**Novos globals em `master.py` (prefixo `s4_`):**
- `s4_tasks_running` — set com UUIDs de workers atualmente processando tarefas
- `s4_counters` — dict `{"tasks_ok": N, "tasks_nok": N, "workers_dropped": N}`
- `s4_enqueue_times` — dict `{task_id: timestamp}` para calcular `oldest_task_age_s`
- `s4_neighbor_status` — dict `{host:port: {"ok": bool, "ts": float}}`

**Novos campos em `config.py`:**
```python
SUPERVISOR_HOST     # default: "nuted-ia.dev"
SUPERVISOR_PORT     # default: 443
SUPERVISOR_SNI      # default: "nuted-ia.dev"
SUPERVISOR_INTERVAL # default: 10.0 segundos
FARM_ID             # default: MASTER_NAME
FARM_HOSTNAME       # default: socket.gethostname()
```

**Dependência externa adicionada:**
- `psutil>=5.9.0` (primeira dep externa do projeto) — declarada em `requirements.txt`
- Fallback automático se `psutil` não estiver instalado: todos os campos de CPU/memória retornam 0.0

### Decisões de design

**Padrão callback para evitar import circular:**
`master.py` passa a função `get_farm_state` como parâmetro para `monitor.monitor_loop`.
`monitor.py` não importa `master.py` — recebe o snapshot como argumento.

**`except Exception` no loop:**
Captura falhas de rede/TLS silenciosamente. `KeyboardInterrupt` não é capturado, permitindo que o Ctrl+C encerre o processo normalmente.

**`os.getloadavg()` falha no Windows:**
`try/except AttributeError` retorna `(0.0, 0.0)` — o atributo não existe no Windows.

**Dict-based counters:**
`s4_counters = {"tasks_ok": 0, ...}` evita declarações `global` em funções — mutação do dict não requer redeclaração.

### Fluxo do monitor

```
Master inicia
    └── Thread daemon monitor_loop(get_farm_state)
            └── loop infinito a cada SUPERVISOR_INTERVAL (10s)
                    ├── farm_state = get_farm_state()
                    ├── report = build_performance_report(farm_state)
                    ├── TLS connect nuted-ia.dev:443
                    ├── sendall(json + "\n")
                    ├── close (sem recv)
                    └── except Exception → log + continua
```

---

## Resumo Comparativo das Sprints

| Feature                            | Sprint 1 | Sprint 2 | Sprint 2.1 | Sprint 3 | Sprint 4 |
|------------------------------------|:--------:|:--------:|:----------:|:--------:|:--------:|
| Heartbeat TCP                      | ✅       | ✅       | ✅         | ✅       | ✅       |
| Fila de tarefas                    |          | ✅       | ✅         | ✅       | ✅       |
| Ciclo QUERY / STATUS / ACK         |          | ✅       | ✅         | ✅       | ✅       |
| Descoberta UDP broadcast           |          |          | ✅         | ✅       | ✅       |
| Eleição determinística             |          |          | ✅         | ✅       | ✅       |
| Handshake ELECTION_ACK             |          |          | ✅         | ✅       | ✅       |
| Negociação M2M (request_help)      |          |          |            | ✅       | ✅       |
| Redirecionamento de worker         |          |          |            | ✅       | ✅       |
| Liberação automática (histerese)   |          |          |            | ✅       | ✅       |
| notify_worker_returned             |          |          |            | ✅       | ✅       |
| Despacho imediato pós-ACK          |          |          |            | ✅       | ✅       |
| Monitor de métricas (TLS TCP)      |          |          |            |          | ✅       |
| Payload JSON schema sprint4-monitor|          |          |            |          | ✅       |
| psutil (CPU, memória, disco)       |          |          |            |          | ✅       |
| Telemetria ao supervisor externo   |          |          |            |          | ✅       |
