# Transition Plan: Orchard UI → TART-Direct Architecture

> **Date**: 2026-02-21
> **Source**: Existing Orchard-based implementation (Modules 1–3 complete)
> **Target**: TART-Direct + Local Docker Registry (see `refurbish_plan.md`)
> **Status**: ✅ Complete — all phases implemented 2026-02-21

---

## Guiding Principles

- **Never break what works**: Keep the Flask app runnable after each phase
- **Parallel construction**: Build new components alongside old ones, then cut over
- **File-by-file substitution**: Replace old files one at a time so diffs are reviewable
- **Test each phase**: Every phase ends with a working system

---

## Overview

```
Phase 0: Foundation prep (DB, models, auth)           ✅ Complete
Phase 1: TART Agent (new component, deployed to Mac nodes)  ✅ Complete
Phase 2: TartClient (replaces OrchardClient)          ✅ Complete
Phase 3: TunnelManager (replaces WebsockifyManager for VNC)  ✅ Complete
Phase 4: Routes + Templates (adapt all blueprints)    ✅ Complete
Phase 5: Remove Orchard code                          ✅ Complete
Phase 6: Node management UI                           ✅ Complete
Phase 7: Polish & deploy                              ✅ Complete
```

---

## Phase 0: Foundation Preparation

**Goal**: Add SQLite database, models, and auth to the Flask app. No breaking changes — existing routes still use OrchardClient.

### 0.1 Add dependencies ✅

Updated `requirements.txt`:

```
Flask==3.1.0
requests==2.32.3
python-dotenv==1.0.1
websockify==0.12.0
gunicorn==23.0.0
paramiko==3.5.0           # NEW — SSH tunnels for VNC
Flask-SQLAlchemy==3.1.1   # NEW — ORM for DB
Flask-Login==0.6.3        # NEW — user session management
Flask-Bcrypt==1.0.1       # NEW — password hashing
```

Installed:
```bash
cd /Users/isa/Documents/Personal/CodingProjects/orchard_ui/orchard_UI
source .venv/bin/activate
pip install paramiko Flask-SQLAlchemy Flask-Login Flask-Bcrypt
pip freeze > requirements.txt
```

### 0.2 Create `app/models.py` ✅

New file with User, Node, VM ORM models. `lazy='select'` on relationships (SQLAlchemy 2.x compatible).

### 0.3 Update `app/extensions.py` ✅

Replaced empty placeholder stub with real SQLAlchemy + Flask-Login + Bcrypt initialization:

```python
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'warning'
bcrypt = Bcrypt()

def init_extensions(app):
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
```

### 0.4 Update `config.py` ✅

Added new keys, removed Orchard keys:

```python
SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///orchard_ui.db')
SQLALCHEMY_TRACK_MODIFICATIONS = False
REGISTRY_URL = os.environ.get('REGISTRY_URL', 'localhost:5001')
AGENT_TOKEN = os.environ.get('AGENT_TOKEN', '')
```

### 0.5 Update `app/__init__.py` ✅

Added DB initialization + table creation, wired TartClient + NodeManager + TunnelManager, registered all blueprints.

### 0.6 Create auth blueprint ✅

- **`app/auth/__init__.py`**: Activated from empty placeholder to real Blueprint definition
- **`app/auth/routes.py`**: Created login, logout, register routes
- **`app/templates/auth/login.html`** and **`register.html`**: Bootstrap 5 dark forms

### 0.7 Register auth blueprint in `app/__init__.py` ✅

Auth blueprint registered at `/auth` prefix.

### Phase 0 checkpoint ✅

- `flask run` starts without errors
- `/auth/register` creates a user
- `/auth/login` logs in
- Database file `orchard_ui.db` created with 3 tables (users, vms, nodes)

---

## Phase 1: Build the TART Agent

**Goal**: Create the `tart_agent/` package that runs on each Mac node. This is independent of the Flask UI. Developed as a **sibling directory** to `orchard_UI/` (at `/Users/isa/Documents/Personal/CodingProjects/orchard_ui/tart_agent/`).

### 1.1 Create `tart_agent/` directory structure ✅

