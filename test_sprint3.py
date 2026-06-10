#!/usr/bin/env python3
"""
test_sprint3.py — Testes de conformidade Sprint 3
Valida protocolo, lógica de negócio e correções aplicadas.
"""

import json
import sys
import os
import unittest
from unittest.mock import MagicMock, call

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import master
import worker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decode_sendall(mock_conn, call_index=-1):
    """Extrai e desserializa a mensagem enviada via sendall."""
    raw = mock_conn.sendall.call_args_list[call_index][0][0]
    return json.loads(raw.decode().rstrip("\n"))


def _reset_master_state():
    with master.worker_state_lock:
        master.workers.clear()
        master.worker_metadata.clear()
    with master.task_queue_lock:
        master.task_queue.clear()
    with master.pending_lock:
        master.pending = 0
    with master.borrowed_outgoing_workers_lock:
        master.borrowed_outgoing_workers.clear()


def _reset_worker_state():
    worker.original_master_target = None
    worker.original_master_uuid = None
    worker.original_master_name = None
    worker.current_master_uuid = None
    worker.last_registration_master_uuid = None
    worker.pending_temporary_registration = False
    with worker.master_target_lock:
        worker.master_target["host"] = None
        worker.master_target["port"] = None


# ---------------------------------------------------------------------------
# 1. Construção de mensagens de protocolo
# ---------------------------------------------------------------------------

class TestProtocolMessageBuilding(unittest.TestCase):

    def test_build_protocol_message_campos_obrigatorios(self):
        msg = master.build_protocol_message("request_help", {"key": "val"})
        self.assertEqual(msg["type"], "request_help")
        self.assertIn("request_id", msg)
        self.assertIsInstance(msg["request_id"], str)
        self.assertTrue(msg["request_id"].strip())
        self.assertIn("payload", msg)
        self.assertEqual(msg["payload"]["key"], "val")

    def test_build_protocol_message_request_id_customizado(self):
        msg = master.build_protocol_message("test_type", {}, request_id="fixed-id")
        self.assertEqual(msg["request_id"], "fixed-id")

    def test_request_help_payload_campos_obrigatorios(self):
        payload = master.build_help_request_payload(6, 2)
        for campo in ("master_uuid", "master_name", "master_host", "master_port",
                      "current_load", "workers_needed", "local_workers"):
            self.assertIn(campo, payload, f"Campo ausente: {campo}")
        self.assertEqual(payload["current_load"], 6)
        self.assertEqual(payload["workers_needed"], 2)

    def test_discovery_reply_campos_obrigatorios(self):
        reply = master.build_discovery_reply()
        for campo in ("TYPE", "MASTER_NAME", "MASTER_IP", "MASTER_PORT", "STATUS", "SERVER_UUID"):
            self.assertIn(campo, reply, f"Campo ausente: {campo}")
        self.assertEqual(reply["TYPE"], "DISCOVERY_REPLY")
        self.assertEqual(reply["STATUS"], "AVAILABLE")

    def test_election_ack_response_campos_obrigatorios(self):
        resp = master.build_election_ack_response("worker-x")
        self.assertEqual(resp["TYPE"], "ELECTION_ACK")
        self.assertEqual(resp["STATUS"], "ACCEPTED")
        self.assertIn("MASTER_NAME", resp)
        self.assertEqual(resp["WORKER_UUID"], "worker-x")

    def test_alive_response_campos_obrigatorios(self):
        resp = master.build_alive_response()
        self.assertEqual(resp["TASK"], "HEARTBEAT")
        self.assertEqual(resp["RESPONSE"], "ALIVE")
        self.assertIn("SERVER_UUID", resp)


# ---------------------------------------------------------------------------
# 2. Validação de mensagens de protocolo
# ---------------------------------------------------------------------------

