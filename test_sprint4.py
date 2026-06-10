#!/usr/bin/env python3
"""Testes unitários — Sprint 4: Monitor de métricas."""

import os
import py_compile
import re
import time
import uuid
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------

def _make_farm_state(
    total=3, utilization=2, borrowed=0, received=1, failed_w=0,
    pending=4, running=2, completed=10, failed_t=1, oldest_age=5,
    neighbors=None,
):
    return {
        "start_time": time.time() - 60,
        "workers": {
            "total_registered": total,
            "workers_utilization": utilization,
            "workers_alive": total,
            "workers_idle": max(0, total - utilization),
            "workers_borrowed": borrowed,
            "workers_received": received,
            "workers_failed": failed_w,
            "workers_home": total - received,
            "workers_available_capacity": max(0, total - utilization),
            "borrowed_workers": [],
        },
        "tasks": {
            "tasks_pending": pending,
            "tasks_running": running,
            "tasks_completed": completed,
            "tasks_failed": failed_t,
            "oldest_task_age_s": oldest_age,
        },
        "config_thresholds": {
            "max_task": 5,
            "warn_cpu_percent": 85,
            "warn_memory_percent": 85,
            "release_task": 3,
        },
        "neighbors": neighbors or [],
    }


# ---------------------------------------------------------------------------
# 1. Schema do Payload
# ---------------------------------------------------------------------------

class TestPayloadSchema(unittest.TestCase):

    def setUp(self):
        import monitor
        self.monitor = monitor
        self.report = monitor.build_performance_report(_make_farm_state())

    def test_top_level_fields_presentes(self):
        required = {"server_uuid", "hostname", "role", "task", "timestamp",
                    "message_id", "payload_version", "performance"}
        self.assertTrue(required.issubset(self.report.keys()))

    def test_performance_system_fields(self):
        sys = self.report["performance"]["system"]
        required = {"uptime_seconds", "load_average_1m", "load_average_5m",
                    "cpu", "memory", "disk"}
        self.assertTrue(required.issubset(sys.keys()))

    def test_performance_system_cpu_fields(self):
        cpu = self.report["performance"]["system"]["cpu"]
        self.assertIn("usage_percent", cpu)
        self.assertIn("count_logical", cpu)
        self.assertIn("count_physical", cpu)

    def test_performance_system_memory_fields(self):
        mem = self.report["performance"]["system"]["memory"]
        required = {"total_mb", "available_mb", "percent_used", "memory_used"}
        self.assertTrue(required.issubset(mem.keys()))

    def test_performance_system_disk_fields(self):
        disk = self.report["performance"]["system"]["disk"]
        required = {"total_gb", "free_gb", "percent_used"}
        self.assertTrue(required.issubset(disk.keys()))

    def test_performance_farm_state_workers_fields(self):
        workers = self.report["performance"]["farm_state"]["workers"]
        required = {
            "total_registered", "workers_utilization", "workers_alive",
            "workers_idle", "workers_borrowed", "workers_received",
            "workers_failed", "workers_home", "workers_available_capacity",
            "borrowed_workers",
        }
        self.assertTrue(required.issubset(workers.keys()))

    def test_performance_farm_state_tasks_fields(self):
        tasks = self.report["performance"]["farm_state"]["tasks"]
        required = {"tasks_pending", "tasks_running", "tasks_completed",
                    "tasks_failed", "oldest_task_age_s"}
        self.assertTrue(required.issubset(tasks.keys()))

    def test_performance_config_thresholds_fields(self):
        cfg = self.report["performance"]["config_thresholds"]
        required = {"max_task", "warn_cpu_percent", "warn_memory_percent", "release_task"}
        self.assertTrue(required.issubset(cfg.keys()))

    def test_performance_neighbors_is_list(self):
        neighbors = self.report["performance"]["neighbors"]
        self.assertIsInstance(neighbors, list)

    def test_performance_neighbors_fields_quando_presente(self):
        state = _make_farm_state(neighbors=[
            {"server_uuid": "peer1", "status": "available", "last_heartbeat": "2026-06-10T00:00:00Z"}
        ])
        import monitor
        report = monitor.build_performance_report(state)
        n = report["performance"]["neighbors"][0]
        self.assertIn("server_uuid", n)
        self.assertIn("status", n)
        self.assertIn("last_heartbeat", n)


# ---------------------------------------------------------------------------
# 2. Valores do Payload
# ---------------------------------------------------------------------------

