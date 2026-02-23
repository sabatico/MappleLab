# Orchard UI - Critical Software BOM

This document lists the critical software components used by Orchard UI.

> Scope: runtime and infrastructure components that are required (or strongly recommended) for install, operation, and maintenance.

---

## Core Platform Components

| Component | Role in system | Required | Version guidance | Install source |
|---|---|---|---|---|
| macOS (manager + nodes) | Host OS for manager and TART nodes | Yes | Current supported macOS release | Apple |
| Python | Runtime for Flask app and tools | Yes | 3.10+ (3.12 recommended) | Homebrew |
| Flask | Web application framework | Yes | Pinned in `requirements.txt` | `pip` |
| Flask-SQLAlchemy | ORM/data access layer | Yes | Pinned in `requirements.txt` | `pip` |
| SQLAlchemy | DB engine abstraction | Yes | Pinned in `requirements.txt` | `pip` |
| SQLite | Default application database | Yes (default) | Built into Python runtime | Python stdlib |
| Usage telemetry tables (`vm_status_events`, `vm_vnc_sessions`) | VM/VNC time analytics for admin usage view | Yes (feature) | DB schema managed by app models | Project DB |

---

## VM and Orchestration Components

| Component | Role in system | Required | Version guidance | Install source |
|---|---|---|---|---|
| TART | VM runtime on node Macs | Yes | Latest stable | Homebrew (`cirruslabs/cli/tart`) |
| tart_agent (project component) | Node-side API service to manage TART VMs | Yes | Comes from this repo deploy scripts | Deployed via `scripts/deploy_agent.sh` |
| Paramiko | SSH transport for tunnel and remote operations | Yes | Pinned in `requirements.txt` | `pip` |
| Flask-Sock + simple-websocket | WebSocket bridge for VNC traffic | Yes | Pinned in `requirements.txt` | `pip` |

---

## Registry and Container Components

| Component | Role in system | Required | Version guidance | Install source |
|---|---|---|---|---|
| Docker CLI | Container management commands | Yes | Current stable | Homebrew |
| Colima | Local Docker engine on macOS | Yes (recommended path) | Current stable | Homebrew |
| Docker Registry (`registry:2`) | Stores saved VM artefacts for resume/migrate | Yes | `registry:2` image | Docker Hub |

---

## Network and Access Components

| Component | Role in system | Required | Version guidance | Install source |
|---|---|---|---|---|
| OpenSSH client/server | Manager-node SSH key auth and remote command execution | Yes | OS default is sufficient | macOS default / Homebrew |
| noVNC | Browser-side VNC client | Yes | Pulled by `scripts/setup_novnc.sh` | GitHub (noVNC release) |
| websockify | WS <-> TCP VNC bridge support | Yes | Pinned in `requirements.txt` | `pip` |
| Apple Screen Sharing (`.vncloc`) | Native macOS VNC client path over direct TCP | Optional | macOS built-in | Apple |
| Caddy or nginx | TLS reverse proxy for production browser access | Recommended (prod) | Current stable | Homebrew / package manager |

---

## Operational Components

| Component | Role in system | Required | Version guidance | Install source |
|---|---|---|---|---|
| Gunicorn | Production WSGI server (via `run.sh` in production mode) | Recommended (prod) | Pinned in `requirements.txt` | `pip` |
| launchd | Service supervision on macOS | Recommended (prod) | macOS built-in | Apple |
| curl | Health checks and endpoint validation | Recommended | OS default | macOS default |

---

## Security and Identity Components

| Component | Role in system | Required | Version guidance | Install source |
|---|---|---|---|---|
| Flask-Login | Session-based authentication | Yes | Pinned in `requirements.txt` | `pip` |
| Flask-Bcrypt / bcrypt | Password hashing | Yes | Pinned in `requirements.txt` | `pip` |
| AGENT_TOKEN (configuration secret) | Shared manager-node API auth token | Yes | Strong random token | Project `.env` / `~/.agent_token` |
| SECRET_KEY (configuration secret) | Flask session signing key | Yes | Strong random key | Project `.env` |

---

## Notes

- Exact Python dependency versions are tracked in `requirements.txt`.
- If PostgreSQL is introduced later, update this BOM and corresponding admin docs.
- For production use, HTTPS with reverse proxy is strongly recommended due to browser VNC security requirements.
- Native `.vncloc` sessions require raw TCP reachability to manager direct-proxy ports (`VNC_DIRECT_PORT_MIN`-`VNC_DIRECT_PORT_MAX`, default `57000-57099`).