class TestProtocolValidation(unittest.TestCase):

    # STATUS report
    def test_status_report_ok_valido(self):
        msg = {"STATUS": "OK", "TASK": "QUERY", "WORKER_UUID": "w-1"}
        self.assertTrue(master.valid_status_report(msg))

    def test_status_report_nok_valido(self):
        msg = {"STATUS": "NOK", "TASK": "QUERY", "WORKER_UUID": "w-1"}
        self.assertTrue(master.valid_status_report(msg))

    def test_status_report_sem_worker_uuid_invalido(self):
        msg = {"STATUS": "OK", "TASK": "QUERY"}
        self.assertFalse(master.valid_status_report(msg))

    def test_status_report_status_invalido(self):
        msg = {"STATUS": "MAYBE", "TASK": "QUERY", "WORKER_UUID": "w-1"}
        self.assertFalse(master.valid_status_report(msg))

    def test_status_report_nao_dict_invalido(self):
        self.assertFalse(master.valid_status_report("string"))
        self.assertFalse(master.valid_status_report(None))

    # Discovery
    def test_discovery_request_valido(self):
        msg = {"TYPE": "DISCOVERY", "WORKER_UUID": "w-2"}
        self.assertTrue(master.valid_discovery_request(msg))

    def test_discovery_request_sem_worker_uuid_invalido(self):
        self.assertFalse(master.valid_discovery_request({"TYPE": "DISCOVERY"}))

    def test_discovery_request_tipo_errado_invalido(self):
        self.assertFalse(master.valid_discovery_request({"TYPE": "OTHER", "WORKER_UUID": "w-2"}))

    # Election ACK
    def test_election_ack_valido(self):
        msg = {"TYPE": "ELECTION_ACK", "WORKER_UUID": "w-3", "SELECTED_MASTER": "MASTER_1"}
        self.assertTrue(master.valid_election_ack(msg))

    def test_election_ack_master_vazio_invalido(self):
        msg = {"TYPE": "ELECTION_ACK", "WORKER_UUID": "w-3", "SELECTED_MASTER": ""}
        self.assertFalse(master.valid_election_ack(msg))

    def test_election_ack_sem_worker_uuid_invalido(self):
        msg = {"TYPE": "ELECTION_ACK", "SELECTED_MASTER": "MASTER_1"}
        self.assertFalse(master.valid_election_ack(msg))

    # Heartbeat
    def test_heartbeat_valido(self):
        msg = {"TASK": "HEARTBEAT", "SERVER_UUID": "srv-1"}
        self.assertTrue(master.valid_heartbeat(msg))

    def test_alive_valido(self):
        msg = {"WORKER": "ALIVE", "WORKER_UUID": "w-4"}
        self.assertTrue(master.valid_heartbeat(msg))

    def test_heartbeat_sem_server_uuid_invalido(self):
        self.assertFalse(master.valid_heartbeat({"TASK": "HEARTBEAT"}))

    # Worker — discovery reply
    def test_discovery_reply_valido(self):
        msg = {"TYPE": "DISCOVERY_REPLY", "MASTER_NAME": "M1",
               "MASTER_IP": "127.0.0.1", "MASTER_PORT": 5000, "STATUS": "AVAILABLE"}
        self.assertTrue(worker.valid_discovery_reply(msg))

    def test_discovery_reply_status_errado_invalido(self):
        msg = {"TYPE": "DISCOVERY_REPLY", "MASTER_NAME": "M1",
               "MASTER_IP": "127.0.0.1", "MASTER_PORT": 5000, "STATUS": "BUSY"}
        self.assertFalse(worker.valid_discovery_reply(msg))

    def test_discovery_reply_sem_porta_invalido(self):
        msg = {"TYPE": "DISCOVERY_REPLY", "MASTER_NAME": "M1",
               "MASTER_IP": "127.0.0.1", "STATUS": "AVAILABLE"}
        self.assertFalse(worker.valid_discovery_reply(msg))

    def test_discovery_reply_nao_dict_invalido(self):
        self.assertFalse(worker.valid_discovery_reply(None))
        self.assertFalse(worker.valid_discovery_reply("texto"))


