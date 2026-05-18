#!/usr/bin/env python3
# ============================================================
#  master.py
#  - Aceita conexoes de Workers
#  - Responde a descoberta UDP com nome e porta do Master
#  - Confirma a eleicao via TCP antes do fluxo de heartbeat
#  - Gera requisicoes e ENVIA tarefas para os Workers
#  - Monitora saturacao e negocia com Master vizinho
# ============================================================

import json
import socket
import threading
import time
import uuid

from config import (
    SERVER_UUID,
    MASTER_NAME,
    MASTER_HOST,
    MASTER_BIND_HOST,
    MASTER_PORT,
    DISCOVERY_PORT,
    LOAD_THRESHOLD,
    RELEASE_THRESHOLD,
    TASK_DURATION,
    REQUEST_INTERVAL,
    NEIGHBOR_MASTERS,
    SPRINT3_HELP_TIMEOUT,
    SPRINT3_DEFAULT_WORKERS_TO_BORROW,
    SPRINT1_HEARTBEAT_ONLY,
)

# ── Estado global ────────────────────────────────────────────
workers = {}          # { worker_uuid: socket }
worker_metadata = {}   # { worker_uuid: info }
pending = 0           # requisicoes ainda nao atribuidas
pending_lock = threading.Lock()
task_queue = []       # fila de tarefas aguardando worker
task_queue_lock = threading.Lock()
worker_state_lock = threading.Lock()
help_request_in_progress = False
help_request_lock = threading.Lock()
borrowed_outgoing_workers = {}
borrowed_outgoing_workers_lock = threading.Lock()


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


def protocol_message_type(msg):
    if not isinstance(msg, dict):
        return None
    return msg.get("type") or msg.get("TYPE") or msg.get("TASK")


def protocol_request_id(msg):
    if not isinstance(msg, dict):
        return None
    request_id = msg.get("request_id") or msg.get("REQUEST_ID")
    if isinstance(request_id, str) and request_id.strip():
        return request_id
    return None


def protocol_payload(msg):
    if not isinstance(msg, dict):
        return {}
    payload = msg.get("payload")
    if isinstance(payload, dict):
        return payload
    return msg


def build_protocol_message(message_type, payload, request_id=None):
    if request_id is None:
        request_id = str(uuid.uuid4())
    return {"type": message_type, "request_id": request_id, "payload": payload}


def get_worker_connection(worker_uuid):
    with worker_state_lock:
        return workers.get(worker_uuid)


def store_worker_session(worker_uuid, conn, metadata=None):
    with worker_state_lock:
        workers[worker_uuid] = conn
        worker_metadata[worker_uuid] = metadata or {}


def remove_worker_session(worker_uuid):
    with worker_state_lock:
        workers.pop(worker_uuid, None)
        worker_metadata.pop(worker_uuid, None)


def list_workers_by_role(role):
    with worker_state_lock:
        return [worker_uuid for worker_uuid, info in worker_metadata.items() if info.get("role") == role]


def list_temporary_workers():
    return list_workers_by_role("temporary")


def list_local_workers():
    return list_workers_by_role("local")


def mark_worker_temporary(worker_uuid, owner_info, request_id):
    metadata = {
        "role": "temporary",
        "owner_master_uuid": owner_info.get("owner_master_uuid"),
        "owner_master_name": owner_info.get("owner_master_name"),
        "owner_master_host": owner_info.get("owner_master_host"),
        "owner_master_port": owner_info.get("owner_master_port"),
        "borrow_request_id": request_id,
    }
    with worker_state_lock:
        if worker_uuid in workers:
            worker_metadata[worker_uuid] = metadata


def mark_worker_local(worker_uuid, conn, extra_metadata=None):
    metadata = {"role": "local"}
    if extra_metadata:
        metadata.update(extra_metadata)
    store_worker_session(worker_uuid, conn, metadata)


