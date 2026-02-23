# Orchard UI

A Flask web dashboard for managing TART virtual machines across multiple Mac nodes, with save/resume support via a local Docker registry.

## Features

- Multi-user login with per-user VM namespacing
- Invitation-based onboarding (admin creates user, user sets password from invite link)
- Per-user quotas: active VMs, saved VMs, and saved-disk quota (GB)
- Admin user management UI (role + quota controls)
- Admin settings UI for SMTP configuration and test email
- Multi-node Mac cloud — schedule VMs across multiple Mac Minis automatically
- Create VMs from TART images (macOS/Linux)
- Start/stop local VMs from the dashboard
- Recover failed VMs by starting them again from UI
- **Save & Shutdown** — push VM disk to local Docker registry, free the Mac node
- **Resume** — pull VM from registry, start on any available Mac node
- VM detail progress panel for save/resume/re-pull/migrate (stage, %, transferred GB, and latest raw Tart line)
- Global loading overlay mirrors current operation stage/progress while async actions are running
- In-browser VNC console via noVNC (direct WS on LAN, SSH tunnel for WAN)
- Live VNC profile switch (`Optimize Bandwidth` / `Optimize Render`) in console toolbar
- Admin node management UI (add/remove Mac nodes)
- Node deactivation drain guardrail: deactivating a node marks it inactive immediately and archives resident running/stopped VMs before users continue
- Node deactivation now shows live multi-VM archive progress in global overlay (current VM + completed/total)
- Admin **Dashboard** (cross-user operational view) with status-aware VM actions
- Admin **My VMs** tab preserved for personal VM view (same as non-admin users)
- Admin **Registry Storage** tab: trackable vs orphaned registry artefacts, per-item size, and manual orphan delete
- HTMX auto-refresh dashboard

VM states shown in UI: `creating`, `running`, `stopped`, `pushing`, `archived`, `pulling`, `failed`.
Dashboard polling reconciles DB VM status with each node agent's VM list to avoid stale status labels.
Delete operations are defensive: manager stops VNC + VM first, then deletes, to handle Tart's "running VM delete appears as not found" behavior.
Save/migrate actions perform a fast preflight against registry-backed free space and fail early when capacity is insufficient.
Save quota enforcement uses archived VM sizes from SQL plus current VM `SizeOnDisk` from the node before starting save.
Registry repository segments are sanitized before Tart push/pull (safe with email-like usernames).

## Architecture

```
Browser → Caddy (TLS) → Flask UI (:5000) → TART Agent (:7000 on each Mac) → TART VMs

VNC console (LAN, default):
  Browser WSS → Caddy → Flask WS bridge → node websockify → VM VNC :5900

VNC console (WAN / VNC_USE_SSH_TUNNEL=true):
  Browser WSS → Caddy → Flask WS bridge → SSH tunnel → node websockify → VM VNC :5900

VNC console (browser-direct, optional):
  Browser WSS → node websockify endpoint directly (no Flask WS bridge)
  (requires TLS-capable node endpoint; plain node `ws://:6900` cannot be used from `https://` pages)