# ---------------------------------------------------------------------------
# 3. Eleição determinística no Worker
# ---------------------------------------------------------------------------

class TestWorkerElection(unittest.TestCase):

    def test_ganha_menor_nome_lexico(self):
        replies = [
            {"name": "MASTER_3", "host": "10.0.0.3", "port": 5002},
            {"name": "MASTER_1", "host": "10.0.0.1", "port": 5000},
            {"name": "MASTER_2", "host": "10.0.0.2", "port": 5001},
        ]
        winner = worker.choose_discovery_winner(replies)
        self.assertEqual(winner["name"], "MASTER_1")

    def test_lista_vazia_retorna_none(self):
        self.assertIsNone(worker.choose_discovery_winner([]))

    def test_candidato_unico_vence(self):
        replies = [{"name": "MASTER_X", "host": "10.0.0.9", "port": 5009}]
        self.assertEqual(worker.choose_discovery_winner(replies)["name"], "MASTER_X")

    def test_desempate_por_host_depois_do_nome(self):
        # Mesmo nome, desempata por host
        replies = [
            {"name": "MASTER_A", "host": "10.0.0.2", "port": 5000},
            {"name": "MASTER_A", "host": "10.0.0.1", "port": 5000},
        ]
        winner = worker.choose_discovery_winner(replies)
        self.assertEqual(winner["host"], "10.0.0.1")


# ---------------------------------------------------------------------------
# 4. Mensagens de registro do Worker (Sprint 3 — registro temporário)
# ---------------------------------------------------------------------------

class TestWorkerRegistrationMessages(unittest.TestCase):

    def setUp(self):
        _reset_worker_state()

    # Apresentação de worker local
    def test_apresentacao_worker_local_sem_server_uuid(self):
        msg = worker.build_presentation_payload()
        self.assertEqual(msg["WORKER"], "ALIVE")
        self.assertIn("WORKER_UUID", msg)
        self.assertNotIn("SERVER_UUID", msg)

    # Apresentação de worker emprestado (SERVER_UUID presente)
    def test_apresentacao_worker_emprestado_com_server_uuid(self):
        worker.original_master_target = ("127.0.0.1", 5001)
        worker.original_master_uuid = "uuid-original"
        with worker.master_target_lock:
            worker.master_target["host"] = "127.0.0.1"
            worker.master_target["port"] = 5000
        msg = worker.build_presentation_payload()
        self.assertEqual(msg.get("SERVER_UUID"), "uuid-original")

    # Registro temporário deve incluir ORIGINAL_MASTER_NAME (correção Sprint 3)
    def test_registro_temporario_contem_original_master_name(self):
        worker.original_master_target = ("127.0.0.1", 5001)
        worker.original_master_uuid = "uuid-b"
        worker.original_master_name = "MASTER_B"
        worker.pending_temporary_registration = True
        with worker.master_target_lock:
            worker.master_target["host"] = "127.0.0.1"
            worker.master_target["port"] = 5000

        msg = worker.build_temporary_registration_message()
        payload = msg.get("payload", {})

        self.assertEqual(msg["type"], "register_temporary_worker")
        self.assertEqual(payload.get("ORIGINAL_MASTER_NAME"), "MASTER_B")

    def test_registro_temporario_todos_campos_presentes(self):
        worker.original_master_target = ("192.168.1.10", 5001)
        worker.original_master_uuid = "uuid-original"
        worker.original_master_name = "MASTER_ORIGEM"
        worker.pending_temporary_registration = True
        with worker.master_target_lock:
            worker.master_target["host"] = "192.168.1.20"
            worker.master_target["port"] = 5000

        payload = worker.build_temporary_registration_message().get("payload", {})

        self.assertEqual(payload["ORIGINAL_MASTER_UUID"], "uuid-original")
        self.assertEqual(payload["ORIGINAL_MASTER_NAME"], "MASTER_ORIGEM")
        self.assertEqual(payload["ORIGINAL_MASTER_HOST"], "192.168.1.10")
        self.assertEqual(payload["ORIGINAL_MASTER_PORT"], 5001)
        self.assertIn("WORKER_UUID", payload)

    def test_registro_temporario_name_none_nao_quebra(self):
        # Sem nome definido (conexão direta, sem descoberta) não deve lançar erro
        worker.original_master_target = ("127.0.0.1", 5001)
        worker.original_master_uuid = "uuid-b"
        worker.original_master_name = None
        worker.pending_temporary_registration = True
        with worker.master_target_lock:
            worker.master_target["host"] = "127.0.0.1"
            worker.master_target["port"] = 5000

        msg = worker.build_temporary_registration_message()
        payload = msg.get("payload", {})
        self.assertIsNone(payload.get("ORIGINAL_MASTER_NAME"))