```
tart_agent/
├── agent.py           # Flask app entrypoint
├── tart_runner.py     # tart CLI subprocess wrapper
├── vnc_manager.py     # websockify lifecycle (local to each Mac node)
├── agent_config.py    # configuration
└── requirements.txt   # Flask, websockify
```

### 1.2 `tart_agent/requirements.txt` ✅

```
Flask==3.1.0
websockify==0.12.0
```

### 1.3 `tart_agent/agent_config.py` ✅

Environment-variable based config for port, token, registry URL, binary paths.

### 1.4 `tart_agent/tart_runner.py` ✅

Wraps `tart` CLI calls as Python functions: list_vms, get_vm_ip, create_vm, start_vm, stop_vm, push_vm, pull_vm, delete_vm, vm_exists.

### 1.5 `tart_agent/vnc_manager.py` ✅

Thread-safe websockify subprocess manager local to each Mac node. Same port-range pattern as the old `websockify_manager.py`.

### 1.6 `tart_agent/agent.py` ✅

Full Flask HTTP service with:
- All REST endpoints (health, vms CRUD, vnc start/stop)
- Async save/restore via daemon threads
- In-progress ops tracker `_ops` dict (poll `/vms/<name>/op`)
- Bearer token auth middleware (all endpoints except `/health`)

### 1.7 Deploy agent script: `scripts/deploy_agent.sh` ✅

`rsync` + `pip install` + start script generation via SSH.

### 1.8 `tart_agent/README.md` ✅

Full API reference and setup instructions.

### Phase 1 checkpoint ✅

- Agent structure created at sibling path `tart_agent/`
- All source files complete and importable
- `scripts/deploy_agent.sh` script created and chmod +x

---

## Phase 2: Build TartClient (Flask-side)

**Goal**: Create `app/tart_client.py` to replace `app/orchard_client.py`. The Flask UI uses this to call TART agents.

### 2.1 Create `app/tart_client.py` ✅

HTTP client for TART Agent API with:
- `TartAPIError` exception class
- Bearer token auth headers
- Per-call `Node` object routing
- All agent endpoint wrappers: get_health, list_vms, create_vm, start_vm, stop_vm, save_vm, restore_vm, get_op_status, get_vm_ip, delete_vm, start_vnc, stop_vnc

### 2.2 Add `NodeManager` service: `app/node_manager.py` ✅

- `find_best_node()`: picks active node with fewest running VMs via health checks
- `get_all_nodes_health()`: returns list of `(node, health_dict | None)` tuples
- `registry_tag_for(username, vm_name, registry_url)`: builds OCI path

### 2.3 Wire TartClient + NodeManager into `app/__init__.py` ✅

```python
app.tart = TartClient(app)
app.node_manager = NodeManager(app)
app.tunnel_manager = TunnelManager(app)
```

### Phase 2 checkpoint ✅

- All new services created and wired into the app
- App still starts cleanly

---

## Phase 3: TunnelManager (VNC via SSH)

**Goal**: Create `app/tunnel_manager.py` to replace local websockify. The agent manages local websockify on each Mac node; Flask manages the SSH tunnel.

### 3.1 Create `app/tunnel_manager.py` ✅

paramiko SSH port-forward tunnel manager:
- Thread-safe tunnels dict keyed by `vm_name`
- Port range from `WEBSOCKIFY_PORT_MIN`/`MAX` config (reuses same env vars)
- `start_tunnel(vm_name, node, remote_port)` → local_port
- `stop_tunnel(vm_name)`, `get_tunnel_port(vm_name)`, `cleanup_all()`

### 3.2 Register atexit cleanup in `app/__init__.py` ✅

```python
import atexit
atexit.register(app.tunnel_manager.cleanup_all)
```

### Phase 3 checkpoint ✅

- `current_app.tunnel_manager` available in app context
- atexit cleanup registered

---

## Phase 4: Update Routes and Templates

**Goal**: Port all blueprints to use TartClient + DB instead of OrchardClient. Templates updated for new VM states.

### 4.1 Add login_required guards ✅

All routes in `main/routes.py`, `console/routes.py`, `api/routes.py` decorated with `@login_required`.

### 4.2 Rewrite `app/main/routes.py` ✅

