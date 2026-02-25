# MAppleLab — Refurbished Architecture Plan
# TART-Direct + Local Docker Registry + Multi-Node Mac Cloud

> **Status**: ✅ Complete — implemented 2026-02-21
> **Replaces**: Orchard-based architecture (all 3 existing modules)
> **Date**: 2026-02-21

---

## 1. Problem Statement

The original implementation used Orchard as a VM orchestrator. Orchard does not support:
- Suspending and resuming VMs with state preserved across sessions
- Moving VMs between physical Mac nodes with user data intact

**The new architecture removes Orchard entirely** and manages TART directly across multiple physical Mac nodes, using a local Docker/OCI registry as the persistence and distribution layer.

---

## 2. Core Concept

```
User clicks "Save & Shutdown"
  → VM gracefully shuts down (disk is flushed)
  → tart push <vm> registry/<user>/<vm>:latest
  → tart delete <vm>  (free local disk)

User clicks "Resume VM" next day
  → Find a Mac node with < 2 running VMs
  → tart pull registry/<user>/<vm>:latest <vm>
  → tart run <vm>  (boots fresh, files exactly as left)
```

**User experience**: "Save & Shutdown" takes 30-60 seconds. "Resume" takes 30-60 seconds to pull + boot. Files are exactly as left. Open apps must be relaunched (trade-off vs true suspend, which TART cannot push cross-node).

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Central Registry Machine                                │
│                                                                             │
│  ┌─────────────────────────────┐   ┌─────────────────────────────────────┐  │
│  │  Flask UI (orchard_ui)      │   │  Local Docker Registry              │  │
│  │  Port 5000 (HTTPS)          │   │  Port 5001 (HTTP, LAN-only)         │  │
│  │                             │   │  docker run -d -p 5001:5000         │  │
│  │  - Manage nodes/VMs         │   │  registry:2                         │  │
│  │  - SSH into TART agents     │   │                                     │  │
│  │  - VNC WebSocket proxy      │   │  Stores: user/vm-name:latest        │  │
│  └─────────────────────────────┘   └─────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ SSH + HTTP
          ┌─────────────────┼──────────────────┐
          │                 │                  │
          ▼                 ▼                  ▼