# ---------------------------------------------------------------------------
# 5. Gerenciamento de sessão de Workers no Master
# ---------------------------------------------------------------------------

class TestMasterWorkerSession(unittest.TestCase):

    def setUp(self):
        _reset_master_state()

    def test_mark_worker_local_define_role(self):
        conn = MagicMock()
        master.mark_worker_local("w-local", conn)
        with master.worker_state_lock:
            self.assertEqual(master.worker_metadata["w-local"]["role"], "local")

    def test_mark_worker_temporary_define_owner(self):
        conn = MagicMock()
        master.store_worker_session("w-tmp", conn, {"role": "local"})
        master.mark_worker_temporary(
            "w-tmp",
            {"owner_master_uuid": "m-b", "owner_master_name": "MASTER_B",
             "owner_master_host": "127.0.0.1", "owner_master_port": 5001},
            "req-001",
        )
        with master.worker_state_lock:
            meta = master.worker_metadata["w-tmp"]
        self.assertEqual(meta["role"], "temporary")
        self.assertEqual(meta["owner_master_name"], "MASTER_B")
        self.assertEqual(meta["owner_master_host"], "127.0.0.1")

    def test_list_local_workers_apenas_locais(self):
        conn = MagicMock()
        master.mark_worker_local("w-1", conn)
        master.mark_worker_local("w-2", conn)
        master.store_worker_session("w-tmp", conn, {
            "role": "temporary", "owner_master_uuid": "m", "owner_master_name": "M",
            "owner_master_host": "h", "owner_master_port": 0,
        })
        locals_ = master.list_local_workers()
        self.assertIn("w-1", locals_)
        self.assertIn("w-2", locals_)
        self.assertNotIn("w-tmp", locals_)

    def test_list_temporary_workers(self):
        conn = MagicMock()
        master.store_worker_session("w-tmp2", conn, {
            "role": "temporary", "owner_master_uuid": "m", "owner_master_name": "M",
            "owner_master_host": "h", "owner_master_port": 0,
        })
        self.assertIn("w-tmp2", master.list_temporary_workers())

    def test_select_workers_to_lend_respeita_quantidade(self):
        conn = MagicMock()
        for i in range(5):
            master.mark_worker_local(f"w-{i}", conn)
        selected = master.select_workers_to_lend(3)
        self.assertEqual(len(selected), 3)

    def test_select_workers_to_lend_apenas_locais(self):
        conn = MagicMock()
        master.mark_worker_local("w-local", conn)
        master.store_worker_session("w-tmp3", conn, {
            "role": "temporary", "owner_master_uuid": "m", "owner_master_name": "M",
            "owner_master_host": "h", "owner_master_port": 0,
        })
        selected = master.select_workers_to_lend(10)
        self.assertIn("w-local", selected)
        self.assertNotIn("w-tmp3", selected)

    def test_get_worker_connection_retorna_none_para_ausente(self):
        self.assertIsNone(master.get_worker_connection("inexistente"))

    def test_remove_worker_session(self):
        conn = MagicMock()
        master.mark_worker_local("w-rem", conn)
        master.remove_worker_session("w-rem")
        self.assertIsNone(master.get_worker_connection("w-rem"))