def maybe_register_borrowed_worker(msg, worker_uuid, conn):
    payload = protocol_payload(msg)
    owner_uuid = payload.get("ORIGINAL_MASTER_UUID") or msg.get("SERVER_UUID")
    owner_name = payload.get("ORIGINAL_MASTER_NAME")
    owner_host = payload.get("ORIGINAL_MASTER_HOST")
    owner_port = payload.get("ORIGINAL_MASTER_PORT")
    if owner_uuid:
        store_worker_session(
            worker_uuid,
            conn,
            {
                "role": "temporary",
                "owner_master_uuid": owner_uuid,
                "owner_master_name": owner_name,
                "owner_master_host": owner_host,
                "owner_master_port": owner_port,
                "borrow_request_id": payload.get("REQUEST_ID") or payload.get("request_id"),
            },
        )


def send_notify_worker_returned(owner_info, worker_uuid, request_id, borrowed_master_uuid, borrowed_master_name):
    host = owner_info.get("owner_master_host")
    port = owner_info.get("owner_master_port")
    if host is None or port is None:
        return

    payload = {
        "worker_uuid": worker_uuid,
        "owner_master_uuid": owner_info.get("owner_master_uuid"),
        "owner_master_name": owner_info.get("owner_master_name"),
        "borrowed_master_uuid": borrowed_master_uuid,
        "borrowed_master_name": borrowed_master_name,
        "borrowed_master_host": MASTER_HOST,
        "borrowed_master_port": MASTER_PORT,
    }
    message = build_protocol_message("notify_worker_returned", payload, request_id)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SPRINT3_HELP_TIMEOUT)
        sock.connect((host, int(port)))
        send(sock, message)
        sock.close()
        print(f"[MASTER] notify_worker_returned enviado para {host}:{port} sobre {worker_uuid[:8]}.")
    except OSError as error:
        print(f"[MASTER] Falha ao notificar retorno do Worker {worker_uuid[:8]} para {host}:{port} - {error}")


def release_temporary_workers_if_needed():
    with pending_lock:
        current_pending = pending

    if current_pending > RELEASE_THRESHOLD:
        return

    temporary_workers = list_temporary_workers()
    if not temporary_workers:
        return

    print(
        f"[MASTER] Carga normalizada ({current_pending} pendentes). "
        f"Liberando {len(temporary_workers)} worker(s) emprestado(s)..."
    )

    for worker_uuid in temporary_workers:
        with worker_state_lock:
            metadata = worker_metadata.get(worker_uuid, {}).copy()
            conn = workers.get(worker_uuid)

        if conn is None:
            remove_worker_session(worker_uuid)
            continue

        request_id = metadata.get("borrow_request_id") or str(uuid.uuid4())
        owner_payload = {
            "return_to_master_uuid": metadata.get("owner_master_uuid"),
            "return_to_master_name": metadata.get("owner_master_name"),
            "return_to_master_host": metadata.get("owner_master_host"),
            "return_to_master_port": metadata.get("owner_master_port"),
            "worker_uuid": worker_uuid,
            "borrowed_master_uuid": SERVER_UUID,
            "borrowed_master_name": MASTER_NAME,
            "borrowed_master_host": MASTER_HOST,
            "borrowed_master_port": MASTER_PORT,
        }

        send(conn, build_protocol_message("command_release", owner_payload, request_id))
        remove_worker_session(worker_uuid)
        send_notify_worker_returned(metadata, worker_uuid, request_id, SERVER_UUID, MASTER_NAME)
        print(f"[MASTER] Worker {worker_uuid[:8]} liberado e redirecionado de volta ao Master original.")


def build_help_request_payload(current_pending, workers_needed):
    return {
        "master_uuid": SERVER_UUID,
        "master_name": MASTER_NAME,
        "master_host": MASTER_HOST,
        "master_port": MASTER_PORT,
        "current_load": current_pending,
        "saturation_threshold": LOAD_THRESHOLD,
        "release_threshold": RELEASE_THRESHOLD,
        "workers_needed": workers_needed,
        "local_workers": len(list_local_workers()),
    }


