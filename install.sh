#!/bin/bash
# ============================================================
#   TRIBAL CHIEF SSH — Installer & Deployment Script
#   Deploys: panel, WebSocket bridge, auto-limiter, expiry cron
# ============================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────
RED='\e[31m'
GREEN='\e[32m'
YELLOW='\e[33m'
CYAN='\e[36m'
BOLD='\e[1m'
RESET='\e[0m'

ok()   { echo -e "${GREEN}[✔]${RESET} $1"; }
info() { echo -e "${YELLOW}[*]${RESET} $1"; }
err()  { echo -e "${RED}[✘]${RESET} $1"; }
hdr()  { echo -e "\n${BOLD}${CYAN}══════════════════════════════════════${RESET}"; \
         echo -e "${BOLD}${CYAN}  $1${RESET}"; \
         echo -e "${BOLD}${CYAN}══════════════════════════════════════${RESET}"; }

# ── Root check ────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    err "This installer must be run as root."
    exit 1
fi

# ── Uninstall mode ────────────────────────────────────────────────────────
if [[ "${1:-}" == "--uninstall" ]]; then
    hdr "Uninstalling Tribal Chief"
    systemctl stop wsbridge 2>/dev/null || true
    systemctl disable wsbridge 2>/dev/null || true
    rm -f /etc/systemd/system/wsbridge.service
    systemctl daemon-reload
    crontab -l 2>/dev/null | grep -v 'tribal-chief' | crontab - || true
    rm -rf /root/tribal-chief /opt/tribal
    sed -i "/alias chief=/d" ~/.bashrc
    ok "Tribal Chief uninstalled successfully."
    exit 0
fi

INSTALL_DIR="/root/tribal-chief"
DATA_DIR="/opt/tribal"
LOG_DIR="${DATA_DIR}/logs"
DB_DIR="${DATA_DIR}/database"

hdr "TRIBAL CHIEF — Deployment Starting"

# ── Step 1: System update & packages ─────────────────────────────────────
hdr "Step 1: System Update & Dependencies"
info "Updating package lists..."
apt-get update -y -qq

info "Installing system packages..."
apt-get install -y -qq \
    python3 python3-pip curl wget git \
    ufw cron certbot python3-certbot-nginx \
    vnstat speedtest-cli

ok "System packages installed."

# ── Step 2: Python modules ────────────────────────────────────────────────
hdr "Step 2: Python Modules"
info "Installing Python dependencies..."
pip3 install rich bcrypt psutil --break-system-packages -q 2>/dev/null \
    || pip3 install rich bcrypt psutil -q
ok "Python modules installed."

# ── Step 3: Directory structure ───────────────────────────────────────────
hdr "Step 3: Directory Structure"
mkdir -p "${INSTALL_DIR}" \
         "${LOG_DIR}" \
         "${DB_DIR}" \
         "${DATA_DIR}/core" \
         "${DATA_DIR}/modules" \
         "${DATA_DIR}/utils"
ok "Directories created."

# ── Step 4: Clone / update panel ─────────────────────────────────────────
hdr "Step 4: Panel Script"
# If already present, skip re-download (allows self-contained deploys)
if [[ ! -f "${INSTALL_DIR}/tribal_cli.py" ]]; then
    info "Panel script not found at ${INSTALL_DIR}/tribal_cli.py"
    info "Place tribal_cli.py in ${INSTALL_DIR}/ and re-run, or clone your repo:"
    echo -e "  ${CYAN}git clone https://github.com/YOUR_USERNAME/tribal-chief ${INSTALL_DIR}${RESET}"
    info "Continuing with other components..."
else
    chmod +x "${INSTALL_DIR}/tribal_cli.py"
    ok "Panel script found and made executable."
fi

# ── Step 5: WebSocket Bridge ──────────────────────────────────────────────
hdr "Step 5: WebSocket Bridge (port 10015)"
info "Writing wsbridge.py..."

cat << 'PYEOF' > "${INSTALL_DIR}/wsbridge.py"
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

