#!/usr/bin/env python3
# ============================================================
#  worker.py
#  - Conecta em um Master e RECEBE tarefas
#  - Processa (simula com sleep) e avisa que terminou
#  - Pode ser redirecionado para outro Master
# ============================================================
#  Como usar:
#    python worker.py 127.0.0.1 5000
# ============================================================

import socket
import time
import uuid
import json
import sys
import os
import shutil
import subprocess
import threading

from config import (
    HEARTBEAT_INTERVAL,
    HEARTBEAT_TIMEOUT,
    MASTER_PORT,
    TASK_DURATION,
    CONNECTION_ERROR_THRESHOLD,
    ELECTION_PORT,
    ELECTION_RETRY_INTERVAL,
    ELECTION_CANDIDATES,
)

WORKER_UUID = str(uuid.uuid4())
master_target = {"host": None, "port": None}
master_target_lock = threading.Lock()
master_process = None
master_process_lock = threading.Lock()

original_master_target = None
original_master_uuid = None
current_master_uuid = None
last_registration_master_uuid = None


# ── Envio de mensagem JSON ───────────────────────────────────
def send(sock, payload):
    try:
        sock.sendall((json.dumps(payload) + "\n").encode())
    except OSError:
        pass


# ── Recebimento de mensagem JSON ─────────────────────────────
def receive(sock):
    try:
        data = b""
        while b"\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                return None
            data += chunk
        return json.loads(data.split(b"\n")[0])
    except Exception:
        return None


def receive_with_timeout(sock, timeout_seconds):
    original_timeout = sock.gettimeout()
    try:
        sock.settimeout(timeout_seconds)
        return receive(sock)
    except socket.timeout:
        return None
    finally:
        sock.settimeout(original_timeout)


# ── Conecta no Master ───────────────────────────────────────
def connect(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(HEARTBEAT_TIMEOUT)
    sock.connect((host, port))
    print(f"[WORKER] Conectado em {host}:{port}")
    return sock


def local_addresses():
    hosts = {"127.0.0.1", "localhost"}
    try:
        hosts.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return hosts


def build_presentation_payload():
    current_host, current_port = get_master_target()
    payload = {
        # Apresentação inicial do Worker para o Master.
        "WORKER": "ALIVE",
        "WORKER_UUID": WORKER_UUID,
    }

    borrowed = (
        original_master_target is not None
        and original_master_uuid is not None
        and (current_host, current_port) != original_master_target
    )

    if borrowed:
        # Quando o Worker estiver emprestado, informa o Master original.
        payload["SERVER_UUID"] = original_master_uuid

    return payload


def process_task(sock, task_msg):
    task_id = task_msg.get("TASK_ID", "SEM_ID")
    user = task_msg.get("USER", "desconhecido")
    force_nok = bool(task_msg.get("FORCE_NOK", False))

    # Simula o processamento do trabalho recebido do Master.
    print(f"[WORKER] Processando tarefa {task_id} para {user}...")
    time.sleep(TASK_DURATION)

    status_payload = {
        # Reporte de status exigido na Sprint 2.
        "STATUS": "NOK" if force_nok else "OK",
        "TASK": "QUERY",
        "WORKER_UUID": WORKER_UUID,
        "TASK_ID": task_id,
    }
    send(sock, status_payload)

    ack = receive(sock)
    if ack and ack.get("STATUS") == "ACK":
        print(f"[WORKER] ACK recebido da tarefa {task_id}.")
    else:
        print(f"[WORKER] Sem ACK explícito para a tarefa {task_id}.")


def handle_master_message(sock, msg):
    if not isinstance(msg, dict):
        return

    if msg.get("TASK") == "QUERY":
        process_task(sock, msg)
    elif msg.get("TASK") == "NO_TASK":
        print("[WORKER] Master informou que não há tarefa na fila.")
    elif msg.get("TASK") == "HEARTBEAT" and msg.get("RESPONSE") == "ALIVE":
        print("[WORKER] Heartbeat confirmado pelo Master.")

def is_local_host(host):
    return host in local_addresses()


def set_master_target(host, port, reason=""):
    global original_master_target
    with master_target_lock:
        master_target["host"] = host
        master_target["port"] = port
        if original_master_target is None:
            original_master_target = (host, port)
    if reason:
        print(f"[WORKER] Novo master alvo: {host}:{port} ({reason})")


def get_master_target():
    with master_target_lock:
        return master_target["host"], master_target["port"]


def get_free_disk_bytes():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    return shutil.disk_usage(project_dir).free


def ensure_local_master_running():
    global master_process
    with master_process_lock:
        if master_process is not None and master_process.poll() is None:
            return
        master_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "master.py")
        master_process = subprocess.Popen([sys.executable, master_file], cwd=os.path.dirname(master_file))
        print("[WORKER] Este no foi eleito master. Iniciando master.py local.")


def unique_candidates():
    ordered = []
    for host in ELECTION_CANDIDATES:
        if host and host not in ordered:
            ordered.append(host)
    for host in local_addresses():
        if host not in ordered:
            ordered.append(host)
    return ordered


def handle_election_message(conn):
    msg = receive(conn)
    if msg is None:
        conn.close()
        return

    task = msg.get("TASK")
    if task == "ELECTION_QUERY":
        send(
            conn,
            {
                "TASK": "ELECTION_RESPONSE",
                "WORKER_UUID": WORKER_UUID,
                "FREE_BYTES": get_free_disk_bytes(),
            },
        )

    elif task == "ELECTION_ANNOUNCE":
        new_host = msg.get("NEW_MASTER_HOST")
        new_port = int(msg.get("NEW_MASTER_PORT", MASTER_PORT))
        if isinstance(new_host, str) and new_host:
            set_master_target(new_host, new_port, "consenso")
            if is_local_host(new_host):
                ensure_local_master_running()
            send(conn, {"TASK": "ACK", "WORKER_UUID": WORKER_UUID})

    conn.close()


