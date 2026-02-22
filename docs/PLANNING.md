# Orchard UI — Full Architecture & Implementation Plan

> **Purpose**: This document contains every detail a developer agent needs to implement the Orchard UI project from scratch — architecture, file structure, pseudocode, API contracts, and integration specifics.

---

## Implementation Modules

Each module has its own planning document. Implement in order — each depends on the previous.

| # | Module | File | Status |
|---|--------|------|--------|
| 1 | Core Scaffold + Orchard API Client | [1_scaffold_and_client.md](1_scaffold_and_client.md) | ✅ Complete |
| 2 | Dashboard + VM CRUD + API Endpoints | [2_dashboard_and_crud.md](2_dashboard_and_crud.md) | ✅ Complete |
| 3 | Console — Websockify + noVNC | [3_console_and_vnc.md](3_console_and_vnc.md) | ✅ Complete |

**Status key**: ⬜ Not started · 🔄 In progress · ✅ Complete

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack & Dependencies](#2-tech-stack--dependencies)
3. [Project File Structure](#3-project-file-structure)
4. [Configuration System](#4-configuration-system)
5. [App Factory & Wiring](#5-app-factory--wiring)
6. [Orchard API Client](#6-orchard-api-client)
7. [Websockify Manager](#7-websockify-manager)
8. [Main Blueprint — Dashboard & VM Management](#8-main-blueprint)
9. [Console Blueprint — VNC Access](#9-console-blueprint)
10. [API Blueprint — HTMX/AJAX Endpoints](#10-api-blueprint)
11. [Templates — Full Specifications](#11-templates)
12. [Static Assets — JS & CSS](#12-static-assets)
13. [noVNC Integration Guide](#13-novnc-integration)
14. [Future Auth Preparation](#14-future-auth)
15. [Error Handling Strategy](#15-error-handling)
16. [Implementation Order](#16-implementation-order)
17. [Verification & Testing](#17-verification)

---

## 1. Project Overview

### What We're Building
A Flask + Jinja2 web dashboard to manage TART virtual machines through the Orchard orchestrator REST API. The tool:

- Lists all VMs with live-updating statuses
- Creates new VMs from available TART images (pulled from OCI registries)
- Deletes/wipes VMs
- Provides in-browser VNC console access to running VMs (keyboard, mouse, copy/paste)

### Deployment Context
- Runs on the **same Mac** that hosts the Orchard controller+worker
- All Orchard API calls are **local** (localhost:6120)
- VNC connections to VMs are also local (VM IPs on the host network)
- Single user initially — no auth — but architecture supports adding it later

### Key Products
- **TART** (github.com/cirruslabs/tart): Apple Silicon virtualization tool using Apple's Virtualization.Framework. Runs macOS/Linux VMs. Supports VNC via `--vnc` flag on port 5900.
- **Orchard** (github.com/cirruslabs/orchard): Orchestrator for TART VMs. Controller+Worker architecture. REST API + gRPC. Manages VM lifecycle, provides port forwarding.

### Data Flow Diagram

```
┌─────────────────────────┐     ┌─────────────────────────┐
│     Browser (User)      │     │     Browser (User)      │
│   Dashboard / Forms     │     │   noVNC Console Page    │
└────────┬────────────────┘     └────────┬────────────────┘
         │ HTTP (port 5000)              │ WebSocket (port 69xx)
         ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│   Flask App (:5000)     │     │  websockify (:69xx)     │
│  Routes, Templates,     │     │  WS→TCP proxy           │
│  Orchard API Client     │     │  (one per active VM)    │
└────────┬────────────────┘     └────────┬────────────────┘
         │ HTTP + Basic Auth             │ TCP
         ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│ Orchard Controller      │     │ TART VM                 │
│ REST API (:6120)        │     │ VNC Server (:5900)      │
└────────┬────────────────┘     └─────────────────────────┘
         │ gRPC
         ▼
┌─────────────────────────┐
│ Orchard Worker          │
│ → runs TART VMs         │
└─────────────────────────┘
```

**Critical insight**: Flask never touches VNC traffic. It only orchestrates — gets VM IP from Orchard API, starts a websockify subprocess pointing at that IP, and tells the browser which websockify port to connect to.

---

## 2. Tech Stack & Dependencies

### `requirements.txt`
```
Flask==3.1.0
requests==2.32.3
python-dotenv==1.0.1
websockify==0.12.0
gunicorn==23.0.0
```

### External (CDN / Static — no pip)
| Library | Version | How Loaded | Purpose |
|---------|---------|------------|---------|
| Bootstrap 5 | 5.3.3 | CDN `<link>` + `<script>` | UI framework |
| HTMX | 2.0.4 | CDN `<script>` | Dashboard polling, partial page updates |
| noVNC | 1.5.0 | Static files in `app/static/novnc/` | In-browser VNC client |
| Bootstrap Icons | 1.11.3 | CDN `<link>` | Icons for buttons/badges |

### Why These Choices
- **No WTForms**: Only 1-2 simple forms; `request.form` is sufficient
- **No SQLAlchemy/Flask-Login**: Deferred until auth phase
- **No Celery**: Orchard API calls return immediately (Orchard handles async internally)
- **No webpack/vite**: noVNC works as native ES modules, no build step needed
- **websockify via pip**: Ensures the `websockify` CLI binary is in the virtualenv

---

## 3. Project File Structure

```
orchard_ui/                             # Project root (git repo)
├── PLANNING.md                         # THIS document
├── README.md                           # Setup & usage instructions
├── run.py                              # Entry point
├── config.py                           # Configuration classes
├── requirements.txt                    # Python dependencies
├── .env.example                        # Env var template (committed)
├── .env                                # Actual env vars (gitignored)
├── .flaskenv                           # Flask CLI env vars (committed)
├── .gitignore
│
├── app/
│   ├── __init__.py                     # create_app() factory
│   ├── extensions.py                   # Future extension instances (placeholder)
│   ├── orchard_client.py               # Orchard API wrapper class
│   ├── websockify_manager.py           # Websockify subprocess manager
│   │
│   ├── main/                           # Dashboard & VM management blueprint
│   │   ├── __init__.py                 # Blueprint definition
│   │   └── routes.py                   # Page routes
│   │
│   ├── console/                        # VNC console blueprint
│   │   ├── __init__.py                 # Blueprint definition
│   │   └── routes.py                   # Console routes
│   │
│   ├── api/                            # Internal AJAX/HTMX endpoints
│   │   ├── __init__.py                 # Blueprint definition
│   │   └── routes.py                   # JSON/partial endpoints
│   │
│   ├── auth/                           # RESERVED for future auth
│   │   └── __init__.py                 # Empty blueprint placeholder
│   │
│   ├── templates/
│   │   ├── base.html                   # Master layout (Bootstrap, navbar, flashes)
│   │   ├── main/
│   │   │   ├── dashboard.html          # VM list table + HTMX polling
│   │   │   ├── vm_detail.html          # Single VM detail + events
│   │   │   └── create_vm.html          # Create VM form
│   │   ├── console/
│   │   │   └── vnc.html                # Standalone noVNC page (no base.html)
│   │   └── _partials/
│   │       ├── vm_table.html           # Table body partial for HTMX swap
│   │       ├── vm_status_badge.html    # Status badge snippet
│   │       └── flash_messages.html     # Flash message block
│   │
│   └── static/
│       ├── css/
│       │   └── style.css               # Custom CSS overrides
│       ├── js/
│       │   ├── app.js                  # Dashboard logic (confirm dialogs, etc.)
│       │   └── console.js              # noVNC RFB initialization
│       └── novnc/                      # noVNC library files (downloaded)
│           ├── core/
│           │   └── rfb.js              # Main RFB class (+ other ES modules)
│           └── vendor/                 # noVNC vendor dependencies
│
└── scripts/
    └── setup_novnc.sh                  # Helper to download & install noVNC
```

---

## 4. Configuration System

### `config.py` — Full Pseudocode

```python
import os

class Config:
    """Base configuration. All values can be overridden by env vars."""

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

    # Orchard API connection
    ORCHARD_URL = os.environ.get('ORCHARD_URL', 'http://localhost:6120')
    ORCHARD_API_PREFIX = os.environ.get('ORCHARD_API_PREFIX', '/v1')
    ORCHARD_SERVICE_ACCOUNT_NAME = os.environ.get('ORCHARD_SERVICE_ACCOUNT_NAME', '')
    ORCHARD_SERVICE_ACCOUNT_TOKEN = os.environ.get('ORCHARD_SERVICE_ACCOUNT_TOKEN', '')

    # Websockify port range (each active VNC console uses one port)
    WEBSOCKIFY_PORT_MIN = int(os.environ.get('WEBSOCKIFY_PORT_MIN', 6900))
    WEBSOCKIFY_PORT_MAX = int(os.environ.get('WEBSOCKIFY_PORT_MAX', 6999))
    WEBSOCKIFY_BIN = os.environ.get('WEBSOCKIFY_BIN', 'websockify')
    # Host that the browser uses to reach websockify (default: localhost)
    WEBSOCKIFY_HOST = os.environ.get('WEBSOCKIFY_HOST', 'localhost')

    # VNC defaults (TART default credentials)
    VNC_PORT = 5900
    VNC_DEFAULT_PASSWORD = os.environ.get('VNC_DEFAULT_PASSWORD', 'admin')

    # UI behavior
    VM_POLL_INTERVAL_MS = int(os.environ.get('VM_POLL_INTERVAL_MS', 5000))

    # Known TART images for the "Create VM" dropdown
    # Can be extended via env var as comma-separated list
    TART_IMAGES = os.environ.get('TART_IMAGES', ','.join([
        'ghcr.io/cirruslabs/macos-sonoma-base:latest',
        'ghcr.io/cirruslabs/macos-tahoe-base:latest',
    ])).split(',')


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    # In production, SECRET_KEY MUST be set via env var
```

### `.env.example`
```bash
# Orchard connection
ORCHARD_URL=http://localhost:6120
ORCHARD_API_PREFIX=/v1
ORCHARD_SERVICE_ACCOUNT_NAME=my-service-account
ORCHARD_SERVICE_ACCOUNT_TOKEN=my-secret-token

# Flask
SECRET_KEY=generate-a-random-string-here

# Websockify
WEBSOCKIFY_PORT_MIN=6900
WEBSOCKIFY_PORT_MAX=6999
WEBSOCKIFY_HOST=localhost

# VNC
VNC_DEFAULT_PASSWORD=admin

# UI
VM_POLL_INTERVAL_MS=5000
```

### `.flaskenv`
```bash
FLASK_APP=run.py
FLASK_DEBUG=1
```

### `.gitignore`
```
.env
__pycache__/
*.pyc
.venv/
venv/
app/static/novnc/
*.egg-info/
dist/
build/
```

---

## 5. App Factory & Wiring

### `run.py` — Entry Point

```python
import os
from app import create_app
from config import DevelopmentConfig, ProductionConfig

config = ProductionConfig if os.environ.get('FLASK_ENV') == 'production' else DevelopmentConfig
app = create_app(config)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
```

### `app/__init__.py` — App Factory (Full Pseudocode)

```python
from flask import Flask

def create_app(config_class=None):
    """
    Application factory.
    Creates and configures the Flask app, initializes services,
    registers blueprints, and sets up shutdown hooks.
    """
    if config_class is None:
        from config import DevelopmentConfig
        config_class = DevelopmentConfig

    app = Flask(__name__)
    app.config.from_object(config_class)

    # --- Initialize extensions (future: db, login_manager) ---
    from app.extensions import init_extensions
    init_extensions(app)

    # --- Initialize services ---
    # These are stored on the app object so blueprints can access
    # them via current_app.orchard / current_app.websockify
    from app.orchard_client import OrchardClient
    from app.websockify_manager import WebsockifyManager

    app.orchard = OrchardClient(app)
    app.websockify = WebsockifyManager(app)

    # --- Register blueprints ---
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.console import bp as console_bp
    app.register_blueprint(console_bp, url_prefix='/console')

    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    # auth blueprint registered here in the future:
    # from app.auth import bp as auth_bp
    # app.register_blueprint(auth_bp, url_prefix='/auth')

    # --- Shutdown hook: kill all websockify processes ---
    import atexit
    atexit.register(app.websockify.cleanup_all)

    # --- Template context processors ---
    @app.context_processor
    def inject_config():
        """Make certain config values available in all templates."""
        return {
            'poll_interval_ms': app.config['VM_POLL_INTERVAL_MS'],
        }

    return app
```

### `app/extensions.py` — Placeholder

```python
"""
Flask extension instances.
Currently empty — this is where SQLAlchemy, Flask-Login, etc.
will be initialized when auth is added.

Future pattern:
    from flask_sqlalchemy import SQLAlchemy
    from flask_login import LoginManager

    db = SQLAlchemy()
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
"""

def init_extensions(app):
    """Initialize Flask extensions. No-op for now."""
    pass
```

---

## 6. Orchard API Client

### `app/orchard_client.py` — Full Implementation

This is the **core service class**. Every route that interacts with VMs goes through this.

```python
import requests
import logging

logger = logging.getLogger(__name__)


class OrchardAPIError(Exception):
    """
    Raised when the Orchard API returns an error or is unreachable.

    Attributes:
        message: Human-readable error description
        status_code: HTTP status code (None if connection failed)
        response: Raw requests.Response object (None if connection failed)
    """
    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class OrchardClient:
    """
    Wrapper around the Orchard REST API.

    Usage:
        client = OrchardClient(app)  # or client.init_app(app)
        vms = client.list_vms()      # returns list of dicts

    All methods return parsed JSON (dicts/lists).
    All methods raise OrchardAPIError on failure.
    """

    def __init__(self, app=None):
        self.base_url = None
        self.session = requests.Session()
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Configure the client from Flask app config."""
        self.base_url = (
            app.config['ORCHARD_URL'].rstrip('/')
            + app.config['ORCHARD_API_PREFIX']
        )
        name = app.config['ORCHARD_SERVICE_ACCOUNT_NAME']
        token = app.config['ORCHARD_SERVICE_ACCOUNT_TOKEN']
        if name and token:
            self.session.auth = (name, token)
            logger.info(f"Orchard client configured: {self.base_url} (auth: {name})")
        else:
            logger.warning("Orchard client: no service account configured (dev mode?)")

    def _url(self, path):
        """Build full API URL. path should start with /."""
        return f"{self.base_url}{path}"

    def _request(self, method, path, **kwargs):
        """
        Core HTTP request method.

        Handles:
        - Connection errors → OrchardAPIError("Cannot connect...")
        - HTTP errors → OrchardAPIError with status code
        - Timeout: 10s default

        Returns: requests.Response object
        """
        kwargs.setdefault('timeout', 10)
        url = self._url(path)

        try:
            logger.debug(f"Orchard API: {method} {url}")
            resp = self.session.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.ConnectionError:
            raise OrchardAPIError(
                f"Cannot connect to Orchard controller at {self.base_url}. "
                "Is the controller running?"
            )
        except requests.exceptions.Timeout:
            raise OrchardAPIError(
                f"Orchard API request timed out: {method} {path}"
            )
        except requests.exceptions.HTTPError as e:
            # Try to extract error message from response body
            detail = ""
            try:
                body = e.response.json()
                detail = body.get('message', body.get('error', ''))
            except (ValueError, AttributeError):
                detail = e.response.text[:200] if e.response.text else ''

            raise OrchardAPIError(
                f"Orchard API error ({e.response.status_code}): {detail or str(e)}",
                status_code=e.response.status_code,
                response=e.response
            )

    # ──────────────────────────────────────────────
    # VM CRUD Operations
    # ──────────────────────────────────────────────

    def list_vms(self):
        """
        List all VMs.

        Returns: list of VM dicts, e.g.:
        [
            {
                "name": "my-vm",
                "image": "ghcr.io/cirruslabs/macos-sequoia-base:latest",
                "status": "running",    # "pending", "running", "failed"
                "worker": "worker-1",   # or null if not assigned
                ...
            },
            ...
        ]
        """
        resp = self._request('GET', '/vms')
        return resp.json() or []  # Orchard may return null for empty list

    def get_vm(self, name):
        """
        Get a single VM by name.

        Returns: dict with VM details
        Raises: OrchardAPIError (404 if not found)
        """
        resp = self._request('GET', f'/vms/{name}')
        return resp.json()

    def create_vm(self, name, image, cpu=None, memory=None, startup_script=None):
        """
        Create/schedule a new VM.

        Args:
            name: VM name (must be unique)
            image: OCI image reference, e.g. "ghcr.io/cirruslabs/macos-sequoia-base:latest"
            cpu: Number of CPU cores (optional, Orchard default applies)
            memory: Memory in MB (optional, Orchard default applies)
            startup_script: Shell script to run on boot (optional)

        Returns: dict with created VM info

        Orchard API body format:
        {
            "name": "my-vm",
            "image": "ghcr.io/cirruslabs/...",
            "resources": {
                "org.cirruslabs.logical-cores": <cpu>,
                "org.cirruslabs.memory-mib": <memory>
            },
            "startupScript": {
                "scriptContent": "#!/bin/bash\n..."
            }
        }
        """
        body = {
            'name': name,
            'image': image,
        }

        # Resources are specified as a dict of resource labels → values
        resources = {}
        if cpu:
            resources['org.cirruslabs.logical-cores'] = cpu
        if memory:
            resources['org.cirruslabs.memory-mib'] = memory
        if resources:
            body['resources'] = resources

        if startup_script:
            body['startupScript'] = {'scriptContent': startup_script}

        resp = self._request('POST', '/vms', json=body)
        # Orchard returns 200/201 on success
        if resp.content:
            return resp.json()
        return {'name': name, 'status': 'pending'}

    def delete_vm(self, name):
        """
        Delete/wipe a VM.

        This stops the VM if running and removes it entirely.
        Raises: OrchardAPIError (404 if not found)
        """
        self._request('DELETE', f'/vms/{name}')

    # ──────────────────────────────────────────────
    # VM Information
    # ──────────────────────────────────────────────

    def get_vm_ip(self, name, wait=5):
        """
        Get the IP address of a running VM.

        Args:
            name: VM name
            wait: Seconds to wait for IP assignment (default 5)

        Returns: IP address string, e.g. "192.168.64.5"
        Returns None if no IP assigned yet.
        Raises: OrchardAPIError on API failure

        NOTE: The `wait` param tells Orchard to block up to N seconds
        waiting for the VM to get an IP. Useful for newly started VMs.
        """
        try:
            resp = self._request('GET', f'/vms/{name}/ip', params={'wait': wait})
            data = resp.json()
            # Response format may be {"ip": "..."} or just the IP string
            if isinstance(data, dict):
                return data.get('ip')
            return data
        except OrchardAPIError as e:
            if e.status_code == 404 or e.status_code == 408:
                return None  # No IP yet
            raise

    def get_vm_events(self, name, limit=50):
        """
        Get recent events/logs for a VM.

        Returns: list of event dicts, e.g.:
        [
            {
                "timestamp": "2024-01-15T10:30:00Z",
                "message": "VM scheduled on worker-1",
                "kind": "info"
            },
            ...
        ]
        """
        resp = self._request('GET', f'/vms/{name}/events')
        events = resp.json() or []
        return events[:limit]

    # ──────────────────────────────────────────────
    # Controller/Cluster Info
    # ──────────────────────────────────────────────

    def get_controller_info(self):
        """
        Get Orchard controller info (version, etc.)
        Useful for health checks and the dashboard footer.
        """
        try:
            resp = self._request('GET', '/controller/info')
            return resp.json()
        except OrchardAPIError:
            return None

    def health_check(self):
        """
        Quick check if Orchard is reachable.
        Returns True/False. Does not raise.
        """
        try:
            self._request('GET', '/vms')
            return True
        except OrchardAPIError:
            return False
```

### Important Notes on the Orchard API

1. **Authentication**: HTTP Basic Auth. The "username" is the service account name, "password" is the token. Create a service account via: `orchard create service-account <name>` which prints the token.

2. **VM Statuses**: Orchard VMs go through these states:
   - `pending` → Scheduled but not yet assigned to a worker
   - `running` → VM is active on a worker
   - `failed` → Something went wrong
   - (VMs don't have an explicit "stopped" state — they're either running or deleted)

3. **VNC Access**: TART VMs expose VNC on port 5900 when started with `--vnc`. Orchard workers run VMs with VNC enabled. The VM IP is on the host's local network, so websockify on localhost can reach it directly.

4. **API Prefix**: If the Orchard controller was started with `--api-prefix foo/bar`, then all endpoints are under `/foo/bar/v1/...`. Our `ORCHARD_API_PREFIX` config handles this.

---

## 7. Websockify Manager

### `app/websockify_manager.py` — Full Implementation

This is the most complex service. It manages one websockify subprocess per active VNC console session.

```python
import subprocess
import threading
import socket
import logging
import time

logger = logging.getLogger(__name__)


class WebsockifyManager:
    """
    Manages websockify subprocess lifecycles for VNC console access.

    Each running VM that a user wants to access via the web console
    gets its own websockify process that bridges:
        browser WebSocket (ws://localhost:<port>) → VM VNC (tcp://<vm_ip>:5900)

    The manager handles:
    - Port allocation from a configurable range
    - Starting/stopping websockify subprocesses
    - Idempotent start (reuse existing proxy if alive)
    - Dead process detection and cleanup
    - Full cleanup on app shutdown via atexit

    Thread-safe: all _proxies dict access is protected by a lock.
    """

    def __init__(self, app=None):
        # vm_name -> {
        #   'process': subprocess.Popen,
        #   'port': int,
        #   'vm_ip': str,
        #   'started_at': float (time.time())
        # }
        self._proxies = {}
        self._lock = threading.Lock()
        self._port_min = 6900
        self._port_max = 6999
        self._websockify_bin = 'websockify'
        self._vnc_port = 5900
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Configure from Flask app config."""
        self._port_min = app.config['WEBSOCKIFY_PORT_MIN']
        self._port_max = app.config['WEBSOCKIFY_PORT_MAX']
        self._websockify_bin = app.config['WEBSOCKIFY_BIN']
        self._vnc_port = app.config.get('VNC_PORT', 5900)
        logger.info(
            f"WebsockifyManager: ports {self._port_min}-{self._port_max}, "
            f"binary: {self._websockify_bin}"
        )

    def _find_free_port(self):
        """
        Find an available port in the configured range.

        Strategy:
        1. Skip ports already tracked in _proxies
        2. Attempt socket.bind() to verify OS-level availability
        3. Return first available port

        Raises RuntimeError if no port is free.

        IMPORTANT: Called while self._lock is NOT held (to avoid deadlock
        with socket operations). The caller must handle race conditions
        by catching port-in-use errors from subprocess launch.
        """
        used_ports = set()
        with self._lock:
            used_ports = {info['port'] for info in self._proxies.values()}

        for port in range(self._port_min, self._port_max + 1):
            if port in used_ports:
                continue
            # Verify the port is actually free at the OS level
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('127.0.0.1', port))
                    return port
            except OSError:
                continue

        raise RuntimeError(
            f"No free websockify ports in range "
            f"{self._port_min}-{self._port_max}. "
            f"Close some console sessions first."
        )

    def start_proxy(self, vm_name, vm_ip):
        """
        Start a websockify proxy for the given VM.

        If a proxy is already running for this VM, returns its port.
        If the existing process died, cleans it up and starts a new one.

        Args:
            vm_name: Name of the VM (used as key)
            vm_ip: IP address of the VM

        Returns: int — the local WebSocket port number

        Raises: RuntimeError if no ports available or process fails to start.

        The launched command is:
            websockify <local_port> <vm_ip>:5900
        """
        # Check for existing proxy
        with self._lock:
            if vm_name in self._proxies:
                info = self._proxies[vm_name]
                if info['process'].poll() is None:
                    # Still alive
                    logger.debug(f"Reusing websockify for {vm_name} on port {info['port']}")
                    return info['port']
                else:
                    # Process died — clean up
                    logger.warning(
                        f"websockify for {vm_name} died "
                        f"(exit code {info['process'].returncode}). Restarting."
                    )
                    del self._proxies[vm_name]

        # Allocate port and start process
        port = self._find_free_port()
        target = f"{vm_ip}:{self._vnc_port}"

        logger.info(f"Starting websockify: port {port} → {target} (VM: {vm_name})")

        try:
            proc = subprocess.Popen(
                [self._websockify_bin, '--web', '.', str(port), target],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"websockify binary not found at '{self._websockify_bin}'. "
                "Install it with: pip install websockify"
            )

        # Give websockify a moment to start (or fail)
        time.sleep(0.3)
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ''
            raise RuntimeError(
                f"websockify failed to start for {vm_name}: {stderr}"
            )

        with self._lock:
            self._proxies[vm_name] = {
                'process': proc,
                'port': port,
                'vm_ip': vm_ip,
                'started_at': time.time(),
            }

        logger.info(f"websockify started for {vm_name} on port {port} → {target}")
        return port

    def stop_proxy(self, vm_name):
        """
        Stop the websockify proxy for a VM.

        Safe to call even if no proxy is running (no-op).
        Uses SIGTERM first, then SIGKILL after 5s timeout.
        """
        with self._lock:
            info = self._proxies.pop(vm_name, None)

        if info is None:
            return

        proc = info['process']
        if proc.poll() is None:
            logger.info(f"Stopping websockify for {vm_name} (port {info['port']})")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(f"websockify for {vm_name} didn't stop, killing")
                proc.kill()
                proc.wait(timeout=2)
        else:
            logger.debug(f"websockify for {vm_name} already exited")

    def get_proxy_port(self, vm_name):
        """
        Get the websockify port for a VM, or None if not running.

        Also checks if the process is still alive.
        """
        with self._lock:
            info = self._proxies.get(vm_name)
            if info is None:
                return None
            if info['process'].poll() is not None:
                # Process died
                del self._proxies[vm_name]
                return None
            return info['port']

    def get_active_proxies(self):
        """
        Return a dict of all active proxies.
        Useful for admin/debug display.

        Returns: {vm_name: {'port': int, 'vm_ip': str, 'started_at': float}}
        """
        result = {}
        with self._lock:
            for vm_name, info in list(self._proxies.items()):
                if info['process'].poll() is None:
                    result[vm_name] = {
                        'port': info['port'],
                        'vm_ip': info['vm_ip'],
                        'started_at': info['started_at'],
                    }
                else:
                    del self._proxies[vm_name]
        return result

    def cleanup_all(self):
        """
        Terminate ALL websockify processes.
        Called on app shutdown via atexit.
        """
        with self._lock:
            names = list(self._proxies.keys())

        logger.info(f"Cleaning up {len(names)} websockify proxies...")
        for name in names:
            self.stop_proxy(name)
        logger.info("All websockify proxies cleaned up")
```

### How Port Allocation Works

```
Port Range: 6900 ─────────────────────────────── 6999
              │                                     │
              ├── 6900: VM "macos-dev" ✓ (in use)   │
              ├── 6901: (free)                       │
              ├── 6902: VM "ubuntu-test" ✓ (in use)  │
              ├── 6903: (free) ← next allocation     │
              │   ...                                │
              └── 6999: (free)                       │
```

- 100 ports = up to 100 concurrent VNC sessions (far more than needed on a single Mac)
- On `start_proxy()`: scans range, skips tracked + OS-occupied ports
- On `stop_proxy()`: kills process, frees port for reuse

---

## 8. Main Blueprint — Dashboard & VM Management

### `app/main/__init__.py`

```python
from flask import Blueprint

bp = Blueprint('main', __name__, template_folder='../templates/main')

from app.main import routes  # noqa: F401 — registers routes
```

### `app/main/routes.py` — Full Pseudocode

```python
from flask import (
    render_template, redirect, url_for, flash,
    request, current_app
)
from app.main import bp
from app.orchard_client import OrchardAPIError


@bp.route('/')
def dashboard():
    """
    Main dashboard — lists all VMs with status, actions.
    The table body auto-refreshes via HTMX polling.
    """
    try:
        vms = current_app.orchard.list_vms()
    except OrchardAPIError as e:
        flash(f'Cannot reach Orchard: {e}', 'danger')
        vms = []

    # Enrich VMs with websockify proxy status
    for vm in vms:
        vm['_console_port'] = current_app.websockify.get_proxy_port(vm.get('name', ''))

    return render_template('dashboard.html', vms=vms)


@bp.route('/vms/create', methods=['GET', 'POST'])
def create_vm():
    """
    GET: Show the create VM form.
    POST: Process form submission, create VM via Orchard API.
    """
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        image = request.form.get('image', '').strip()
        cpu = request.form.get('cpu', type=int)
        memory = request.form.get('memory', type=int)

        # Validation
        if not name:
            flash('VM name is required.', 'warning')
            return render_template('create_vm.html',
                                   images=current_app.config['TART_IMAGES'])

        if not image:
            flash('Image is required.', 'warning')
            return render_template('create_vm.html',
                                   images=current_app.config['TART_IMAGES'])

        try:
            current_app.orchard.create_vm(
                name=name, image=image, cpu=cpu, memory=memory
            )
            flash(f'VM "{name}" created successfully! It may take a moment to start.', 'success')
            return redirect(url_for('main.dashboard'))
        except OrchardAPIError as e:
            flash(f'Failed to create VM: {e}', 'danger')

    return render_template('create_vm.html',
                           images=current_app.config['TART_IMAGES'])


@bp.route('/vms/<vm_name>')
def vm_detail(vm_name):
    """
    Detail page for a single VM.
    Shows: status, image, worker, IP, events log.
    Actions: open console, delete.
    """
    try:
        vm = current_app.orchard.get_vm(vm_name)
    except OrchardAPIError as e:
        flash(f'VM not found: {e}', 'danger')
        return redirect(url_for('main.dashboard'))

    # Get events
    events = []
    try:
        events = current_app.orchard.get_vm_events(vm_name, limit=25)
    except OrchardAPIError:
        pass  # Non-critical — show page without events

    # Get IP if running
    ip_address = None
    if vm.get('status') == 'running':
        try:
            ip_address = current_app.orchard.get_vm_ip(vm_name, wait=2)
        except OrchardAPIError:
            pass

    # Check console status
    console_port = current_app.websockify.get_proxy_port(vm_name)

    return render_template('vm_detail.html',
                           vm=vm,
                           events=events,
                           ip_address=ip_address,
                           console_port=console_port)


@bp.route('/vms/<vm_name>/delete', methods=['POST'])
def delete_vm(vm_name):
    """
    Delete/wipe a VM.
    Also stops any running websockify proxy for this VM.
    """
    try:
        # Stop console proxy first (if running)
        current_app.websockify.stop_proxy(vm_name)
        # Delete from Orchard
        current_app.orchard.delete_vm(vm_name)
        flash(f'VM "{vm_name}" has been deleted.', 'success')
    except OrchardAPIError as e:
        flash(f'Failed to delete VM: {e}', 'danger')

    return redirect(url_for('main.dashboard'))
```

---

## 9. Console Blueprint — VNC Access

### `app/console/__init__.py`

```python
from flask import Blueprint

bp = Blueprint('console', __name__, template_folder='../templates/console')

from app.console import routes  # noqa: F401
```

### `app/console/routes.py` — Full Pseudocode

```python
from flask import (
    render_template, redirect, url_for, flash, current_app
)
from app.console import bp
from app.orchard_client import OrchardAPIError


@bp.route('/<vm_name>')
def vnc(vm_name):
    """
    VNC console page for a VM.

    Flow:
    1. Verify VM exists and is running
    2. Get VM IP from Orchard
    3. Start websockify proxy (or reuse existing)
    4. Render noVNC page with WebSocket port info

    The browser's noVNC client connects to:
        ws://localhost:<ws_port>
    Which websockify bridges to:
        tcp://<vm_ip>:5900
    """
    # Step 1: Check VM exists and is running
    try:
        vm = current_app.orchard.get_vm(vm_name)
    except OrchardAPIError:
        flash('VM not found.', 'danger')
        return redirect(url_for('main.dashboard'))

    status = vm.get('status', '')
    if status != 'running':
        flash(f'VM "{vm_name}" is not running (status: {status}). '
              f'Cannot open console.', 'warning')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    # Step 2: Get VM IP address
    try:
        vm_ip = current_app.orchard.get_vm_ip(vm_name, wait=10)
    except OrchardAPIError:
        vm_ip = None

    if not vm_ip:
        flash(f'Cannot determine IP address for VM "{vm_name}". '
              f'The VM may still be starting up.', 'warning')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    # Step 3: Start (or reuse) websockify proxy
    try:
        ws_port = current_app.websockify.start_proxy(vm_name, vm_ip)
    except RuntimeError as e:
        flash(f'Failed to start VNC proxy: {e}', 'danger')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    # Step 4: Render the noVNC console page
    return render_template(
        'vnc.html',
        vm_name=vm_name,
        vm=vm,
        ws_host=current_app.config.get('WEBSOCKIFY_HOST', 'localhost'),
        ws_port=ws_port,
        vnc_password=current_app.config['VNC_DEFAULT_PASSWORD'],
    )


@bp.route('/<vm_name>/disconnect', methods=['POST'])
def disconnect(vm_name):
    """
    Stop the websockify proxy for a VM.
    Called when user clicks "Disconnect" in the console.
    """
    current_app.websockify.stop_proxy(vm_name)
    flash(f'Console disconnected for "{vm_name}".', 'info')
    return redirect(url_for('main.vm_detail', vm_name=vm_name))
```

---

## 10. API Blueprint — HTMX/AJAX Endpoints

### `app/api/__init__.py`

```python
from flask import Blueprint

bp = Blueprint('api', __name__)

from app.api import routes  # noqa: F401
```

### `app/api/routes.py` — Full Pseudocode

```python
from flask import jsonify, current_app, request, render_template
from app.api import bp
from app.orchard_client import OrchardAPIError


@bp.route('/vms')
def list_vms():
    """
    List all VMs.

    If request has HX-Request header (HTMX), returns HTML partial.
    Otherwise returns JSON.

    Used by dashboard for auto-refresh polling:
        <div hx-get="/api/vms" hx-trigger="every 5s" hx-swap="innerHTML">
    """
    try:
        vms = current_app.orchard.list_vms()
    except OrchardAPIError as e:
        if request.headers.get('HX-Request'):
            # For HTMX, return an error row
            return f'<tr><td colspan="5" class="text-danger">Orchard API error: {e}</td></tr>'
        return jsonify({'error': str(e)}), 502

    # Enrich with console status
    for vm in vms:
        vm['_console_port'] = current_app.websockify.get_proxy_port(vm.get('name', ''))

    if request.headers.get('HX-Request'):
        return render_template('_partials/vm_table.html', vms=vms)

    return jsonify(vms)


@bp.route('/vms/<vm_name>/status')
def vm_status(vm_name):
    """
    Quick status check for a single VM.
    Returns JSON: {"name": "...", "status": "running|pending|failed"}

    Used by vm_detail page for status badge polling.
    """
    try:
        vm = current_app.orchard.get_vm(vm_name)
        return jsonify({
            'name': vm_name,
            'status': vm.get('status', 'unknown'),
        })
    except OrchardAPIError as e:
        return jsonify({'error': str(e)}), 502


@bp.route('/vms/<vm_name>/events')
def vm_events(vm_name):
    """
    Return recent events for a VM as JSON.
    Used for live event feed on vm_detail page.
    """
    try:
        events = current_app.orchard.get_vm_events(vm_name, limit=25)
        return jsonify(events)
    except OrchardAPIError as e:
        return jsonify({'error': str(e)}), 502
```

---

## 11. Templates — Full Specifications

### `templates/base.html` — Master Layout

```html
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Orchard UI{% endblock %}</title>

    <!-- Bootstrap 5 CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
          rel="stylesheet">
    <!-- Bootstrap Icons -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css"
          rel="stylesheet">
    <!-- Custom CSS -->
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">

    {% block head %}{% endblock %}
</head>
<body>

    <!-- Navigation -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark border-bottom">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('main.dashboard') }}">
                <i class="bi bi-pc-display"></i> Orchard UI
            </a>
            <button class="navbar-toggler" type="button"
                    data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('main.dashboard') }}">
                            <i class="bi bi-grid-3x3-gap"></i> Dashboard
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('main.create_vm') }}">
                            <i class="bi bi-plus-circle"></i> Create VM
                        </a>
                    </li>
                </ul>
                {# Future: user menu / login link goes here #}
                <ul class="navbar-nav">
                    {# <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('auth.login') }}">Login</a>
                    </li> #}
                </ul>
            </div>
        </div>
    </nav>

    <!-- Main content -->
    <main class="container-fluid mt-3 px-4">
        <!-- Flash messages -->
        {% include '_partials/flash_messages.html' %}

        {% block content %}{% endblock %}
    </main>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js">
    </script>
    <!-- HTMX -->
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    <!-- Custom JS -->
    <script src="{{ url_for('static', filename='js/app.js') }}"></script>

    {% block scripts %}{% endblock %}
</body>
</html>
```

**Design notes:**
- `data-bs-theme="dark"` — dark theme by default (looks professional for a server management UI)
- `container-fluid` — full width for dashboard table
- HTMX loaded globally (used on dashboard for polling)

### `templates/_partials/flash_messages.html`

```html
{% with messages = get_flashed_messages(with_categories=true) %}
{% if messages %}
    {% for category, message in messages %}
    <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
        {{ message }}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    </div>
    {% endfor %}
{% endif %}
{% endwith %}
```

### `templates/_partials/vm_status_badge.html`

```html
{# Expects: vm dict with 'status' key #}
{% if vm.status == 'running' %}
    <span class="badge bg-success"><i class="bi bi-play-fill"></i> Running</span>
{% elif vm.status == 'pending' %}
    <span class="badge bg-warning text-dark">
        <i class="bi bi-hourglass-split"></i> Pending
    </span>
{% elif vm.status == 'failed' %}
    <span class="badge bg-danger"><i class="bi bi-x-circle"></i> Failed</span>
{% else %}
    <span class="badge bg-secondary">{{ vm.status | default('Unknown') }}</span>
{% endif %}
```

### `templates/main/dashboard.html`

```html
{% extends "base.html" %}

{% block title %}Dashboard — Orchard UI{% endblock %}

{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
    <h2><i class="bi bi-grid-3x3-gap"></i> Virtual Machines</h2>
    <a href="{{ url_for('main.create_vm') }}" class="btn btn-primary">
        <i class="bi bi-plus-circle"></i> Create VM
    </a>
</div>

<div class="card">
    <div class="card-body p-0">
        <table class="table table-hover mb-0">
            <thead class="table-dark">
                <tr>
                    <th>Name</th>
                    <th>Image</th>
                    <th>Status</th>
                    <th>Worker</th>
                    <th style="width: 250px;">Actions</th>
                </tr>
            </thead>
            <tbody
                hx-get="{{ url_for('api.list_vms') }}"
                hx-trigger="every {{ poll_interval_ms // 1000 }}s"
                hx-swap="innerHTML"
            >
                {# Initial render — same partial used for HTMX updates #}
                {% include '_partials/vm_table.html' %}
            </tbody>
        </table>
    </div>
</div>

{# Empty state is handled inside _partials/vm_table.html —
   the partial renders an empty-state row when vms is empty,
   which keeps it consistent between initial load and HTMX polling. #}
{% endblock %}
```

### `templates/_partials/vm_table.html`

```html
{# Partial template: table body rows for VM list.
   Used both for initial render and HTMX polling updates.
   Expects: vms (list of VM dicts) #}

{% for vm in vms %}
<tr>
    <td>
        <a href="{{ url_for('main.vm_detail', vm_name=vm.name) }}"
           class="text-decoration-none fw-bold">
            {{ vm.name }}
        </a>
    </td>
    <td>
        <small class="text-muted">{{ vm.image | default('—') }}</small>
    </td>
    <td>
        {% include '_partials/vm_status_badge.html' %}
    </td>
    <td>{{ vm.worker | default('—') }}</td>
    <td>
        {# Console button — only for running VMs #}
        {% if vm.status == 'running' %}
        <a href="{{ url_for('console.vnc', vm_name=vm.name) }}"
           class="btn btn-sm btn-success me-1"
           title="Open VNC Console">
            <i class="bi bi-terminal"></i> Console
        </a>
        {% else %}
        <button class="btn btn-sm btn-outline-secondary me-1" disabled
                title="VM must be running">
            <i class="bi bi-terminal"></i> Console
        </button>
        {% endif %}

        {# Detail button #}
        <a href="{{ url_for('main.vm_detail', vm_name=vm.name) }}"
           class="btn btn-sm btn-outline-info me-1"
           title="View Details">
            <i class="bi bi-info-circle"></i>
        </a>

        {# Delete button #}
        <form method="POST"
              action="{{ url_for('main.delete_vm', vm_name=vm.name) }}"
              style="display: inline-block;"
              onsubmit="return confirm('Are you sure you want to delete VM \'{{ vm.name }}\'? This cannot be undone.')">
            <button type="submit" class="btn btn-sm btn-outline-danger"
                    title="Delete VM">
                <i class="bi bi-trash"></i>
            </button>
        </form>
    </td>
</tr>
{% endfor %}

{% if not vms %}
<tr>
    <td colspan="5" class="text-center text-muted py-4">
        No virtual machines found.
        <a href="{{ url_for('main.create_vm') }}">Create one?</a>
    </td>
</tr>
{% endif %}
```

### `templates/main/vm_detail.html`

```html
{% extends "base.html" %}

{% block title %}{{ vm.name }} — Orchard UI{% endblock %}

{% block content %}
<nav aria-label="breadcrumb">
    <ol class="breadcrumb">
        <li class="breadcrumb-item"><a href="{{ url_for('main.dashboard') }}">Dashboard</a></li>
        <li class="breadcrumb-item active">{{ vm.name }}</li>
    </ol>
</nav>

<div class="row">
    <!-- VM Info Card -->
    <div class="col-md-6">
        <div class="card mb-3">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h4 class="mb-0">{{ vm.name }}</h4>
                <span
                    hx-get="{{ url_for('api.vm_status', vm_name=vm.name) }}"
                    hx-trigger="every 3s"
                    hx-swap="innerHTML"
                    hx-target="this"
                >
                    {% include '_partials/vm_status_badge.html' %}
                </span>
            </div>
            <div class="card-body">
                <table class="table table-sm">
                    <tr><th>Image</th><td>{{ vm.image | default('—') }}</td></tr>
                    <tr><th>Worker</th><td>{{ vm.worker | default('—') }}</td></tr>
                    <tr>
                        <th>IP Address</th>
                        <td>{{ ip_address | default('Not available') }}</td>
                    </tr>
                    {# Add more VM fields as discovered from the API #}
                </table>

                <div class="d-flex gap-2 mt-3">
                    {% if vm.status == 'running' %}
                    <a href="{{ url_for('console.vnc', vm_name=vm.name) }}"
                       class="btn btn-success">
                        <i class="bi bi-terminal"></i> Open Console
                    </a>
                    {% endif %}

                    {% if console_port %}
                    <form method="POST"
                          action="{{ url_for('console.disconnect', vm_name=vm.name) }}">
                        <button class="btn btn-outline-warning">
                            <i class="bi bi-x-circle"></i> Disconnect Console
                        </button>
                    </form>
                    {% endif %}

                    <form method="POST"
                          action="{{ url_for('main.delete_vm', vm_name=vm.name) }}"
                          onsubmit="return confirm('Delete VM \'{{ vm.name }}\'?')">
                        <button class="btn btn-outline-danger">
                            <i class="bi bi-trash"></i> Delete
                        </button>
                    </form>
                </div>
            </div>
        </div>
    </div>

    <!-- Events Log -->
    <div class="col-md-6">
        <div class="card mb-3">
            <div class="card-header">
                <h5 class="mb-0"><i class="bi bi-journal-text"></i> Events</h5>
            </div>
            <div class="card-body p-0" style="max-height: 400px; overflow-y: auto;">
                <table class="table table-sm table-striped mb-0">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Message</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for event in events %}
                        <tr>
                            <td class="text-nowrap">
                                <small>{{ event.timestamp | default('—') }}</small>
                            </td>
                            <td>{{ event.message | default(event | string) }}</td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="2" class="text-muted text-center">
                                No events recorded.
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

**Note on status polling**: The status badge on vm_detail uses `hx-swap="outerHTML"` so the entire `<span>` is replaced on each poll. The `/api/vms/<name>/status` endpoint detects the `HX-Request` header and returns the rendered `_partials/vm_status_badge.html` partial directly.

### `templates/main/create_vm.html`

```html
{% extends "base.html" %}

{% block title %}Create VM — Orchard UI{% endblock %}

{% block content %}
<nav aria-label="breadcrumb">
    <ol class="breadcrumb">
        <li class="breadcrumb-item"><a href="{{ url_for('main.dashboard') }}">Dashboard</a></li>
        <li class="breadcrumb-item active">Create VM</li>
    </ol>
</nav>

<div class="row justify-content-center">
    <div class="col-md-8 col-lg-6">
        <div class="card">
            <div class="card-header">
                <h4 class="mb-0"><i class="bi bi-plus-circle"></i> Create Virtual Machine</h4>
            </div>
            <div class="card-body">
                <form method="POST" action="{{ url_for('main.create_vm') }}">

                    <!-- VM Name -->
                    <div class="mb-3">
                        <label for="name" class="form-label">VM Name</label>
                        <input type="text" class="form-control" id="name" name="name"
                               required placeholder="e.g., my-dev-machine"
                               pattern="[a-zA-Z0-9][a-zA-Z0-9._-]*"
                               title="Letters, numbers, dots, hyphens, underscores. Start with letter/number.">
                        <div class="form-text">
                            Unique name for this VM. Letters, numbers, hyphens, underscores.
                        </div>
                    </div>

                    <!-- Image Selection -->
                    <div class="mb-3">
                        <label for="image" class="form-label">Image</label>
                        <select class="form-select" id="image" name="image" required>
                            <option value="">Select an image...</option>
                            {% for img in images %}
                            <option value="{{ img }}">{{ img }}</option>
                            {% endfor %}
                        </select>
                        <div class="form-text">
                            TART VM image from OCI registry.
                        </div>
                    </div>

                    <!-- CPU (optional) -->
                    <div class="mb-3">
                        <label for="cpu" class="form-label">
                            CPU Cores <small class="text-muted">(optional)</small>
                        </label>
                        <input type="number" class="form-control" id="cpu" name="cpu"
                               min="1" max="16" placeholder="Default: Orchard decides">
                    </div>

                    <!-- Memory (optional) -->
                    <div class="mb-3">
                        <label for="memory" class="form-label">
                            Memory (MB) <small class="text-muted">(optional)</small>
                        </label>
                        <input type="number" class="form-control" id="memory" name="memory"
                               min="1024" step="1024" placeholder="Default: Orchard decides">
                    </div>

                    <div class="d-flex gap-2">
                        <button type="submit" class="btn btn-primary">
                            <i class="bi bi-plus-circle"></i> Create VM
                        </button>
                        <a href="{{ url_for('main.dashboard') }}" class="btn btn-outline-secondary">
                            Cancel
                        </a>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

### `templates/console/vnc.html` — Standalone noVNC Page

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Console: {{ vm_name }} — Orchard UI</title>
    <style>
        /* Full-page layout — no base.html, maximum screen real estate */
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { height: 100%; overflow: hidden; background: #1a1a1a; }

        #top-bar {
            background: #212529;
            color: #e0e0e0;
            padding: 6px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #333;
            height: 44px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 14px;
        }

        #top-bar .vm-name { font-weight: 600; color: #fff; }
        #top-bar a { color: #8ab4f8; text-decoration: none; margin-left: 16px; }
        #top-bar a:hover { text-decoration: underline; }

        #top-bar .controls { display: flex; align-items: center; gap: 12px; }

        .btn-disconnect {
            background: none; border: 1px solid #dc3545; color: #dc3545;
            padding: 2px 10px; border-radius: 4px; cursor: pointer;
            font-size: 13px;
        }
        .btn-disconnect:hover { background: #dc3545; color: white; }

        #status-indicator {
            display: inline-block; width: 8px; height: 8px;
            border-radius: 50%; margin-right: 6px;
        }
        #status-indicator.connected { background: #28a745; }
        #status-indicator.disconnected { background: #dc3545; }
        #status-indicator.connecting { background: #ffc107; }

        /* noVNC container fills remaining space */
        #vnc-container {
            width: 100%;
            height: calc(100vh - 44px);
        }

        /* Overlay message when disconnected */
        #disconnect-overlay {
            display: none;
            position: absolute;
            top: 44px; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.8);
            color: white;
            justify-content: center;
            align-items: center;
            flex-direction: column;
            font-family: -apple-system, sans-serif;
            z-index: 100;
        }
        #disconnect-overlay.visible { display: flex; }
        #disconnect-overlay h3 { margin-bottom: 16px; }
        #disconnect-overlay a {
            color: #8ab4f8; text-decoration: none;
            padding: 8px 24px; border: 1px solid #8ab4f8;
            border-radius: 4px;
        }
    </style>
</head>
<body>

    <!-- Top bar with VM name, status, and navigation -->
    <div id="top-bar">
        <div>
            <span id="status-indicator" class="connecting"></span>
            Console: <span class="vm-name">{{ vm_name }}</span>
        </div>
        <div class="controls">
            <a href="{{ url_for('main.vm_detail', vm_name=vm_name) }}">← Back to VM</a>
            <a href="{{ url_for('main.dashboard') }}">Dashboard</a>
            <form method="POST"
                  action="{{ url_for('console.disconnect', vm_name=vm_name) }}"
                  style="display:inline">
                <button type="submit" class="btn-disconnect">Disconnect</button>
            </form>
        </div>
    </div>

    <!-- noVNC renders into this container -->
    <div id="vnc-container"></div>

    <!-- Overlay shown when connection is lost -->
    <div id="disconnect-overlay">
        <h3 id="disconnect-message">Connection Lost</h3>
        <a href="{{ url_for('console.vnc', vm_name=vm_name) }}">Reconnect</a>
        <br><br>
        <a href="{{ url_for('main.dashboard') }}">Back to Dashboard</a>
    </div>

    <!-- Pass config to JS -->
    <script>
        window.VNC_CONFIG = {
            wsHost: '{{ ws_host }}',
            wsPort: {{ ws_port }},
            password: '{{ vnc_password }}',
            vmName: '{{ vm_name }}'
        };
    </script>

    <!-- noVNC initialization (ES module) -->
    <script type="module" src="{{ url_for('static', filename='js/console.js') }}"></script>

</body>
</html>
```

---

## 12. Static Assets — JS & CSS

### `static/js/app.js` — Dashboard Logic

```javascript
/**
 * app.js — General dashboard JavaScript.
 *
 * Responsibilities:
 * - Confirmation dialogs for delete actions (handled inline via onsubmit)
 * - Any future JS enhancements for the dashboard
 *
 * HTMX handles polling automatically via HTML attributes.
 * This file is intentionally minimal.
 */

document.addEventListener('DOMContentLoaded', () => {
    // Auto-dismiss flash messages after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 5000);
    });
});

// HTMX event hooks (optional, for future enhancements)
document.body.addEventListener('htmx:afterSwap', (evt) => {
    // Called after HTMX swaps content (e.g., VM table update)
    // Could be used for animations, tooltips, etc.
});

document.body.addEventListener('htmx:responseError', (evt) => {
    // Handle HTMX request failures gracefully
    console.warn('HTMX request failed:', evt.detail);
});
```

### `static/js/console.js` — noVNC Integration

```javascript
/**
 * console.js — noVNC integration for Orchard UI.
 *
 * ES module — deferred by default, no DOMContentLoaded wrapper needed.
 * Config is injected from Flask via window.VNC_CONFIG.
 *
 * Connection flow:
 *   Browser → WebSocket (ws://<wsHost>:<wsPort>) → websockify → VM:5900
 */

import RFB from '/static/novnc/core/rfb.js';

const { wsHost, wsPort, password, vmName } = window.VNC_CONFIG;

const indicator = document.getElementById('status-indicator');
const overlay = document.getElementById('disconnect-overlay');
const overlayMessage = document.getElementById('disconnect-message');

function setStatus(state) {
    indicator.className = '';
    indicator.classList.add(state);
}

function showOverlay(message) {
    overlayMessage.textContent = message || 'Connection Lost';
    overlay.classList.add('visible');
}

function hideOverlay() {
    overlay.classList.remove('visible');
}

setStatus('connecting');

const wsUrl = `ws://${wsHost}:${wsPort}`;

const rfb = new RFB(
    document.getElementById('vnc-container'),
    wsUrl,
    { credentials: { password }, shared: true }
);

rfb.scaleViewport = true;
rfb.resizeSession = false;
rfb.clipViewport = false;

rfb.addEventListener('connect', () => {
    setStatus('connected');
    hideOverlay();
    console.log(`noVNC connected to ${vmName}`);
});

rfb.addEventListener('disconnect', (evt) => {
    setStatus('disconnected');
    if (evt.detail?.clean) {
        console.log(`noVNC disconnected cleanly from ${vmName}`);
        showOverlay('VNC session ended.');
    } else {
        const reason = evt.detail?.reason || 'Connection lost unexpectedly.';
        console.warn(`noVNC disconnected from ${vmName}:`, reason);
        showOverlay(reason);
    }
});

rfb.addEventListener('credentialsrequired', () => {
    rfb.sendCredentials({ password });
});

rfb.addEventListener('securityfailure', (evt) => {
    setStatus('disconnected');
    showOverlay(`Security failure: ${evt.detail?.reason || 'wrong password?'}`);
});
```

### `static/css/style.css` — Custom Overrides

```css
/**
 * style.css — Custom overrides on top of Bootstrap 5 dark theme.
 * Keep this minimal — leverage Bootstrap classes in templates.
 */

/* Slightly softer background for cards */
.card {
    border-color: #333;
}

/* Dashboard table: tighter rows */
.table td, .table th {
    vertical-align: middle;
}

/* Status badges: slightly larger */
.badge {
    font-size: 0.8rem;
    padding: 0.4em 0.6em;
}

/* Navbar brand icon */
.navbar-brand i {
    margin-right: 4px;
}

/* Form labels */
.form-label {
    font-weight: 500;
}

/* Flash messages */
.alert {
    margin-bottom: 0.5rem;
}
```

---

## 13. noVNC Integration Guide

### Setup Script: `scripts/setup_novnc.sh`

```bash
#!/bin/bash
#
# Download and install noVNC static files into the Flask app.
# Run this once during project setup.
#

set -e

NOVNC_VERSION="1.5.0"
DEST_DIR="app/static/novnc"

echo "Downloading noVNC v${NOVNC_VERSION}..."

# Clean previous install
rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"

# Download and extract
curl -L "https://github.com/novnc/noVNC/archive/refs/tags/v${NOVNC_VERSION}.tar.gz" | tar xz

# Copy only what we need (core library + vendor deps)
cp -r "noVNC-${NOVNC_VERSION}/core" "$DEST_DIR/core"
cp -r "noVNC-${NOVNC_VERSION}/vendor" "$DEST_DIR/vendor"

# Clean up
rm -rf "noVNC-${NOVNC_VERSION}"

echo "noVNC v${NOVNC_VERSION} installed to ${DEST_DIR}/"
echo "Files:"
ls -la "$DEST_DIR/core/"
```

### How noVNC Works (for the developer)

1. **`RFB` class** is the main entry point — it's a JavaScript ES module in `core/rfb.js`
2. It connects to a WebSocket URL and speaks the **RFB (Remote Framebuffer) protocol** — the underlying protocol of VNC
3. It renders the VM's display into a `<canvas>` element inside the target container
4. It captures keyboard and mouse events and forwards them to the VM
5. Clipboard integration works via the VNC clipboard extension

### Connection Chain

```
Browser                    websockify               VM
  │                           │                      │
  │  WebSocket connect        │                      │
  │  ws://localhost:6901      │                      │
  │ ─────────────────────►    │                      │
  │                           │  TCP connect          │
  │                           │  192.168.64.5:5900    │
  │                           │ ──────────────────►   │
  │                           │                      │
  │  ◄── RFB handshake ──►   │  ◄── RFB data ──►    │
  │  ◄── framebuffer ────    │  ◄── framebuffer ──   │
  │  ── keyboard/mouse ──►   │  ── keyboard/mouse ►  │
  │  ◄── clipboard ──────►   │  ◄── clipboard ────►  │
```

### Key noVNC Configuration Options

| Option | Value | Effect |
|--------|-------|--------|
| `scaleViewport` | `true` | Scale VM display to fit browser window |
| `resizeSession` | `false` | Don't change VM's actual resolution |
| `clipViewport` | `false` | Show full VM screen (with scroll if needed) |
| `shared` | `true` | Allow multiple VNC connections to same VM |
| `credentials.password` | `'admin'` | TART default VNC password |

---

## 14. Future Auth Preparation

### What Changes When Auth Is Added

**New dependencies:**
```
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
```

**New/modified files:**

1. **`app/extensions.py`** — Initialize db and login_manager:
   ```python
   from flask_sqlalchemy import SQLAlchemy
   from flask_login import LoginManager

   db = SQLAlchemy()
   login_manager = LoginManager()
   login_manager.login_view = 'auth.login'
   login_manager.login_message_category = 'warning'

   def init_extensions(app):
       db.init_app(app)
       login_manager.init_app(app)
   ```

2. **`app/auth/models.py`** — User model:
   ```python
   from app.extensions import db
   from flask_login import UserMixin

   class User(UserMixin, db.Model):
       id = db.Column(db.Integer, primary_key=True)
       username = db.Column(db.String(64), unique=True, nullable=False)
       password_hash = db.Column(db.String(128), nullable=False)
       # Future: relationship to user's VMs
   ```

3. **`app/auth/routes.py`** — Login/logout/register routes

4. **`config.py`** — Add:
   ```python
   SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///orchard_ui.db')
   ```

5. **Existing routes** — Add `@login_required`:
   ```python
   from flask_login import login_required

   @bp.route('/')
   @login_required
   def dashboard():
       ...
   ```

6. **`base.html`** — Add user menu in navbar

**What does NOT change:** OrchardClient, WebsockifyManager, all template layouts, static assets, noVNC integration.

### User-VM Ownership Model (Future)

When users are added, each user will have their own list of VMs they can manage. Options:

1. **Prefix naming**: VMs are named `<username>-<vmname>`, filtered by prefix
2. **Database tracking**: A `user_vms` table maps users to VM names they own
3. **Orchard labels**: Use Orchard's label system to tag VMs with owner info

Recommend option 2 (database tracking) — most flexible, doesn't pollute VM names.

---

## 15. Error Handling Strategy

### Layer 1: Orchard API Client
- All errors become `OrchardAPIError(message, status_code, response)`
- Connection errors → "Cannot connect to Orchard controller"
- HTTP errors → extract detail from response body JSON
- Timeouts → "Request timed out"

### Layer 2: Route Handlers
- Catch `OrchardAPIError`, flash user-friendly message, redirect
- Non-critical failures (events, IP) → skip gracefully, show partial page
- Critical failures (VM not found) → redirect to dashboard

### Layer 3: Websockify Manager
- `RuntimeError` for port exhaustion or binary-not-found
- Route catches and flashes error, redirects to VM detail

### Layer 4: Templates
- Empty states: "No VMs found", "No events recorded"
- HTMX error row: `<td colspan="5" class="text-danger">Error message</td>`
- noVNC disconnect overlay with reconnect link

### Global Error Handler (add to `app/__init__.py`)

```python
@app.errorhandler(500)
def internal_error(error):
    return render_template('errors/500.html'), 500

@app.errorhandler(404)
def not_found(error):
    return render_template('errors/404.html'), 404
```

---

## 16. Implementation Order

### Phase 1: Scaffold (do first — everything depends on this)
1. Create project directory structure
2. Write `requirements.txt`
3. Write `config.py` with all config classes
4. Write `.env.example`, `.flaskenv`, `.gitignore`
5. Write `run.py`
6. Write `app/__init__.py` (app factory)
7. Write `app/extensions.py` (placeholder)
8. Verify: `flask run` starts without errors

### Phase 2: Orchard API Client
1. Write `app/orchard_client.py` with all methods
2. Test manually: `flask shell` → `app.orchard.list_vms()`
3. Handle edge cases: empty responses, connection failures

### Phase 3: Dashboard (first visible page)
1. Write `app/main/__init__.py` (blueprint)
2. Write `templates/base.html` (master layout)
3. Write `templates/_partials/flash_messages.html`
4. Write `templates/_partials/vm_status_badge.html`
5. Write `templates/_partials/vm_table.html`
6. Write `templates/main/dashboard.html`
7. Write `app/main/routes.py` (dashboard route only first)
8. Write `static/css/style.css`
9. Write `static/js/app.js`
10. Verify: dashboard shows VMs from Orchard

### Phase 4: VM Operations
1. Add `create_vm` route + `templates/main/create_vm.html`
2. Add `vm_detail` route + `templates/main/vm_detail.html`
3. Add `delete_vm` route
4. Verify: full CRUD lifecycle works

### Phase 5: API Endpoints + HTMX Polling
1. Write `app/api/__init__.py` + `routes.py`
2. Add HTMX attributes to dashboard template
3. Verify: dashboard auto-refreshes every 5 seconds

### Phase 6: noVNC Setup
1. Run `scripts/setup_novnc.sh` to download noVNC
2. Write `static/js/console.js`
3. Verify: noVNC files are loadable from browser

### Phase 7: Websockify Manager
1. Write `app/websockify_manager.py`
2. Wire into app factory (atexit hook)
3. Test: manually start/stop proxy, verify port allocation

### Phase 8: Console Blueprint
1. Write `app/console/__init__.py` + `routes.py`
2. Write `templates/console/vnc.html`
3. Verify: open console for a running VM, see VNC display

### Phase 9: Polish
1. Error pages (404, 500)
2. Loading states
3. Responsive tweaks
4. README with setup instructions

---

## 17. Verification & Testing

### Manual Test Checklist

1. **Setup**
   - `pip install -r requirements.txt`
   - Copy `.env.example` → `.env`, fill in Orchard credentials
   - Run `scripts/setup_novnc.sh`
   - `flask run`

2. **Dashboard**
   - Open `http://localhost:5000` — page loads, shows VM table
   - If Orchard is down → flash error, empty table
   - Table auto-refreshes (open browser dev tools → network tab, see HTMX requests)

3. **Create VM**
   - Click "Create VM", fill form, submit
   - VM appears in dashboard with "Pending" badge
   - Badge changes to "Running" after a few seconds (auto-refresh)

4. **VM Detail**
   - Click VM name → detail page loads
   - Shows events, IP, status badge
   - Status badge polls and updates

5. **VNC Console**
   - Click "Console" on a running VM
   - Full-page noVNC loads, connects to VM
   - VM display visible, keyboard/mouse work
   - Status indicator shows green "connected"
   - Check: `ps aux | grep websockify` — process is running

6. **Console Disconnect**
   - Click "Disconnect" → redirected to VM detail
   - Check: websockify process is killed

7. **Delete VM**
   - Click "Delete" on a VM with active console
   - Confirm dialog appears
   - VM disappears from dashboard
   - Check: websockify process for that VM is killed

8. **App Shutdown**
   - `Ctrl+C` Flask
   - Check: `ps aux | grep websockify` — all processes cleaned up

### Automated Testing (future)

```python
# tests/test_orchard_client.py
# Mock the requests.Session to test OrchardClient methods
# without a real Orchard controller

# tests/test_websockify_manager.py
# Mock subprocess.Popen to test port allocation,
# start/stop logic, cleanup

# tests/test_routes.py
# Flask test client with mocked OrchardClient
```

---

## Appendix: Orchard CLI Reference (for manual testing)

```bash
# Start Orchard in dev mode (no auth, single machine)
orchard dev

# Create a service account (for controller+worker mode)
orchard create service-account my-ui-account
# → prints token

# List VMs
orchard list vms

# Create a VM
orchard create vm --image ghcr.io/cirruslabs/macos-sequoia-base:latest my-test-vm

# Get VM IP
orchard get vm my-test-vm

# SSH to a VM
orchard ssh vm my-test-vm

# VNC to a VM (opens macOS Screen Sharing)
orchard vnc vm my-test-vm

# Delete a VM
orchard delete vm my-test-vm

# Check API directly
curl -u my-ui-account:<token> http://localhost:6120/v1/vms
curl -u my-ui-account:<token> http://localhost:6120/v1/vms/my-test-vm/ip
```

---

*End of planning document.*