VM disks stored in: Local Docker Registry (:5001)
VM state tracked in: SQLite DB (orchard_ui.db)
```

### Why This Architecture

- **Reverse proxy (Caddy/nginx)** terminates TLS so Flask/Gunicorn stay on plain HTTP. Apple VNC/ARD authentication (`RFB 003.889`) uses browser WebCrypto APIs that only work in a secure context -- remote VNC requires HTTPS.
- **Same-origin WS gateway** (`/console/ws/<vm>`) keeps all browser traffic on the manager endpoint. The Flask bridge relays frames between the browser and node-side websockify.
- **Direct WS to node** (default on LAN) connects straight to the node's websockify, avoiding SSH encryption and tunnel-thread overhead. On WAN/data-center setups, set `VNC_USE_SSH_TUNNEL=true` to route through an encrypted SSH tunnel instead.
- **Node-local websockify** converts WebSocket frames to raw TCP for the VM's VNC port. Each node agent manages its own websockify processes.
- **DB state + agent reconciliation**: the database stores VM state for fast UI rendering, but agent polling on page load/refresh is the source of truth for actual runtime state.

See `docs/5.Production_refurbish_vnc.md` and `docs/refurbish_plan.md` for deeper technical notes.

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

Run Orchard UI behind a reverse proxy (nginx/caddy) with TLS enabled.

#### Reverse proxy prerequisites

Before enabling `FORCE_HTTPS=true`, make sure:

- The Flask/Gunicorn app is reachable on local HTTP (recommended: `127.0.0.1:5000`)
- A reverse proxy is configured to terminate TLS and forward to that local HTTP upstream
- WebSocket upgrades are supported by the proxy for `/console/ws/<vm_name>`
- Flask trusts proxy headers (`TRUST_PROXY=true`) so `request.is_secure` is correct

Without a proxy, forcing HTTPS can cause timeout/protocol errors (browser HTTPS to an HTTP-only backend).

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
In production, prefer `./run.sh` (it loads `.env` and automatically uses gunicorn when `FLASK_ENV=production`).
Default VNC profile is bandwidth-optimized; you can switch profiles live inside the console toolbar.

#### Simple Caddy option (LAN/VPN)

Caddy is the easiest reverse proxy setup for a private network.

1) Install Caddy on manager:

```bash
brew install caddy
```

2) Create a Caddyfile (path depends on brew prefix, e.g. `/opt/homebrew/etc/Caddyfile`):

```caddy
192.168.1.195 {
    tls internal
    reverse_proxy 127.0.0.1:5000
}
```

3) Start Caddy:

```bash
brew services start caddy
```

4) Validate/format Caddyfile when updating config:

```bash
caddy fmt --overwrite /opt/homebrew/etc/Caddyfile
caddy validate --config /opt/homebrew/etc/Caddyfile
brew services restart caddy
```

5) Trust Caddy local CA on user Macs (one-time) so browser accepts the certificate.

- Homebrew Caddy certificate paths (Apple Silicon):
  - leaf certs: `/opt/homebrew/var/lib/caddy/certificates/local/<manager-ip>/`
  - CA root to trust on clients: `/opt/homebrew/var/lib/caddy/pki/authorities/local/root.crt`
- Import `root.crt` into macOS Keychain (`System`) and set **Always Trust**.

Then open the manager UI using `https://<manager-ip>`.

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

Initial account bootstrap is now invitation/admin-based.  
If this is a fresh install with no admins, follow **Bootstrap initial admin (one-time)** in the Multi-user section below.

---

## Mac Node Setup (each Mac)
### Disable keychain locking on each Mac
security set-keychain-settings -t 0 login.keychain

### Enable automatic login
Set automatic login in System Settings > Users & Groups so Tart/keychain-backed operations can run after reboot without an interactive login prompt.

### macOS Tahoe local-network permission (important)

On fresh Tahoe installs, `tart pull` can fail with:

- `Error: The Internet connection appears to be offline.`

even when `curl` to the registry works. This is usually macOS Local Network privacy gating for the runtime process.

Check on each node:

- `System Settings > Privacy & Security > Local Network`

Recommended entries for the node user/session:

- `Terminal` → enabled
- `sshd-session` → enabled (if using SSH sessions for operations)
- `Python` (venv/system) → enabled when agent/runtime uses python networking

One-time fallback to trigger the permission popup (run on the node as the same user that runs Tart/agent):

```bash
tart pull <manager-ip>:5001/<user>/<vm>:latest --insecure
```

If popup appears ("allow to find devices on local network"), click **Allow**.  
After granting, retry save/migrate/re-pull from Orchard UI.




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

Operational defaults used by the setup script:

- Registry data path: `/Users/Shared/tart-registry` (stable absolute mount)
- Delete API enabled: `REGISTRY_STORAGE_DELETE_ENABLED=true`

If you need to recreate the container while preserving existing images, keep the same host path mount:

```bash
docker stop tart-registry || true
docker rm tart-registry || true
docker run -d \
  -p 5001:5000 \
  -v /Users/Shared/tart-registry:/var/lib/registry \
  -e REGISTRY_STORAGE_DELETE_ENABLED=true \
  --restart always \
  --name tart-registry \
  registry:2
```

