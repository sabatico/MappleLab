# VNC Console Guide

Use either the browser console or native macOS Screen Sharing to access running VMs.

## Open Console

1. Start VM
2. Open VM details
3. Click **Open Console** for browser noVNC

## Download `.vncloc` (macOS Native)

1. Keep VM in `running` state
2. Open VM details
3. Click **Download .vncloc**
4. Open the downloaded file with Screen Sharing

The download route is `GET /console/<vm_name>/vncloc` and is protected by login + ownership checks.

## Transport Modes

- Manager relay (default LAN)
- SSH tunnel mode (`VNC_USE_SSH_TUNNEL=true`)
- Browser-direct mode (`VNC_BROWSER_DIRECT_NODE_WS=true`)

## Remote Access Requirement

Use `https://` for remote browser sessions.

Apple ARD auth (`RFB 003.889`) requires browser crypto APIs available only in secure context.

## Console Controls

- Disconnect action
- Bandwidth/render profile switching (where available)
- Session recovers by reopening console route

## Common Issues

- VM not running: console route blocks with warning
- No reachable VNC endpoint: restart VM and retry
- Mixed-content errors: use HTTPS and valid WSS path
- Native `.vncloc` timeout: ensure manager direct TCP range (`57000-57099` default) is reachable

## Security Note

Current implementation includes configured VNC defaults in the generated `vnc://` URL when `VNC_DEFAULT_USERNAME` or `VNC_DEFAULT_PASSWORD` is set.

## Usage Telemetry Note

Both browser websocket (noVNC) and native `.vncloc` direct TCP sessions are recorded for admin usage analytics (`vm_vnc_sessions`). The Admin Usage tab shows "VNC active" time for both connection types.
