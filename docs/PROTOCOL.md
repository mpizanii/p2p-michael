# Protocolo de Comunicação

Todas as mensagens trafegam como **JSON de linha única** seguido de `\n` (newline-delimited JSON).
Encoding: UTF-8. Transport: TCP (todas as mensagens de controle) e UDP (apenas discovery).

---

## Convenções de Formato

### Mensagens legadas (Sprints 1 e 2)

Campos em `UPPER_CASE` diretamente no objeto raiz:

```json
{ "WORKER": "ALIVE", "WORKER_UUID": "<uuid>" }
```

### Mensagens Sprint 3 (M2M e redirect)

Envelope padronizado com três campos obrigatórios:

```json
{
  "type": "<tipo>",
  "request_id": "<uuid>",
  "payload": { ... }
}
```

O `request_id` correlaciona request/response e evita duplicatas.

---

## Sprint 1 — Heartbeat

### Worker → Master (apresentação)
```json
{ "WORKER": "ALIVE", "WORKER_UUID": "abc-123" }
```

### Master → Worker (resposta de heartbeat)
```json
{ "SERVER_UUID": "xyz-456", "TASK": "HEARTBEAT", "RESPONSE": "ALIVE" }
```

### Worker → Master (heartbeat periódico a cada 30s)
```json
{ "TASK": "HEARTBEAT", "WORKER_UUID": "abc-123", "SERVER_UUID": "xyz-456" }
```

---

## Sprint 2 — Ciclo Completo de Tarefas

```mermaid
sequenceDiagram
    participant W as Worker
    participant M as Master

    W->>M: {"WORKER":"ALIVE","WORKER_UUID":"abc"}
    M->>W: {"TASK":"QUERY","USER":"User1","TASK_ID":"TASK-0001","FORCE_NOK":false,"SERVER_UUID":"xyz"}
    Note over W: executa simulação (3s)
    W->>M: {"TASK":"QUERY","STATUS":"OK","TASK_ID":"TASK-0001","WORKER_UUID":"abc"}
    M->>W: {"STATUS":"ACK","WORKER_UUID":"abc","TASK_ID":"TASK-0001"}
    M->>W: próxima QUERY (ou NO_TASK)
```

### Master → Worker (despacho de tarefa)
```json
{
  "TASK": "QUERY",
  "USER": "User1",
  "TASK_ID": "TASK-0001",
  "FORCE_NOK": false,
  "SERVER_UUID": "xyz-456"
}
```

### Worker → Master (relatório de status)
```json
{
  "TASK": "QUERY",
  "STATUS": "OK",
  "TASK_ID": "TASK-0001",
  "WORKER_UUID": "abc-123"
}
```
`STATUS` pode ser `"OK"` (sucesso) ou `"NOK"` (falha simulada; acontece quando `FORCE_NOK=true`).

### Master → Worker (confirmação)
```json
{ "STATUS": "ACK", "WORKER_UUID": "abc-123", "TASK_ID": "TASK-0001" }
```

### Master → Worker (sem tarefa disponível)
```json
{ "TASK": "NO_TASK", "SERVER_UUID": "xyz-456" }
```

---

## Sprint 2.1 — Descoberta UDP e Eleição

```mermaid
sequenceDiagram
    participant W as Worker
    participant MA as Master A (menor nome)
    participant MB as Master B

    W->>+Rede: UDP broadcast {"TYPE":"DISCOVERY","WORKER_UUID":"w1"} → 255.255.255.255
    MA-->>W: UDP unicast {"TYPE":"DISCOVERY_REPLY","MASTER_NAME":"MASTER_1","MASTER_IP":"...","MASTER_PORT":5000,...}
    MB-->>W: UDP unicast {"TYPE":"DISCOVERY_REPLY","MASTER_NAME":"MASTER_2",...}
    Note over W: eleição: menor nome lexicográfico → MASTER_1
    W->>MA: TCP {"TYPE":"ELECTION_ACK","WORKER_UUID":"w1","SELECTED_MASTER":"MASTER_1"}
    MA->>W: TCP {"TYPE":"ELECTION_ACK","STATUS":"ACCEPTED","MASTER_NAME":"MASTER_1",...}
    Note over W: inicia fluxo normal (WORKER ALIVE)
```

