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

from config import HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT

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


# ── Conecta no Master ───────────────────────────────────────
def connect(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(HEARTBEAT_TIMEOUT)
    sock.connect((host, port))
    print(f"[WORKER] Conectado em {host}:{port}")
    return sock


def connect_with_retry(host, port, retry_seconds=5):
    while True:
        try:
            return connect(host, port)
        except OSError:
            print("[WORKER] Status: OFFLINE - Tentando Reconectar")
            time.sleep(retry_seconds)


# ── Loop principal: heartbeat periódico com reconexão ────────
def run(host, port):
    original_host = host
    original_port = port
    master_server_uuid = "UNKNOWN_MASTER"
    sock = connect_with_retry(host, port)

    while True:
        try:
            heartbeat = {"SERVER_UUID": master_server_uuid, "TASK": "HEARTBEAT"}
            send(sock, heartbeat)

            msg = receive(sock)
            if msg and msg.get("TASK") == "HEARTBEAT" and msg.get("RESPONSE") == "ALIVE":
                response_server_uuid = msg.get("SERVER_UUID")
                if isinstance(response_server_uuid, str) and response_server_uuid.strip():
                    master_server_uuid = response_server_uuid
                print("[WORKER] Status: ALIVE")
            else:
                raise TimeoutError("Resposta inválida ou ausente do Master")

            time.sleep(HEARTBEAT_INTERVAL)

        except (socket.timeout, TimeoutError, OSError):
            print("[WORKER] Status: OFFLINE - Tentando Reconectar")
            try:
                sock.close()
            except OSError:
                pass
            sock = connect_with_retry(original_host, original_port)


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
