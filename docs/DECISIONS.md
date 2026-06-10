# Registros de Decisões Arquiteturais (ADRs)

Cada ADR documenta uma decisão técnica significativa: o contexto, as alternativas consideradas,
a escolha feita e as consequências.

---

## ADR-001: Sem dependências externas

**Status:** Aceito

**Contexto:** O projeto é acadêmico e precisa rodar em qualquer máquina com Python 3.x instalado,
sem necessidade de `pip install`.

**Decisão:** Usar exclusivamente a biblioteca padrão do Python (`socket`, `threading`, `json`, `uuid`, `os`, `time`).

**Consequências:**
- Positivo: zero configuração de ambiente; portável.
- Negativo: sem serialização Protobuf/MessagePack, sem async/await nativo, sem framework de rede.
- Negativo: implementamos manualmente o framing de mensagens (newline-delimited JSON).

---

## ADR-002: Newline-delimited JSON como protocolo de mensagens

**Status:** Aceito

**Contexto:** TCP é um protocolo de stream sem fronteiras de mensagem. Precisamos delimitar onde
cada mensagem JSON termina.

**Decisão:** Usar `json.dumps(msg) + "\n"` para envio. Receptor lê bytes até encontrar `\n`,
depois faz `json.loads`.

**Alternativas rejeitadas:**
- Length-prefix: mais complexo de implementar manualmente.
- `recv` com tamanho fixo: mensagens têm tamanho variável.

**Consequências:**
- Simples de debugar (mensagens legíveis no Wireshark/netcat).
- Mensagens não podem conter `\n` internos (não é problema com JSON sem formatação).

---

## ADR-003: Thread por conexão

**Status:** Aceito

**Contexto:** Múltiplos workers se conectam simultaneamente ao Master. Precisamos atender
cada um em paralelo.

**Decisão:** Para cada conexão aceita em `accept_loop`, criar uma `threading.Thread(target=handle_worker, daemon=True)`.

**Alternativas rejeitadas:**
- `asyncio`: mais complexo, e o constraint de stdlib não ajudaria (asyncio existe, mas mistura com threads é delicada).
- Pool fixo de threads: limita arbitrariamente o número de workers.

**Consequências:**
- Escalabilidade limitada pelo GIL e custo de threads do SO, mas aceitável para escala acadêmica.
- Daemon threads garantem que o processo Master termina mesmo com workers conectados.

---

## ADR-004: Eleição por menor nome lexicográfico

**Status:** Aceito

**Contexto:** Quando múltiplos Masters respondem ao broadcast UDP, o Worker precisa escolher
um de forma determinística, sem comunicação adicional entre Masters.

**Decisão:** Ordenar Masters respondentes por `MASTER_NAME` e escolher o lexicograficamente menor.

**Alternativas rejeitadas:**
- Menor UUID: UUIDs são aleatórios; o administrador não controla a eleição.
- Menor carga: exigiria os Masters reportarem carga no reply UDP, acoplando descoberta com balanceamento.
- Round-robin: não é determinístico; Workers diferentes escolheriam Masters diferentes aleatoriamente.

**Consequências:**
- Positivo: administrador controla qual Master é o "primário" pelo nome (`MASTER_1` < `MASTER_2`).
- Positivo: sem comunicação adicional entre Masters para resolver a eleição.
- Negativo: todos os Workers novos vão para o mesmo Master, que precisa redistribuir via Sprint 3.

---

## ADR-005: Histerese com dois limiares (LOAD_THRESHOLD e RELEASE_THRESHOLD)

**Status:** Aceito

**Contexto:** Usar um único limiar para saturação e liberação causaria *flapping*: o sistema pediria
ajuda, a carga cairia, liberaria o worker, a carga subiria, pediria ajuda novamente, num loop.

**Decisão:** `LOAD_THRESHOLD=5` (acima disso → pede ajuda) e `RELEASE_THRESHOLD=3`
(abaixo disso → libera workers emprestados). Zona neutra entre 3 e 5.