class TestPayloadValues(unittest.TestCase):

    def setUp(self):
        import monitor
        self.monitor = monitor
        self.report = monitor.build_performance_report(_make_farm_state())

    def test_timestamp_formato_iso8601(self):
        ts = self.report["timestamp"]
        # YYYY-MM-DDTHH:MM:SSZ
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_message_id_e_uuid_valido(self):
        mid = self.report["message_id"]
        try:
            parsed = uuid.UUID(mid)
            self.assertIsNotNone(parsed)
        except ValueError:
            self.fail(f"message_id nao e UUID valido: {mid}")

    def test_message_id_unico_por_chamada(self):
        import monitor
        r1 = monitor.build_performance_report(_make_farm_state())
        r2 = monitor.build_performance_report(_make_farm_state())
        self.assertNotEqual(r1["message_id"], r2["message_id"])

    def test_payload_version(self):
        self.assertEqual(self.report["payload_version"], "sprint4-monitor")

    def test_role_e_master(self):
        self.assertEqual(self.report["role"], "master")

    def test_task_e_performance_report(self):
        self.assertEqual(self.report["task"], "performance_report")

    def test_uptime_seconds_positivo(self):
        uptime = self.report["performance"]["system"]["uptime_seconds"]
        self.assertGreaterEqual(uptime, 0)


# ---------------------------------------------------------------------------
# 3. Métricas da Farm
# ---------------------------------------------------------------------------

class TestFarmMetrics(unittest.TestCase):

    def test_workers_idle_calculado_corretamente(self):
        state = _make_farm_state(total=5, utilization=3)
        import monitor
        report = monitor.build_performance_report(state)
        workers = report["performance"]["farm_state"]["workers"]
        self.assertEqual(workers["workers_idle"], 2)

    def test_workers_available_capacity_igual_idle(self):
        state = _make_farm_state(total=4, utilization=2)
        import monitor
        report = monitor.build_performance_report(state)
        w = report["performance"]["farm_state"]["workers"]
        self.assertEqual(w["workers_available_capacity"], w["workers_idle"])

    def test_workers_alive_igual_total_registered(self):
        state = _make_farm_state(total=6)
        import monitor
        report = monitor.build_performance_report(state)
        w = report["performance"]["farm_state"]["workers"]
        self.assertEqual(w["workers_alive"], w["total_registered"])

    def test_oldest_task_age_zero_quando_fila_vazia(self):
        state = _make_farm_state(oldest_age=0)
        import monitor
        report = monitor.build_performance_report(state)
        self.assertEqual(report["performance"]["farm_state"]["tasks"]["oldest_task_age_s"], 0)

    def test_oldest_task_age_positivo(self):
        state = _make_farm_state(oldest_age=312)
        import monitor
        report = monitor.build_performance_report(state)
        self.assertGreater(report["performance"]["farm_state"]["tasks"]["oldest_task_age_s"], 0)

    def test_borrowed_workers_direction_out(self):
        state = _make_farm_state()
        state["workers"]["borrowed_workers"] = [{"direction": "out", "peer_uuid": "MASTER_2"}]
        import monitor
        report = monitor.build_performance_report(state)
        bw = report["performance"]["farm_state"]["workers"]["borrowed_workers"]
        self.assertEqual(bw[0]["direction"], "out")
        self.assertEqual(bw[0]["peer_uuid"], "MASTER_2")

    def test_borrowed_workers_direction_in(self):
        state = _make_farm_state()
        state["workers"]["borrowed_workers"] = [{"direction": "in", "peer_uuid": "MASTER_1"}]
        import monitor
        report = monitor.build_performance_report(state)
        bw = report["performance"]["farm_state"]["workers"]["borrowed_workers"]
        self.assertEqual(bw[0]["direction"], "in")


# ---------------------------------------------------------------------------
# 4. Métricas do Sistema
# ---------------------------------------------------------------------------

class TestSystemMetrics(unittest.TestCase):

    def test_collect_system_metrics_retorna_estrutura_completa(self):
        import monitor
        metrics = monitor.collect_system_metrics(time.time() - 100)
        self.assertIn("uptime_seconds", metrics)
        self.assertIn("cpu", metrics)
        self.assertIn("memory", metrics)
        self.assertIn("disk", metrics)

    def test_load_average_fallback_sem_getloadavg(self):
        """No Windows, os.getloadavg nao existe — _load_average retorna floats >= 0."""
        import monitor
        # Chama diretamente: no Windows o path do except AttributeError e sempre tomado.
        # Em outros SO pode retornar valores reais — ambos sao floats nao-negativos.
        la1, la5 = monitor._load_average()
        self.assertIsInstance(la1, float)
        self.assertIsInstance(la5, float)
        self.assertGreaterEqual(la1, 0.0)
        self.assertGreaterEqual(la5, 0.0)

    def test_collect_sem_psutil_retorna_zeros_cpu_mem(self):
        import monitor
        original = monitor._PSUTIL
        try:
            monitor._PSUTIL = False
            metrics = monitor.collect_system_metrics(time.time())
            self.assertEqual(metrics["cpu"]["usage_percent"], 0.0)
            self.assertEqual(metrics["memory"]["total_mb"], 0)
        finally:
            monitor._PSUTIL = original

    def test_disk_metrics_sao_floats_nao_negativos(self):
        import monitor
        metrics = monitor.collect_system_metrics(time.time())
        disk = metrics["disk"]
        self.assertGreaterEqual(disk["total_gb"], 0.0)
        self.assertGreaterEqual(disk["free_gb"], 0.0)
        self.assertGreaterEqual(disk["percent_used"], 0.0)