┌─────────────────┐ ┌───────────────┐ ┌───────────────┐
│  Mac Node A     │ │  Mac Node B   │ │  Mac Node C   │
│                 │ │               │ │               │
│  TART Agent     │ │  TART Agent   │ │  TART Agent   │
│  (HTTP :7000)   │ │  (HTTP :7000) │ │  (HTTP :7000) │
│                 │ │               │ │               │
│  VM 1: running  │ │  VM 1: running│ │  (0 running)  │
│  VM 2: running  │ │  (1 slot free)│ │  (2 slots free│
│  [FULL]         │ │               │ │               │
│                 │ │  websockify   │ │  websockify   │
│  websockify     │ │  (on demand)  │ │  (on demand)  │
│  (on demand)    │ │               │ │               │
└─────────────────┘ └───────────────┘ └───────────────┘
```

**Key**: All TART CLI operations are executed via the TART Agent on each Mac node. Flask never runs `tart` directly — it calls the agent's HTTP API.

---

## 4. Components

### 4.1 Flask UI (Central — on Registry Machine)

**Location**: Same machine as the Docker registry.

**Responsibilities**:
- User-facing web dashboard
- VM lifecycle management (create, save & shutdown, resume, delete)
- Node capacity tracking (which nodes have free VM slots)
- VNC console access via SSH tunnel + websockify proxy
- VM state tracking via SQLite database (where is each VM? running on which node?)

**New technologies added vs. old implementation**:
- `paramiko` or `asyncssh`: SSH into TART agents
- `sqlite3` / Flask-SQLAlchemy: persistent VM state + user management
- Flask-Login: authentication (user namespacing in registry requires this)

### 4.2 TART Agent (on each Mac Node)

A **small Python/Flask HTTP service** running on each Mac that:
- Wraps `tart` CLI commands in a REST API
- Manages local websockify processes for VNC
- Reports node capacity (running VM count, disk space)
- Handles `tart push` / `tart pull` targeting the central registry

**Endpoints (example)**:
```
GET  /health                  → {status, running_vms, capacity}
GET  /vms                     → list of local VMs + status
POST /vms/create              → tart clone + configure
POST /vms/<name>/start        → tart run (non-blocking)
POST /vms/<name>/stop         → graceful shutdown
POST /vms/<name>/save         → shutdown + tart push + tart delete
POST /vms/<name>/restore      → tart pull + tart run
GET  /vms/<name>/ip           → tart ip <name>
GET  /vms/<name>/status       → running/stopped/pulling/pushing
POST /vnc/<name>/start        → start websockify, return port
POST /vnc/<name>/stop         → kill websockify
```

**Why HTTP agent instead of raw SSH**:
- More robust: structured JSON responses, proper error codes
- Async operations: push/pull can take minutes; agent handles the subprocess + reports status
- Reusable: the agent can be extended independently of Flask UI
- Auth: the agent can require a shared secret token

### 4.3 Local Docker Registry

A standard Docker Distribution registry running as a Docker container on the registry machine.

```bash
docker run -d \
  -p 5001:5000 \
  -v /data/registry:/var/lib/registry \
  --restart always \
  --name tart-registry \
  registry:2
```

**VM naming in registry**:
```
<registry-host>:5001/<username>/<vm-name>:latest
# e.g.: registry.local:5001/alice/dev-macbook:latest
```

**Why local Docker registry**:
- No auth complexity for LAN use
- `tart push` / `tart pull` are OCI-compatible and work with Docker Distribution
- Full control, no egress costs, fast LAN speeds (10GbE if available)

### 4.4 SQLite Database (new — on Flask server)

Tracks VM state that TART itself does not persist:

```sql
-- Users
users (id, username, password_hash, created_at)

-- VMs
vms (
  id,
  name,               -- globally unique
  user_id,            -- owner
  status,             -- 'running' | 'stopped' | 'archived' | 'pushing' | 'pulling'
  node_id,            -- which Mac node it's currently on (null if archived)
  registry_tag,       -- full registry path (registry.local:5001/user/vm:latest)
  base_image,         -- the OCI image it was created from
  cpu, memory_mb,     -- resource config
  created_at,
  last_saved_at,
  last_started_at
)

-- Nodes
nodes (
  id,
  name,               -- human-readable (e.g. "mac-mini-01")
  host,               -- hostname or IP
  agent_port,         -- default 7000
  ssh_user,           -- for SSH tunnel (VNC)
  ssh_key_path,       -- path to SSH private key on Flask server
  max_vms,            -- 2 for macOS, higher for Linux-only
  active              -- boolean
)
```

---

## 5. VM Lifecycle

### 5.1 State Machine

```
                         ┌─────────────────────────────┐
                         │                             │
         Create New VM   │                             │ Resume
              │          ▼                             │
              │     [running]  ──── Save & Shutdown ──►[archived]
              │          │                             │
              │          │ Delete                      │ Delete
              │          ▼                             ▼
              └────► [deleted]  ◄─────────────────[deleted]
                         ▲
              Error      │
         [pushing] ──────┘
         [pulling] ──────┘
```

**States**:
- `creating` — VM clone/start requested; state is reconciled with node agent shortly after create
- `running` — VM is active on a TART node, user can VNC in
- `stopped` — VM exists on a node but is powered off; can be started without registry pull
- `archived` — VM disk image is in registry, not on any node
- `pushing` — Save & Shutdown in progress (shutdown → push → delete local)
- `pulling` — Resume in progress (find node → pull → start)
- `deleted` — Removed from all locations

### 5.2 Create VM Flow

```
User fills form: name, base_image, cpu, memory
  → Pick least-loaded node (or any with < 2 running)
  → DB: insert vm (status=creating, node=chosen_node)
  → Agent POST /vms/create: tart clone <base_image> <vm-name>
  → Agent POST /vms/<name>/start: tart run <vm-name>
  → Flask reconciles with agent /vms result: status becomes running or stopped
  → Redirect to VM detail page
```

### 5.3 Save & Shutdown Flow

```
User clicks "Save & Shutdown"
  → Flask: update DB status = 'pushing'
  → Agent POST /vms/<name>/save:
      1. Graceful shutdown (tart stop <name> or send ACPI shutdown to VNC)
      2. Wait for VM to stop
      3. tart push <name> <registry>/<user>/<name>:latest
      4. tart delete <name>  (free local disk)
      5. Return {success: true}
  → Flask: update DB status = 'archived', node = null, last_saved_at = now
  → Redirect to dashboard
```

**Push is blocking within the agent** (can take 5-30 min for large VMs). Flask polls the agent for status updates and shows progress to the user via HTMX.

### 5.4 Resume Flow

```
User clicks "Resume"
  → Flask: find best node (fewest running VMs, enough disk)
  → Flask: update DB status = 'pulling', node = chosen_node
  → Agent POST /vms/<name>/restore {registry_tag, name}:
      1. tart pull <registry_tag> <name>
      2. tart run <name> (non-blocking, returns immediately)
      3. Return {success: true, port: <vnc_ready_when_running>}
  → Flask: update DB status = 'running', last_started_at = now
  → Show VM detail page (status polling shows it starting)
```

### 5.4b Start/Stop Local Flow

```
User clicks "Stop" on a running local VM
  → Flask: close SSH tunnel + stop remote VNC proxy (best effort)
  → Agent POST /vms/<name>/stop
  → Flask: update DB status = 'stopped'

User clicks "Start" on a stopped local VM
  → Agent POST /vms/<name>/start
  → Flask: update DB status = 'running', last_started_at = now
```

### 5.5 VNC Console Flow

```
User clicks "Open Console"
  → Flask: get VM's node from DB
  → Flask: call Agent POST /vnc/<name>/start
      → Agent: start websockify on node (port 69xx)
      → Returns {port: 6901}
  → Flask: create SSH tunnel: local_port → node:6901
      paramiko: forward local 0.0.0.0:<free_port> → <node>:6901
  → Flask: store tunnel in memory (like current websockify dict)
  → Render vnc.html with ws_host=flask_server, ws_port=local_tunnel_port
  → Browser connects ws://flask-server:<port>
      → SSH tunnel → node websockify :6901
      → TCP → VM :5900
      → noVNC displays desktop
```

**Disconnect**:
```
  → Flask: close SSH tunnel
  → Agent POST /vnc/<name>/stop
```

---

## 6. File Structure (Final State)

```
orchard_ui/
├── app/
│   ├── __init__.py              # create_app — same pattern, new services
│   ├── extensions.py            # SQLAlchemy, Flask-Login
│   ├── models.py                # User, VM, Node ORM models
│   ├── logging_config.py        # (unchanged)
│   │
│   ├── tart_client.py           # REPLACES orchard_client.py
│   │                            # HTTP client for TART Agent API
│   │
│   ├── node_manager.py          # REPLACES websockify_manager.py (partially)
│   │                            # Tracks nodes, picks best node for scheduling
│   │
│   ├── tunnel_manager.py        # NEW — SSH tunnels for VNC proxying
│   │                            # (paramiko-based, replaces local websockify)
│   │
│   ├── main/
│   │   ├── __init__.py
│   │   └── routes.py            # Updated for new VM states + node-aware
│   │
│   ├── console/
│   │   ├── __init__.py
│   │   └── routes.py            # Updated: creates SSH tunnel, calls agent
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py            # Updated: polls DB instead of Orchard API
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── routes.py            # NEW — login, logout, register
│   │   └── models.py            # (or in app/models.py)
│   │
│   ├── nodes/                   # NEW blueprint
│   │   ├── __init__.py
│   │   └── routes.py            # Admin: add/remove/view nodes
│   │
│   ├── templates/
│   │   ├── base.html            # Updated navbar (add user menu, node status)
│   │   ├── main/
│   │   │   ├── dashboard.html   # Updated: new VM states, start/stop/save/resume buttons
│   │   │   ├── vm_detail.html   # Updated: progress display for push/pull
│   │   │   └── create_vm.html   # Updated: node selection removed (auto)
│   │   ├── console/
│   │   │   └── vnc.html         # (unchanged — ws config still injected)
│   │   ├── auth/                # NEW
│   │   │   ├── login.html
│   │   │   └── register.html
│   │   ├── nodes/               # NEW
│   │   │   └── index.html       # Node status dashboard
│   │   └── _partials/
│   │       ├── vm_status_badge.html   # Updated: new states
│   │       ├── vm_table.html          # Updated: start/stop/save/resume actions
│   │       ├── flash_messages.html    # (unchanged)
│   │       └── progress_bar.html      # NEW — push/pull progress
│   │
│   └── static/                  # (unchanged)
│
├── tart_agent/                  # NEW — deployed to each Mac node
│   ├── agent.py                 # Flask app (small, standalone)
│   ├── tart_runner.py           # Wraps tart CLI subprocess calls
│   ├── vnc_manager.py           # Local websockify lifecycle
│   ├── requirements.txt         # Flask, websockify only
│   └── agent_config.py         # Port, registry URL, auth token
│
├── config.py                    # Updated: remove Orchard, add DB, registry
├── run.py                       # (unchanged)
├── requirements.txt             # Add: paramiko, Flask-SQLAlchemy, Flask-Login
├── scripts/
│   ├── setup_novnc.sh           # (unchanged)
│   ├── setup_registry.sh        # NEW — docker run registry:2
│   └── deploy_agent.sh          # NEW — SSH + install agent on a Mac node
└── docs/
    ├── PLANNING.md
    ├── refurbish_plan.md        # THIS document
    └── transition_to_refurbish.md
```

---

## 7. Configuration

### Flask UI `config.py` (updated)

```python
# Registry
REGISTRY_URL = os.environ.get('REGISTRY_URL', 'registry.local:5001')
REGISTRY_INSECURE = True  # local registry, no TLS needed

# Database
SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///orchard_ui.db')

# Auth
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

# REMOVED: All ORCHARD_* config
# REMOVED: TART_IMAGES (now stored per-node or in DB)
# KEPT: WEBSOCKIFY_* (now for SSH tunnel local port range)
# KEPT: VNC_DEFAULT_PASSWORD
```

### TART Agent `agent_config.py`

```python
AGENT_PORT = 7000
REGISTRY_URL = 'registry.local:5001'  # must match Flask config
AGENT_TOKEN = os.environ.get('AGENT_TOKEN', '')  # shared secret
TART_BIN = '/usr/local/bin/tart'
WEBSOCKIFY_BIN = 'websockify'
VNC_PORT = 5900
WEBSOCKIFY_PORT_MIN = 6900
WEBSOCKIFY_PORT_MAX = 6999
MAX_VMS = 2  # Apple Silicon limit for macOS VMs
```

### `.env` example (updated)

```bash
# Flask UI
SECRET_KEY=generate-a-random-string
DATABASE_URL=sqlite:///orchard_ui.db

# Registry
REGISTRY_URL=192.168.1.100:5001

# VNC
VNC_DEFAULT_PASSWORD=admin

# REMOVED: ORCHARD_URL, ORCHARD_SERVICE_ACCOUNT_*
```

---

## 8. TART Agent API Specification

Base URL: `http://<node-ip>:7000`
Auth: `Authorization: Bearer <AGENT_TOKEN>` header

### Node Info

```
GET /health
Response: {
  "status": "ok",
  "tart_version": "2.x.x",
  "running_vms": 1,
  "max_vms": 2,
  "free_slots": 1,
  "disk_free_gb": 150.2
}
```

### VM List

```
GET /vms
Response: [
  {
    "name": "alice-devbox",
    "status": "running",
    "ip": "192.168.64.5",
    "cpu": 4,
    "memory_mb": 8192
  }
]
```

### VM Create (clone from base image)

```
POST /vms/create
Body: {"name": "alice-devbox", "base_image": "ghcr.io/cirruslabs/macos-sequoia-base:latest", "cpu": 4, "memory": 8192}
Response: {"status": "created", "name": "alice-devbox"}
```

### VM Start

```
POST /vms/<name>/start
Response: {"status": "started"}
```

### VM Stop (graceful)

```
POST /vms/<name>/stop
Response: {"status": "stopped"}
```

### VM Save & Shutdown (blocking — may take minutes)

```
POST /vms/<name>/save
Body: {"registry_tag": "registry.local:5001/alice/devbox:latest"}
Response (streaming or long-poll):
  {"status": "shutting_down"}
  {"status": "pushing", "progress_pct": 45}
  {"status": "done"}
```

### VM Restore (blocking — may take minutes)

```
POST /vms/<name>/restore
Body: {"registry_tag": "registry.local:5001/alice/devbox:latest"}
Response:
  {"status": "pulling", "progress_pct": 30}
  {"status": "starting"}
  {"status": "done"}
```

### VM Delete

```
DELETE /vms/<name>
Response: {"status": "deleted"}
```

### VM IP

```
GET /vms/<name>/ip
Response: {"ip": "192.168.64.5"}
```

### VNC Start

```
POST /vnc/<name>/start
Response: {"port": 6901}
```

### VNC Stop

```
POST /vnc/<name>/stop
Response: {"status": "stopped"}
```

---

## 9. VNC Architecture Detail

```
Browser (user's laptop)
  │  WebSocket ws://flask-server:6901
  ▼
Flask Server (central)
  │  SSH Tunnel (paramiko LocalForward)
  │  0.0.0.0:6901 → mac-node-b:6901
  ▼
Mac Node B (TART agent)
  │  websockify :6901 (started by agent on demand)
  │  TCP → VM:5900
  ▼
TART VM running macOS
  │  VNC Server :5900
  │
noVNC displays desktop in browser
```

**SSH Tunnel lifecycle** (managed by `tunnel_manager.py` on Flask server):
- Created when user opens console (tunnels forward local port to agent's websockify port)
- Stored in memory dictionary keyed by vm_name (same pattern as current websockify_manager.py)
- Destroyed when user disconnects or VM is saved/deleted

---

## 10. Security Considerations

- **TART Agent auth**: All agent requests require `Authorization: Bearer <token>` header. Token stored in env on each node.
- **Registry**: LAN-only, no TLS needed for local Docker registry. Nodes communicate on private network.
- **SSH keys**: Flask server has an SSH key for each node. Keys stored in `~/.ssh/` or configurable path.
- **Flask auth**: Flask-Login with username/password for user namespacing. Hash passwords with bcrypt.
- **VNC password**: Still passed via `window.VNC_CONFIG` in the page. Acceptable for LAN use.
- **HTTPS**: Flask server already supports TLS via cert.pem/key.pem. Keep this.

---

## 11. Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| TART agent language | Python/Flask | Same tech stack as UI; websockify already pip-installed on nodes |
| VM state persistence | SQLite → PostgreSQL later | Simple, no extra infra; upgrade path exists |
| VNC proxying | SSH tunnel (paramiko) | No direct node exposure; works across NAT |
| Suspend model | Shutdown + push disk | TART snapshots are not pushable; disk-only is the practical option |
| Registry auth | None (LAN) | Docker registry:2 on LAN, no TLS or auth needed |
| Node scheduling | Least-loaded (fewest VMs) | Simple, deterministic, respects the 2-VM Apple limit |
| Long operations (push/pull) | Agent runs async, Flask polls | Avoids HTTP timeout for 30-min operations |

---

## 12. What Stays vs. What Changes

### Stays (unchanged)

- Flask application factory pattern (`create_app`)
- Blueprint structure (main, api, console, auth)
- Template engine (Jinja2), Bootstrap 5 dark theme
- HTMX for polling and partial page updates
- noVNC library and `console.js` logic
- Logging system (`logging_config.py`)
- TLS support in `run.py`
- `.env` configuration pattern

### Changes

| Old | New |
|-----|-----|
| `orchard_client.py` | `tart_client.py` (HTTP calls to TART agents) |
| `websockify_manager.py` | `tunnel_manager.py` (SSH tunnels) + agent manages local websockify |
| No database | SQLite DB via Flask-SQLAlchemy (`models.py`) |
| No auth | Flask-Login (`auth/` blueprint) |
| No agent | `tart_agent/` package deployed to each Mac |
| VM states: running/pending/failed | VM states: creating/running/stopped/archived/pushing/pulling/failed |
| Node managed by Orchard | Nodes table in DB + health checks |

---

## 13. Open Questions / Future Work

1. **Long operation progress**: Push/pull progress display requires either streaming responses (Server-Sent Events) or polling a status endpoint on the agent. SSE is cleaner.
2. **VM naming conflicts**: When pulling, if a VM name already exists on the target node, the agent should error or auto-rename.
3. **Registry cleanup**: Old VM versions accumulate in the registry. A cleanup policy (keep only `:latest`, delete after N days inactive) should be implemented.
4. **Linux VMs**: Linux VMs have no 2-VM limit. The `max_vms` field in the `nodes` table handles this.
5. **Disk space check**: Before pulling, verify node has enough free disk. Agent's `/health` exposes `disk_free_gb`.
6. **Multi-user VM visibility**: Should users see other users' VMs? Admin role needed.
7. **tart run --no-graphics**: For VMs that don't need a display (CI runners), this saves resources.

---

*End of refurbished architecture plan.*
