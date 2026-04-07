#!/usr/bin/env python3
# ============================================================
#  master.py
#  - Aceita conexões de Workers
#  - Gera requisições e ENVIA tarefas para os Workers
#  - Monitora saturação e negocia com Master vizinho
# ============================================================

import socket
import threading
import time
import uuid
import json

from config import SERVER_UUID, MASTER_HOST, MASTER_PORT, LOAD_THRESHOLD, TASK_DURATION, REQUEST_INTERVAL, NEIGHBOR_MASTERS, SPRINT1_HEARTBEAT_ONLY

# ── Estado global ────────────────────────────────────────────
workers = {}          # { worker_uuid: socket }
pending = 0           # requisições ainda não atribuídas
pending_lock = threading.Lock()


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


def valid_heartbeat(msg):
    if not isinstance(msg, dict):
        return False
    if msg.get("TASK") != "HEARTBEAT":
        return False
    server_uuid = msg.get("SERVER_UUID")
    if not isinstance(server_uuid, str) or not server_uuid.strip():
        return False
    return True


# ── Trata mensagens vindas de um Worker conectado ────────────
def handle_worker(worker_uuid, conn, first_msg=None):
    global pending
    msg = first_msg
    while True:
        if msg is None:
            msg = receive(conn)
        if msg is None:
            print(f"[MASTER] Worker {worker_uuid[:8]} desconectou.")
            workers.pop(worker_uuid, None)
            conn.close()
            return

        if msg.get("TASK") == "HEARTBEAT":
            if not valid_heartbeat(msg):
                print("[MASTER] HEARTBEAT inválido: campos obrigatórios ausentes.")
                workers.pop(worker_uuid, None)
                conn.close()
                return
            send(conn, {"SERVER_UUID": SERVER_UUID, "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"})

        elif msg.get("TASK") == "task_done":
            task_id = msg.get("TASK_ID")
            with pending_lock:
                pending = max(0, pending - 1)
            print(f"[MASTER] Tarefa {task_id} concluída por {worker_uuid[:8]}. Pendentes: {pending}")

        elif msg.get("TASK") == "register_worker" or msg.get("TASK") == "register_temporary_worker":
            # Worker temporário se registrou
            wid = msg.get("WORKER_UUID", worker_uuid)
            workers[wid] = conn
            print(f"[MASTER] Worker {'temporário ' if 'temporary' in msg.get('TASK','') else ''}{wid[:8]} registrado.")

        msg = None


# ── Aceita conexões de Workers ───────────────────────────────
def accept_loop():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((MASTER_HOST, MASTER_PORT))
    server.listen(20)
    print(f"[MASTER] Escutando em {MASTER_HOST}:{MASTER_PORT}")

    while True:
        conn, addr = server.accept()
        msg = receive(conn)
        if msg is None:
            conn.close()
            continue

        task = msg.get("TASK", "")
        worker_uuid = msg.get("WORKER_UUID") or msg.get("SERVER_UUID") or str(uuid.uuid4())

        # Heartbeat do Worker
        if task == "HEARTBEAT":
            if not valid_heartbeat(msg):
                print(f"[MASTER] HEARTBEAT inválido de {addr}. Conexão encerrada.")
                conn.close()
                continue
            print(f"[MASTER] Heartbeat recebido de {worker_uuid[:8]}.")
            threading.Thread(target=handle_worker, args=(worker_uuid, conn, msg), daemon=True).start()

        # Worker se registrando
        elif "register" in task:
            workers[worker_uuid] = conn
            kind = "temporário" if "temporary" in task else "próprio"
            print(f"[MASTER] Worker {kind} {worker_uuid[:8]} conectado de {addr}.")
            threading.Thread(target=handle_worker, args=(worker_uuid, conn, msg), daemon=True).start()

        # Master vizinho pedindo ajuda
        elif task == "request_help":
            if SPRINT1_HEARTBEAT_ONLY:
                print("[MASTER] Modo Sprint 1: ignorando request_help.")
                conn.close()
                continue
            handle_help_request(conn, msg)

        # Master vizinho liberando workers emprestados
        elif task == "command_release":
            if SPRINT1_HEARTBEAT_ONLY:
                print("[MASTER] Modo Sprint 1: ignorando command_release.")
                conn.close()
                continue
            print("[MASTER] Vizinho liberou os workers. Redirecionando de volta.")
            conn.close()


# ── Gera requisições e envia para workers disponíveis ────────
def load_generator():
    global pending
    count = 0
    while True:
        time.sleep(REQUEST_INTERVAL)

        if not workers:
            print("[MASTER] Sem workers disponíveis. Aguardando...")
            continue

        with pending_lock:
            pending += 1
            current_pending = pending

        task_id = f"TASK-{count:04d}"
        count += 1

        # Escolhe um worker (round-robin simples)
        worker_uuid = list(workers.keys())[count % len(workers)]
        sock = workers[worker_uuid]

        print(f"[MASTER] Enviando {task_id} → Worker {worker_uuid[:8]} | Pendentes: {current_pending}")
        send(sock, {"TASK": "assign_task", "TASK_ID": task_id, "DURATION": TASK_DURATION})

        # Verifica saturação
        if current_pending > LOAD_THRESHOLD:
            print(f"[MASTER] SATURADO! ({current_pending} pendentes). Pedindo ajuda...")
            threading.Thread(target=ask_for_help, daemon=True).start()


# ── Pede ajuda a um Master vizinho ───────────────────────────
def ask_for_help():
    for (host, port) in NEIGHBOR_MASTERS:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            send(sock, {"SERVER_UUID": SERVER_UUID, "TASK": "request_help", "MASTER_PORT": MASTER_PORT})

            resp = receive(sock)
            if resp and resp.get("TASK") == "response_accepted":
                print(f"[MASTER] Vizinho {host}:{port} aceitou ajudar!")
                sock.close()
                return
            else:
                print(f"[MASTER] Vizinho {host}:{port} rejeitou.")
                sock.close()
        except OSError as e:
            print(f"[MASTER] Não conectou ao vizinho {host}:{port} — {e}")


# ── Responde pedido de ajuda de outro Master ─────────────────
def handle_help_request(conn, msg):
    if len(workers) > 1:
        # Empresta 1 worker
        w_uuid = list(workers.keys())[0]
        w_sock = workers[w_uuid]
        requester_host, _ = conn.getpeername()
        requester_port = msg.get("MASTER_PORT", MASTER_PORT)

        print(f"[MASTER] Aceitei ajudar. Redirecionando Worker {w_uuid[:8]}.")
        send(conn, {"SERVER_UUID": SERVER_UUID, "TASK": "response_accepted", "WORKERS_TO_SEND": 1})
        send(w_sock, {"TASK": "command_redirect", "NEW_MASTER_HOST": requester_host, "NEW_MASTER_PORT": requester_port})
        workers.pop(w_uuid, None)
    else:
        print("[MASTER] Sem workers para emprestar. Rejeitando.")
        send(conn, {"SERVER_UUID": SERVER_UUID, "TASK": "response_rejected"})
    conn.close()


# ── Entry point ──────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[MASTER] Iniciando | UUID: {SERVER_UUID}")
    print(f"[MASTER] Suba workers com: python worker.py 127.0.0.1 {MASTER_PORT}")
    if SPRINT1_HEARTBEAT_ONLY:
        print("[MASTER] Modo Sprint 1 ativo: apenas HEARTBEAT para demonstracao.")
        accept_loop()
    else:
        threading.Thread(target=accept_loop, daemon=True).start()
        load_generator()