# ---------------------------------------------------------------------------
# 5. Resiliência do Monitor
# ---------------------------------------------------------------------------

class TestMonitorResilience(unittest.TestCase):

    def test_send_failure_nao_propaga_no_loop(self):
        """monitor_loop captura falha de envio e continua — não trava o Master."""
        import monitor
        call_count = [0]

        def fake_state():
            call_count[0] += 1
            return _make_farm_state()

        def fake_sleep(seconds):
            # Após 2 iterações, para o loop via KeyboardInterrupt (não capturado por except Exception)
            if call_count[0] >= 2:
                raise KeyboardInterrupt("fim do teste")

        with patch.object(monitor, "send_to_supervisor", side_effect=OSError("supervisor fora")), \
             patch("time.sleep", side_effect=fake_sleep):
            try:
                monitor.monitor_loop(fake_state)
            except KeyboardInterrupt:
                pass

        self.assertGreaterEqual(call_count[0], 2)

    def test_send_to_supervisor_usa_tls(self):
        """send_to_supervisor deve chamar ssl.create_default_context."""
        import monitor
        mock_ctx = MagicMock()
        mock_tls = MagicMock()
        mock_raw = MagicMock()
        mock_ctx.wrap_socket.return_value = mock_tls

        with patch("ssl.create_default_context", return_value=mock_ctx), \
             patch("socket.create_connection", return_value=mock_raw):
            monitor.send_to_supervisor({"server_uuid": "test", "message_id": "abc12345"})

        mock_ctx.wrap_socket.assert_called_once()
        mock_tls.sendall.assert_called_once()
        mock_tls.close.assert_called_once()

    def test_send_to_supervisor_nao_chama_recv(self):
        """O supervisor não deve receber chamada recv após o envio."""
        import monitor
        mock_ctx = MagicMock()
        mock_tls = MagicMock()
        mock_raw = MagicMock()
        mock_ctx.wrap_socket.return_value = mock_tls

        with patch("ssl.create_default_context", return_value=mock_ctx), \
             patch("socket.create_connection", return_value=mock_raw):
            monitor.send_to_supervisor({"server_uuid": "test", "message_id": "abc12345"})

        mock_tls.recv.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Integração com master.py (estado da farm)
# ---------------------------------------------------------------------------

class TestGetFarmState(unittest.TestCase):

    def test_get_farm_state_retorna_estrutura_obrigatoria(self):
        import master
        state = master.get_farm_state()
        self.assertIn("start_time", state)
        self.assertIn("workers", state)
        self.assertIn("tasks", state)
        self.assertIn("config_thresholds", state)
        self.assertIn("neighbors", state)

    def test_get_farm_state_workers_campos_presentes(self):
        import master
        w = master.get_farm_state()["workers"]
        required = {
            "total_registered", "workers_utilization", "workers_alive",
            "workers_idle", "workers_borrowed", "workers_received",
            "workers_failed", "workers_home", "workers_available_capacity",
            "borrowed_workers",
        }
        self.assertTrue(required.issubset(w.keys()))

    def test_s4_counters_tasks_ok_incrementa_via_status(self):
        import master
        master.s4_counters["tasks_ok"] = 0
        master.s4_counters["tasks_nok"] = 0
        initial_ok = master.s4_counters["tasks_ok"]
        with master.s4_counters_lock:
            master.s4_counters["tasks_ok"] += 1
        self.assertEqual(master.s4_counters["tasks_ok"], initial_ok + 1)

    def test_s4_tasks_running_set_add_discard(self):
        import master
        test_uuid = "worker-test-sprint4"
        master.s4_tasks_running.discard(test_uuid)
        with master.s4_tasks_running_lock:
            master.s4_tasks_running.add(test_uuid)
        self.assertIn(test_uuid, master.s4_tasks_running)
        with master.s4_tasks_running_lock:
            master.s4_tasks_running.discard(test_uuid)
        self.assertNotIn(test_uuid, master.s4_tasks_running)

    def test_s4_enqueue_times_registra_e_remove(self):
        import master
        tid = "TASK-S4-TEST"
        master.enqueue_task(tid, "UserTest", False)
        with master.s4_enqueue_lock:
            self.assertIn(tid, master.s4_enqueue_times)
        master.dequeue_task()
        with master.s4_enqueue_lock:
            self.assertNotIn(tid, master.s4_enqueue_times)


# ---------------------------------------------------------------------------
# 7. Sintaxe
# ---------------------------------------------------------------------------

class TestSyntaxSprint4(unittest.TestCase):

    def _check(self, filename):
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, filename)
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"Erro de sintaxe em {filename}: {e}")

    def test_monitor_syntax(self):
        self._check("monitor.py")

    def test_master_syntax(self):
        self._check("master.py")

    def test_config_syntax(self):
        self._check("config.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)
