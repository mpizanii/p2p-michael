# Casos de Teste e Resultados

## Como Executar

```powershell
# Testes Sprint 3
python -m pytest test_sprint3.py -v
# ou
python test_sprint3.py

# Testes Sprint 4
python -m pytest test_sprint4.py -v
# ou
python test_sprint4.py

# Todos de uma vez
python test_sprint3.py; python test_sprint4.py
```

**Sprint 3:** 60 testes, 0 falhas, tempo ≈ 0.045s.
**Sprint 4:** 39 testes, 0 falhas, tempo ≈ 0.07s.
**Total:** 99 testes unitários, todos sem I/O de rede real.

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

## Cobertura por Requisito — Sprint 3

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

---

## Suíte Sprint 4 (`test_sprint4.py`)

| Classe de Teste              | Foco                                              | Testes |
|------------------------------|---------------------------------------------------|--------|
| `TestPayloadSchema`          | Campos obrigatórios do payload JSON               | 10     |
| `TestPayloadValues`          | Valores: ISO-8601, UUID, payload_version, role    | 7      |
| `TestFarmMetrics`            | workers_idle, oldest_task_age, borrowed_workers   | 7      |
| `TestSystemMetrics`          | Estrutura, fallback psutil, fallback load_average | 4      |
| `TestMonitorResilience`      | Loop continua após falha, TLS, sem recv           | 3      |
| `TestGetFarmState`           | Integração com master.py, s4_counters             | 5      |
| `TestSyntaxSprint4`          | py_compile para monitor.py, master.py, config.py  | 3      |

### TestPayloadSchema (10 testes)

| Caso | Descrição | Resultado |
|------|-----------|-----------|
| `test_top_level_fields_presentes` | `server_uuid`, `hostname`, `role`, `task`, `timestamp`, `message_id`, `payload_version`, `performance` | ✅ PASS |
| `test_performance_system_fields` | `uptime_seconds`, `load_average_1m/5m`, `cpu`, `memory`, `disk` | ✅ PASS |
| `test_performance_system_cpu_fields` | `usage_percent`, `count_logical`, `count_physical` | ✅ PASS |
| `test_performance_system_memory_fields` | `total_mb`, `available_mb`, `percent_used`, `memory_used` | ✅ PASS |
| `test_performance_system_disk_fields` | `total_gb`, `free_gb`, `percent_used` | ✅ PASS |
| `test_performance_farm_state_workers_fields` | 10 campos de workers | ✅ PASS |
| `test_performance_farm_state_tasks_fields` | 5 campos de tasks | ✅ PASS |
| `test_performance_config_thresholds_fields` | `max_task`, `warn_cpu_percent`, `warn_memory_percent`, `release_task` | ✅ PASS |
| `test_performance_neighbors_is_list` | `neighbors` é lista | ✅ PASS |
| `test_performance_neighbors_fields_quando_presente` | `server_uuid`, `status`, `last_heartbeat` | ✅ PASS |

### TestPayloadValues (7 testes)

| Caso | Descrição | Resultado |
|------|-----------|-----------|
| `test_timestamp_formato_iso8601` | Regex `YYYY-MM-DDTHH:MM:SSZ` | ✅ PASS |
| `test_message_id_e_uuid_valido` | `uuid.UUID(mid)` sem exceção | ✅ PASS |
| `test_message_id_unico_por_chamada` | Dois reports com IDs distintos | ✅ PASS |
| `test_payload_version` | Valor exato `"sprint4-monitor"` | ✅ PASS |
| `test_role_e_master` | `role == "master"` | ✅ PASS |
| `test_task_e_performance_report` | `task == "performance_report"` | ✅ PASS |
| `test_uptime_seconds_positivo` | `uptime_seconds >= 0` | ✅ PASS |

### TestFarmMetrics (7 testes)

| Caso | Descrição | Resultado |
|------|-----------|-----------|
| `test_workers_idle_calculado_corretamente` | total=5, util=3 → idle=2 | ✅ PASS |
| `test_workers_available_capacity_igual_idle` | `available_capacity == idle` | ✅ PASS |
| `test_workers_alive_igual_total_registered` | `alive == total_registered` | ✅ PASS |
| `test_oldest_task_age_zero_quando_fila_vazia` | `oldest_age=0` propagado | ✅ PASS |
| `test_oldest_task_age_positivo` | `oldest_age=312 > 0` | ✅ PASS |
| `test_borrowed_workers_direction_out` | `direction="out"` e `peer_uuid` | ✅ PASS |
| `test_borrowed_workers_direction_in` | `direction="in"` | ✅ PASS |