def select_workers_to_lend(requested_workers):
    available_workers = list_local_workers()
    available_workers.sort()
    return available_workers[:requested_workers]


def send_controlled_worker_redirect(worker_uuid, worker_info, request_id, requester_payload):
    conn = get_worker_connection(worker_uuid)
    if conn is None:
        return False

    payload = {
        "worker_uuid": worker_uuid,
        "new_master_uuid": requester_payload.get("master_uuid"),
        "new_master_name": requester_payload.get("master_name"),
        "new_master_host": requester_payload.get("master_host"),
        "new_master_port": requester_payload.get("master_port"),
        "original_master_uuid": SERVER_UUID,
        "original_master_name": MASTER_NAME,
        "original_master_host": MASTER_HOST,
        "original_master_port": MASTER_PORT,
        "request_id": request_id,
    }

    send(conn, build_protocol_message("command_redirect", payload, request_id))
    remove_worker_session(worker_uuid)

    with borrowed_outgoing_workers_lock:
        borrowed_outgoing_workers[worker_uuid] = {
            "request_id": request_id,
            "target_master_uuid": requester_payload.get("master_uuid"),
            "target_master_name": requester_payload.get("master_name"),
            "target_master_host": requester_payload.get("master_host"),
            "target_master_port": requester_payload.get("master_port"),
        }

    print(
        f"[MASTER] Worker {worker_uuid[:8]} redirecionado para "
        f"{requester_payload.get('master_name')} ({requester_payload.get('master_host')}:{requester_payload.get('master_port')})."
    )
    return True


def maybe_request_help(current_pending):
    global help_request_in_progress

    with help_request_lock:
        if help_request_in_progress:
            return
        help_request_in_progress = True

    thread = threading.Thread(target=ask_for_help, args=(current_pending,), daemon=True)
    thread.start()


def finish_help_request():
    global help_request_in_progress
    with help_request_lock:
        help_request_in_progress = False


def decode_datagram(data):
    try:
        return json.loads(data.decode().strip())
    except Exception:
        return None


def valid_heartbeat(msg):
    if not isinstance(msg, dict):
        return False
    if msg.get("TASK") == "HEARTBEAT":
        server_uuid = msg.get("SERVER_UUID")
        if not isinstance(server_uuid, str) or not server_uuid.strip():
            return False
        return True
    if msg.get("WORKER") == "ALIVE":
        worker_uuid = msg.get("WORKER_UUID")
        if not isinstance(worker_uuid, str) or not worker_uuid.strip():
            return False
        return True
    return False


def build_alive_response():
    return {"SERVER_UUID": SERVER_UUID, "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"}


def valid_discovery_request(msg):
    if not isinstance(msg, dict):
        return False
    if msg.get("TYPE") != "DISCOVERY":
        return False
    worker_uuid = msg.get("WORKER_UUID")
    return isinstance(worker_uuid, str) and worker_uuid.strip()


def build_discovery_reply():
    return {
        "TYPE": "DISCOVERY_REPLY",
        "MASTER_NAME": MASTER_NAME,
        "MASTER_IP": MASTER_HOST,
        "MASTER_PORT": MASTER_PORT,
        "STATUS": "AVAILABLE",
        "SERVER_UUID": SERVER_UUID,
    }


def valid_election_ack(msg):
    if not isinstance(msg, dict):
        return False
    if msg.get("TYPE") != "ELECTION_ACK":
        return False
    worker_uuid = msg.get("WORKER_UUID")
    selected_master = msg.get("SELECTED_MASTER")
    if not isinstance(worker_uuid, str) or not worker_uuid.strip():
        return False
    if not isinstance(selected_master, str) or not selected_master.strip():
        return False
    return True


