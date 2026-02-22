# Module 3: Console and VNC

> Status: Complete and actively tuned.

This document reflects the current VNC implementation used by Orchard UI and the related tuning controls.

## Current VNC modes

Orchard UI supports three transport modes:

1. Manager relay (default LAN mode):
   - Browser -> manager `/console/ws/<vm>` (WSS)
   - Manager WS bridge -> node websockify (WS)
2. SSH tunnel mode:
   - Browser -> manager `/console/ws/<vm>` (WSS)
   - Manager WS bridge -> SSH tunnel -> node websockify
3. Browser-direct mode (optional):
   - Browser -> node websockify endpoint directly
   - Bypasses manager WS bridge

Important: browser-direct mode from an HTTPS page requires a TLS-capable node endpoint (`wss://...`).
Plain node `ws://<node>:6900` cannot be used directly from an HTTPS UI page.

## Route flow

Primary route: `GET /console/<vm_name>`

Flow:
1. Validate ownership and `running` VM status.
2. Ask agent to start VNC/websockify and return port.
3. Select transport:
   - `VNC_BROWSER_DIRECT_NODE_WS=true` -> pass direct node URL to client.
   - else `VNC_USE_SSH_TUNNEL=true` -> start SSH tunnel.
   - else -> manager relay without SSH tunnel.
4. Render `app/templates/console/vnc.html`.

WebSocket bridge route (manager relay modes):
- `GET /console/ws/<vm_name>`
- Forwards browser frames <-> backend websockify.
- Emits connect/first-frame/session summary timing logs.

Disconnect route:
- `POST /console/<vm_name>/disconnect`
- Stops tunnel/direct target state and asks agent to stop VNC proxy.

## Client behavior (`app/static/js/console.js`)

noVNC is initialized with:
- Apple ARD credentials (`username` + `password`)
- dynamic WS URL (manager relay or direct node URL)
- connect/disconnect timing logs in browser console

Live profile switch is available in the VNC toolbar:
- `Optimize Bandwidth` (default)
- `Optimize Render`

Profile choice is persisted in `localStorage` and restored on next console open.

## Performance settings

Bandwidth profile (default):
- `scaleViewport=true`
- `resizeSession=true`
- `clipViewport=true`
- `qualityLevel=1`
- `compressionLevel=9`

Render profile:
- `scaleViewport=true`
- `resizeSession=false`
- `clipViewport=false`
- `qualityLevel=2`
- `compressionLevel=6`

These are intentionally conservative defaults for smoother remote usage with acceptable visual quality.

## Useful diagnostics

Manager logs include:
- backend WS connect latency
- time to first frame in both directions
- total frames/bytes each direction
- backend timeout count
- full session duration summary

Normal browser close (`1001`) is handled as informational (not treated as a hard error).

## Related files

- `app/console/routes.py`
- `app/templates/console/vnc.html`
- `app/static/js/console.js`
- `app/tunnel_manager.py`
- `tart_agent/vnc_manager.py`