Replaced all Orchard calls with DB queries + TartClient calls:
- `dashboard()`: VMs from DB, not API
- `create_vm()`: picks best node via NodeManager, creates DB record, calls TartClient
- `vm_detail()`: DB lookup
- `start_vm()` (new): starts a stopped local VM (`status: stopped -> running`)
- `stop_vm()` (new): stops a running local VM (`status: running -> stopped`)
- `delete_vm()`: stops tunnel + VNC, deletes from agent, removes DB record
- `save_vm()` (new): triggers async push, sets status `pushing`
- `resume_vm()` (new): finds best node, triggers async pull, sets status `pulling`

### 4.3 Rewrite `app/api/routes.py` ✅

- `list_vms`: DB query, HTMX or JSON, plus reconciliation of local VM states from each node's `/vms` snapshot
- `vm_status`: polls agent op status when in `pushing`/`pulling`, transitions DB state on completion, and reconciles local `creating|running|stopped` states from agent data

### 4.4 Rewrite `app/console/routes.py` ✅

New VNC chain:
1. Calls `tart.start_vnc(node, vm_name)` → gets remote websockify port
2. Calls `tunnel_manager.start_tunnel(vm_name, node, remote_port)` → gets local port
3. Renders noVNC with `ws_host = request.host.split(':')[0]`

### 4.5 Update templates ✅

- **`base.html`**: Auth nav (user dropdown, login link, admin Nodes link)
- **`_partials/vm_status_badge.html`**: New states (stopped, archived, pushing, pulling, creating)
- **`_partials/vm_table.html`**: Context-aware action buttons (Console + Stop + Save&Shutdown for running; Start for stopped; Resume for archived; spinners for in-progress)
- **`main/dashboard.html`**: "Worker" → "Node" column header
- **`main/vm_detail.html`**: Save&Shutdown/Resume buttons, async progress banner, Registry card, removed events log
- **`main/create_vm.html`**: Minor text updates
- **`auth/login.html`**, **`auth/register.html`**: New Bootstrap 5 dark forms

### 4.6 Add `nodes/` blueprint ✅

New admin blueprint created:
- `GET /nodes/` — node status dashboard (admin only)
- `POST /nodes/add` — add node to DB
- `POST /nodes/<id>/toggle` — activate/deactivate
- `GET /nodes/<id>/health` — JSON health from agent
- `app/templates/nodes/index.html` — Node status table with add-node form

### Phase 4 checkpoint ✅

- Login required on all routes
- Dashboard shows VMs from DB
- Dashboard polling reconciles stale DB status from node agent VM lists
- Running VMs can be stopped; stopped VMs can be started
- Save & Shutdown triggers async push
- Resume triggers async pull
- VNC console wired through SSH tunnel
- Nodes admin page functional

---

## Phase 5: Remove Orchard Code

**Goal**: Delete all Orchard-specific code.

### 5.1 Files deleted ✅

```
app/orchard_client.py       → DELETED
app/websockify_manager.py   → DELETED
```

### 5.2 Files updated ✅

- **`app/__init__.py`**: Removed all Orchard + local WebsockifyManager imports and wiring
- **`config.py`**: Removed all `ORCHARD_*` keys; kept `WEBSOCKIFY_PORT_MIN/MAX` (repurposed for SSH tunnel local port range)
- **`.env.example`**: Rewritten with new keys only (no Orchard variables)

### Phase 5 checkpoint ✅

- `flask run` starts with no reference to Orchard
- No import errors
- All routes work with DB + TartClient

---

## Phase 6: Node Management UI

**Goal**: Admin can add/remove Mac nodes from the web UI.

### 6.1 Node admin page ✅

- `GET /nodes/` — table of all nodes with name, host, status (health check), running/max VMs
- `POST /nodes/add` — form: name, host, SSH user, SSH key path, agent port, max_vms
- `POST /nodes/<id>/toggle` — activate/deactivate node

### 6.2 Admin protection ✅

Node management routes check `current_user.is_admin`. Non-admins get a 403 response.

### Phase 6 checkpoint ✅

- Admin user can view all nodes and their health
- Admin can add a new Mac node via web form
- Deactivated nodes are excluded from `find_best_node()`

