# Casos de Teste e Resultados

## Como Executar

```powershell
# Na raiz do projeto
python -m pytest test_sprint3.py -v
# ou
python test_sprint3.py
```

**Resultado:** 60 testes, 0 falhas, tempo ≈ 0.045s (todos unitários, sem I/O de rede).

---

## Estrutura da Suíte

| Classe de Teste                    | Foco                                          | Testes |
|------------------------------------|-----------------------------------------------|--------|
| `TestProtocolMessageBuilding`      | Formato do envelope Sprint 3                  | 4      |
| `TestProtocolValidation`           | Detecção de mensagens válidas/inválidas        | 6      |
| `TestWorkerElection`               | Algoritmo de eleição lexicográfica             | 5      |
| `TestWorkerRegistrationMessages`   | Mensagens de apresentação e registro           | 7      |
| `TestMasterWorkerSession`          | CRUD de sessões de worker                      | 7      |
| `TestDispatchTarefas`              | Despacho FIFO, NO_TASK, guard pós-release      | 8      |
| `TestSprint3Envelopes`             | Todos os 7 tipos de mensagem M2M               | 12     |
| `TestSaturacaoEAjuda`              | Limiares de saturação e sem pedidos duplicados | 8      |
| `TestCompilaçãoSintaxe`            | Sintaxe Python válida nos 3 arquivos           | 3      |

---

## Casos de Teste por Classe

### TestProtocolMessageBuilding

| Caso                                      | Descrição                                              | Resultado |
|-------------------------------------------|--------------------------------------------------------|-----------|
| `test_build_protocol_message_basic`       | Verifica campos `type`, `request_id`, `payload`        | ✅ PASS    |
| `test_build_protocol_message_with_request_id` | request_id preservado quando fornecido           | ✅ PASS    |
| `test_request_id_generated_when_none`     | UUID gerado automaticamente quando request_id=None     | ✅ PASS    |
| `test_payload_is_dict`                    | payload sempre é dict                                  | ✅ PASS    |

### TestProtocolValidation

| Caso                                      | Descrição                                              | Resultado |
|-------------------------------------------|--------------------------------------------------------|-----------|
| `test_valid_heartbeat_worker_alive`       | `WORKER:ALIVE` com WORKER_UUID válido                  | ✅ PASS    |
| `test_valid_heartbeat_task_heartbeat`     | `TASK:HEARTBEAT` com SERVER_UUID válido                | ✅ PASS    |
| `test_invalid_heartbeat_missing_uuid`     | Heartbeat sem UUID rejeitado                           | ✅ PASS    |
| `test_valid_status_report`               | STATUS:OK com TASK_ID e WORKER_UUID                    | ✅ PASS    |
| `test_invalid_status_report_bad_status`  | STATUS diferente de OK/NOK rejeitado                   | ✅ PASS    |
| `test_invalid_status_report_missing_fields` | Status sem campos obrigatórios rejeitado            | ✅ PASS    |

### TestWorkerElection

| Caso                                      | Descrição                                              | Resultado |
|-------------------------------------------|--------------------------------------------------------|-----------|
| `test_election_selects_lexicographically_smallest` | MASTER_1 < MASTER_2 — MASTER_1 eleito        | ✅ PASS    |
| `test_election_single_master`             | Um único master sempre vence                           | ✅ PASS    |
| `test_election_alphabetical_ordering`     | Ordem: A < B < Z                                       | ✅ PASS    |
| `test_election_same_name_prefix`          | MASTER_1 < MASTER_10 (lexicográfico, não numérico)     | ✅ PASS    |
| `test_election_empty_list`               | Lista vazia retorna None                               | ✅ PASS    |

### TestWorkerRegistrationMessages

| Caso                                      | Descrição                                              | Resultado |
|-------------------------------------------|--------------------------------------------------------|-----------|
| `test_worker_alive_message_format`        | `WORKER:ALIVE` com WORKER_UUID                         | ✅ PASS    |
| `test_worker_alive_borrowed_includes_server_uuid` | Worker emprestado inclui SERVER_UUID diferente | ✅ PASS    |
| `test_temporary_registration_has_required_fields` | register_temporary_worker tem campos obrigatórios | ✅ PASS   |
| `test_temporary_registration_includes_original_master_name` | ORIGINAL_MASTER_NAME presente       | ✅ PASS    |
| `test_temporary_registration_hosts_and_ports` | Endereços do Master original e atual               | ✅ PASS    |
| `test_election_ack_format`               | TYPE:ELECTION_ACK com SELECTED_MASTER                  | ✅ PASS    |
| `test_election_ack_response_format`      | Resposta com STATUS:ACCEPTED                           | ✅ PASS    |

### TestMasterWorkerSession

| Caso                                      | Descrição                                              | Resultado |
|-------------------------------------------|--------------------------------------------------------|-----------|
| `test_store_and_get_worker`               | Armazenar e recuperar conexão por UUID                 | ✅ PASS    |
| `test_remove_worker`                      | Remover worker libera conexão e metadata               | ✅ PASS    |
| `test_list_local_workers`                 | Filtra apenas workers com role=local                   | ✅ PASS    |
| `test_list_temporary_workers`             | Filtra apenas workers com role=temporary               | ✅ PASS    |
| `test_mark_worker_temporary`              | Metadata de empréstimo incluída                        | ✅ PASS    |
| `test_mark_worker_local`                  | role=local definido corretamente                       | ✅ PASS    |
| `test_get_nonexistent_worker_returns_none` | UUID inexistente retorna None                         | ✅ PASS    |

