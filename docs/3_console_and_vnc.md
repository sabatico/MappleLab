# Module 3: Console — SSH Tunnel + noVNC

> **Status**: ✅ Complete (refurbished 2026-02-21)

**Original scope**: Phases 6–8 from PLANNING.md — local websockify + noVNC
**Current state**: Fully transitioned to TART-Direct architecture (see `refurbish_plan.md`)
**Output**: In-browser VNC console via SSH tunnel from Flask server → Mac node websockify → VM
**Depends on**: Module 1 (TunnelManager, TartClient), Module 2 (dashboard links to console)

---

## ⚠️ Architecture Note

This module originally ran `websockify` **locally** on the Flask server (direct TCP to VM IP). This required the Flask server to have direct network access to each VM. It has been **replaced** with a two-tier VNC proxy:

| Old architecture | New architecture |
|-----------------|-----------------|
| `WebsockifyManager` (local subprocess) | `TunnelManager` (paramiko SSH tunnels) |
| Flask spawns `websockify <port> <vm-ip>:5900` | TART agent spawns websockify on Mac node |
| Direct network path Flask → VM | SSH tunnel: Flask → Mac node → VM |
| websockify binary on Flask server | websockify binary on Mac nodes only |

**New VNC chain**:
```
Browser WebSocket
    │  ws://flask-server:<local-tunnel-port>
    ▼
Flask Server (TunnelManager)
    │  SSH tunnel (paramiko) → Mac Node
    ▼
Mac Node TART Agent (VncManager)
    │  websockify <port> <vm-ip>:5900
    ▼
TART VM :5900 (VNC server)
    │
noVNC displays desktop
```

---

## Tasks

### Original console tasks (complete)
- [x] Write and run `scripts/setup_novnc.sh` — download noVNC v1.5.0
- [x] Verify `app/static/novnc/core/rfb.js` exists
- [x] Write `app/console/routes.py` (vnc, disconnect)
- [x] Write `app/templates/console/vnc.html` (standalone full-page layout)
- [x] Write `app/static/js/console.js` (RFB init + event handlers)

### Refurbishment rewrites (complete)
- [x] Rewrite `app/console/routes.py` — calls TartClient.start_vnc() + TunnelManager.start_tunnel()
- [x] Add `@login_required` to all console routes
- [x] Update `vnc.html` — `ws_host` is Flask server hostname (not localhost); tunnel port is dynamic
- [x] Delete `app/websockify_manager.py` (moved to `tart_agent/vnc_manager.py`)
- [x] Verify: console route resolves vm from DB, checks status == 'running'
- [x] Verify: disconnect cleans up SSH tunnel + stops agent websockify

### Items requiring live hardware (not yet verified)
- [ ] Verify: noVNC connects and VM display is visible (requires live Mac node + VM)
- [ ] Verify: keyboard and mouse work in the VM (requires live Mac node + VM)

---

## Files

| File | Status | Notes |
|------|--------|-------|
| `scripts/setup_novnc.sh` | ✅ | Downloads noVNC v1.5.0 static files |
| `app/static/novnc/` | ✅ | Downloaded by setup_novnc.sh (gitignored) |
| `app/console/routes.py` | ✅ | REWRITTEN: TartClient VNC + TunnelManager SSH tunnel |
| `app/templates/console/vnc.html` | ✅ | Standalone full-page (does not extend base.html) |
| `app/static/js/console.js` | ✅ | ES module — RFB init, connect/disconnect handlers |
| `app/websockify_manager.py` | ❌ DELETED | Logic moved to `tart_agent/vnc_manager.py` |
| `tart_agent/vnc_manager.py` | ✅ | Websockify lifecycle — runs on each Mac node |
| `app/tunnel_manager.py` | ✅ | SSH port-forward tunnels (lives in Module 1) |

**Status key**: ⬜ Not started · 🔄 In progress · ✅ Complete · ❌ Deleted

