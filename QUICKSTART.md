# 🚀 TRIBAL CHIEF WEB PANEL — QUICK START

Get your professional web panel running in **5 minutes**!

---

## ⚡ Ultra-Fast Setup

### Option 1: Automated Setup (Recommended)

```bash
# Download and run the installer
curl -sSL https://your-repo/tribal-chief-panel/SETUP.sh | sudo bash

# That's it! Panel is running at http://localhost:8080
```

### Option 2: Manual Setup (2 minutes)

```bash
# 1. Install Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt-get install -y nodejs

# 2. Create directory and install
sudo mkdir -p /root/tribal-chief-panel && cd /root/tribal-chief-panel

# 3. Copy these 4 files here:
#    - server.js
#    - package.json
#    - public/index.html
#    - Dockerfile (optional)

# 4. Install and start
sudo npm install
sudo node server.js

# 5. Open browser to http://localhost:8080
```

### Option 3: Docker (1 minute)

```bash
# Build and run with Docker
docker build -t tribal-chief-panel .
docker run -d -p 8080:8080 \
  -e DB_PATH=/opt/tribal/database/chief.db \
  -v /opt/tribal:/opt/tribal \
  tribal-chief-panel
```

---

## ✅ Verify Installation

```bash
# Check if it's running
curl http://localhost:8080/api/health

# Expected response:
# {"status":"ok","timestamp":"2026-03-19T..."}

# View logs
sudo journalctl -u tribal-chief-panel -f
```

---

## 📖 First Steps

1. **Open the Panel**
   ```
   http://your-server-ip:8080
   ```

2. **Create Your First User**
   - Click "Create User" button
   - Enter username, password, expiry date, connection limit
   - Click Create

3. **Monitor Dashboard**
   - View total users and active sessions
   - See expiring accounts
   - Track suspended users

4. **Manage Users**
   - Kick sessions (instantly disconnect users)
   - Suspend/unsuspend accounts
   - Update expiry dates
   - Delete users

---

## 📋 File Structure

```
tribal-chief-backend/
├── server.js              ← Express.js backend (main)
├── package.json           ← Dependencies
├── public/
│   └── index.html         ← React frontend (single file)
├── Dockerfile             ← For container deployment
├── docker-compose.yml     ← For multi-container setup
├── SETUP.sh               ← Automated installer
├── README.md              ← Full documentation
└── QUICKSTART.md          ← This file
```

---

## 🔧 Configuration

### Change Port
```bash
# Edit systemd service or environment variable
export PORT=9000
node server.js
```

### Change Database Path
```bash
export DB_PATH=/path/to/chief.db
node server.js
```

### Enable Nginx Reverse Proxy
```bash
# During SETUP.sh, choose "y" for Nginx setup
# Or manually:
sudo apt-get install nginx
# Configure /etc/nginx/sites-available/tribal-chief-panel
# (See README for full config)
```

---

## 🎯 Essential Operations

### Create User
```bash
curl -X POST http://localhost:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{
    "username": "john",
    "password": "pass123",
    "expiry": "2026-12-31",
    "conn_limit": 2
  }'
```

### List All Users
```bash
curl http://localhost:8080/api/users | jq
```

### Kick User Sessions
```bash
curl -X POST http://localhost:8080/api/users/john/kick
```

### Suspend User
```bash
curl -X POST http://localhost:8080/api/users/john/suspend
```

### Delete User
```bash
curl -X DELETE http://localhost:8080/api/users/john
```

---

## 🐛 Quick Troubleshooting

### Panel won't start?
```bash
# Check Node.js is installed
node --version

# Check if port is free
sudo lsof -i :8080

# Check database exists
ls -la /opt/tribal/database/chief.db

# Run directly to see errors
sudo node /root/tribal-chief-panel/server.js
```

### Can't access panel?
```bash
# Test locally first
curl http://127.0.0.1:8080/api/health

# Check firewall
sudo ufw allow 8080/tcp
sudo ufw status

# If using Nginx, check it's running
sudo systemctl status nginx
```

### Database errors?
```bash
# Check permissions
sudo chmod 666 /opt/tribal/database/chief.db

# Verify database integrity
sqlite3 /opt/tribal/database/chief.db ".tables"
```

---

## 🔄 Integration with CLI

Your existing Tribal Chief CLI menu still works:

```bash
# CLI menu (as before)
chief

# Web panel (new)
http://localhost:8080

# Both use same database - fully compatible!
```

---

## 📊 Dashboard Overview

**Dashboard Tab:**
- Total users count
- Active sessions right now
- Accounts expiring within 7 days
- Suspended accounts

**Users Tab:**
- Search users by username
- See current/max sessions
- View expiry dates
- Quick actions: kick, suspend, delete

**Audit Tab:**
- Complete action history
- Who did what and when
- All operations logged

---

## 🔐 Security Tips

1. **Use HTTPS in Production**
   ```bash
   # Install certbot and Let's Encrypt
   sudo apt-get install certbot python3-certbot-nginx
   sudo certbot certonly --nginx -d your-domain.com
   ```

2. **Restrict Access**
   ```bash
   # Firewall to specific IPs
   sudo ufw allow from 203.0.113.0/24 to any port 8080
   ```

3. **Use Strong Passwords**
   - For user accounts, use complex passwords
   - Rotate them regularly

4. **Monitor Logs**
   ```bash
   sudo tail -f /opt/tribal/logs/*
   ```

---

## 📞 Need Help?

1. **Check Logs**
   ```bash
   sudo journalctl -u tribal-chief-panel -n 50
   ```

2. **Test API**
   ```bash
   curl http://localhost:8080/api/health
   curl http://localhost:8080/api/users
   ```

3. **Restart Service**
   ```bash
   sudo systemctl restart tribal-chief-panel
   ```

---

## 🎉 You're All Set!

Your professional VPS management panel is ready to use.

**Next**: Open http://localhost:8080 and start managing your users!

---

For full documentation, see **README.md**