### TestDispatchTarefas

| Caso                                      | Descrição                                              | Resultado |
|-------------------------------------------|--------------------------------------------------------|-----------|
| `test_enqueue_dequeue_task`               | FIFO: first in, first out                              | ✅ PASS    |
| `test_dequeue_empty_returns_none`         | Fila vazia retorna None                                | ✅ PASS    |
| `test_dispatch_sends_query_when_task_available` | QUERY enviada quando há tarefa                   | ✅ PASS    |
| `test_dispatch_sends_no_task_when_empty`  | NO_TASK enviado quando fila vazia                      | ✅ PASS    |
| `test_dispatch_multiple_tasks_fifo`       | Ordem FIFO preservada                                  | ✅ PASS    |
| `test_dispatch_force_nok_propagated`      | FORCE_NOK repassado ao worker                          | ✅ PASS    |
| `test_no_dispatch_if_worker_released`     | Guard: worker liberado → tarefa não consumida          | ✅ PASS    |
| `test_dispatch_after_ack_pattern`         | Padrão ACK → release_check → dispatch                  | ✅ PASS    |

### TestSprint3Envelopes

| Caso                                      | Descrição                                              | Resultado |
|-------------------------------------------|--------------------------------------------------------|-----------|
| `test_request_help_envelope`              | Campos master_uuid, workers_needed, current_load       | ✅ PASS    |
| `test_response_accepted_envelope`         | workers_offered presente                               | ✅ PASS    |
| `test_response_rejected_envelope`         | reason presente                                        | ✅ PASS    |
| `test_command_redirect_envelope`          | new_master_* e original_master_* presentes             | ✅ PASS    |
| `test_command_redirect_has_request_id`    | request_id no payload para correlação                  | ✅ PASS    |
| `test_register_temporary_worker_envelope` | Todos os campos de origem e destino                    | ✅ PASS    |
| `test_command_release_envelope`           | return_to_master_* e borrowed_master_* presentes       | ✅ PASS    |
| `test_notify_worker_returned_envelope`    | worker_uuid e ambos os masters identificados           | ✅ PASS    |
| `test_request_id_correlation`             | Mesmo request_id em request e response                 | ✅ PASS    |
| `test_envelope_type_extraction`           | `protocol_message_type` extrai campo `type`            | ✅ PASS    |
| `test_envelope_payload_extraction`        | `protocol_payload` extrai campo `payload`              | ✅ PASS    |
| `test_envelope_request_id_extraction`     | `protocol_request_id` extrai campo `request_id`        | ✅ PASS    |

### TestSaturacaoEAjuda

| Caso                                      | Descrição                                              | Resultado |
|-------------------------------------------|--------------------------------------------------------|-----------|
| `test_saturation_threshold`               | pending > LOAD_THRESHOLD (5) dispara pedido de ajuda   | ✅ PASS    |
| `test_no_saturation_below_threshold`      | pending ≤ 5 não dispara pedido                         | ✅ PASS    |
| `test_release_threshold`                  | pending ≤ RELEASE_THRESHOLD (3) libera workers         | ✅ PASS    |
| `test_no_release_above_threshold`         | pending > 3 não libera workers                         | ✅ PASS    |
| `test_hysteresis_neutral_zone`            | 3 < pending ≤ 5: nenhuma ação                          | ✅ PASS    |
| `test_no_duplicate_help_requests`         | help_request_in_progress bloqueia segundo pedido       | ✅ PASS    |
| `test_help_request_released_after_finish` | finish_help_request() libera a flag                    | ✅ PASS    |
| `test_workers_needed_calculation`         | Cálculo: max(1, pending - LOAD_THRESHOLD)              | ✅ PASS    |

### TestCompilaçãoSintaxe

| Caso                                      | Descrição                                              | Resultado |
|-------------------------------------------|--------------------------------------------------------|-----------|
| `test_master_syntax`                      | `py_compile.compile("master.py")` sem erros            | ✅ PASS    |
| `test_worker_syntax`                      | `py_compile.compile("worker.py")` sem erros            | ✅ PASS    |
| `test_config_syntax`                      | `py_compile.compile("config.py")` sem erros            | ✅ PASS    |

---

## Cobertura por Requisito

| Requisito Sprint 3                              | Coberto por                                    |
|-------------------------------------------------|------------------------------------------------|
| Envelope `{type, request_id, payload}`          | TestProtocolMessageBuilding, TestSprint3Envelopes |
| request_help com carga e workers_needed         | TestSprint3Envelopes.test_request_help_envelope |
| response_accepted / response_rejected           | TestSprint3Envelopes                           |
| command_redirect com endereços completos        | TestSprint3Envelopes.test_command_redirect_*   |
| register_temporary_worker com ORIGINAL_MASTER_NAME | TestWorkerRegistrationMessages.test_temporary_registration_includes_original_master_name |
| command_release com return_to_master            | TestSprint3Envelopes.test_command_release_envelope |
| notify_worker_returned                          | TestSprint3Envelopes.test_notify_worker_returned_envelope |
| Saturação em LOAD_THRESHOLD=5                   | TestSaturacaoEAjuda.test_saturation_threshold  |
| Liberação em RELEASE_THRESHOLD=3                | TestSaturacaoEAjuda.test_release_threshold     |
| Sem pedidos duplicados                          | TestSaturacaoEAjuda.test_no_duplicate_help_requests |
| Guard pós-release no dispatch                   | TestDispatchTarefas.test_no_dispatch_if_worker_released |
| Compilação sem erros                            | TestCompilaçãoSintaxe                          |