---

## Overview

The console module coordinates three components:

```
1. TART Agent (Mac node)  — starts/stops websockify process on the node
2. TunnelManager (Flask)  — SSH port-forward from Flask local port to agent websockify port
3. noVNC (browser)        — WebSocket client connecting to Flask local port
```

Flask's role:
1. Look up VM + node from DB
2. Ask the agent to start websockify → get remote port
3. Start an SSH tunnel from a local port to that remote port
4. Tell the browser: `ws://flask-server:<local-port>`

---

## Console Routes

### `GET /console/<vm_name>` → `vnc(vm_name)`

```python
@bp.route('/<vm_name>')
@login_required
def vnc(vm_name):
    # 1. Load VM from DB (404 if not found or not owned by current_user)
    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()

    # 2. Check VM is running
    if vm.status != 'running':
        flash(f'VM is not running (status: {vm.status}).', 'warning')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    node = vm.node

    # 3. Ask agent to start websockify on the Mac node → remote port
    try:
        remote_port = current_app.tart.start_vnc(node, vm_name)
    except TartAPIError as e:
        flash(f'Failed to start VNC: {e}', 'danger')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    # 4. Create SSH tunnel: Flask local port → node:remote_port
    try:
        local_port = current_app.tunnel_manager.start_tunnel(vm_name, node, remote_port)
    except Exception as e:
        flash(f'Failed to create VNC tunnel: {e}', 'danger')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    # 5. Render noVNC with Flask server host + tunnel port
    return render_template(
        'vnc.html',
        vm_name=vm_name,
        vm=vm,
        ws_host=request.host.split(':')[0],   # Flask server hostname
        ws_port=local_port,
        vnc_password=current_app.config['VNC_DEFAULT_PASSWORD'],
    )
```

### `POST /console/<vm_name>/disconnect` → `disconnect(vm_name)`

```python
@bp.route('/<vm_name>/disconnect', methods=['POST'])
@login_required
def disconnect(vm_name):
    # 1. Close SSH tunnel (local port freed)
    current_app.tunnel_manager.stop_tunnel(vm_name)

    # 2. Stop websockify on agent (optional but clean)
    vm = VM.query.filter_by(name=vm_name).first()
    if vm and vm.node:
        try:
            current_app.tart.stop_vnc(vm.node, vm_name)
        except TartAPIError:
            pass   # non-fatal

    flash('Console disconnected.', 'info')
    return redirect(url_for('main.vm_detail', vm_name=vm_name))
```

---

## vnc.html Template

Standalone full-page layout — does NOT extend `base.html` (maximizes VNC display area).

```
┌──────────────────────────────────────────────────────┐  ← 44px top bar
│ ● Console: <vm-name>    [← Back] [Dashboard] [Disconnect] │
├──────────────────────────────────────────────────────┤
│                                                      │
│              noVNC renders here                      │
│          (fills calc(100vh - 44px))                  │
│                                                      │
└──────────────────────────────────────────────────────┘
```

Config passed to JS via inline script:
```html
<script>
window.VNC_CONFIG = {
    wsHost: '{{ ws_host }}',    ← Flask server hostname (NOT localhost)
    wsPort: {{ ws_port }},      ← SSH tunnel local port (dynamic)
    password: '{{ vnc_password }}',
    vmName: '{{ vm_name }}'
};
</script>
<script type="module" src="{{ url_for('static', filename='js/console.js') }}"></script>
```

Status indicator dot: orange=connecting, green=connected, red=disconnected.
Disconnect overlay shown on connection loss (dark semi-transparent, message + links).

---

## console.js (ES Module)

