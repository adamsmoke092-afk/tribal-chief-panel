#!/usr/bin/env python3
import os
import sys
import re
import pwd
import sqlite3
import psutil
import subprocess
import bcrypt
import socket
import ssl
import shutil
import random
import string
from datetime import datetime, timedelta
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

# --- UI THEME CONFIGURATION ---
console = Console()
GOLD = "gold3"
GRAY = "grey74"
BLACK = "black"
ALERT = "bold red"

DB_PATH = "/opt/tribal/database/chief.db"

# ==========================================
# HELPERS & VALIDATION
# ==========================================

def valid_username(username: str) -> bool:
    return bool(re.match(r'^[a-z][a-z0-9_-]{2,31}$', username))

def valid_domain(domain: str) -> bool:
    return bool(re.match(r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$', domain))

def valid_ip(ip: str) -> bool:
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False

def valid_port(port: str) -> bool:
    try:
        return 1 <= int(port) <= 65535
    except ValueError:
        return False

def get_uid(username: str):
    try:
        return pwd.getpwnam(username).pw_uid
    except KeyError:
        return None

def pause():
    Prompt.ask(f"\n[{GRAY}]Press Enter to return to menu...[/{GRAY}]")

# ==========================================
# DATABASE
# ==========================================

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, expiry TEXT, conn_limit INT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin
                 (id INTEGER PRIMARY KEY, password_hash TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS domains
                 (id INTEGER PRIMARY KEY, domain TEXT UNIQUE, cloudflare INT,
                  ws_path TEXT, tls_status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS payloads
                 (id INTEGER PRIMARY KEY, name TEXT, payload_string TEXT)''')
    conn.commit()
    conn.close()

# ==========================================
# HEADER
# ==========================================

def print_header():
    os.system("clear" if os.name == "posix" else "cls")
    banner = f"[{GOLD}]✯☝︎ 𝐓𝐑𝐈𝐁𝐀𝐋 𝐂𝐇𝐈𝐄𝐅 𝐒𝐒𝐇 ☝︎✯[/{GOLD}]"
    subtitle = f"[{GRAY}]Advanced Terminal Management System[/{GRAY}]"
    console.print(Panel(f"[center]{banner}\n{subtitle}[/center]",
                        border_style=GOLD, style=f"on {BLACK}"))

# ==========================================
# SYSTEM MODULES (1–4)
# ==========================================

def init_system():
    init_db()
    for d in ["/opt/tribal/core", "/opt/tribal/modules", "/opt/tribal/utils",
              "/opt/tribal/database", "/opt/tribal/logs"]:
        os.makedirs(d, exist_ok=True)

    # Failsafe: ensure SSH port is open BEFORE enabling UFW
    subprocess.run(['ufw', 'allow', '22/tcp'],
                   stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    subprocess.run(['ufw', '--force', 'enable'],
                   stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

    for pkg in ['certbot', 'python3-certbot-nginx', 'vnstat', 'speedtest-cli']:
        subprocess.run(['apt-get', 'install', '-y', pkg],
                       stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

    console.print(f"\n[bold green]✔ System Initialization Complete.[/bold green]")
    console.print(f"[{GRAY}]Port 22 (SSH) is kept open as a failsafe.[/{GRAY}]")

def reset_admin():
    new_pass = Prompt.ask(f"[{GRAY}]Enter new admin password[/{GRAY}]", password=True)
    if len(new_pass) < 8:
        console.print(f"[{ALERT}]✘ Password must be at least 8 characters.[/{ALERT}]")
        return
    confirm_pass = Prompt.ask(f"[{GRAY}]Confirm admin password[/{GRAY}]", password=True)
    if new_pass != confirm_pass:
        console.print(f"[{ALERT}]✘ Passwords do not match.[/{ALERT}]")
        return
    hashed = bcrypt.hashpw(new_pass.encode('utf-8'), bcrypt.gensalt())
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM admin")
    c.execute("INSERT INTO admin (password_hash) VALUES (?)", (hashed.decode('utf-8'),))
    conn.commit()
    conn.close()
    console.print(f"[bold green]✔ Admin credentials updated successfully.[/bold green]")

def view_system_status():
    console.print(f"\n[{GOLD}]--- System Status ---[/{GOLD}]")
    for svc in ['ssh', 'nginx', 'ufw', 'wsbridge', 'vnstat']:
        try:
            status = subprocess.check_output(
                ['systemctl', 'is-active', svc],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            color = "bold green" if status == "active" else "bold red"
            console.print(f"[{GRAY}]{svc.upper()}:[/{GRAY}] [{color}]{status}[/{color}]")
        except Exception:
            console.print(f"[{GRAY}]{svc.upper()}:[/{GRAY}] [{ALERT}]error[/{ALERT}]")
    # Show uptime
    try:
        uptime = subprocess.check_output(['uptime', '-p'], text=True).strip()
        console.print(f"[{GRAY}]UPTIME:[/{GRAY}] [bold cyan]{uptime}[/bold cyan]")
    except Exception:
        pass

def view_server_load():
    console.print(f"\n[{GOLD}]--- Server Load ---[/{GOLD}]")
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    console.print(f"[{GRAY}]CPU  :[/{GRAY}] [bold cyan]{cpu}%[/bold cyan]")
    console.print(f"[{GRAY}]MEM  :[/{GRAY}] [bold cyan]{mem.percent}%[/bold cyan]"
                  f"[{GRAY}]  ({mem.used // 1048576} MB / {mem.total // 1048576} MB)[/{GRAY}]")
    console.print(f"[{GRAY}]DISK :[/{GRAY}] [bold cyan]{disk.percent}%[/bold cyan]"
                  f"[{GRAY}]  ({disk.used // 1073741824:.1f} GB / {disk.total // 1073741824:.1f} GB)[/{GRAY}]")

# ==========================================
# DOMAIN MODULES (5–8)
# ==========================================

def add_domain():
    console.print(f"\n[{GOLD}]--- Add New Domain ---[/{GOLD}]")
    domain = Prompt.ask(f"[{GRAY}]Enter Domain[/{GRAY}]").strip().lower()
    if not valid_domain(domain):
        console.print(f"[{ALERT}]✘ Invalid domain format.[/{ALERT}]")
        return
    cf = Prompt.ask(f"[{GRAY}]Is this behind Cloudflare? (y/n)[/{GRAY}]",
                    choices=["y", "n"], default="n")
    ws_path = Prompt.ask(f"[{GRAY}]Enter WebSocket Path[/{GRAY}]", default="/ws").strip()
    if not ws_path.startswith('/'):
        ws_path = '/' + ws_path
    cf_int = 1 if cf == 'y' else 0
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO domains (domain, cloudflare, ws_path, tls_status) VALUES (?, ?, ?, ?)",
                  (domain, cf_int, ws_path, "None"))
        conn.commit()
        conn.close()
        console.print(f"[bold green]✔ Domain {domain} added successfully.[/bold green]")
    except sqlite3.IntegrityError:
        console.print(f"[{ALERT}]✘ Domain already exists.[/{ALERT}]")

def remove_domain():
    list_domains()
    domain_id = Prompt.ask(f"[{GRAY}]Enter Domain ID to remove (or 0 to cancel)[/{GRAY}]")
    if domain_id == '0':
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM domains WHERE id=?", (domain_id,))
    if c.rowcount > 0:
        console.print(f"[bold green]✔ Domain removed.[/bold green]")
    else:
        console.print(f"[{ALERT}]✘ Domain ID not found.[/{ALERT}]")
    conn.commit()
    conn.close()

def list_domains():
    table = Table(border_style=GOLD, style=f"on {BLACK}")
    table.add_column("ID", style=GOLD, justify="center")
    table.add_column("Domain Name", style="white")
    table.add_column("Cloudflare", style="cyan", justify="center")
    table.add_column("WS Path", style=GRAY)
    table.add_column("TLS", style="green", justify="center")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, domain, cloudflare, ws_path, tls_status FROM domains")
    rows = c.fetchall()
    conn.close()
    if not rows:
        console.print(f"[{GRAY}]No domains currently managed.[/{GRAY}]")
        return
    for row in rows:
        cf_status = "[bold green]Yes[/bold green]" if row[2] == 1 else "[bold red]No[/bold red]"
        tls = "[bold green]Active[/bold green]" if row[4] == "Active" else f"[{GRAY}]{row[4]}[/{GRAY}]"
        table.add_row(str(row[0]), row[1], cf_status, row[3], tls)
    console.print(table)

def validate_domain():
    target = Prompt.ask(f"[{GRAY}]Enter Domain to test[/{GRAY}]").strip()
    if not valid_domain(target):
        console.print(f"[{ALERT}]✘ Invalid domain format.[/{ALERT}]")
        return
    try:
        ip = socket.gethostbyname(target)
        console.print(f"[bold green]✔ DNS Resolved:[/bold green] {ip}")
    except socket.gaierror:
        console.print(f"[{ALERT}]✘ DNS Resolution Failed.[/{ALERT}]")

# ==========================================
# SSH USER MODULES (9–15)
# ==========================================

def create_ssh_user():
    console.print(f"\n[{GOLD}]--- Create SSH User ---[/{GOLD}]")
    username = Prompt.ask(f"[{GRAY}]Enter username (blank for random)[/{GRAY}]").strip()
    if not username:
        username = "chief_" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
    if not valid_username(username):
        console.print(f"[{ALERT}]✘ Invalid username. Use lowercase letters, digits, hyphens. 3–32 chars.[/{ALERT}]")
        return
    password = Prompt.ask(f"[{GRAY}]Enter password (blank for random)[/{GRAY}]").strip()
    if not password:
        password = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$", k=12))
    days = Prompt.ask(f"[{GRAY}]Enter expiry in days[/{GRAY}]", default="30")
    limit = Prompt.ask(f"[{GRAY}]Enter connection limit[/{GRAY}]", default="2")

    try:
        expiry_date = (datetime.now() + timedelta(days=int(days))).strftime('%Y-%m-%d')
        subprocess.run(['useradd', '-M', '-s', '/bin/false', username],
                       check=True, stderr=subprocess.DEVNULL)
        proc = subprocess.Popen(['chpasswd'], stdin=subprocess.PIPE, text=True)
        proc.communicate(f"{username}:{password}")
        subprocess.run(['chage', '-E', expiry_date, username], check=True)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (username, expiry, conn_limit) VALUES (?, ?, ?)",
                  (username, expiry_date, int(limit)))
        conn.commit()
        conn.close()

        console.print(f"\n[bold green]✔ User Created Successfully![/bold green]")
        console.print(Panel(
            f"[{GOLD}]Username:[/{GOLD}]   {username}\n"
            f"[{GOLD}]Password:[/{GOLD}]   {password}\n"
            f"[{GOLD}]Expires :[/{GOLD}]   {expiry_date}\n"
            f"[{GOLD}]Limit   :[/{GOLD}]   {limit} sessions",
            border_style=GOLD, title="New User Credentials"
        ))
    except subprocess.CalledProcessError:
        console.print(f"[{ALERT}]✘ Failed. Username may already exist on the system.[/{ALERT}]")

def delete_ssh_user():
    username = Prompt.ask(f"[{GRAY}]Enter username to delete[/{GRAY}]").strip()
    if not valid_username(username):
        console.print(f"[{ALERT}]✘ Invalid username format.[/{ALERT}]")
        return
    confirm = Prompt.ask(f"[{ALERT}]Permanently delete '{username}'? (y/n)[/{ALERT}]",
                         choices=["y", "n"], default="n")
    if confirm != 'y':
        return
    subprocess.run(['userdel', '-f', username], stderr=subprocess.DEVNULL)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE username=?", (username,))
    conn.commit()
    conn.close()
    console.print(f"[bold green]✔ User {username} deleted.[/bold green]")

def suspend_user():
    username = Prompt.ask(f"[{GRAY}]Enter username[/{GRAY}]").strip()
    if not valid_username(username):
        console.print(f"[{ALERT}]✘ Invalid username format.[/{ALERT}]")
        return
    action = Prompt.ask(f"[{GRAY}]Action: 1 (Suspend) | 2 (Unsuspend)[/{GRAY}]", choices=["1", "2"])
    try:
        if action == "1":
            subprocess.run(['usermod', '-L', username], check=True, stderr=subprocess.DEVNULL)
            # Kill only sshd children, not all processes
            subprocess.run(f"pkill -9 -u {username} sshd", shell=True, stderr=subprocess.DEVNULL)
            console.print(f"[bold green]✔ User {username} suspended.[/bold green]")
        else:
            subprocess.run(['usermod', '-U', username], check=True, stderr=subprocess.DEVNULL)
            console.print(f"[bold green]✔ User {username} unsuspended.[/bold green]")
    except subprocess.CalledProcessError:
        console.print(f"[{ALERT}]✘ Operation failed. Check that the user exists.[/{ALERT}]")

def list_ssh_users():
    table = Table(border_style=GOLD, style=f"on {BLACK}")
    table.add_column("Username", style="white")
    table.add_column("Expiry", style="cyan")
    table.add_column("Limit", style=GRAY, justify="center")
    table.add_column("Active Sessions", style="cyan", justify="center")
    table.add_column("Status", style="green")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username, expiry, conn_limit FROM users")
    rows = c.fetchall()
    conn.close()
    if not rows:
        console.print(f"[{GRAY}]No SSH users found.[/{GRAY}]")
        return
    for row in rows:
        status_text = "[bold green]Active[/bold green]"
        try:
            shadow = subprocess.check_output(['passwd', '-S', row[0]],
                                             text=True, stderr=subprocess.DEVNULL)
            if " L " in shadow:
                status_text = "[bold red]Suspended[/bold red]"
        except Exception:
            status_text = f"[{GRAY}]Unknown[/{GRAY}]"
        # Count sessions via 'who'
        try:
            sessions = int(subprocess.check_output(
                f"who | grep -c '^{row[0]} '", shell=True, stderr=subprocess.DEVNULL
            ).strip())
        except Exception:
            sessions = 0
        table.add_row(row[0], row[1], str(row[2]), str(sessions), status_text)
    console.print(table)

def view_active_sessions():
    console.print(f"\n[{GOLD}]--- Active SSH Sessions ---[/{GOLD}]")
    try:
        output = subprocess.check_output(['who'], text=True).strip()
        if not output:
            console.print(f"[{GRAY}]No active sessions.[/{GRAY}]")
            return
        table = Table(border_style=GOLD, style=f"on {BLACK}")
        table.add_column("User", style="white")
        table.add_column("TTY", style="cyan")
        table.add_column("Login Time", style=GRAY)
        table.add_column("From IP", style="yellow")
        for line in output.splitlines():
            parts = line.split()
            user = parts[0] if len(parts) > 0 else "-"
            tty  = parts[1] if len(parts) > 1 else "-"
            time = f"{parts[2]} {parts[3]}" if len(parts) > 3 else "-"
            ip   = parts[4].strip('()') if len(parts) > 4 else "-"
            table.add_row(user, tty, time, ip)
        console.print(table)
    except Exception as e:
        console.print(f"[{ALERT}]✘ Failed to read sessions: {e}[/{ALERT}]")

def set_expiry_date():
    console.print(f"\n[{GOLD}]--- Set User Expiry ---[/{GOLD}]")
    username = Prompt.ask(f"[{GRAY}]Enter username[/{GRAY}]").strip()
    if not valid_username(username):
        console.print(f"[{ALERT}]✘ Invalid username format.[/{ALERT}]")
        return
    days = Prompt.ask(f"[{GRAY}]Enter new expiry in days from today[/{GRAY}]").strip()
    try:
        new_date = (datetime.now() + timedelta(days=int(days))).strftime('%Y-%m-%d')
        subprocess.run(['chage', '-E', new_date, username], check=True, stderr=subprocess.DEVNULL)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET expiry=? WHERE username=?", (new_date, username))
        if c.rowcount == 0:
            console.print(f"[{ALERT}]✘ User not found in database.[/{ALERT}]")
        else:
            console.print(f"[bold green]✔ Expiry for {username} updated to {new_date}.[/bold green]")
        conn.commit()
        conn.close()
    except subprocess.CalledProcessError:
        console.print(f"[{ALERT}]✘ Failed to update system shadow file. User may not exist.[/{ALERT}]")
    except ValueError:
        console.print(f"[{ALERT}]✘ Invalid number of days.[/{ALERT}]")

def set_connection_limit():
    console.print(f"\n[{GOLD}]--- Set Connection Limit ---[/{GOLD}]")
    username = Prompt.ask(f"[{GRAY}]Enter username[/{GRAY}]").strip()
    if not valid_username(username):
        console.print(f"[{ALERT}]✘ Invalid username format.[/{ALERT}]")
        return
    limit = Prompt.ask(f"[{GRAY}]Enter new connection limit[/{GRAY}]").strip()
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET conn_limit=? WHERE username=?", (int(limit), username))
        if c.rowcount > 0:
            console.print(f"[bold green]✔ Connection limit for {username} set to {limit}.[/bold green]")
        else:
            console.print(f"[{ALERT}]✘ User not found in database.[/{ALERT}]")
        conn.commit()
        conn.close()
    except ValueError:
        console.print(f"[{ALERT}]✘ Invalid limit value.[/{ALERT}]")

# ==========================================
# WEBSOCKET & NGINX MODULES (17–20)
# ==========================================

def config_ws_ports():
    console.print(f"\n[{GOLD}]--- Configure WebSocket Ports ---[/{GOLD}]")
    console.print(f"[{GRAY}]Standard HTTP: 80, 8080, 8880 | HTTPS: 443, 8443[/{GRAY}]")
    port = Prompt.ask(f"[{GRAY}]Enter port number to configure[/{GRAY}]").strip()
    if not valid_port(port):
        console.print(f"[{ALERT}]✘ Invalid port number (1–65535).[/{ALERT}]")
        return
    action = Prompt.ask(f"[{GRAY}]Action: 1 (Enable/Open) | 2 (Disable/Close)[/{GRAY}]",
                        choices=["1", "2"])
    subprocess.run(['ufw', '--force', 'enable'],
                   stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    if action == "1":
        subprocess.run(['ufw', 'allow', f'{port}/tcp'],
                       stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        console.print(f"[bold green]✔ Port {port}/tcp opened on the firewall.[/bold green]")
    else:
        if port == '22':
            console.print(f"[{ALERT}]⚠ Refusing to close port 22 — this would lock you out![/{ALERT}]")
            return
        subprocess.run(['ufw', 'delete', 'allow', f'{port}/tcp'],
                       stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        console.print(f"[bold green]✔ Port {port}/tcp closed.[/bold green]")

def config_ws_paths():
    console.print(f"\n[{GOLD}]--- Configure WebSocket Path ---[/{GOLD}]")
    list_domains()
    domain = Prompt.ask(f"[{GRAY}]Enter the Domain Name to update[/{GRAY}]").strip().lower()
    if not valid_domain(domain):
        console.print(f"[{ALERT}]✘ Invalid domain format.[/{ALERT}]")
        return
    new_path = Prompt.ask(f"[{GRAY}]Enter new WS Path (e.g. /ssh)[/{GRAY}]").strip()
    if not new_path.startswith('/'):
        new_path = '/' + new_path
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE domains SET ws_path=? WHERE domain=?", (new_path, domain))
    if c.rowcount > 0:
        console.print(f"[bold green]✔ Path updated. Regenerate Nginx config (Option 20).[/bold green]")
    else:
        console.print(f"[{ALERT}]✘ Domain not found.[/{ALERT}]")
    conn.commit()
    conn.close()

def enable_tls():
    console.print(f"\n[{GOLD}]--- Enable TLS (SSL Certificate) ---[/{GOLD}]")
    console.print(f"[{GRAY}]Note: Your domain must already be pointed to this VPS IP.[/{GRAY}]")
    domain = Prompt.ask(f"[{GRAY}]Enter Domain Name to secure[/{GRAY}]").strip().lower()
    if not valid_domain(domain):
        console.print(f"[{ALERT}]✘ Invalid domain format.[/{ALERT}]")
        return
    console.print(f"\n[{GOLD}]>> Requesting certificate from Let's Encrypt...[/{GOLD}]")
    result = subprocess.run(
        ['certbot', '--nginx', '-d', domain, '--non-interactive',
         '--agree-tos', '-m', f'admin@{domain}']
    )
    if result.returncode == 0:
        console.print(f"[bold green]✔ TLS successfully enabled for {domain}![/bold green]")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE domains SET tls_status='Active' WHERE domain=?", (domain,))
        conn.commit()
        conn.close()
    else:
        console.print(f"[{ALERT}]✘ Certbot failed. Check your DNS records and try again.[/{ALERT}]")

def generate_nginx_config():
    console.print(f"\n[{GOLD}]--- Generate Nginx Configuration ---[/{GOLD}]")
    list_domains()
    domain = Prompt.ask(f"[{GRAY}]Enter Domain Name to generate config for[/{GRAY}]").strip().lower()
    if not valid_domain(domain):
        console.print(f"[{ALERT}]✘ Invalid domain format.[/{ALERT}]")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT ws_path, tls_status FROM domains WHERE domain=?", (domain,))
    row = c.fetchone()
    conn.close()
    if not row:
        console.print(f"[{ALERT}]✘ Domain not found in database.[/{ALERT}]")
        return
    ws_path, tls_status = row

    # Build config — HTTP block only; certbot handles the SSL block if TLS is active
    config_text = f"""server {{
    listen 80;
    listen 8080;
    listen 8880;
    listen [::]:80;
    listen [::]:8080;
    listen [::]:8880;
    server_name {domain};

    location {ws_path} {{
        proxy_pass http://127.0.0.1:10015;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }}

    location / {{
        return 404;
    }}
}}
"""
    # If TLS is already active, append HTTPS block
    if tls_status == "Active":
        config_text += f"""
server {{
    listen 443 ssl http2;
    listen 8443 ssl http2;
    listen [::]:443 ssl http2;
    server_name {domain};

    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location {ws_path} {{
        proxy_pass http://127.0.0.1:10015;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }}

    location / {{
        return 404;
    }}
}}
"""
    file_path = f"/etc/nginx/sites-available/chief_{domain}"
    try:
        with open(file_path, 'w') as f:
            f.write(config_text)
        symlink = f"/etc/nginx/sites-enabled/chief_{domain}"
        if not os.path.exists(symlink):
            os.symlink(file_path, symlink)
        test = subprocess.run(['nginx', '-t'], capture_output=True, text=True)
        if test.returncode != 0:
            console.print(f"[{ALERT}]✘ Nginx config test failed:\n{test.stderr}[/{ALERT}]")
            return
        subprocess.run(['systemctl', 'reload', 'nginx'])
        console.print(f"[bold green]✔ Nginx configuration generated and reloaded![/bold green]")
        console.print(f"[{GRAY}]Config: {file_path}[/{GRAY}]")
    except Exception as e:
        console.print(f"[{ALERT}]✘ Failed to write Nginx config: {e}[/{ALERT}]")

# ==========================================
# PAYLOAD SYSTEM (21–25)
# ==========================================

def generate_payload():
    console.print(f"\n[{GOLD}]--- Generate Custom Payload ---[/{GOLD}]")
    name = Prompt.ask(f"[{GRAY}]Enter Payload Name (e.g., MTN_Bypass)[/{GRAY}]").strip()
    method = Prompt.ask(f"[{GRAY}]HTTP Method (GET, CONNECT, UNLOCK)[/{GRAY}]",
                        default="GET").strip().upper()
    bug_host = Prompt.ask(f"[{GRAY}]Enter Bug Host / SNI[/{GRAY}]").strip()
    ws_path = Prompt.ask(f"[{GRAY}]Enter WebSocket Path[/{GRAY}]", default="/ws").strip()
    if not ws_path.startswith('/'):
        ws_path = '/' + ws_path

    payload = (f"{method} {ws_path} HTTP/1.1\\r\\n"
               f"Host: {bug_host}\\r\\n"
               f"Upgrade: websocket\\r\\n"
               f"Connection: Upgrade\\r\\n\\r\\n")

    display = payload.replace("[", "\\[")
    console.print(f"\n[{GOLD}]Generated Payload:[/{GOLD}]\n[cyan]{display}[/cyan]\n")

    save = Prompt.ask(f"[{GRAY}]Save to database? (y/n)[/{GRAY}]", choices=["y", "n"], default="y")
    if save == 'y':
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO payloads (name, payload_string) VALUES (?, ?)", (name, payload))
        conn.commit()
        conn.close()
        console.print(f"[bold green]✔ Payload '{name}' saved.[/bold green]")

def test_payload():
    console.print(f"\n[{GOLD}]--- Test Bug Host / SNI (TLS Handshake) ---[/{GOLD}]")
    console.print(f"[{GRAY}]Tests TLS handshake on port 443. HTTP status codes are irrelevant for tunneling.[/{GRAY}]")
    sni = Prompt.ask(f"[{GRAY}]Enter Host/SNI to test[/{GRAY}]").strip()
    if not valid_domain(sni):
        console.print(f"[{ALERT}]✘ Invalid domain format.[/{ALERT}]")
        return
    console.print(f"[{GRAY}]>> Initiating TLS Handshake on port 443...[/{GRAY}]")
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((sni, 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=sni) as ssock:
                console.print(f"[bold green]✔ TLS Handshake Successful! Host is active.[/bold green]")
                console.print(f"[{GRAY}]Protocol:[/{GRAY}] [cyan]{ssock.version()}[/cyan]  "
                               f"[{GRAY}]Cipher:[/{GRAY}] [cyan]{ssock.cipher()[0]}[/cyan]")
    except ssl.SSLCertVerificationError:
        console.print(f"[yellow]⚠ TLS Handshake reached but cert is self-signed / untrusted.[/yellow]")
    except Exception as e:
        console.print(f"[{ALERT}]✘ TLS Handshake Failed: {str(e)}[/{ALERT}]")

def optimize_payload():
    console.print(f"\n[{GOLD}]--- Optimize Payload (DPI Evasion Tags) ---[/{GOLD}]")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, payload_string FROM payloads")
    rows = c.fetchall()
    if not rows:
        console.print(f"[{ALERT}]✘ No saved payloads. Generate one first (Option 21).[/{ALERT}]")
        conn.close()
        return
    table = Table(border_style=GOLD, style=f"on {BLACK}")
    table.add_column("ID", style=GOLD, justify="center")
    table.add_column("Name", style="white")
    table.add_column("Payload String", style="cyan")
    for row in rows:
        table.add_row(str(row[0]), row[1], row[2].replace("[", "\\["))
    console.print(table)

    payload_id = Prompt.ask(f"[{GRAY}]Enter Payload ID to optimize (0 to cancel)[/{GRAY}]").strip()
    if payload_id == '0':
        conn.close()
        return
    c.execute("SELECT name, payload_string FROM payloads WHERE id=?", (payload_id,))
    target = c.fetchone()
    if not target:
        console.print(f"[{ALERT}]✘ Invalid ID.[/{ALERT}]")
        conn.close()
        return
    name, payload = target

    console.print(f"\n[{GOLD}]Select Optimization Method:[/{GOLD}]")
    console.print(f"[{GRAY}]1.[/{GRAY}] [split] before Host      (Standard DPI Bypass)")
    console.print(f"[{GRAY}]2.[/{GRAY}] [delay_split] before Host (Aggressive DPI Bypass)")
    console.print(f"[{GRAY}]3.[/{GRAY}] [crlf] header obfuscation")
    console.print(f"[{GRAY}]4.[/{GRAY}] Custom manual tag injection")
    opt_choice = Prompt.ask(f"[{GOLD}]Select option[/{GOLD}]", choices=["1", "2", "3", "4"])

    optimized = payload
    if opt_choice == "1":
        optimized = payload.replace("Host:", "[split]Host:")
    elif opt_choice == "2":
        optimized = payload.replace("Host:", "[delay_split]Host:")
    elif opt_choice == "3":
        optimized = payload.replace("HTTP/1.1\\r\\n", "HTTP/1.1[crlf]")
    elif opt_choice == "4":
        custom_tag = Prompt.ask(f"[{GRAY}]Custom replacement for 'Host:' (e.g. [split][crlf]Host:)[/{GRAY}]")
        optimized = payload.replace("Host:", custom_tag)

    console.print(f"\n[{GOLD}]Optimized Payload:[/{GOLD}]\n[cyan]{optimized.replace('[', chr(92)+'[')}[/cyan]\n")
    save = Prompt.ask(f"[{GRAY}]Update database? (y/n)[/{GRAY}]", choices=["y", "n"], default="y")
    if save == 'y':
        c.execute("UPDATE payloads SET payload_string=? WHERE id=?", (optimized, payload_id))
        conn.commit()
        console.print(f"[bold green]✔ Payload '{name}' optimized and updated.[/bold green]")
    conn.close()

def view_saved_payloads():
    console.print(f"\n[{GOLD}]--- Saved Payloads ---[/{GOLD}]")
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, name, payload_string FROM payloads")
        rows = c.fetchall()
        conn.close()
        if not rows:
            console.print(f"[{GRAY}]No payloads saved yet.[/{GRAY}]")
            return
        table = Table(border_style=GOLD, style=f"on {BLACK}")
        table.add_column("ID", style=GOLD, justify="center")
        table.add_column("Name", style="white")
        table.add_column("Payload String", style="cyan")
        for row in rows:
            table.add_row(str(row[0]), row[1], row[2].replace("[", "\\["))
        console.print(table)
    except sqlite3.OperationalError:
        console.print(f"[{GRAY}]No payloads saved yet.[/{GRAY}]")

def delete_payload():
    console.print(f"\n[{GOLD}]--- Delete Payload ---[/{GOLD}]")
    view_saved_payloads()
    payload_id = Prompt.ask(f"[{GRAY}]Enter Payload ID to delete (0 to cancel)[/{GRAY}]").strip()
    if payload_id == '0':
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM payloads WHERE id=?", (payload_id,))
    if c.rowcount > 0:
        console.print(f"[bold green]✔ Payload deleted.[/bold green]")
    else:
        console.print(f"[{ALERT}]✘ Payload ID not found.[/{ALERT}]")
    conn.commit()
    conn.close()

# ==========================================
# NETWORK CONTROL & BANDWIDTH (26–32)
# ==========================================

def connection_limiter():
    console.print(f"\n[{GOLD}]--- Active Connection Limiter ---[/{GOLD}]")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username, conn_limit FROM users")
    users = c.fetchall()
    conn.close()

    table = Table(border_style=GOLD, style=f"on {BLACK}")
    table.add_column("Username", style="white")
    table.add_column("Active Sessions", style="cyan", justify="center")
    table.add_column("Limit", style=GRAY, justify="center")
    table.add_column("Action", style="bold red")

    abusers_found = False
    for user in users:
        username, limit = user[0], user[1]
        try:
            raw = subprocess.check_output(
                f"who | grep -c '^{username} '",
                shell=True, stderr=subprocess.DEVNULL
            ).strip()
            active_sessions = int(raw)
        except Exception:
            active_sessions = 0

        action = "[green]Pass[/green]"
        if active_sessions > limit:
            # Kill only SSH sessions, not all user processes
            subprocess.run(f"pkill -9 -u {username} sshd",
                           shell=True, stderr=subprocess.DEVNULL)
            action = "[red]KICKED (Limit Exceeded)[/red]"
            abusers_found = True

        if active_sessions > 0 or abusers_found:
            table.add_row(username, str(active_sessions), str(limit), action)

    if table.row_count > 0:
        console.print(table)
    else:
        console.print(f"[{GRAY}]✔ No active SSH users found.[/{GRAY}]")

    if abusers_found:
        console.print(f"\n[{ALERT}]⚠️  Abusers detected and SSH sessions dropped.[/{ALERT}]")

def firewall_manager():
    console.print(f"\n[{GOLD}]--- Advanced Firewall Manager ---[/{GOLD}]")
    if not os.path.exists('/usr/sbin/ufw'):
        console.print(f"[{ALERT}]✘ UFW is not installed. Run: apt install ufw[/{ALERT}]")
        return
    action = Prompt.ask(
        f"[{GRAY}]1.[/{GRAY}] View Status  "
        f"[{GRAY}]2.[/{GRAY}] Allow Port  "
        f"[{GRAY}]3.[/{GRAY}] Block IP  "
        f"[{GRAY}]4.[/{GRAY}] Reset Firewall",
        choices=["1", "2", "3", "4"]
    )
    if action == "1":
        console.print(f"\n[{GOLD}]>> UFW Status:[/{GOLD}]")
        subprocess.run(['ufw', 'status', 'numbered'])
    elif action == "2":
        port = Prompt.ask(f"[{GRAY}]Enter port number to open[/{GRAY}]").strip()
        if not valid_port(port):
            console.print(f"[{ALERT}]✘ Invalid port.[/{ALERT}]")
            return
        subprocess.run(['ufw', 'allow', f'{port}/tcp'])
        console.print(f"[bold green]✔ Port {port} is now open.[/bold green]")
    elif action == "3":
        ip = Prompt.ask(f"[{GRAY}]Enter IP address to block[/{GRAY}]").strip()
        if not valid_ip(ip):
            console.print(f"[{ALERT}]✘ Invalid IP address format.[/{ALERT}]")
            return
        subprocess.run(['ufw', 'deny', 'from', ip])
        console.print(f"[bold red]⛔ IP {ip} blocked.[/bold red]")
    elif action == "4":
        confirm = Prompt.ask(f"[{ALERT}]Wipe ALL rules? Port 22 will be re-added. (y/n)[/{ALERT}]",
                             choices=["y", "n"])
        if confirm == 'y':
            subprocess.run(['ufw', '--force', 'reset'])
            subprocess.run(['ufw', 'allow', '22/tcp'])
            subprocess.run(['ufw', '--force', 'enable'])
            console.print(f"[bold green]✔ Firewall reset. Port 22 kept open.[/bold green]")

def ssl_cert_manager():
    console.print(f"\n[{GOLD}]--- SSL Certificate Manager ---[/{GOLD}]")
    subprocess.run(['certbot', 'certificates'])

def view_bandwidth_user():
    console.print(f"\n[{GOLD}]--- Per-User Bandwidth Usage ---[/{GOLD}]")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username FROM users")
    users = c.fetchall()
    conn.close()
    if not users:
        console.print(f"[{GRAY}]No users found in database.[/{GRAY}]")
        return

    table = Table(border_style=GOLD, style=f"on {BLACK}")
    table.add_column("Username", style="white")
    table.add_column("Data Consumed", style="cyan", justify="right")

    for user in users:
        uname = user[0]
        uid = get_uid(uname)
        if uid is None:
            table.add_row(uname, f"[{GRAY}]N/A (no system user)[/{GRAY}]")
            continue
        try:
            # Use numeric UID for iptables owner match
            check_rule = ['iptables', '-C', 'OUTPUT', '-m', 'owner',
                          '--uid-owner', str(uid), '-j', 'ACCEPT']
            if subprocess.call(check_rule, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL) != 0:
                subprocess.run(['iptables', '-A', 'OUTPUT', '-m', 'owner',
                                '--uid-owner', str(uid), '-j', 'ACCEPT'],
                               stderr=subprocess.DEVNULL)

            output = subprocess.check_output(
                f"iptables -L OUTPUT -v -n -x | grep 'owner UID match {uid}'",
                shell=True, text=True
            ).strip()
            bytes_used = int(output.split()[1])
            if bytes_used >= 1073741824:
                usage_str = f"{bytes_used / 1073741824:.2f} GB"
            elif bytes_used >= 1048576:
                usage_str = f"{bytes_used / 1048576:.2f} MB"
            else:
                usage_str = f"{bytes_used / 1024:.2f} KB"
            table.add_row(uname, usage_str)
        except Exception:
            table.add_row(uname, f"[{GRAY}]0.00 KB[/{GRAY}]")

    console.print(table)

def total_server_bw():
    console.print(f"\n[{GOLD}]--- Total Server Bandwidth (vnStat) ---[/{GOLD}]")
    if not shutil.which('vnstat'):
        console.print(f"[{GRAY}]Installing vnstat...[/{GRAY}]")
        subprocess.run(['apt-get', 'install', '-y', 'vnstat'],
                       stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        console.print(f"[bold green]✔ vnstat installed. Wait a few minutes for initial data.[/bold green]")
        return
    try:
        output = subprocess.check_output(['vnstat'], text=True)
        console.print(f"[cyan]{output}[/cyan]")
    except subprocess.CalledProcessError:
        console.print(f"[{ALERT}]✘ vnstat is building its database. Try again in 5 minutes.[/{ALERT}]")

def reset_counters():
    console.print(f"\n[{GOLD}]--- Reset Bandwidth Counters ---[/{GOLD}]")
    confirm = Prompt.ask(f"[{ALERT}]Reset ALL user bandwidth counters to 0? (y/n)[/{ALERT}]",
                         choices=["y", "n"], default="n")
    if confirm == 'y':
        subprocess.run(['iptables', '-Z', 'OUTPUT'])
        console.print(f"[bold green]✔ All per-user bandwidth counters reset to 0.[/bold green]")

# ==========================================
# UTILITIES (33–37)
# ==========================================

def network_speedtest():
    console.print(f"\n[{GOLD}]--- Network Speedtest ---[/{GOLD}]")
    if not shutil.which('speedtest-cli'):
        subprocess.run(['apt-get', 'install', '-y', 'speedtest-cli'],
                       stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    try:
        console.print(f"[{GRAY}]Running speedtest, please wait...[/{GRAY}]\n")
        output = subprocess.check_output(['speedtest-cli', '--simple'], text=True)
        console.print(f"[bold cyan]{output}[/bold cyan]")
    except Exception:
        console.print(f"[{ALERT}]✘ speedtest-cli failed.[/{ALERT}]")

def view_logs():
    console.print(f"\n[{GOLD}]--- System Diagnostics & Logs ---[/{GOLD}]")
    log_choice = Prompt.ask(
        f"[{GRAY}]1.[/{GRAY}] SSH Auth  "
        f"[{GRAY}]2.[/{GRAY}] Nginx Error  "
        f"[{GRAY}]3.[/{GRAY}] WS Bridge  "
        f"[{GRAY}]4.[/{GRAY}] UFW",
        choices=["1", "2", "3", "4"]
    )
    console.print(f"\n[{GOLD}]>> Last 20 lines:[/{GOLD}]\n")
    cmds = {
        "1": "tail -n 20 /var/log/auth.log",
        "2": "tail -n 20 /var/log/nginx/error.log",
        "3": "journalctl -u wsbridge -n 20 --no-pager",
        "4": "tail -n 20 /var/log/ufw.log",
    }
    os.system(cmds[log_choice])

def custom_server_message():
    console.print(f"\n[{GOLD}]--- Custom Server Message (SSH Banner) ---[/{GOLD}]")
    console.print(f"[{GRAY}]Displayed to users on successful SSH login.[/{GRAY}]")
    message = Prompt.ask(f"[{GRAY}]Enter new banner text[/{GRAY}]")
    try:
        with open("/etc/issue.net", "w") as f:
            f.write(message + "\n")
        subprocess.run(
            ['sed', '-i', r's/^#*Banner.*/Banner \/etc\/issue.net/',
             '/etc/ssh/sshd_config']
        )
        subprocess.run(['systemctl', 'restart', 'ssh'])
        console.print(f"\n[bold green]✔ Server banner updated and SSH restarted![/bold green]")
        console.print(f"[{GOLD}]Active Banner:[/{GOLD}] {message}")
    except Exception as e:
        console.print(f"[{ALERT}]✘ Failed: {e}[/{ALERT}]")

def backup_database():
    console.print(f"\n[{GOLD}]--- Backup Database ---[/{GOLD}]")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"/opt/tribal/database/chief_backup_{timestamp}.db"
    try:
        shutil.copy2(DB_PATH, backup_path)
        console.print(f"[bold green]✔ Database backed up to:[/bold green] {backup_path}")
    except Exception as e:
        console.print(f"[{ALERT}]✘ Backup failed: {e}[/{ALERT}]")

# ==========================================
# AUTHENTICATION & MAIN LOOP
# ==========================================

def authenticate():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT password_hash FROM admin LIMIT 1")
    row = c.fetchone()
    conn.close()
    print_header()

    if not row:
        # First-time setup — force user to set a real password
        console.print(f"[{ALERT}]⚠ No admin password set! Please create one now.[/{ALERT}]")
        while True:
            new_pass = Prompt.ask(f"[{GOLD}]Set Admin Password[/{GOLD}]", password=True)
            if len(new_pass) < 8:
                console.print(f"[{ALERT}]✘ Password must be at least 8 characters.[/{ALERT}]")
                continue
            confirm = Prompt.ask(f"[{GOLD}]Confirm Password[/{GOLD}]", password=True)
            if new_pass != confirm:
                console.print(f"[{ALERT}]✘ Passwords do not match.[/{ALERT}]")
                continue
            break
        hashed = bcrypt.hashpw(new_pass.encode('utf-8'), bcrypt.gensalt())
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO admin (password_hash) VALUES (?)", (hashed.decode('utf-8'),))
        conn.commit()
        conn.close()
        console.print(f"[bold green]✔ Admin password set.[/bold green]")
        return True

    attempts = 3
    while attempts > 0:
        entered = Prompt.ask(f"[{GOLD}]Enter Admin Password[/{GOLD}]", password=True)
        if bcrypt.checkpw(entered.encode('utf-8'), row[0].encode('utf-8')):
            return True
        attempts -= 1
        console.print(f"[{ALERT}]✘ Incorrect. {attempts} attempt(s) left.[/{ALERT}]")
    console.print(f"[{ALERT}]✘ Too many failed attempts. Exiting.[/{ALERT}]")
    sys.exit(1)

def main_menu():
    while True:
        print_header()
        menu_text = f"""
[{GOLD}]SYSTEM[/{GOLD}]
[{GRAY}]1.[/{GRAY}]  Install/Init System    [{GRAY}]2.[/{GRAY}]  Reset Admin Creds
[{GRAY}]3.[/{GRAY}]  View System Status     [{GRAY}]4.[/{GRAY}]  View Server Load

[{GOLD}]DOMAIN MANAGEMENT[/{GOLD}]
[{GRAY}]5.[/{GRAY}]  Add Domain             [{GRAY}]6.[/{GRAY}]  Remove Domain
[{GRAY}]7.[/{GRAY}]  List Domains           [{GRAY}]8.[/{GRAY}]  Validate Domain

[{GOLD}]SSH USER MANAGEMENT[/{GOLD}]
[{GRAY}]9.[/{GRAY}]  Create SSH User        [{GRAY}]10.[/{GRAY}] Delete SSH User
[{GRAY}]11.[/{GRAY}] Suspend User           [{GRAY}]12.[/{GRAY}] List SSH Users
[{GRAY}]13.[/{GRAY}] View Active Sessions   [{GRAY}]14.[/{GRAY}] Set Expiry Date
[{GRAY}]15.[/{GRAY}] Set Connection Limit

[{GOLD}]WEBSOCKET & NGINX[/{GOLD}]
[{GRAY}]17.[/{GRAY}] Config WS Ports        [{GRAY}]18.[/{GRAY}] Config WS Paths
[{GRAY}]19.[/{GOLD}] Enable TLS (SSL)       [{GRAY}]20.[/{GRAY}] Gen Nginx Config

[{GOLD}]PAYLOAD SYSTEM[/{GOLD}]
[{GRAY}]21.[/{GRAY}] Generate Payload       [{GRAY}]22.[/{GRAY}] Test Payload
[{GRAY}]23.[/{GRAY}] Optimize Payload       [{GRAY}]24.[/{GRAY}] View Saved Payloads
[{GRAY}]25.[/{GRAY}] Delete Payload

[{GOLD}]NETWORK & BANDWIDTH[/{GOLD}]
[{GRAY}]26.[/{GRAY}] Connection Limiter     [{GRAY}]27.[/{GRAY}] Firewall Manager
[{GRAY}]28.[/{GRAY}] SSL Cert Manager       [{GRAY}]29.[/{GRAY}] View Bandwidth/User
[{GRAY}]30.[/{GRAY}] Total Server BW        [{GRAY}]31.[/{GRAY}] Reset Counters

[{GOLD}]UTILITIES[/{GOLD}]
[{GRAY}]33.[/{GRAY}] Network Speedtest      [{GRAY}]34.[/{GRAY}] View Logs
[{GRAY}]35.[/{GRAY}] Custom Server Message  [{GRAY}]36.[/{GRAY}] Backup Database

[{ALERT}]0.  Exit[/{ALERT}]
        """
        console.print(menu_text)
        choice = Prompt.ask(f"[{GOLD}]Select an option[/{GOLD}]")

        actions = {
            '1': init_system, '2': reset_admin, '3': view_system_status,
            '4': view_server_load, '5': add_domain, '6': remove_domain,
            '7': list_domains, '8': validate_domain, '9': create_ssh_user,
            '10': delete_ssh_user, '11': suspend_user, '12': list_ssh_users,
            '13': view_active_sessions, '14': set_expiry_date,
            '15': set_connection_limit, '17': config_ws_ports,
            '18': config_ws_paths, '19': enable_tls, '20': generate_nginx_config,
            '21': generate_payload, '22': test_payload, '23': optimize_payload,
            '24': view_saved_payloads, '25': delete_payload,
            '26': connection_limiter, '27': firewall_manager,
            '28': ssl_cert_manager, '29': view_bandwidth_user,
            '30': total_server_bw, '31': reset_counters,
            '33': network_speedtest, '34': view_logs,
            '35': custom_server_message, '36': backup_database,
        }

        if choice == '0':
            sys.exit(0)
        elif choice in actions:
            actions[choice]()
        else:
            console.print(f"[{GRAY}]Invalid option.[/{GRAY}]")

        pause()


if __name__ == "__main__":
    if os.geteuid() != 0:
        console.print(f"[{ALERT}]✘ This script must be run as root (sudo).[/{ALERT}]")
        sys.exit(1)
    if authenticate():
        main_menu()