Set `REGISTRY_URL` in your `.env` (both formats are accepted):
- `<this-machine-ip>:5001`
- `http://<this-machine-ip>:5001/v2/`

---

## VM UI Behavior (latest)

- Navbar naming:
  - All users see `My VMs`
  - Admins also see `Dashboard` (cross-user operations)
- Admin dashboard includes `running`, `stopped`, `archived`, `pushing`, `pulling`, and `failed` rows.
- Admin dashboard actions are status-aware (`Start`, `Stop`, `Archive`, `Resume`, `Re-Pull`, `Delete`).
- In-progress rows include a one-time progress snapshot (stage/percent/transfer) at page render.
- VM details page polls live operation data every 5s and shows:
  - stage label
  - percent
  - transferred/total GB (when available)
  - latest raw Tart line (for example `waiting for lock...`)

---

## Registry Artefact Cleanup

Cleanup behavior after successful lifecycle operations:

- `resume` / `re-pull` / migration restore completion (`pulling -> running`):
  - manager resolves manifest digest from `vm.registry_tag`
  - manager deletes manifest by digest (`DELETE /v2/<repo>/manifests/<digest>`)
- delete (user/admin):
  - manager deletes local VM first
  - manager then performs registry cleanup before DB row removal

Operational guarantees:

- cleanup is best-effort and idempotent
- missing tag/manifest is treated as already-cleaned success
- cleanup failures do **not** rollback successful VM lifecycle outcome
- cleanup outcome is stored on VM metadata:
  - `cleanup_status`
  - `cleanup_last_error`
  - `cleanup_last_run_at`
  - `cleanup_target_digest`
- admin dashboard shows cleanup warnings and supports **Retry Cleanup**

Registry garbage collection note:

- deleting a manifest removes the tag/manifests reference immediately
- underlying blobs may still occupy disk until registry GC compacts them
- disk reclamation timing depends on your registry GC policy/runtime

---

## Troubleshooting

### Re-pull stuck at `waiting for lock...`

Symptom in node logs:

- `pulling manifest...`
- `waiting for lock...`

Cause:

- orphaned `tart pull` processes from earlier failed/abandoned attempts keep Tart's image lock.

Fix:

- update node agent to include stale-pull cleanup before each new pull (`tart_runner.pull_vm` now terminates old matching `tart pull` processes for the same tag).
- if needed before upgrade, manually terminate stale pulls on node:

```bash
ps -ax | rg "tart pull"
kill <pid>
```

Additional note:

- operation progress now exposes the latest raw Tart line in UI and overlay, so lock waits are visible immediately.

### Cleanup failed (warning badge)

Symptom:

- VM lifecycle operation succeeded, but cleanup badge shows `Warning`.

What to do:

- use `Retry Cleanup` from admin dashboard row
- verify manager can reach registry endpoint from `REGISTRY_URL`
- check manager logs for entries starting with `registry_cleanup`
- ensure registry container was started with `REGISTRY_STORAGE_DELETE_ENABLED=true`
- ensure registry container mounts the expected persistent path (`/Users/Shared/tart-registry`)

Expected behavior:

- VM stays in its successful state (`running`, `archived`, or deleted)
- only cleanup metadata indicates warning/failure until retry succeeds

### Registry Storage page looks empty after registry recreate

Symptom:

- Admin `Registry Storage` shows no artefacts and full free capacity.

Most common cause:

- registry container was recreated with a different host mount path.

Check:

```bash
docker inspect tart-registry --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
curl http://localhost:5001/v2/_catalog
```

Fix:

- recreate container with the original path mount:
  `/Users/Shared/tart-registry:/var/lib/registry`

---

## Adding Mac Nodes (web UI)

1. Log in as an admin user
2. Go to **Nodes** in the navbar
3. Click **Add Node** — fill in name, host/IP, SSH user, SSH key path, agent port (default 7000), max VMs
4. The node will appear in the table with its current health status

### Nodes table snapshots

For each node, the table shows one-time snapshots at page load:

- `VMs`: running / max
- `RAM`: used / total (GB)
- `CPU`: usage %
- `Network`: throughput + interface type (for example `12.3 Mbps/Wifi`, `75.0 Mbps/Eth`)
- `Disk Free`: free GB

