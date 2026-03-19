#!/usr/bin/env python3
"""
Tribal Chief — WebSocket-to-SSH Bridge
Listens on 127.0.0.1:10015, upgrades HTTP/WS connections,
then tunnels traffic transparently to local SSH (port 22).
"""

import socket
import threading
import logging
import time
from collections import defaultdict

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    filename='/opt/tribal/logs/wsbridge.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

# ── Rate Limiting ───────────────────────────────────────────────────────────
RATE_LIMIT     = 15        # max new connections per IP per minute
BUFFER_SIZE    = 8192      # bytes per recv call
SOCKET_TIMEOUT = 300       # seconds of inactivity before disconnect

_rate_lock          = threading.Lock()
_connection_counts  = defaultdict(list)

def is_rate_limited(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        _connection_counts[ip] = [t for t in _connection_counts[ip] if now - t < 60]
        _connection_counts[ip].append(now)
        return len(_connection_counts[ip]) > RATE_LIMIT

# ── Connection counter ──────────────────────────────────────────────────────
_active_lock        = threading.Lock()
_active_connections = 0

def inc_active():
    global _active_connections
    with _active_lock:
        _active_connections += 1

def dec_active():
    global _active_connections
    with _active_lock:
        _active_connections -= 1

# ── Core forwarding ─────────────────────────────────────────────────────────

def forward(src: socket.socket, dst: socket.socket, label: str):
    """Pipe bytes from src → dst until either side closes."""
    try:
        while True:
            data = src.recv(BUFFER_SIZE)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                s.close()
            except Exception:
                pass

def handle_client(client_socket: socket.socket, addr):
    ip = addr[0]

    if is_rate_limited(ip):
        log.warning(f"Rate limited: {ip}")
        try:
            client_socket.close()
        except Exception:
            pass
        return

    inc_active()
    ssh_socket = None

    try:
        client_socket.settimeout(SOCKET_TIMEOUT)

        # Connect to local SSH daemon
        ssh_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ssh_socket.settimeout(10)
        ssh_socket.connect(('127.0.0.1', 22))
        ssh_socket.settimeout(SOCKET_TIMEOUT)

        # Peek at the first chunk to detect HTTP upgrade requests
        data = client_socket.recv(BUFFER_SIZE)
        if not data:
            return

        if b"HTTP" in data and b"Upgrade" in data:
            # WebSocket upgrade — send 101 and start tunneling
            # Do NOT forward the HTTP headers to SSH
            ws_response = (
                b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\n"
                b"Connection: Upgrade\r\n"
                b"\r\n"
            )
            client_socket.sendall(ws_response)
            log.info(f"WS upgrade accepted: {ip} — active={_active_connections}")
        else:
            # Raw TCP / non-WS connection — forward first chunk directly
            ssh_socket.sendall(data)
            log.info(f"Raw TCP tunnel: {ip} — active={_active_connections}")

        # Spawn bidirectional forwarding threads
        t1 = threading.Thread(
            target=forward,
            args=(client_socket, ssh_socket, f"{ip}→SSH"),
            daemon=True
        )
        t2 = threading.Thread(
            target=forward,
            args=(ssh_socket, client_socket, f"SSH→{ip}"),
            daemon=True
        )
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    except Exception as e:
        log.debug(f"Connection error from {ip}: {e}")
    finally:
        for s in (client_socket, ssh_socket):
            if s:
                try:
                    s.close()
                except Exception:
                    pass
        dec_active()

# ── Server ──────────────────────────────────────────────────────────────────

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('127.0.0.1', 10015))
    server.listen(256)
    log.info("WebSocket bridge started on 127.0.0.1:10015")
    print("[✔] WS Bridge running on 127.0.0.1:10015 — logs: /opt/tribal/logs/wsbridge.log")

    try:
        while True:
            try:
                client, addr = server.accept()
                threading.Thread(
                    target=handle_client,
                    args=(client, addr),
                    daemon=True
                ).start()
            except Exception as e:
                log.error(f"Accept error: {e}")
    except KeyboardInterrupt:
        log.info("Bridge stopped by user.")
    finally:
        server.close()

if __name__ == "__main__":
    main()