# ---------------------------------------------------------------------------
# 6. Despacho de tarefas (Sprint 3 — fix: dispatch após ACK)
# ---------------------------------------------------------------------------

class TestDispatchTarefas(unittest.TestCase):

    def setUp(self):
        _reset_master_state()

    def test_dispatch_envia_query_quando_ha_tarefa(self):
        conn = MagicMock()
        master.enqueue_task("TASK-001", "User1", force_nok=False)
        master.dispatch_next_task(conn, "w-test")

        msg = _decode_sendall(conn)
        self.assertEqual(msg["TASK"], "QUERY")
        self.assertEqual(msg["TASK_ID"], "TASK-001")
        self.assertEqual(msg["USER"], "User1")

    def test_dispatch_envia_no_task_quando_fila_vazia(self):
        conn = MagicMock()
        master.dispatch_next_task(conn, "w-test")

        msg = _decode_sendall(conn)
        self.assertEqual(msg["TASK"], "NO_TASK")

    def test_dispatch_consome_da_fila_em_ordem(self):
        conn = MagicMock()
        master.enqueue_task("TASK-A", "User1")
        master.enqueue_task("TASK-B", "User2")
        master.dispatch_next_task(conn, "w-test")

        msg = _decode_sendall(conn)
        self.assertEqual(msg["TASK_ID"], "TASK-A")  # FIFO

        with master.task_queue_lock:
            remaining = list(master.task_queue)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["TASK_ID"], "TASK-B")

    # Correção Sprint 3: guarda impede dispatch para worker liberado
    def test_guard_impede_dispatch_para_worker_liberado(self):
        conn = MagicMock()
        master.enqueue_task("TASK-NOLOSS", "User1")

        # Worker NÃO está na sessão (foi liberado)
        worker_uuid = "worker-liberado"
        # Simula a lógica do guard inserida em handle_worker
        if master.get_worker_connection(worker_uuid) is not None:
            master.dispatch_next_task(conn, worker_uuid)

        # sendall NÃO deve ter sido chamado
        conn.sendall.assert_not_called()
        # Tarefa NÃO deve ter sido consumida da fila
        with master.task_queue_lock:
            self.assertEqual(len(master.task_queue), 1)

    # Correção Sprint 3: dispatch imediato após ACK para worker registrado
    def test_dispatch_imediato_apos_ack_para_worker_registrado(self):
        conn = MagicMock()
        worker_uuid = "w-continuo"
        master.mark_worker_local(worker_uuid, conn)
        master.enqueue_task("TASK-NEXT", "User2")

        # Simula o padrão inserido em handle_worker após o ACK
        if master.get_worker_connection(worker_uuid) is not None:
            master.dispatch_next_task(conn, worker_uuid)

        msg = _decode_sendall(conn)
        self.assertEqual(msg["TASK"], "QUERY")
        self.assertEqual(msg["TASK_ID"], "TASK-NEXT")

    def test_enqueue_dequeue_preserva_force_nok(self):
        master.enqueue_task("TASK-NOK", "User3", force_nok=True)
        item = master.dequeue_task()
        self.assertTrue(item["FORCE_NOK"])

    def test_dequeue_fila_vazia_retorna_none(self):
        self.assertIsNone(master.dequeue_task())


# ---------------------------------------------------------------------------
# 7. Envelopes Sprint 3 — formato das mensagens Master-to-Master
# ---------------------------------------------------------------------------