logging.basicConfig(
    filename='/opt/tribal/logs/wsbridge.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

RATE_LIMIT     = 15
BUFFER_SIZE    = 8192
SOCKET_TIMEOUT = 300

_rate_lock          = threading.Lock()
_connection_counts  = defaultdict(list)

def is_rate_limited(ip):
    now = time.time()
    with _rate_lock:
        _connection_counts[ip] = [t for t in _connection_counts[ip] if now - t < 60]
        _connection_counts[ip].append(now)
        return len(_connection_counts[ip]) > RATE_LIMIT

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

def forward(src, dst, label):
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
            try: s.shutdown(socket.SHUT_RDWR)
            except Exception: pass
            try: s.close()
            except Exception: pass

def handle_client(client_socket, addr):
    ip = addr[0]
    if is_rate_limited(ip):
        log.warning(f"Rate limited: {ip}")
        try: client_socket.close()
        except Exception: pass
        return

    inc_active()
    ssh_socket = None
    try:
        client_socket.settimeout(SOCKET_TIMEOUT)
        ssh_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ssh_socket.settimeout(10)
        ssh_socket.connect(('127.0.0.1', 22))
        ssh_socket.settimeout(SOCKET_TIMEOUT)

        data = client_socket.recv(BUFFER_SIZE)
        if not data:
            return

        if b"HTTP" in data and b"Upgrade" in data:
            ws_response = (
                b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\n"
                b"Connection: Upgrade\r\n"
                b"\r\n"
            )
            client_socket.sendall(ws_response)
            log.info(f"WS upgrade: {ip} active={_active_connections}")
        else:
            ssh_socket.sendall(data)
            log.info(f"Raw TCP tunnel: {ip} active={_active_connections}")

        t1 = threading.Thread(target=forward, args=(client_socket, ssh_socket, f"{ip}->SSH"), daemon=True)
        t2 = threading.Thread(target=forward, args=(ssh_socket, client_socket, f"SSH->{ip}"), daemon=True)
        t1.start(); t2.start()
        t1.join(); t2.join()

    except Exception as e:
        log.debug(f"Error from {ip}: {e}")
    finally:
        for s in (client_socket, ssh_socket):
            if s:
                try: s.close()
                except Exception: pass
        dec_active()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('127.0.0.1', 10015))
    server.listen(256)
    log.info("WebSocket bridge started on 127.0.0.1:10015")
    print("[✔] WS Bridge running on 127.0.0.1:10015")
    try:
        while True:
            try:
                client, addr = server.accept()
                threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()
            except Exception as e:
                log.error(f"Accept error: {e}")
    except KeyboardInterrupt:
        log.info("Bridge stopped.")
    finally:
        server.close()

if __name__ == "__main__":
    main()
PYEOF

chmod +x "${INSTALL_DIR}/wsbridge.py"
ok "wsbridge.py written."

# ── Step 6: Systemd service ───────────────────────────────────────────────
info "Registering wsbridge as a systemd service..."
cat << 'EOF' > /etc/systemd/system/wsbridge.service
[Unit]
Description=Tribal Chief WebSocket Bridge
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/tribal-chief
ExecStart=/usr/bin/python3 /root/tribal-chief/wsbridge.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable wsbridge --quiet
systemctl restart wsbridge
sleep 2

if systemctl is-active --quiet wsbridge; then
    ok "wsbridge service is running."
else
    err "wsbridge failed to start. Check: journalctl -u wsbridge -n 20"
fi

# ── Step 7: Cron limiter ──────────────────────────────────────────────────
hdr "Step 6: Auto-Limiter & Expiry Enforcer"
info "Writing cron_limiter.py..."

cat << 'PYEOF' > "${INSTALL_DIR}/cron_limiter.py"
#!/usr/bin/env python3
"""
Tribal Chief — Headless Auto-Limiter & Expiry Enforcer
Runs every minute via cron.
"""

import sqlite3
import subprocess
import os
import logging
from datetime import datetime

DB_PATH  = "/opt/tribal/database/chief.db"
LOG_PATH = "/opt/tribal/logs/cron_limiter.log"

os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

def count_sessions(username):
    try:
        raw = subprocess.check_output(
            f"who | grep -c '^{username} '",
            shell=True, stderr=subprocess.DEVNULL
        ).strip()
        return int(raw)
    except Exception:
        return 0

def kick_ssh_sessions(username):
    subprocess.run(f"pkill -9 -u {username} sshd",
                   shell=True, stderr=subprocess.DEVNULL)