### Worker → Masters (broadcast UDP)
```json
{ "TYPE": "DISCOVERY", "WORKER_UUID": "abc-123" }
```

### Master → Worker (resposta unicast UDP)
```json
{
  "TYPE": "DISCOVERY_REPLY",
  "MASTER_NAME": "MASTER_1",
  "MASTER_IP": "127.0.0.1",
  "MASTER_PORT": 5000,
  "STATUS": "AVAILABLE",
  "SERVER_UUID": "xyz-456"
}
```

### Worker → Master eleito (TCP)
```json
{
  "TYPE": "ELECTION_ACK",
  "WORKER_UUID": "abc-123",
  "SELECTED_MASTER": "MASTER_1"
}
```

### Master → Worker (handshake aceito)
```json
{
  "TYPE": "ELECTION_ACK",
  "STATUS": "ACCEPTED",
  "MASTER_NAME": "MASTER_1",
  "MASTER_IP": "127.0.0.1",
  "MASTER_PORT": 5000,
  "SERVER_UUID": "xyz-456",
  "WORKER_UUID": "abc-123"
}
```

**Critério de eleição:** menor nome lexicográfico entre os Masters que responderam ao broadcast dentro de `DISCOVERY_TIMEOUT` (padrão 3s).

---

## Sprint 3 — Negociação Master-to-Master

### Fluxo Completo de Empréstimo e Devolução

```mermaid
sequenceDiagram
    participant MA as Master A (saturado)
    participant MB as Master B (vizinho)
    participant W as Worker (emprestado)

    Note over MA: pending > LOAD_THRESHOLD (5)
    MA->>MB: TCP {type:"request_help", request_id:"R1", payload:{master_uuid, master_name, master_host, master_port, workers_needed, current_load}}
    MB->>MA: {type:"response_accepted", request_id:"R1", payload:{workers_offered:1,...}}
    MB->>W: {type:"command_redirect", request_id:"R1", payload:{new_master_host, new_master_port, original_master_host, original_master_port,...}}
    Note over W: fecha conexão com MB, conecta em MA
    W->>MA: {type:"register_temporary_worker", WORKER_UUID, ORIGINAL_MASTER_UUID, ORIGINAL_MASTER_NAME, ORIGINAL_MASTER_HOST, ORIGINAL_MASTER_PORT, ...}
    Note over MA: worker processa tarefas normalmente

    Note over MA: pending <= RELEASE_THRESHOLD (3)
    MA->>W: {type:"command_release", request_id:"R1", payload:{return_to_master_host, return_to_master_port,...}}
    Note over W: fecha conexão com MA, reconecta em MB
    W->>MB: {WORKER:"ALIVE", WORKER_UUID, SERVER_UUID:MB_uuid}
    MA->>MB: {type:"notify_worker_returned", request_id:"R1", payload:{worker_uuid,...}}
```

### Master A → Master B: `request_help`
```json
{
  "type": "request_help",
  "request_id": "R1",
  "payload": {
    "master_uuid": "uuid-A",
    "master_name": "MASTER_1",
    "master_host": "127.0.0.1",
    "master_port": 5000,
    "current_load": 7,
    "saturation_threshold": 5,
    "release_threshold": 3,
    "workers_needed": 2,
    "local_workers": 3
  }
}
```

### Master B → Master A: `response_accepted`
```json
{
  "type": "response_accepted",
  "request_id": "R1",
  "payload": {
    "master_uuid": "uuid-B",
    "master_name": "MASTER_2",
    "workers_offered": 1,
    "worker_details": [{"worker_uuid": "w1"}]
  }
}
```