```javascript
import RFB from '/static/novnc/core/rfb.js';

document.addEventListener('DOMContentLoaded', () => {
    const { wsHost, wsPort, password, vmName } = window.VNC_CONFIG;
    const wsUrl = `ws://${wsHost}:${wsPort}`;

    const rfb = new RFB(
        document.getElementById('vnc-container'),
        wsUrl,
        { credentials: { password }, shared: true }
    );

    rfb.scaleViewport = true;
    rfb.resizeSession = false;
    rfb.clipViewport = false;

    rfb.addEventListener('connect', () => { /* green dot, hide overlay */ });
    rfb.addEventListener('disconnect', (e) => { /* red dot, show overlay */ });
    rfb.addEventListener('credentialsrequired', () => {
        rfb.sendCredentials({ password });
    });
});
```

**Key change from original**: `wsHost` is now the Flask server hostname (since the browser connects to the SSH tunnel local port on the Flask server), not `localhost`.

---

## VncManager (Agent-side — `tart_agent/vnc_manager.py`)

The websockify manager that was removed from Flask now lives on each Mac node in the agent:

- Thread-safe `_proxies` dict keyed by `vm_name`
- `start_proxy(vm_name, vm_ip)` → allocate port in range 6900–6999, spawn websockify, return port
- Idempotent: if process alive for vm_name, return existing port
- `stop_proxy(vm_name)` → SIGTERM, wait 5s, SIGKILL if needed
- `cleanup_all()` → called on agent shutdown

---

## TunnelManager (Flask-side — `app/tunnel_manager.py`)

See Module 1 for full implementation details. Summary:

- `start_tunnel(vm_name, node, remote_port)` → allocates a free local port in `WEBSOCKIFY_PORT_MIN`–`WEBSOCKIFY_PORT_MAX`; opens SSH connection via paramiko; starts thread to forward connections
- `stop_tunnel(vm_name)` → signals stop event, closes SSH connection
- `cleanup_all()` → registered with `atexit`; closes all tunnels on Flask shutdown
- Thread-safe: `threading.Lock()` guards `_tunnels` dict

---

## Verification Checklist

- [x] `app/static/novnc/core/rfb.js` exists (setup_novnc.sh ran successfully)
- [x] Navigate to `/console/<vm_name>` when not logged in → redirect to `/auth/login`
- [x] Navigate to `/console/<vm_name>` when VM is `archived` → flash warning, redirect to vm_detail
- [x] `current_app.tunnel_manager` exists and is wired
- [x] Disconnect route stops tunnel and calls agent stop_vnc
- [x] Flask shutdown → atexit cleanup_all() fires (tunnel sockets closed)
- [ ] Live test: console page loads for a running VM (noVNC top bar visible)
- [ ] Live test: status dot turns green → noVNC connected to VM
- [ ] Live test: VM display is visible in browser
- [ ] Live test: keyboard and mouse work inside VM
- [ ] Live test: `ps aux | grep websockify` on Mac node shows process running
- [ ] Live test: click "Disconnect" → websockify process gone from Mac node

---

## Common Pitfalls

| Problem | Cause | Fix |
|---------|-------|-----|
| "VM is not running" flash | VM status in DB not `running` | Verify VM was created and started successfully |
| SSH tunnel fails to open | SSH key not accessible or wrong path | Check `node.ssh_key_path` in DB; verify key works: `ssh -i <key> <user>@<host>` |
| noVNC "Connection failed" | Tunnel opened but websockify not started on agent | Check agent `/vnc/<name>/start` response; check `ps aux | grep websockify` on node |
| Black screen / no connection | Wrong VNC password or VM not fully booted | Check `VNC_DEFAULT_PASSWORD` env var; wait for VM to fully boot |
| Port not freed after disconnect | Tunnel stop event not fired | Disconnect route calls `stop_tunnel()`; if skipped (browser closed), tunnel leaks until Flask restart |
| noVNC import fails | `rfb.js` not found | Verify setup_novnc.sh ran; check `app/static/novnc/core/rfb.js` exists |
| WebSocket uses wrong host | `ws_host` still set to `localhost` | Must use Flask server hostname, not `localhost`, since browser connects remotely |