def election_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", ELECTION_PORT))
    server.listen(20)
    print(f"[WORKER] Servidor de eleicao ativo em 0.0.0.0:{ELECTION_PORT}")

    while True:
        conn, _ = server.accept()
        threading.Thread(target=handle_election_message, args=(conn,), daemon=True).start()


def query_candidate_disk(host):
    if is_local_host(host):
        return {"host": host, "free_bytes": get_free_disk_bytes()}

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(HEARTBEAT_TIMEOUT)
        sock.connect((host, ELECTION_PORT))
        send(sock, {"TASK": "ELECTION_QUERY", "WORKER_UUID": WORKER_UUID})
        resp = receive(sock)
        sock.close()
        if resp and resp.get("TASK") == "ELECTION_RESPONSE":
            free_bytes = int(resp.get("FREE_BYTES", -1))
            if free_bytes >= 0:
                return {"host": host, "free_bytes": free_bytes}
    except (OSError, ValueError):
        return None
    return None


def announce_winner(host, winner_host, winner_port):
    if is_local_host(host):
        set_master_target(winner_host, winner_port, "consenso local")
        if is_local_host(winner_host):
            ensure_local_master_running()
        return True

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(HEARTBEAT_TIMEOUT)
        sock.connect((host, ELECTION_PORT))
        send(
            sock,
            {
                "TASK": "ELECTION_ANNOUNCE",
                "NEW_MASTER_HOST": winner_host,
                "NEW_MASTER_PORT": winner_port,
                "INITIATOR_UUID": WORKER_UUID,
            },
        )
        ack = receive(sock)
        sock.close()
        return bool(ack and ack.get("TASK") == "ACK")
    except OSError:
        return False


def run_master_election():
    candidates = unique_candidates()
    results = []
    for host in candidates:
        data = query_candidate_disk(host)
        if data is not None:
            results.append(data)

    if not results:
        current_host, current_port = get_master_target()
        print("[WORKER] Eleicao falhou: nenhum candidato respondeu.")
        return current_host, current_port

    winner = max(results, key=lambda item: (item["free_bytes"], item["host"]))
    winner_host = winner["host"]
    winner_port = MASTER_PORT
    print(f"[WORKER] Eleicao: novo master = {winner_host} (free={winner['free_bytes']} bytes)")

    ack_count = 0
    for host in candidates:
        if announce_winner(host, winner_host, winner_port):
            ack_count += 1

    required = (len(candidates) // 2) + 1
    if ack_count >= required:
        print(f"[WORKER] Consenso atingido: {ack_count}/{len(candidates)} ACKs.")
    else:
        print(f"[WORKER] Consenso parcial: {ack_count}/{len(candidates)} ACKs.")

    set_master_target(winner_host, winner_port, "eleicao")
    if is_local_host(winner_host):
        ensure_local_master_running()
    return winner_host, winner_port


def register_with_master(sock):
    global original_master_uuid, current_master_uuid, last_registration_master_uuid

    payload = build_presentation_payload()
    send(sock, payload)

    response = receive(sock)
    if not response:
        return None

    response_server_uuid = response.get("SERVER_UUID")
    if isinstance(response_server_uuid, str) and response_server_uuid.strip():
        current_master_uuid = response_server_uuid
        if original_master_uuid is None:
            original_master_uuid = response_server_uuid

    print(f"[WORKER] Apresentacao enviada: {payload}")

    if response.get("TASK") == "QUERY":
        process_task(sock, response)
    elif response.get("TASK") == "NO_TASK":
        print("[WORKER] Master informou que não havia tarefa na apresentação.")

    last_registration_master_uuid = current_master_uuid
    return response

# ── Loop principal: heartbeat periódico com reconexão ────────
def run(host, port):
    global original_master_uuid, current_master_uuid, last_registration_master_uuid

    set_master_target(host, port, "inicial")
    threading.Thread(target=election_server, daemon=True).start()

    sock = None
    consecutive_errors = 0

    while True:
        target_host, target_port = get_master_target()
        try:
            if sock is None:
                sock = connect(target_host, target_port)

            # Na Sprint 2 o Worker solicita trabalho com payload WORKER=ALIVE.
            response = register_with_master(sock)
            if response is None:
                raise TimeoutError("Resposta inválida ou ausente do Master na solicitacao")

            consecutive_errors = 0

            time.sleep(HEARTBEAT_INTERVAL)

        except (socket.timeout, TimeoutError, OSError):
            consecutive_errors += 1
            print(
                f"[WORKER] Status: OFFLINE - Tentando Reconectar "
                f"({consecutive_errors}/{CONNECTION_ERROR_THRESHOLD})"
            )
            try:
                if sock is not None:
                    sock.close()
            except OSError:
                pass
            sock = None
            last_registration_master_uuid = None

            if consecutive_errors >= CONNECTION_ERROR_THRESHOLD:
                print("[WORKER] Downtime detectado. Iniciando eleicao de master.")
                run_master_election()
                consecutive_errors = 0

            time.sleep(ELECTION_RETRY_INTERVAL)


# ── Entry point ──────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python worker.py <host> <porta>")
        print("Exemplo: python worker.py 127.0.0.1 5000")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])

    print(f"[WORKER] UUID: {WORKER_UUID}")
    run(host, port)