---

## Phase 7: Polish & Deploy

### 7.1 Setup scripts ✅

- **`scripts/setup_registry.sh`**: Starts `registry:2` Docker container on port 5001
- **`scripts/deploy_agent.sh`**: rsync + pip install + start script via SSH; chmod +x applied

### 7.2 TART Agent README ✅

`tart_agent/README.md` documents:
1. Setup instructions for each Mac node
2. Full API endpoint reference table
3. Auth configuration

### 7.3 Smoke tests passed ✅

- `python -c "from app import create_app; app = create_app(); print('OK')"` → OK
- 3 DB tables created (users, vms, nodes)
- 5 blueprints registered (main, console, api, auth, nodes)
- 18 URL rules verified

### Phase 7 checkpoint ✅

- App starts cleanly with no Orchard dependencies
- Scripts are executable and functional
- All docs updated

---

## File-Level Change Summary

| File | Action | Phase | Status |
|------|--------|-------|--------|
| `requirements.txt` | Add paramiko, Flask-SQLAlchemy, Flask-Login, Flask-Bcrypt | 0 | ✅ |
| `config.py` | Add DB/registry config; remove Orchard | 0, 5 | ✅ |
| `app/extensions.py` | Add db, login_manager, bcrypt | 0 | ✅ |
| `app/models.py` | CREATE: User, VM, Node models | 0 | ✅ |
| `app/__init__.py` | Add DB init, auth blueprint, TartClient, TunnelManager; remove Orchard | 0, 2, 3, 5 | ✅ |
| `app/auth/__init__.py` | Activate (was empty stub) | 0 | ✅ |
| `app/auth/routes.py` | CREATE: login, logout, register | 0 | ✅ |
| `app/templates/auth/login.html` | CREATE | 0 | ✅ |
| `app/templates/auth/register.html` | CREATE | 0 | ✅ |
| `tart_agent/agent.py` | CREATE | 1 | ✅ |
| `tart_agent/tart_runner.py` | CREATE | 1 | ✅ |
| `tart_agent/vnc_manager.py` | CREATE | 1 | ✅ |
| `tart_agent/agent_config.py` | CREATE | 1 | ✅ |
| `tart_agent/requirements.txt` | CREATE | 1 | ✅ |
| `tart_agent/README.md` | CREATE | 1 | ✅ |
| `scripts/deploy_agent.sh` | CREATE | 1 | ✅ |
| `app/tart_client.py` | CREATE: HTTP client for agent | 2 | ✅ |
| `app/node_manager.py` | CREATE: node scheduling | 2 | ✅ |
| `app/tunnel_manager.py` | CREATE: SSH tunnel VNC proxy | 3 | ✅ |
| `app/main/routes.py` | REWRITE: DB-based, new states, login_required | 4 | ✅ |
| `app/api/routes.py` | REWRITE: DB + agent polling | 4 | ✅ |
| `app/console/routes.py` | REWRITE: SSH tunnel + agent VNC | 4 | ✅ |
| `app/nodes/__init__.py` | CREATE | 4 | ✅ |
| `app/nodes/routes.py` | CREATE: admin node management | 4, 6 | ✅ |
| `app/templates/base.html` | UPDATE: auth nav, node link | 4 | ✅ |
| `app/templates/main/dashboard.html` | UPDATE: new VM states, new buttons | 4 | ✅ |
| `app/templates/main/vm_detail.html` | UPDATE: progress display, new actions | 4 | ✅ |
| `app/templates/_partials/vm_status_badge.html` | UPDATE: new states | 4 | ✅ |
| `app/templates/_partials/vm_table.html` | UPDATE: save/resume/delete buttons | 4 | ✅ |
| `app/templates/nodes/index.html` | CREATE | 6 | ✅ |
| `app/orchard_client.py` | DELETE | 5 | ✅ |
| `app/websockify_manager.py` | DELETE | 5 | ✅ |
| `.env.example` | REWRITE: remove Orchard vars | 5 | ✅ |
| `scripts/setup_registry.sh` | CREATE | 7 | ✅ |

---

*Transition complete. All phases implemented 2026-02-21.*