### TestSystemMetrics (4 testes)

| Caso | Descrição | Resultado |
|------|-----------|-----------|
| `test_collect_system_metrics_retorna_estrutura_completa` | uptime, cpu, memory, disk presentes | ✅ PASS |
| `test_load_average_fallback_sem_getloadavg` | No Windows retorna floats >= 0 | ✅ PASS |
| `test_collect_sem_psutil_retorna_zeros_cpu_mem` | `_PSUTIL=False` → cpu=0.0, mem=0 | ✅ PASS |
| `test_disk_metrics_sao_floats_nao_negativos` | total_gb, free_gb, percent >= 0 | ✅ PASS |

### TestMonitorResilience (3 testes)

| Caso | Descrição | Resultado |
|------|-----------|-----------|
| `test_send_failure_nao_propaga_no_loop` | OSError em `send_to_supervisor` → loop continua | ✅ PASS |
| `test_send_to_supervisor_usa_tls` | `ssl.create_default_context` chamado | ✅ PASS |
| `test_send_to_supervisor_nao_chama_recv` | `mock_tls.recv` nunca chamado | ✅ PASS |

### TestGetFarmState (5 testes)

| Caso | Descrição | Resultado |
|------|-----------|-----------|
| `test_get_farm_state_retorna_estrutura_obrigatoria` | start_time, workers, tasks, config_thresholds, neighbors | ✅ PASS |
| `test_get_farm_state_workers_campos_presentes` | 10 campos de workers | ✅ PASS |
| `test_s4_counters_tasks_ok_incrementa_via_status` | Incremento thread-safe via lock | ✅ PASS |
| `test_s4_tasks_running_set_add_discard` | add/discard com lock | ✅ PASS |
| `test_s4_enqueue_times_registra_e_remove` | enqueue_task → registra; dequeue_task → remove | ✅ PASS |

### TestSyntaxSprint4 (3 testes)

| Caso | Descrição | Resultado |
|------|-----------|-----------|
| `test_monitor_syntax` | `py_compile.compile("monitor.py")` | ✅ PASS |
| `test_master_syntax` | `py_compile.compile("master.py")` | ✅ PASS |
| `test_config_syntax` | `py_compile.compile("config.py")` | ✅ PASS |

---

## Cobertura por Requisito — Sprint 4

| Requisito Sprint 4                                  | Coberto por                                        |
|-----------------------------------------------------|----------------------------------------------------|
| Payload com todos os campos obrigatórios            | TestPayloadSchema (10 testes)                      |
| `message_id` UUID único por envio                   | TestPayloadValues.test_message_id_*                |
| `timestamp` em ISO-8601 UTC                         | TestPayloadValues.test_timestamp_formato_iso8601   |
| `payload_version = "sprint4-monitor"`               | TestPayloadValues.test_payload_version             |
| Métricas corretas de workers_idle                   | TestFarmMetrics.test_workers_idle_calculado_corretamente |
| `oldest_task_age_s` calculado desde enfileiramento  | TestFarmMetrics.test_oldest_task_age_*             |
| Fallback quando psutil não instalado                | TestSystemMetrics.test_collect_sem_psutil_*        |
| Fallback `os.getloadavg` (Windows)                  | TestSystemMetrics.test_load_average_fallback_*     |
| Loop não para com falha de envio                    | TestMonitorResilience.test_send_failure_*          |
| TLS obrigatório (`ssl.create_default_context`)      | TestMonitorResilience.test_send_to_supervisor_usa_tls |
| Fire-and-forget (sem recv)                          | TestMonitorResilience.test_send_to_supervisor_nao_chama_recv |
| `get_farm_state()` retorna snapshot completo        | TestGetFarmState (5 testes)                        |
| `s4_counters` incrementados no fluxo STATUS         | TestGetFarmState.test_s4_counters_tasks_ok_*       |
| `s4_enqueue_times` rastreia timestamps na fila      | TestGetFarmState.test_s4_enqueue_times_*           |
| Sintaxe válida em monitor.py, master.py, config.py  | TestSyntaxSprint4 (3 testes)                       |
