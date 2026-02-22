# Module 1: Core Scaffold + API Client

> **Status**: ✅ Complete (refurbished 2026-02-21)

**Original scope**: Phases 1–2 from PLANNING.md — scaffold + OrchardClient
**Current state**: Fully transitioned to TART-Direct architecture (see `refurbish_plan.md`)
**Output**: Runnable Flask app with DB, auth, TartClient, NodeManager, TunnelManager
**Depends on**: nothing
**Other modules depend on this**: all others

---

## ⚠️ Architecture Note

This module originally scaffolded an Orchard-based client (`OrchardClient`) and a local websockify manager (`WebsockifyManager`). Both have been **replaced** as part of the refurbishment:

| Original | Replacement |
|----------|-------------|
| `app/orchard_client.py` | `app/tart_client.py` (HTTP client for TART agents) |
| `app/websockify_manager.py` | `app/tunnel_manager.py` (SSH tunnels via paramiko) |
| No database | `app/models.py` + Flask-SQLAlchemy |
| No auth | `app/auth/` blueprint + Flask-Login + Flask-Bcrypt |

The scaffold structure (Flask factory, blueprints, config pattern, `.env`, `run.py`) remains unchanged.

---

## Tasks

### Original scaffold tasks (complete)
- [x] Create project directory structure
- [x] Write `requirements.txt`
- [x] Write `config.py` (Config, DevelopmentConfig, ProductionConfig)
- [x] Write `.env.example`, `.flaskenv`, `.gitignore`
- [x] Write `run.py`
- [x] Write `app/__init__.py` (create_app factory)
- [x] Write `app/extensions.py` (placeholder)
- [x] Write blueprint `__init__.py` files (main, console, api, auth)
- [x] Write stub routes for main, console, api blueprints

### Refurbishment additions (complete)
- [x] Add `paramiko`, `Flask-SQLAlchemy`, `Flask-Login`, `Flask-Bcrypt` to `requirements.txt`
- [x] Update `app/extensions.py` with real db, login_manager, bcrypt instances
- [x] Create `app/models.py` (User, Node, VM ORM models)
- [x] Update `config.py` — add SQLALCHEMY_DATABASE_URI, REGISTRY_URL, AGENT_TOKEN; remove ORCHARD_* keys
- [x] Create `app/tart_client.py` (TartClient + TartAPIError)
- [x] Create `app/node_manager.py` (NodeManager — node scheduling)
- [x] Create `app/tunnel_manager.py` (TunnelManager — SSH tunnel VNC proxy)
- [x] Activate `app/auth/__init__.py` (was empty placeholder)
- [x] Create `app/auth/routes.py` (login, logout, register)
- [x] Create `app/templates/auth/login.html` and `register.html`
- [x] Update `app/__init__.py` — wire all new services, DB init, all 5 blueprints
- [x] Delete `app/orchard_client.py`
- [x] Delete `app/websockify_manager.py`
- [x] Verify: `flask run` starts without errors
- [x] Verify: DB tables created (users, vms, nodes)
- [x] Verify: 5 blueprints registered (main, console, api, auth, nodes)
- [x] Verify: auth routes work (`/auth/register`, `/auth/login`, `/auth/logout`)

---

## Files