def suspend_user(username):
    subprocess.run(['usermod', '-L', username], stderr=subprocess.DEVNULL)
    kick_ssh_sessions(username)

def is_account_locked(username):
    try:
        output = subprocess.check_output(
            ['passwd', '-S', username], text=True, stderr=subprocess.DEVNULL
        )
        return ' L ' in output
    except Exception:
        return False

def main():
    if not os.path.exists(DB_PATH):
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT username, expiry, conn_limit FROM users")
        users = c.fetchall()
        conn.close()
    except Exception as e:
        log.error(f"DB read error: {e}")
        return

    today = datetime.now().date()

    for username, expiry_str, limit in users:
        try:
            expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date()
            if expiry_date < today:
                if not is_account_locked(username):
                    suspend_user(username)
                    log.info(f"EXPIRED → suspended: {username} (expired {expiry_str})")
                continue
        except Exception as e:
            log.warning(f"Expiry parse error for {username}: {e}")

        try:
            sessions = count_sessions(username)
            if sessions > limit:
                kick_ssh_sessions(username)
                log.info(f"LIMIT EXCEEDED → kicked: {username} (sessions={sessions}, limit={limit})")
        except Exception as e:
            log.warning(f"Limit check error for {username}: {e}")

if __name__ == "__main__":
    main()
PYEOF

chmod +x "${INSTALL_DIR}/cron_limiter.py"
ok "cron_limiter.py written."

# Register both cron jobs (limiter every minute, expiry check daily at midnight)
info "Wiring cron jobs..."
( crontab -l 2>/dev/null \
    | grep -v 'tribal-chief' \
    ; echo "* * * * * /usr/bin/python3 /root/tribal-chief/cron_limiter.py >> /opt/tribal/logs/cron_limiter.log 2>&1" \
) | crontab -
ok "Cron jobs registered."

# ── Step 8: Firewall ──────────────────────────────────────────────────────
hdr "Step 7: Firewall"
info "Configuring UFW..."
# Failsafe: always ensure SSH is open before enabling
ufw allow 22/tcp   > /dev/null 2>&1
ufw allow 80/tcp   > /dev/null 2>&1
ufw allow 443/tcp  > /dev/null 2>&1
ufw allow 8080/tcp > /dev/null 2>&1
ufw allow 8443/tcp > /dev/null 2>&1
ufw --force enable > /dev/null 2>&1
ok "UFW enabled. Ports 22, 80, 443, 8080, 8443 open."

# ── Step 9: Global alias ──────────────────────────────────────────────────
hdr "Step 8: Global Command"
ALIAS_LINE="alias chief='python3 /root/tribal-chief/tribal_cli.py'"

# Add to ~/.bashrc if not already present
grep -qxF "${ALIAS_LINE}" ~/.bashrc || echo "${ALIAS_LINE}" >> ~/.bashrc

# Also add to /etc/profile.d/ for system-wide / non-interactive shells
echo "${ALIAS_LINE}" > /etc/profile.d/tribal_chief.sh
chmod +x /etc/profile.d/tribal_chief.sh

ok "'chief' command registered globally."

# ── Done ──────────────────────────────────────────────────────────────────
hdr "Deployment Complete"
echo -e "${GREEN}${BOLD}"
echo "  ✯ TRIBAL CHIEF ARCHITECTURE DEPLOYED ✯"
echo -e "${RESET}"
echo -e "  ${CYAN}WebSocket Bridge :${RESET} Running on 127.0.0.1:10015"
echo -e "  ${CYAN}Auto-Limiter     :${RESET} Cron active (every 1 min)"
echo -e "  ${CYAN}Expiry Enforcer  :${RESET} Built into cron_limiter"
echo -e "  ${CYAN}Logs             :${RESET} /opt/tribal/logs/"
echo -e "  ${CYAN}Database         :${RESET} /opt/tribal/database/chief.db"
echo ""
echo -e "  ${YELLOW}To launch the panel:${RESET}"
echo -e "  ${BOLD}source ~/.bashrc && chief${RESET}"
echo ""
echo -e "  ${YELLOW}To uninstall:${RESET}"
echo -e "  ${BOLD}bash install.sh --uninstall${RESET}"
echo ""
