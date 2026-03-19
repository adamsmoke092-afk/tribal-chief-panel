#!/usr/bin/env python3
"""
Tribal Chief — Headless Auto-Limiter & Expiry Enforcer
Designed to run every minute via cron.
  - Kicks users who exceed their session limit
  - Suspends users whose account has expired
"""

import sqlite3
import subprocess
import os
import logging
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────────
DB_PATH  = "/opt/tribal/database/chief.db"
LOG_PATH = "/opt/tribal/logs/cron_limiter.log"

# ── Logging ─────────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

def count_sessions(username: str) -> int:
    """Count active SSH sessions using 'who' — reliable across distros."""
    try:
        raw = subprocess.check_output(
            f"who | grep -c '^{username} '",
            shell=True,
            stderr=subprocess.DEVNULL
        ).strip()
        return int(raw)
    except Exception:
        return 0

def kick_ssh_sessions(username: str):
    """Kill only SSH sessions — does not touch other user processes."""
    subprocess.run(
        f"pkill -9 -u {username} sshd",
        shell=True,
        stderr=subprocess.DEVNULL
    )

def suspend_user(username: str):
    """Lock the Linux account and kill its SSH sessions."""
    subprocess.run(['usermod', '-L', username], stderr=subprocess.DEVNULL)
    kick_ssh_sessions(username)

def is_account_locked(username: str) -> bool:
    """Check if the Linux account is already locked."""
    try:
        output = subprocess.check_output(
            ['passwd', '-S', username],
            text=True,
            stderr=subprocess.DEVNULL
        )
        return ' L ' in output
    except Exception:
        return False

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(DB_PATH):
        log.debug("Database not found — skipping run.")
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
        # ── 1. Expiry check ────────────────────────────────────────────────
        try:
            expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date()
            if expiry_date < today:
                if not is_account_locked(username):
                    suspend_user(username)
                    log.info(f"EXPIRED → suspended: {username} (expired {expiry_str})")
                continue  # No need to check limits on an expired account
        except Exception as e:
            log.warning(f"Expiry parse error for {username}: {e}")

        # ── 2. Connection limit check ──────────────────────────────────────
        try:
            sessions = count_sessions(username)
            if sessions > limit:
                kick_ssh_sessions(username)
                log.info(f"LIMIT EXCEEDED → kicked: {username} "
                         f"(sessions={sessions}, limit={limit})")
        except Exception as e:
            log.warning(f"Limit check error for {username}: {e}")

if __name__ == "__main__":
    main()