def build_election_ack_response(worker_uuid):
    return {
        "TYPE": "ELECTION_ACK",
        "STATUS": "ACCEPTED",
        "MASTER_NAME": MASTER_NAME,
        "MASTER_IP": MASTER_HOST,
        "MASTER_PORT": MASTER_PORT,
        "SERVER_UUID": SERVER_UUID,
        "WORKER_UUID": worker_uuid,
    }


def borrowed_worker(msg):
    server_uuid = msg.get("SERVER_UUID")
    return isinstance(server_uuid, str) and server_uuid.strip() and server_uuid != SERVER_UUID


def enqueue_task(task_id, user, force_nok=False):
    # Fila da Sprint 2: cada item guarda a tarefa e metadados de simulacao.
    with task_queue_lock:
        task_queue.append({"TASK_ID": task_id, "USER": user, "FORCE_NOK": force_nok})


def dequeue_task():
    with task_queue_lock:
        if not task_queue:
            return None
        return task_queue.pop(0)


def dispatch_next_task(conn, worker_uuid):
    task = dequeue_task()
    if task is None:
        # Quando nao ha trabalho pendente, o Master responde explicitamente.
        send(conn, {"TASK": "NO_TASK", "SERVER_UUID": SERVER_UUID})
        print(f"[MASTER] Sem tarefa para o Worker {worker_uuid[:8]}.")
        return

    # Quando ha fila, o Master entrega uma QUERY para o Worker processar.
    send(
        conn,
        {
            "TASK": "QUERY",
            "USER": task["USER"],
            "TASK_ID": task["TASK_ID"],
            "FORCE_NOK": task["FORCE_NOK"],
            "SERVER_UUID": SERVER_UUID,
        },
    )
    print(f"[MASTER] Enviando {task['TASK_ID']} para Worker {worker_uuid[:8]} | USER={task['USER']}")


def valid_status_report(msg):
    if not isinstance(msg, dict):
        return False

    required = ("STATUS", "TASK", "WORKER_UUID")
    for key in required:
        if key not in msg:
            return False

    status = msg.get("STATUS")
    task = msg.get("TASK")
    worker_uuid = msg.get("WORKER_UUID")

    if status not in {"OK", "NOK"}:
        return False
    if task != "QUERY":
        return False
    if not isinstance(worker_uuid, str) or not worker_uuid.strip():
        return False

    return True


