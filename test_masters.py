#!/usr/bin/env python3
"""
test_masters.py — verifica conectividade e protocolo entre os dois masters.

Uso:
  # Testa Master 6 (este lado que vai emprestar workers):
  python test_masters.py 10.62.206.49 5000

  # Testa Master 66 (outro lado que vai pedir ajuda) — rode na outra maquina:
  python test_masters.py 10.62.206.48 5000

  # Teste completo do fluxo de emprestimo (rode nesta maquina, com Master 6 rodando):
  python test_masters.py 10.62.206.49 5000 --help-request
"""

import json
import socket
import sys
import uuid

TIMEOUT = 5.0
FAKE_MASTER_UUID = str(uuid.uuid4())
FAKE_MASTER_NAME = "master_66_teste"


def send(sock, payload):
    sock.sendall((json.dumps(payload) + "\n").encode())


def receive(sock):
    data = b""
    sock.settimeout(TIMEOUT)
    while b"\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            return None
        data += chunk
    return json.loads(data.split(b"\n")[0])


def check_tcp(host, port):
    print(f"\n[1] Conectividade TCP em {host}:{port} ...")
    try:
        sock = socket.create_connection((host, port), timeout=TIMEOUT)
        sock.close()
        print(f"    OK — porta acessivel")
        return True
    except OSError as e:
        print(f"    FALHA — {e}")
        print("    Verifique: master esta rodando? Firewall bloqueando a porta?")
        return False


def check_udp_discovery(host, port):
    print(f"\n[2] UDP Discovery em {host}:{port} ...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)
    probe = (json.dumps({"TYPE": "DISCOVERY", "WORKER_UUID": str(uuid.uuid4())}) + "\n").encode()
    try:
        sock.sendto(probe, (host, port))
        data, addr = sock.recvfrom(4096)
        msg = json.loads(data.decode().strip())
        if msg.get("TYPE") == "DISCOVERY_REPLY":
            print(f"    OK — Master respondeu: nome={msg.get('MASTER_NAME')} ip={msg.get('MASTER_IP')}:{msg.get('MASTER_PORT')}")
            return True
        else:
            print(f"    Resposta inesperada: {msg}")
            return False
    except socket.timeout:
        print("    FALHA — sem resposta UDP (timeout)")
        print("    Verifique: porta UDP esta aberta? SO_BROADCAST permitido?")
        return False
    except OSError as e:
        print(f"    FALHA — {e}")
        return False
    finally:
        sock.close()


def check_help_request(host, port):
    print(f"\n[3] Protocolo request_help em {host}:{port} ...")
    print("    (simula Master 66 pedindo workers emprestados ao Master 6)")
    try:
        sock = socket.create_connection((host, port), timeout=TIMEOUT)
        request_id = str(uuid.uuid4())
        payload = {
            "master_uuid": FAKE_MASTER_UUID,
            "master_name": FAKE_MASTER_NAME,
            "master_host": "10.62.206.48",
            "master_port": 5000,
            "current_load": 8,
            "saturation_threshold": 5,
            "release_threshold": 3,
            "workers_needed": 1,
            "local_workers": 0,
        }
        msg = {"type": "request_help", "request_id": request_id, "payload": payload}
        send(sock, msg)
        resp = receive(sock)
        sock.close()

        if resp is None:
            print("    FALHA — sem resposta do Master")
            return False

        resp_type = resp.get("type") or resp.get("TYPE")
        resp_id = resp.get("request_id") or resp.get("REQUEST_ID")

        if resp_type == "response_accepted" and resp_id == request_id:
            rp = resp.get("payload", {})
            offered = rp.get("workers_offered", 0)
            print(f"    OK — Master ACEITOU ajudar | workers_offered={offered}")
            if offered == 0:
                print("    AVISO: nenhum worker disponivel para emprestar ainda")
                print("    Inicie os workers (iniciar_worker.bat) antes de testar este passo")
            return True
        elif resp_type == "response_rejected" and resp_id == request_id:
            rp = resp.get("payload", {})
            reason = rp.get("reason", "desconhecido")
            print(f"    AVISO — Master rejeitou: {reason}")
            print("    Inicie os workers (iniciar_worker.bat) e tente novamente")
            return True  # protocolo funcionou, so nao tem workers
        else:
            print(f"    FALHA — resposta inesperada: {resp}")
            return False

    except OSError as e:
        print(f"    FALHA — {e}")
        return False


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    host = args[0]
    port = int(args[1]) if len(args) > 1 else 5000
    run_help = "--help-request" in args

    print("=" * 55)
    print(f"  Testando Master em {host}:{port}")
    print("=" * 55)

    tcp_ok = check_tcp(host, port)
    if not tcp_ok:
        print("\nAbortando: sem conectividade TCP basica.")
        sys.exit(1)

    check_udp_discovery(host, port)

    if run_help:
        check_help_request(host, port)

    print("\n" + "=" * 55)
    print("  Dica: rode com --help-request para testar o protocolo")
    print("  de emprestimo de workers (Master 6 precisa estar rodando")
    print("  e com workers conectados)")
    print("=" * 55)


if __name__ == "__main__":
    main()