**Consequências:**
- Positivo: estabilidade — o sistema não oscila rapidamente.
- Parâmetros configuráveis via `os.getenv("RELEASE_THRESHOLD", "3")`.

---

## ADR-006: Flag help_request_in_progress para evitar pedidos duplicados

**Status:** Aceito

**Contexto:** `load_generator` roda em loop com 1 iteração por segundo. Sem controle,
acionaria `ask_for_help` múltiplas vezes enquanto o pedido ainda está em andamento.

**Decisão:** Flag global `help_request_in_progress` protegida por `help_request_lock`.
`ask_for_help` roda em thread separada; ao terminar, chama `finish_help_request()`.

**Consequências:**
- No máximo uma negociação M2M ativa por vez.
- Se o vizinho não responde dentro de `SPRINT3_HELP_TIMEOUT`, a flag é liberada pela thread de ajuda.

---

## ADR-007: request_id UUID para correlação M2M

**Status:** Aceito

**Contexto:** A negociação M2M envolve 7 tipos de mensagem diferentes, possivelmente com
múltiplos workers sendo emprestados em paralelo. Precisamos correlacionar request e response,
e o `notify_worker_returned` precisa saber a qual sessão de empréstimo pertence.

**Decisão:** Cada sessão de `ask_for_help` gera um `request_id = str(uuid.uuid4())`.
Esse ID viaja em todas as mensagens da sessão: request_help, response_accepted/rejected,
command_redirect, register_temporary_worker, command_release, notify_worker_returned.

**Consequências:**
- Idempotência: mensagens retransmitidas com o mesmo ID podem ser detectadas.
- Rastreabilidade: logs mostram qual worker pertence a qual sessão de empréstimo.

---

## ADR-008: Worker guarda ORIGINAL_MASTER_NAME para reconexão correta

**Status:** Aceito — correção aplicada em 2026-06-10

**Contexto:** Quando um worker emprestado recebe `command_release`, precisa saber para qual Master
retornar. O host e porta são suficientes para a conexão TCP, mas o nome é necessário para o
handshake ELECTION_ACK — o Master verifica se o Worker escolheu `SELECTED_MASTER == MASTER_NAME`.

**Decisão:** Worker mantém global `original_master_name`. Preenchido em dois pontos:
1. Após eleição bem-sucedida em `run()`: `original_master_name = selected_master["name"]`
2. Ao receber `command_redirect`: `original_master_name = payload.get("original_master_name")`

Incluído em `register_temporary_worker` como `ORIGINAL_MASTER_NAME` para que o Master emprestador
também saiba o nome do dono original.

**Consequências:**
- Workers que não usam descoberta UDP (conexão direta) nunca precisam deste campo.
- Workers que foram redirecionados mais de uma vez mantêm o nome do Master *original* (não intermediário).

---

## ADR-009: Despacho imediato de tarefa após ACK

**Status:** Aceito — correção crítica aplicada em 2026-06-10

**Contexto:** Na implementação original, o Master só enviava uma nova QUERY após receber um
heartbeat periódico (30s). Com `TASK_DURATION=3s` e `REQUEST_INTERVAL=1s`, a fila crescia
ilimitadamente — `RELEASE_THRESHOLD` nunca era atingido.

**Decisão:** Após enviar `STATUS: ACK`, Master chama `dispatch_next_task` imediatamente.
Guard adicionado: verifica `get_worker_connection(worker_uuid) is not None` para não
consumir uma tarefa da fila se o worker já foi liberado por `release_temporary_workers_if_needed`.

**Consequências:**
- Worker processa 1 tarefa a cada ~3s (tempo de execução) em vez de 1 a cada 30s.
- Com 2+ workers, taxa de drenagem ≥ taxa de geração → fila se estabiliza.
- RELEASE_THRESHOLD pode ser atingido naturalmente durante a demonstração.