def handle_worker(worker_uuid, conn, first_msg=None):
    global pending
    msg = first_msg
    while True:
        if msg is None:
            msg = receive(conn)
        if msg is None:
            print(f"[MASTER] Worker {worker_uuid[:8]} desconectou.")
            remove_worker_session(worker_uuid)
            try:
                conn.close()
            except OSError:
                pass
            return

        message_type = protocol_message_type(msg)

        if message_type == "ELECTION_ACK":
            if not valid_election_ack(msg):
                print(f"[MASTER] ELECTION_ACK invalido de {worker_uuid[:8]}. Encerrando conexao.")
                remove_worker_session(worker_uuid)
                try:
                    conn.close()
                except OSError:
                    pass
                return
            if msg.get("SELECTED_MASTER") != MASTER_NAME:
                print(
                    f"[MASTER] Worker {worker_uuid[:8]} escolheu {msg.get('SELECTED_MASTER')} em vez de {MASTER_NAME}."
                )
                send(
                    conn,
                    {
                        "TYPE": "ELECTION_ACK",
                        "STATUS": "REJECTED",
                        "MASTER_NAME": MASTER_NAME,
                        "SERVER_UUID": SERVER_UUID,
                        "WORKER_UUID": worker_uuid,
                    },
                )
                remove_worker_session(worker_uuid)
                try:
                    conn.close()
                except OSError:
                    pass
                return

            store_worker_session(worker_uuid, conn, {"role": "local"})
            print(f"[MASTER] ELECTION_ACK recebido de {worker_uuid[:8]} para {MASTER_NAME}.")
            send(conn, build_election_ack_response(worker_uuid))
            msg = None
            continue

        if msg.get("TASK") == "HEARTBEAT" or msg.get("WORKER") == "ALIVE":
            if not valid_heartbeat(msg):
                print("[MASTER] HEARTBEAT/APRESENTACAO invalido: campos obrigatorios ausentes.")
                remove_worker_session(worker_uuid)
                try:
                    conn.close()
                except OSError:
                    pass
                return
            if msg.get("WORKER") == "ALIVE":
                origem = "emprestado" if borrowed_worker(msg) else "local"
                if borrowed_worker(msg):
                    maybe_register_borrowed_worker(msg, worker_uuid, conn)
                else:
                    mark_worker_local(worker_uuid, conn)
                print(f"[MASTER] Worker {origem} {worker_uuid[:8]} apresentado.")
                # Na apresentacao, o Master ja libera a primeira tarefa da fila.
                dispatch_next_task(conn, worker_uuid)
            else:
                send(conn, build_alive_response())

                # Apos o heartbeat, o Master pode liberar outra tarefa, se houver.
                dispatch_next_task(conn, worker_uuid)

        elif "STATUS" in msg or msg.get("TASK") == "QUERY":
            if not valid_status_report(msg):
                print(f"[MASTER] Status invalido de {worker_uuid[:8]}. Encerrando conexao.")
                remove_worker_session(worker_uuid)
                try:
                    conn.close()
                except OSError:
                    pass
                return

            task_id = msg.get("TASK_ID", "SEM_ID")
            status = msg.get("STATUS")
            with pending_lock:
                pending = max(0, pending - 1)
            print(f"[MASTER] Tarefa {task_id} concluida por {worker_uuid[:8]} com status {status}. Pendentes: {pending}")
            # O ACK final fecha o ciclo de confirmacao pedido na Sprint 2.
            send(conn, {"STATUS": "ACK", "WORKER_UUID": worker_uuid, "TASK_ID": task_id})
            release_temporary_workers_if_needed()

        elif msg.get("TASK") == "task_done":
            task_id = msg.get("TASK_ID")
            with pending_lock:
                pending = max(0, pending - 1)
            print(f"[MASTER] Tarefa {task_id} concluida por {worker_uuid[:8]}. Pendentes: {pending}")
            release_temporary_workers_if_needed()

        elif message_type == "register_worker" or message_type == "register_temporary_worker":
            wid = msg.get("WORKER_UUID", worker_uuid)
            if message_type == "register_temporary_worker":
                maybe_register_borrowed_worker(msg, wid, conn)
                print(f"[MASTER] Worker temporario {wid[:8]} registrado.")
            else:
                mark_worker_local(wid, conn)
                print(f"[MASTER] Worker {wid[:8]} registrado.")

            dispatch_next_task(conn, wid)

        msg = None


def discovery_loop():
    udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_server.bind((MASTER_BIND_HOST, DISCOVERY_PORT))
    print(f"[MASTER] Descoberta UDP ativa em {MASTER_BIND_HOST}:{DISCOVERY_PORT} | nome={MASTER_NAME}")

    while True:
        data, addr = udp_server.recvfrom(4096)
        msg = decode_datagram(data)
        if not valid_discovery_request(msg):
            print(f"[MASTER] Discovery invalido de {addr}. Ignorando.")
            continue

        reply = build_discovery_reply()
        sendto_payload = (json.dumps(reply) + "\n").encode()
        udp_server.sendto(sendto_payload, addr)
        print(f"[MASTER] Discovery reply enviado para {msg['WORKER_UUID'][:8]} em {addr[0]}:{addr[1]}.")