class TestSprint3Envelopes(unittest.TestCase):

    def test_request_help_envelope_correto(self):
        payload = master.build_help_request_payload(6, 2)
        msg = master.build_protocol_message("request_help", payload, "req-s3-1")
        self.assertEqual(msg["type"], "request_help")
        self.assertEqual(msg["request_id"], "req-s3-1")
        self.assertIsInstance(msg["payload"], dict)
        self.assertIn("master_uuid", msg["payload"])

    def test_response_accepted_preserva_request_id(self):
        msg = master.build_protocol_message(
            "response_accepted", {"workers_offered": 2}, "req-s3-2"
        )
        self.assertEqual(msg["type"], "response_accepted")
        self.assertEqual(msg["request_id"], "req-s3-2")

    def test_response_rejected_preserva_request_id(self):
        msg = master.build_protocol_message(
            "response_rejected", {"reason": "no_workers"}, "req-s3-3"
        )
        self.assertEqual(msg["type"], "response_rejected")
        self.assertEqual(msg["request_id"], "req-s3-3")

    def test_command_redirect_campos_endereco(self):
        payload = {
            "new_master_host": "127.0.0.1",
            "new_master_port": 5001,
            "original_master_host": "127.0.0.1",
            "original_master_port": 5000,
            "original_master_name": "MASTER_A",
        }
        msg = master.build_protocol_message("command_redirect", payload, "req-s3-4")
        self.assertEqual(msg["type"], "command_redirect")
        self.assertEqual(msg["payload"]["original_master_name"], "MASTER_A")

    def test_notify_worker_returned_envelope(self):
        payload = {
            "worker_uuid": "w-x",
            "owner_master_uuid": "m-original",
            "borrowed_master_uuid": "m-borrowed",
        }
        msg = master.build_protocol_message("notify_worker_returned", payload, "req-s3-5")
        self.assertEqual(msg["type"], "notify_worker_returned")
        self.assertIn("worker_uuid", msg["payload"])

    def test_todos_envelopes_tem_request_id_unico_por_padrao(self):
        ids = {
            master.build_protocol_message("t", {})["request_id"]
            for _ in range(5)
        }
        self.assertEqual(len(ids), 5)  # todos distintos


# ---------------------------------------------------------------------------
# 8. Lógica de saturação e ajuda
# ---------------------------------------------------------------------------

class TestSaturacaoEAjuda(unittest.TestCase):

    def setUp(self):
        _reset_master_state()
        with master.help_request_lock:
            master.help_request_in_progress = False

    def test_threshold_configurados(self):
        from config import LOAD_THRESHOLD, RELEASE_THRESHOLD
        self.assertGreater(LOAD_THRESHOLD, RELEASE_THRESHOLD,
                           "LOAD_THRESHOLD deve ser maior que RELEASE_THRESHOLD")

    def test_release_nao_dispara_acima_do_threshold(self):
        conn = MagicMock()
        master.mark_worker_local("w-tmp-rel", conn)
        master.store_worker_session("w-tmp-rel", conn, {
            "role": "temporary",
            "owner_master_uuid": "m",
            "owner_master_name": "M",
            "owner_master_host": "127.0.0.1",
            "owner_master_port": 5001,
        })
        with master.pending_lock:
            master.pending = master.LOAD_THRESHOLD + 1  # acima — não deve liberar

        master.release_temporary_workers_if_needed()

        # worker ainda deve estar registrado
        self.assertIsNotNone(master.get_worker_connection("w-tmp-rel"))

    def test_maybe_request_help_nao_duplica_pedido(self):
        with master.help_request_lock:
            master.help_request_in_progress = True  # já em andamento
        # Não deve lançar nem iniciar segundo pedido
        master.maybe_request_help(10)
        # finish_help_request reseta o flag
        master.finish_help_request()
        self.assertFalse(master.help_request_in_progress)


# ---------------------------------------------------------------------------
# 9. Sintaxe — compilação dos arquivos do projeto
# ---------------------------------------------------------------------------

class TestCompilaçãoSintaxe(unittest.TestCase):

    def _compile(self, filename):
        import py_compile
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as exc:
            self.fail(f"Erro de sintaxe em {filename}: {exc}")

    def test_config_compila(self):
        self._compile("config.py")

    def test_master_compila(self):
        self._compile("master.py")

    def test_worker_compila(self):
        self._compile("worker.py")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