### Master B → Master A: `response_rejected`
```json
{
  "type": "response_rejected",
  "request_id": "R1",
  "payload": {
    "master_uuid": "uuid-B",
    "master_name": "MASTER_2",
    "reason": "no_local_workers_available"
  }
}
```

### Master B → Worker: `command_redirect`
```json
{
  "type": "command_redirect",
  "request_id": "R1",
  "payload": {
    "worker_uuid": "w1",
    "new_master_uuid": "uuid-A",
    "new_master_name": "MASTER_1",
    "new_master_host": "127.0.0.1",
    "new_master_port": 5000,
    "original_master_uuid": "uuid-B",
    "original_master_name": "MASTER_2",
    "original_master_host": "127.0.0.1",
    "original_master_port": 5001,
    "request_id": "R1"
  }
}
```

### Worker → Master A: `register_temporary_worker`
```json
{
  "type": "register_temporary_worker",
  "WORKER_UUID": "w1",
  "ORIGINAL_MASTER_UUID": "uuid-B",
  "ORIGINAL_MASTER_NAME": "MASTER_2",
  "ORIGINAL_MASTER_HOST": "127.0.0.1",
  "ORIGINAL_MASTER_PORT": 5001,
  "CURRENT_MASTER_HOST": "127.0.0.1",
  "CURRENT_MASTER_PORT": 5000,
  "SERVER_UUID": "uuid-B"
}
```

### Master A → Worker: `command_release`
```json
{
  "type": "command_release",
  "request_id": "R1",
  "payload": {
    "return_to_master_uuid": "uuid-B",
    "return_to_master_name": "MASTER_2",
    "return_to_master_host": "127.0.0.1",
    "return_to_master_port": 5001,
    "worker_uuid": "w1",
    "borrowed_master_uuid": "uuid-A",
    "borrowed_master_name": "MASTER_1",
    "borrowed_master_host": "127.0.0.1",
    "borrowed_master_port": 5000
  }
}
```

### Master A → Master B: `notify_worker_returned`
```json
{
  "type": "notify_worker_returned",
  "request_id": "R1",
  "payload": {
    "worker_uuid": "w1",
    "owner_master_uuid": "uuid-B",
    "owner_master_name": "MASTER_2",
    "borrowed_master_uuid": "uuid-A",
    "borrowed_master_name": "MASTER_1",
    "borrowed_master_host": "127.0.0.1",
    "borrowed_master_port": 5000
  }
}
```

---

## Sumário de Todos os Tipos de Mensagem

| Tipo                       | Protocolo | Direção          | Sprint |
|----------------------------|-----------|------------------|--------|
| `WORKER: ALIVE`            | TCP       | Worker → Master  | 1      |
| `TASK: HEARTBEAT` (resposta)| TCP      | Master → Worker  | 1      |
| `TASK: HEARTBEAT` (periódico)| TCP     | Worker → Master  | 1      |
| `TYPE: DISCOVERY`          | UDP       | Worker → Masters | 2.1    |
| `TYPE: DISCOVERY_REPLY`    | UDP       | Master → Worker  | 2.1    |
| `TYPE: ELECTION_ACK` (req) | TCP       | Worker → Master  | 2.1    |
| `TYPE: ELECTION_ACK` (resp)| TCP       | Master → Worker  | 2.1    |
| `TASK: QUERY`              | TCP       | Master → Worker  | 2      |
| `STATUS: OK/NOK`           | TCP       | Worker → Master  | 2      |
| `STATUS: ACK`              | TCP       | Master → Worker  | 2      |
| `TASK: NO_TASK`            | TCP       | Master → Worker  | 2      |
| `request_help`             | TCP       | Master → Master  | 3      |
| `response_accepted`        | TCP       | Master → Master  | 3      |
| `response_rejected`        | TCP       | Master → Master  | 3      |
| `command_redirect`         | TCP       | Master → Worker  | 3      |
| `register_temporary_worker`| TCP       | Worker → Master  | 3      |
| `command_release`          | TCP       | Master → Worker  | 3      |
| `notify_worker_returned`   | TCP       | Master → Master  | 3      |