# ── Aceita conexoes de Workers ───────────────────────────────
def accept_loop():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((MASTER_BIND_HOST, MASTER_PORT))
    server.listen(20)
    print(f"[MASTER] Escutando em {MASTER_BIND_HOST}:{MASTER_PORT} | anunciado como {MASTER_HOST}:{MASTER_PORT}")

    while True:
        conn, addr = server.accept()
        msg = receive(conn)
        if msg is None:
            conn.close()
            continue

        task = msg.get("TASK", "")
        message_type = protocol_message_type(msg)
        worker_uuid = msg.get("WORKER_UUID") or msg.get("SERVER_UUID") or str(uuid.uuid4())

        # Heartbeat, apresentacao ou primeiro ACK da eleicao do Worker.
        if task == "HEARTBEAT" or msg.get("WORKER") == "ALIVE" or message_type == "ELECTION_ACK":
            if message_type == "ELECTION_ACK":
                print(f"[MASTER] Worker {worker_uuid[:8]} iniciou handshake de eleicao de {addr}.")
            elif msg.get("WORKER") == "ALIVE":
                origem = "emprestado" if borrowed_worker(msg) else "proprio"
                print(f"[MASTER] Worker {origem} {worker_uuid[:8]} apresentou-se de {addr}.")
            else:
                print(f"[MASTER] Heartbeat recebido de {worker_uuid[:8]}.")
            if msg.get("WORKER") == "ALIVE" and borrowed_worker(msg):
                maybe_register_borrowed_worker(msg, worker_uuid, conn)
            elif msg.get("WORKER") == "ALIVE":
                mark_worker_local(worker_uuid, conn)
            elif message_type == "ELECTION_ACK":
                store_worker_session(worker_uuid, conn, {"role": "local"})
            threading.Thread(target=handle_worker, args=(worker_uuid, conn, msg), daemon=True).start()

        # Worker se registrando.
        elif "register" in task or message_type == "register_temporary_worker":
            if message_type == "register_temporary_worker":
                kind = "temporario"
                maybe_register_borrowed_worker(msg, worker_uuid, conn)
            else:
                kind = "proprio"
                mark_worker_local(worker_uuid, conn)
            print(f"[MASTER] Worker {kind} {worker_uuid[:8]} conectado de {addr}.")
            threading.Thread(target=handle_worker, args=(worker_uuid, conn, msg), daemon=True).start()

        # Master vizinho pedindo ajuda.
        elif task == "request_help" or message_type == "request_help":
            if SPRINT1_HEARTBEAT_ONLY:
                print("[MASTER] Modo Sprint 1: ignorando request_help.")
                conn.close()
                continue
            handle_help_request(conn, msg)

        # Master vizinho liberando workers emprestados.
        elif task == "command_release" or message_type == "command_release":
            if SPRINT1_HEARTBEAT_ONLY:
                print("[MASTER] Modo Sprint 1: ignorando command_release.")
                conn.close()
                continue
            print("[MASTER] Vizinho liberou os workers. Redirecionando de volta.")
            conn.close()

        elif message_type == "notify_worker_returned":
            payload = protocol_payload(msg)
            worker_returned_uuid = payload.get("worker_uuid") or worker_uuid
            with borrowed_outgoing_workers_lock:
                borrowed_outgoing_workers.pop(worker_returned_uuid, None)
            print(f"[MASTER] Worker {worker_returned_uuid[:8]} retornou do empréstimo.")
            conn.close()


# ── Gera requisicoes e envia para workers disponiveis ────────
def load_generator():
    global pending
    users = ["User1", "User2", "User3", "User4"]
    count = 0
    while True:
        time.sleep(REQUEST_INTERVAL)

        task_id = f"TASK-{count:04d}"
        user = users[count % len(users)]
        force_nok = (count % 5 == 0)
        count += 1

        # Em vez de enviar direto, a Sprint 2 usa uma fila interna de tarefas.
        enqueue_task(task_id, user, force_nok)

        with pending_lock:
            pending += 1
            current_pending = pending

        print(f"[MASTER] Tarefa {task_id} enfileirada para {user}. Pendentes: {current_pending}")

        # Verifica saturacao da mesma forma, agora com base na fila.
        if current_pending > LOAD_THRESHOLD:
            print(f"[MASTER] SATURADO! ({current_pending} pendentes). Pedindo ajuda...")
            maybe_request_help(current_pending)

        release_temporary_workers_if_needed()


