# Orchard UI

A Flask web dashboard for managing TART virtual machines across multiple Mac nodes, with save/resume support via a local Docker registry.

## Features

- Multi-user login with per-user VM namespacing
- Multi-node Mac cloud — schedule VMs across multiple Mac Minis automatically
- Create VMs from TART images (macOS/Linux)
- Start/stop local VMs from the dashboard
- **Save & Shutdown** — push VM disk to local Docker registry, free the Mac node
- **Resume** — pull VM from registry, start on any available Mac node
- In-browser VNC console via noVNC + SSH tunnel
- Admin node management UI (add/remove Mac nodes)
- HTMX auto-refresh dashboard

VM states shown in UI: `creating`, `running`, `stopped`, `pushing`, `archived`, `pulling`, `failed`.
Dashboard polling reconciles DB VM status with each node agent's VM list to avoid stale status labels.

## Architecture

```
Browser → Flask UI (:5000) → TART Agent (:7000 on each Mac) → TART VMs
Browser → Flask SSH tunnel → Mac node websockify → VM VNC (:5900)

VM disks stored in: Local Docker Registry (:5001)
VM state tracked in: SQLite DB (orchard_ui.db)
```

See `docs/refurbish_plan.md` for full architecture documentation.

---

## Requirements

- Python 3.10+
- One or more Mac nodes with [TART](https://github.com/cirruslabs/tart) installed
- Docker (for the local VM registry) on the central machine
- SSH key access from the Flask server to each Mac node

# Install the Docker command line tools and Colima (the engine)
brew install docker colima
colima start
brew services start colima # IMPORTANT


# create SSH key on manager MAC, adn authorise it on all nodes
ssh-keygen -t ed25519 -f /Users/admin/.ssh/id_ed25519 -N ""

authorise it by copying:
ssh-copy-id -i /Users/admin/.ssh/id_ed25519.pub admin@192.168.1.196

# INCREASE FILE LIMITs
Create system limit file:
sudo nano /Library/LaunchDaemons/limit.maxfiles.plist

PASTE THIS CONTENT:
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>limit.maxfiles</string>
    <key>ProgramArguments</key>
    <array>
      <string>launchctl</string>
      <string>limit</string>
      <string>maxfiles</string>
      <string>65536</string>
      <string>200000</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
  </dict>
</plist>

Fix permissions:
sudo chown root:wheel /Library/LaunchDaemons/limit.maxfiles.plist
sudo chmod 644 /Library/LaunchDaemons/limit.maxfiles.plist

Reload systemctl:
sudo launchctl load -w /Library/LaunchDaemons/limit.maxfiles.plist

REBOOT MAC








## Development Setup (Flask server)

```bash
# 1. Create and activate virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download noVNC static files
bash scripts/setup_novnc.sh

# 4. Configure environment
cp .env.example .env
# Edit .env — minimum: set SECRET_KEY, REGISTRY_URL, AGENT_TOKEN

# 5. (Optional) Generate a self-signed TLS certificate for HTTPS
bash scripts/generate_cert.sh
# Then set 
echo SSL_CERT=cert.pem >> .env
echo SSL_KEY=key.pem >> .env

# 6. Run
source .venv/bin/activate
python run.py          # respects SSL_CERT/SSL_KEY from .env
# or: flask run        # for development
# or: helper script that prepares .venv + deps automatically
./run.sh
```

Open [http://localhost:5000](http://localhost:5000) (or `https://` if SSL vars are set).
Default user: admin/admin123

On first run, the SQLite database is created automatically (`orchard_ui.db`).

Note for VNC: when connecting from a remote browser, open Orchard UI over `https://`.
Apple ARD VNC auth requires browser cryptography APIs that are restricted on plain HTTP.

### Production runtime (recommended)

Run Orchard UI behind a reverse proxy (nginx/caddy) with TLS enabled:

```bash
# Example gunicorn command (threaded workers support Flask-Sock websocket bridge)
gunicorn -w 2 --threads 8 -b 127.0.0.1:5000 run:app
```

Set these env vars in production:

```bash
TRUST_PROXY=true
FORCE_HTTPS=true
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Lax
```

The console now uses same-origin websocket path `/console/ws/<vm_name>`, so browser VNC traffic stays on manager HTTPS/WSS endpoint.

### Operational git workflow (manager host)

Use this once to connect an existing operational folder to Git while preserving local data:

```bash
cd /Users/Shared
tar -czf TART_Manager_backup_$(date +%Y%m%d_%H%M%S).tar.gz TART_Manager

cd /Users/Shared/TART_Manager
mkdir -p /tmp/tart_manager_keep
cp -a .env instance logs /tmp/tart_manager_keep/ 2>/dev/null || true

git init
git remote add origin https://github.com/sabatico/orchard_ui.git
git fetch origin
git reset --hard origin/main
git branch -M main
git branch --set-upstream-to=origin/main main

cp -a /tmp/tart_manager_keep/.env /Users/Shared/TART_Manager/ 2>/dev/null || true
cp -a /tmp/tart_manager_keep/instance /Users/Shared/TART_Manager/ 2>/dev/null || true
cp -a /tmp/tart_manager_keep/logs /Users/Shared/TART_Manager/ 2>/dev/null || true
```

Daily update command:

```bash
cd /Users/Shared/TART_Manager
./deploy.sh
```

Optional service restart during deploy:

```bash
RESTART_CMD='sudo launchctl kickstart -k system/com.orchard-ui' ./deploy.sh
```

Quick manual start:

```bash
cd /Users/Shared/TART_Manager
./run.sh
```

**Create your first user** by visiting `/auth/register`.
To make yourself an admin, open a flask shell:
```bash
flask shell
>>> from app.extensions import db
>>> from app.models import User
>>> u = User.query.filter_by(username='your-username').first()
>>> u.is_admin = True
>>> db.session.commit()
```

---

## Mac Node Setup (each Mac)
###DISABLE Keychain locking on every mac
security set-keychain-settings -t 0 login.keychain

### enable automatic log in in ui ( this is to enable keychain access withto uscripts that cotain plain text passwords)
Enable Automatic Login: Go to System Settings > Users & Groups and set "Automatic login" to your admin user.




```bash
# Deploy agent (run from the Flask server machine):
bash scripts/deploy_agent.sh <mac-node-ip> <ssh-user>

# Set the shared auth token on the node:
ssh <ssh-user>@<mac-node-ip> 'echo YOUR_TOKEN > ~/.agent_token'

# Start the agent on the node:
ssh <ssh-user>@<mac-node-ip> '~/tart_agent/start_agent.sh'
```

See `tart_agent/README.md` for full agent documentation and endpoint reference.

---

## Registry Setup (central machine)

```bash
# Start the local Docker registry (stores VM disk images):
bash scripts/setup_registry.sh

# Verify:
curl http://localhost:5001/v2/
```

Set `REGISTRY_URL` in your `.env` (both formats are accepted):
- `<this-machine-ip>:5001`
- `http://<this-machine-ip>:5001/v2/`

---

## Adding Mac Nodes (web UI)

1. Log in as an admin user
2. Go to **Nodes** in the navbar
3. Click **Add Node** — fill in name, host/IP, SSH user, SSH key path, agent port (default 7000), max VMs
4. The node will appear in the table with its current health status

---

## Configuration

All config is via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | dev value | Flask session secret — **change in production** |
| `DATABASE_URL` | `sqlite:///orchard_ui.db` | SQLAlchemy DB URI |
| `REGISTRY_URL` | `localhost:5001` | Local Docker registry endpoint (`host:port` or `http://host:port/v2/`) |
| `AGENT_TOKEN` | (empty) | Shared secret for TART agent auth — set same value on all nodes |
| `VNC_DEFAULT_PASSWORD` | `admin` | TART default VNC password |
| `WEBSOCKIFY_PORT_MIN` | `6900` | Start of SSH tunnel local port range |
| `WEBSOCKIFY_PORT_MAX` | `6999` | End of SSH tunnel local port range |
| `SSL_CERT` | — | Path to TLS certificate (PEM). Enables HTTPS when set. |
| `SSL_KEY` | — | Path to TLS private key (PEM). |
| `TRUST_PROXY` | `false` | Trust `X-Forwarded-*` headers when running behind nginx/caddy. |
| `FORCE_HTTPS` | `false` | Redirect HTTP to HTTPS for non-localhost requests. |
| `SESSION_COOKIE_SECURE` | `false` | Send session cookie over HTTPS only. |
| `SESSION_COOKIE_HTTPONLY` | `true` | Mark session cookie HttpOnly. |
| `SESSION_COOKIE_SAMESITE` | `Lax` | SameSite policy for session cookie. |
| `VM_POLL_INTERVAL_MS` | `5000` | Dashboard auto-refresh interval (ms) |
| `TART_IMAGES` | (5 cirruslabs images) | Comma-separated list of base images for the create form |

---

## Project Structure

```
orchard_UI/          ← Flask web app (this repo)
├── app/
│   ├── __init__.py          # App factory
│   ├── models.py            # User, Node, VM ORM models
│   ├── tart_client.py       # HTTP client for TART agents
│   ├── node_manager.py      # Node scheduling (find best node)
│   ├── tunnel_manager.py    # SSH tunnel manager (VNC proxy)
│   ├── main/                # Dashboard, create/start/stop/save/resume/delete routes
│   ├── api/                 # HTMX polling endpoints
│   ├── console/             # VNC console routes
│   ├── auth/                # Login, logout, register
│   └── nodes/               # Admin node management
├── config.py
├── run.py
├── scripts/
│   ├── setup_novnc.sh       # Download noVNC
│   ├── setup_registry.sh    # Start local Docker registry
│   └── deploy_agent.sh      # Deploy TART agent to a Mac node
└── docs/                    # Architecture and module documentation

tart_agent/          ← Agent (deployed to each Mac node, sibling dir)
├── agent.py                 # Flask HTTP service
├── tart_runner.py           # tart CLI wrappers
├── vnc_manager.py           # Local websockify lifecycle
└── requirements.txt
```
