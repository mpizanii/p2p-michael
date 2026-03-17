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

WORKER_UUID = str(uuid.uuid4())


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


# ── Conecta no Master e se registra ─────────────────────────
def connect(host, port, temporary=False):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    task_type = "register_temporary_worker" if temporary else "register_worker"
    send(sock, {"TASK": task_type, "WORKER_UUID": WORKER_UUID})
    print(f"[WORKER] Conectado em {host}:{port} ({'temporário' if temporary else 'próprio'})")
    return sock


# ── Loop principal: só fica recebendo mensagens do Master ────
def run(host, port):
    original_host = host
    original_port = port
    sock = connect(host, port)

    while True:
        msg = receive(sock)

        if msg is None:
            print("[WORKER] Master desconectou. Tentando reconectar em 5s...")
            time.sleep(5)
            sock = connect(original_host, original_port)
            continue

        task = msg.get("TASK")
        print(f"[WORKER] Recebeu: {msg}")

        # ── Executar uma tarefa ──────────────────────────────
        if task == "assign_task":
            task_id = msg.get("TASK_ID")
            duration = msg.get("DURATION", 3)
            print(f"[WORKER] Processando {task_id} por {duration}s...")
            time.sleep(duration)
            send(sock, {"TASK": "task_done", "WORKER_UUID": WORKER_UUID, "TASK_ID": task_id})
            print(f"[WORKER] {task_id} concluída.")

        # ── Ir para outro Master (temporariamente) ───────────
        elif task == "command_redirect":
            new_host = msg.get("NEW_MASTER_HOST")
            new_port = msg.get("NEW_MASTER_PORT")
            print(f"[WORKER] Redirecionando para {new_host}:{new_port}...")
            sock.close()
            sock = connect(new_host, new_port, temporary=True)

        # ── Voltar ao Master original ────────────────────────
        elif task == "command_release":
            print(f"[WORKER] Liberado! Voltando ao Master original {original_host}:{original_port}...")
            sock.close()
            sock = connect(original_host, original_port)

        # ── Heartbeat ────────────────────────────────────────
        elif task == "HEARTBEAT":
            send(sock, {"SERVER_UUID": WORKER_UUID, "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"})


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