# ── Pede ajuda a um Master vizinho ───────────────────────────
def ask_for_help(current_pending):
    global help_request_in_progress

    requested_workers = max(1, current_pending - LOAD_THRESHOLD)
    requested_workers = max(requested_workers, SPRINT3_DEFAULT_WORKERS_TO_BORROW)
    request_id = str(uuid.uuid4())

    for (host, port) in NEIGHBOR_MASTERS:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(SPRINT3_HELP_TIMEOUT)
            sock.connect((host, port))
            payload = build_help_request_payload(current_pending, requested_workers)
            send(sock, build_protocol_message("request_help", payload, request_id))

            resp = receive(sock)
            if resp and protocol_message_type(resp) == "response_accepted" and protocol_request_id(resp) == request_id:
                response_payload = protocol_payload(resp)
                print(
                    f"[MASTER] Vizinho {host}:{port} aceitou ajudar com "
                    f"{response_payload.get('workers_offered', 0)} worker(s)."
                )
                sock.close()
                break
            elif resp and protocol_message_type(resp) == "response_rejected" and protocol_request_id(resp) == request_id:
                response_payload = protocol_payload(resp)
                reason = response_payload.get("reason", "sem motivo informado")
                print(f"[MASTER] Vizinho {host}:{port} rejeitou: {reason}")
                sock.close()
            else:
                print(f"[MASTER] Vizinho {host}:{port} nao respondeu adequadamente ao pedido de ajuda.")
                sock.close()
        except OSError as e:
            print(f"[MASTER] Nao conectou ao vizinho {host}:{port} — {e}")
    finish_help_request()


# ── Responde pedido de ajuda de outro Master ─────────────────
def handle_help_request(conn, msg):
    request_id = protocol_request_id(msg) or str(uuid.uuid4())
    payload = protocol_payload(msg)
    workers_needed = int(payload.get("workers_needed", SPRINT3_DEFAULT_WORKERS_TO_BORROW))
    selected_workers = select_workers_to_lend(workers_needed)

    if selected_workers:
        requester_payload = {
            "master_uuid": payload.get("master_uuid"),
            "master_name": payload.get("master_name"),
            "master_host": payload.get("master_host"),
            "master_port": payload.get("master_port"),
        }
        worker_details = [{"worker_uuid": worker_uuid} for worker_uuid in selected_workers]

        print(f"[MASTER] Aceitei ajudar o Master {requester_payload.get('master_name')}.")
        response_payload = {
            "master_uuid": SERVER_UUID,
            "master_name": MASTER_NAME,
            "workers_offered": len(selected_workers),
            "worker_details": worker_details,
        }
        send(conn, build_protocol_message("response_accepted", response_payload, request_id))

        for worker_uuid in selected_workers:
            send_controlled_worker_redirect(worker_uuid, {}, request_id, requester_payload)
    else:
        print("[MASTER] Sem workers locais para emprestar. Rejeitando.")
        rejection_payload = {
            "master_uuid": SERVER_UUID,
            "master_name": MASTER_NAME,
            "reason": "no_local_workers_available",
        }
        send(conn, build_protocol_message("response_rejected", rejection_payload, request_id))
    conn.close()


# ── Entry point ──────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[MASTER] Iniciando | UUID: {SERVER_UUID} | nome: {MASTER_NAME}")
    print(f"[MASTER] Suba workers com: python worker.py 127.0.0.1 {MASTER_PORT}")
    threading.Thread(target=discovery_loop, daemon=True).start()
    if SPRINT1_HEARTBEAT_ONLY:
        print("[MASTER] Modo Sprint 1 ativo: apenas HEARTBEAT para demonstracao.")
        accept_loop()
    else:
        threading.Thread(target=accept_loop, daemon=True).start()
        load_generator()
