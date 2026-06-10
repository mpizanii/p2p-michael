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

## Resumo Comparativo das Sprints

| Feature                            | Sprint 1 | Sprint 2 | Sprint 2.1 | Sprint 3 |
|------------------------------------|:--------:|:--------:|:----------:|:--------:|
| Heartbeat TCP                      | ✅       | ✅       | ✅         | ✅       |
| Fila de tarefas                    |          | ✅       | ✅         | ✅       |
| Ciclo QUERY / STATUS / ACK         |          | ✅       | ✅         | ✅       |
| Descoberta UDP broadcast           |          |          | ✅         | ✅       |
| Eleição determinística             |          |          | ✅         | ✅       |
| Handshake ELECTION_ACK             |          |          | ✅         | ✅       |
| Negociação M2M (request_help)      |          |          |            | ✅       |
| Redirecionamento de worker         |          |          |            | ✅       |
| Liberação automática (histerese)   |          |          |            | ✅       |
| notify_worker_returned             |          |          |            | ✅       |
| Despacho imediato pós-ACK          |          |          |            | ✅       |
