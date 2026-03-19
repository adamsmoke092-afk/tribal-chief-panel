# 🔥 TRIBAL CHIEF WEB PANEL



![License](https://img.shields.io/badge/license-MIT-blue.svg)




![Node.js](https://img.shields.io/badge/node-%3E%3D14-green)




![React](https://img.shields.io/badge/react-%3E%3D18-61dafb)




![Status](https://img.shields.io/badge/status-production%20ready-brightgreen)

A professional, modern web dashboard for managing your Tribal Chief VPS control system. Built with **React + Node.js**, inspired by the clean aesthetics of 3xui.

---

## 🚀 Features

✨ **Dashboard**
- Real-time system monitoring
- Active session tracking
- User status overview
- Session limit visualization

👥 **User Management**
- Create/delete users
- Set expiration dates
- Configure connection limits
- Search & filter users
- Suspend/unsuspend accounts

⚡ **Real-time Controls**
- Kick user sessions instantly
- Lock/unlock accounts
- Monitor active connections
- Live status updates

📋 **Audit Logging**
- Track all actions
- Timestamp every operation
- User accountability
- Full action history

🎨 **Professional Design**
- Dark theme (easy on the eyes)
- Responsive layout
- Smooth animations
- Intuitive controls

---

## 📋 Requirements

- **OS**: Ubuntu/Debian (Linux)
- **Node.js**: v14+ 
- **Python 3**: For existing Tribal Chief system
- **SQLite3**: For database
- **Root access**: Required for system operations

---

## 🔧 Installation

### Quick Start (One Command)

```bash
curl -sSL https://raw.githubusercontent.com/YOUR_REPO/tribal-chief-panel/main/SETUP.sh | sudo bash
```

### Manual Installation

```bash
# 1. Install Node.js (if not already installed)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# 2. Clone or download the panel files
sudo mkdir -p /root/tribal-chief-panel
cd /root/tribal-chief-panel

# 3. Copy your files here (server.js, package.json, public/index.html)
# Then install dependencies:
sudo npm install

# 4. Start the service
sudo systemctl start tribal-chief-panel
sudo systemctl status tribal-chief-panel
```

### Verify Installation

```bash
# Check if panel is running
curl http://localhost:8080/api/health

# Should respond with:
# {"status":"ok","timestamp":"2026-03-19T..."}

# View logs
journalctl -u tribal-chief-panel -f
```

---

## 🌐 Access the Panel

Once installed, open your browser and navigate to:

```
http://your-server-ip:8080
```

**Default Port**: `8080`

If you set up Nginx reverse proxy, you can access via:
```
http://your-server-ip
```

---

## 📡 API Endpoints

The backend provides a REST API for programmatic access:

### Health & Stats
```
GET /api/health                     - Health check
GET /api/stats                      - System statistics
```

### User Management
```
GET    /api/users                   - List all users
POST   /api/users                   - Create new user
GET    /api/users/:username         - Get user details
PUT    /api/users/:username         - Update user (expiry, limits)
DELETE /api/users/:username         - Delete user
```

### User Actions
```
POST /api/users/:username/kick       - Disconnect all sessions
POST /api/users/:username/suspend    - Lock account
POST /api/users/:username/unsuspend  - Unlock account
```

### Audit
```
GET /api/audit                       - View audit log (last 100 entries)
```

---

## 📝 API Examples

### Create a User
```bash
curl -X POST http://localhost:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "password": "secure_password",
    "expiry": "2026-12-31",
    "conn_limit": 2
  }'
```

### Get All Users
```bash
curl http://localhost:8080/api/users
```

### Update User Expiry
```bash
curl -X PUT http://localhost:8080/api/users/alice \
  -H "Content-Type: application/json" \
  -d '{
    "expiry": "2027-01-15",
    "conn_limit": 3
  }'
```

### Kick User Sessions
```bash
curl -X POST http://localhost:8080/api/users/alice/kick
```

### View Audit Log
```bash
curl http://localhost:8080/api/audit | jq
```

---

## 🔐 Security Considerations

### Important Notes:
1. **Run on HTTPS** - Use Nginx with Let's Encrypt (see setup)
2. **Firewall** - Restrict access to trusted networks
3. **Authentication** - This version has basic auth; add proper authentication for production
4. **Database** - SQLite is for small deployments; consider PostgreSQL for larger ones
5. **Logs** - All actions are logged in the audit table

### Hardening (Optional but Recommended)

**Add Basic Auth to Nginx:**
```nginx
server {
    listen 80;
    
    auth_basic "Tribal Chief Panel";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
```

Create password file:
```bash
sudo apt-get install apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd admin
```

---

## 🛠️ Configuration

### Environment Variables

```bash
# In /etc/systemd/system/tribal-chief-panel.service:
Environment="PORT=8080"
Environment="DB_PATH=/opt/tribal/database/chief.db"
```

To change:
```bash
sudo systemctl edit tribal-chief-panel
# Edit the Environment lines
sudo systemctl restart tribal-chief-panel
```

---

## 📊 Database Schema

The panel uses your existing SQLite database. Tables:

### users
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,
    password_hash TEXT,
    expiry TEXT,           -- YYYY-MM-DD format
    conn_limit INTEGER,    -- Max concurrent connections
    created_at DATETIME,
    is_active BOOLEAN
);
```

### sessions
```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    username TEXT,
    ip_address TEXT,
    session_start DATETIME
);
```

### audit_log
```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    action TEXT,           -- CREATE_USER, DELETE_USER, KICK_SESSIONS, etc.
    target_user TEXT,      -- Affected username
    details TEXT,          -- JSON details
    timestamp DATETIME
);
```

---

## 🚨 Troubleshooting

### Panel won't start
```bash
# Check logs
journalctl -u tribal-chief-panel -n 50

# Check if port 8080 is in use
sudo lsof -i :8080

# Try manual start to see errors
sudo /usr/bin/node /root/tribal-chief-panel/server.js
```

### Database connection error
```bash
# Check database file exists and has permissions
ls -la /opt/tribal/database/chief.db

# Fix permissions if needed
sudo chmod 666 /opt/tribal/database/chief.db
```

### Can't connect to panel
```bash
# Check service status
sudo systemctl status tribal-chief-panel

# Check firewall
sudo ufw status
sudo ufw allow 8080/tcp

# Test API locally
curl http://127.0.0.1:8080/api/health
```

### Users not showing up
```bash
# Check database has users
sqlite3 /opt/tribal/database/chief.db "SELECT COUNT(*) FROM users;"

# Check database permissions
sudo chown root:root /opt/tribal/database/chief.db
sudo chmod 644 /opt/tribal/database/chief.db
```

---

## 📦 Docker Deployment (Optional)

Create a `Dockerfile`:

```dockerfile
FROM node:18-alpine

WORKDIR /app

# Install system dependencies
RUN apk add --no-cache python3 python3-dev gcc musl-dev

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 8080

CMD ["node", "server.js"]
```

Build and run:
```bash
docker build -t tribal-chief-panel .

docker run -d \
  --name tribal-chief \
  -p 8080:8080 \
  -e DB_PATH=/opt/tribal/database/chief.db \
  -v /opt/tribal:/opt/tribal \
  tribal-chief-panel
```

---

## 🔄 Updating

To update the panel:

```bash
cd /root/tribal-chief-panel
sudo git pull                    # If using git
sudo npm install                 # Update dependencies
sudo systemctl restart tribal-chief-panel
```

---

## 🐛 Reporting Issues

If you encounter problems:

1. Check the logs: `journalctl -u tribal-chief-panel -f`
2. Verify database: `sqlite3 /opt/tribal/database/chief.db ".tables"`
3. Test API: `curl http://localhost:8080/api/health`
4. Check permissions: `ls -la /opt/tribal/`

---

## 📖 Integration with Existing System

This panel is designed to work **alongside** your existing Tribal Chief CLI menu:

```bash
# Your existing menu still works
chief                           # CLI menu

# Panel provides web access
http://localhost:8080           # Web dashboard

# Both share the same database
/opt/tribal/database/chief.db
```

They're fully compatible! Use whichever interface you prefer.

---

## 🎯 Roadmap

Future enhancements:
- [ ] User authentication & role-based access
- [ ] Traffic statistics & bandwidth monitoring
- [ ] User notes/comments
- [ ] Bulk user operations
- [ ] Email notifications
- [ ] 2FA support
- [ ] IP whitelist management
- [ ] Custom branding

---

## 📄 License

This project is part of Tribal Chief ecosystem.

---

## 💬 Support

For questions or help:
- Check the troubleshooting section
- Review API documentation
- Check logs in `/opt/tribal/logs/`

---

## 🙏 Credits

Built for the Tribal Chief VPS management community.

Inspired by the excellent design of 3xui panel.

---

**Happy Managing! 🎉**
