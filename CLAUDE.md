# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Development
source .venv/bin/activate
python run.py                            # Flask dev server (default port 5000)

# First-time setup
python3 -m venv .venv
pip install -r requirements.txt
bash scripts/setup_novnc.sh             # Download noVNC static files
bash scripts/setup_registry.sh         # Spin up local Docker registry on :5001
bash scripts/generate_cert.sh          # Self-signed TLS cert for local HTTPS dev
bash scripts/deploy_agent.sh           # Deploy TART agent to a Mac node
cp .env.example .env                    # Then edit .env

# Tests
python -m unittest discover tests/
python -m unittest tests.test_registry_cleanup                          # Single test file
python -m unittest tests.test_registry_cleanup.RegistryCleanupTests    # Single test class

# Production
FLASK_ENV=production gunicorn -w 2 --threads 8 -b 127.0.0.1:5000 run:app

# Database migrations (Flask-Migrate)
flask db migrate -m "description"
flask db upgrade
```

## Architecture

**Stack:** Flask 3 + SQLAlchemy + SQLite, Jinja2 templates + HTMX for dynamic updates, WebSocket (flask-sock) for VNC bridging.

**App factory:** `app/__init__.py → create_app()` initializes extensions, creates DB tables, wires up services, and registers blueprints.

**Blueprints:**

| Blueprint | Prefix | Purpose |
|-----------|--------|---------|
| `main` | `/` | User dashboard, VM CRUD (create/start/stop/save/resume/delete) |
| `console` | `/console` | VNC console page + WebSocket bridge |
| `api` | `/api` | HTMX polling endpoints for status/progress |
| `auth` | `/auth` | Login, signup, invite-based onboarding |
| `admin` | `/admin` | User management, registry, gold images, metrics |
| `nodes` | `/nodes` | Node health, activation, deactivation workflow |

**Core services** (instantiated in `create_app`, stored on `app`):
- `TartClient` (`app/tart_client.py`) — HTTP client for the TART agent API (Bearer token auth). All VM operations go through this.
- `NodeManager` (`app/node_manager.py`) — selects the best node for new VMs, builds registry tags.
- `TunnelManager` (`app/tunnel_manager.py`) — manages SSH port-forward tunnels for VNC over WAN.
- `DirectTcpProxyManager` (`app/direct_tcp_proxy.py`) — raw TCP proxy for native `.vncloc` VNC clients.
- `registry_cleanup` / `registry_inventory` — OCI registry manifest operations.

**VNC modes** (controlled by env vars):
1. **LAN direct** (default): Browser WS → Flask WS bridge → node websockify → VM VNC :5900
2. **SSH tunnel** (`VNC_USE_SSH_TUNNEL=true`): Adds SSH hop between Flask and node
3. **Browser-direct** (`VNC_BROWSER_DIRECT_NODE_WS=true`): Browser connects directly to node websockify

**Key data flow for VM operations:**
1. User action hits a main/admin blueprint route
2. Route calls `TartClient` method on the appropriate node
3. Long-running ops (save, resume, migrate) return an `op_key`; the `/api/vms/<name>/operation` endpoint polls progress
4. DB status is updated to reflect the new state; HTMX polls `/api/vms` to refresh the dashboard

**Multi-tenancy:** VMs are namespaced per user via OCI registry tags (`user@domain` → sanitized to OCI-safe path). Each user has quota fields on the `User` model (max VMs, disk GB).

**SQLite compatibility layer:** `app/__init__.py` runs `ALTER TABLE` statements on startup to add columns that may be missing from older schema versions (instead of relying solely on Flask-Migrate).

## Infrastructure

SSH certificate-based access is available to all nodes (no password needed):

| IP | Role | Install path |
|----|------|-------------|
| 192.168.1.195 | Manager + Agent node | `/Users/Shared/TART_Manager` (manager), `/Users/Shared/TART_Agent` (agent) |
| 192.168.1.196 | Agent node | `/Users/Shared/TART_Agent` |
| 192.168.1.141 | Agent node | `/Users/Shared/TART_Agent` |

The manager app (Flask + gunicorn) runs on `.195`. Agent nodes run the TART agent process. Service restart uses macOS launchctl (e.g. `sudo launchctl kickstart -k system/com.orchard-ui` on the manager).

**Key env vars** (see `.env.example` and `config.py` for full list):
- `SECRET_KEY` — Flask session secret
- `AGENT_TOKEN` — shared secret for TART agent auth
- `REGISTRY_URL` — Docker registry endpoint (e.g. `https://registry.example.com:5001`)
- `REGISTRY_STORAGE_TOTAL_GB` — capacity gauge shown on Admin → Registry page
- `VNC_USE_SSH_TUNNEL`, `VNC_BROWSER_DIRECT_NODE_WS` — VNC transport mode
- `VNC_DEFAULT_USERNAME`, `VNC_DEFAULT_PASSWORD` — Cirrus Labs base images default to `admin/admin`; required for ARD auth
- `VNC_DIRECT_PORT_MIN/MAX` (57000–57099) — port range for raw TCP proxy (`.vncloc` native client)
- `VNC_DIRECT_HOST` — override hostname in `.vncloc` files for external VNC clients
- `VNC_TCP_TUNNEL_PORT_MIN/MAX` (57100–57199) — SSH tunnel forwarding port range
- `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER` — SMTP (also configurable at runtime via `AppSettings` model)
- `FORCE_HTTPS`, `TRUST_PROXY` — reverse proxy config
- `FLASK_ENV` — `development` or `production`
- `VM_POLL_INTERVAL_MS` — HTMX polling interval (default 5000)

**Auth & access control:**
- `@admin_required` decorator (`app/utils.py`) — redirects non-admins to dashboard
- Invite flow: tokens valid 72 hours; `must_set_password` flag on User forces password change before login
- `RegistrationRequest` model tracks open signup requests pending admin approval

**Audit & usage models:**
- `VMStatusEvent` — immutable log of every VM status transition (source, context, timestamps)
- `VMVncSession` — records VNC session start/end per connection; drives usage metrics
- Helpers in `app/usage_events.py`: `record_vm_status_transition()`, `set_vm_status()`, `start_vnc_session()`, `close_vnc_session()`

**Gold image distribution:**
- `GoldImage` / `GoldImageNode` models track per-node image distribution state (pending → pulling → ready/failed)
- `trigger_gold_distribution()` in `app/gold_distribution.py` fans out a `pull_image` call to every node

**Logging:** `configure_logging()` in `run.py` must run before any app import. Writes to `logs/orchard_ui.log` (5 MB rotating, 3 backups).