| File | Status | Notes |
|------|--------|-------|
| `requirements.txt` | ✅ | Added: paramiko, Flask-SQLAlchemy, Flask-Login, Flask-Bcrypt |
| `config.py` | ✅ | ORCHARD_* removed; DB, REGISTRY_URL, AGENT_TOKEN added |
| `.env.example` | ✅ | Rewritten — Orchard vars removed, new vars documented |
| `.flaskenv` | ✅ | Unchanged |
| `.gitignore` | ✅ | Unchanged |
| `run.py` | ✅ | Unchanged |
| `app/__init__.py` | ✅ | Wires DB, TartClient, NodeManager, TunnelManager; 5 blueprints |
| `app/extensions.py` | ✅ | db, login_manager, bcrypt + init_extensions() |
| `app/models.py` | ✅ | User, Node, VM — SQLAlchemy ORM models |
| `app/tart_client.py` | ✅ | Replaces orchard_client.py — HTTP client for TART agents |
| `app/node_manager.py` | ✅ | Node scheduling, health checks, registry tag builder |
| `app/tunnel_manager.py` | ✅ | paramiko SSH tunnels for VNC (replaces local websockify) |
| `app/auth/__init__.py` | ✅ | Activated from empty placeholder |
| `app/auth/routes.py` | ✅ | login, logout, register |
| `app/templates/auth/login.html` | ✅ | Bootstrap 5 dark form |
| `app/templates/auth/register.html` | ✅ | Bootstrap 5 dark form |
| `app/main/__init__.py` | ✅ | Blueprint definition (unchanged) |
| `app/console/__init__.py` | ✅ | Blueprint definition (unchanged) |
| `app/api/__init__.py` | ✅ | Blueprint definition (unchanged) |
| `app/nodes/__init__.py` | ✅ | New admin blueprint |
| `app/orchard_client.py` | ❌ DELETED | Replaced by tart_client.py |
| `app/websockify_manager.py` | ❌ DELETED | Replaced by tunnel_manager.py |

**Status key**: ⬜ Not started · 🔄 In progress · ✅ Complete · ❌ Deleted

---

## App Services (registered in `create_app()`)

| Attribute | Type | Description |
|-----------|------|-------------|
| `app.tart` | `TartClient` | HTTP client for TART agent REST API |
| `app.node_manager` | `NodeManager` | Picks best Mac node for VM scheduling |
| `app.tunnel_manager` | `TunnelManager` | SSH port-forward tunnels for VNC |

---

## Config Values

| Key | Default | Source |
|-----|---------|--------|
| `SECRET_KEY` | dev-secret-change-in-production | env `SECRET_KEY` |
| `SQLALCHEMY_DATABASE_URI` | sqlite:///orchard_ui.db | env `DATABASE_URL` |
| `REGISTRY_URL` | localhost:5001 | env `REGISTRY_URL` |
| `AGENT_TOKEN` | (empty) | env `AGENT_TOKEN` |
| `WEBSOCKIFY_PORT_MIN` | 6900 | env `WEBSOCKIFY_PORT_MIN` |
| `WEBSOCKIFY_PORT_MAX` | 6999 | env `WEBSOCKIFY_PORT_MAX` |
| `VNC_PORT` | 5900 | hardcoded |
| `VNC_DEFAULT_PASSWORD` | admin | env `VNC_DEFAULT_PASSWORD` |
| `VM_POLL_INTERVAL_MS` | 5000 | env `VM_POLL_INTERVAL_MS` |
| `TART_IMAGES` | (5 cirruslabs images) | env `TART_IMAGES` |

*Removed*: `ORCHARD_URL`, `ORCHARD_API_PREFIX`, `ORCHARD_SERVICE_ACCOUNT_NAME`, `ORCHARD_SERVICE_ACCOUNT_TOKEN`, `WEBSOCKIFY_BIN`, `WEBSOCKIFY_HOST`

---

## Verification

```bash
# Activate venv
source .venv/bin/activate

# Start app
flask run
# → "Running on http://127.0.0.1:5000"

# In flask shell:
from flask import current_app
from app.extensions import db
from app.models import User, Node, VM

# Check tables exist
db.engine.table_names()   # → ['users', 'nodes', 'vms']

# Check services
current_app.tart           # → <TartClient>
current_app.node_manager   # → <NodeManager>
current_app.tunnel_manager # → <TunnelManager>

# Check blueprints
[r.endpoint for r in current_app.url_map.iter_rules()]
# → includes: main.*, api.*, console.*, auth.*, nodes.*
```

## Key Implementation Notes

- `TartClient` uses `requests.Session` with `Authorization: Bearer <AGENT_TOKEN>` header
- `NodeManager.find_best_node()` picks the active node with the most free VM slots
- `TunnelManager` stores tunnels in a thread-safe dict keyed by `vm_name`
- `lazy='select'` on all SQLAlchemy relationships (SQLAlchemy 2.x compatible; `lazy='dynamic'` is deprecated)
- atexit hook: `tunnel_manager.cleanup_all()` — closes all SSH tunnels on Flask shutdown
- All routes (except auth) are `@login_required` — unauthenticated users redirect to `/auth/login`