### Node deactivation behavior (guardrail)

When admin presses `Deactivate` on a node:

1. Node is marked inactive immediately (scheduler stops placing new workloads there).
2. New start/migrate/re-pull actions targeting that node are blocked.
3. Existing `running`/`stopped` VMs on that node are archived.
4. A live global overlay tracks deactivation progress (`VM x/y`, current VM, and error/done state).
5. Users later see those VMs in `archived` state (`node_id` cleared).

If any VM archive fails, the node remains inactive and admin gets failure details to resolve manually.
Inactive nodes remain visible in the Nodes UI and can be re-activated or deleted (delete action is available only when node is inactive and no VM rows still reference that node).

---

## Configuration

Core runtime config is via environment variables (see `.env.example`).
SMTP can be configured in two ways:
- Preferred: **Admin UI** -> `Settings` (saved in DB `app_settings`)
- Optional fallback: environment variables below

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | dev value | Flask session secret — **change in production** |
| `DATABASE_URL` | `sqlite:///orchard_ui.db` | SQLAlchemy DB URI |
| `REGISTRY_URL` | `localhost:5001` | Local Docker registry endpoint (`host:port` or `http://host:port/v2/`) |
| `REGISTRY_STORAGE_TOTAL_GB` | `600` | Total registry capacity used by Admin Registry Storage bar |
| `AGENT_TOKEN` | (empty) | Shared secret for TART agent auth — set same value on all nodes |
| `MAIL_SERVER` | (empty) | SMTP host fallback (used when admin settings are not configured) |
| `MAIL_PORT` | `587` | SMTP port fallback |
| `MAIL_USE_TLS` | `true` | STARTTLS fallback flag |
| `MAIL_USE_SSL` | `false` | SMTP SSL fallback flag |
| `MAIL_USERNAME` | (empty) | SMTP username fallback |
| `MAIL_PASSWORD` | (empty) | SMTP password fallback |
| `MAIL_DEFAULT_SENDER` | (empty) | Sender email fallback |
| `VNC_DEFAULT_PASSWORD` | `admin` | TART default VNC password |
| `VNC_USE_SSH_TUNNEL` | `false` | Route VNC through SSH tunnel (set `true` for WAN/data center) |
| `VNC_BROWSER_DIRECT_NODE_WS` | `false` | Browser connects directly to node websockify (bypasses Flask WS relay) |
| `VNC_BROWSER_DIRECT_NODE_WS_SCHEME` | auto | Direct mode scheme override (`ws` or `wss`) |
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
│   ├── models.py            # User, Node, VM, AppSettings ORM models
│   ├── tart_client.py       # HTTP client for TART agents
│   ├── node_manager.py      # Node scheduling (find best node)
│   ├── tunnel_manager.py    # SSH tunnel manager (VNC proxy)
│   ├── main/                # Dashboard, create/start/stop/save/resume/delete routes
│   ├── api/                 # HTMX polling endpoints
│   ├── console/             # VNC console routes
│   ├── auth/                # Login/logout + invite password setup
│   ├── admin/               # Manage users + SMTP settings
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

---

## Multi-user Flow

1. Bootstrap one initial admin account (one-time, if DB is empty).
2. Admin logs in and opens `Manage Users` from the account dropdown.
3. Admin creates users by email and sets role/quotas:
   - Active VM limit (default `1`)
   - Saved VM limit (default `2`)
   - Saved-disk quota in GB (default `100`)
4. Admin configures SMTP in `Settings` (or uses env fallback values).
5. User receives invite email and sets password via `/auth/set-password/<token>`.
6. After first password set, user logs in with email/password and works within quotas.

### Bootstrap initial admin (one-time)

If you have no admin yet, create one from Flask shell:

```bash
flask shell
>>> from app.extensions import db, bcrypt
>>> from app.models import User
>>> u = User(
...     username='admin@example.com',
...     email='admin@example.com',
...     password_hash=bcrypt.generate_password_hash('ChangeMeNow123!').decode('utf-8'),
...     is_admin=True,
...     must_set_password=False,
... )
>>> db.session.add(u)
>>> db.session.commit()
```
