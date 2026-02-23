# VNC Architecture

Source references: `app/console/routes.py`, `config.py`, legacy notes in `docs/drafts/`.

## Modes

1. Manager relay mode (default)
   - Browser -> `/console/ws/<vm>` on manager
   - Manager bridge -> node websockify

2. SSH tunnel mode
   - Browser -> manager WebSocket bridge
   - Manager bridge -> local SSH tunnel -> node websockify

3. Browser-direct mode
   - Browser connects directly to node websockify endpoint
   - Bypasses manager WebSocket relay

4. Native macOS `.vncloc` mode
   - User downloads `GET /console/<vm_name>/vncloc`
   - Manager starts/reuses direct TCP proxy listener (`VNC_DIRECT_PORT_MIN/MAX`)
   - Apple Screen Sharing connects raw TCP to manager, then manager forwards to VM IP + VNC port

## Security Constraints

- Remote sessions must use HTTPS/WSS
- Apple ARD auth path needs secure browser context
- Mixed HTTP/HTTPS WS topology can break auth and connect flow

## Usage Instrumentation

- Browser console websocket open records `start_vnc_session(...)`; bridge close records `close_vnc_session(...)`.
- Direct TCP (`.vncloc`) client connect records `start_vnc_session(...)`; bridge close records `close_vnc_session(...)`.
- Both paths write to `vm_vnc_sessions` and feed admin usage segmentation for `running + VNC` intervals.

## Route Flow

1. `GET /console/<vm_name>` validates VM state and ownership
2. Agent starts or confirms node websockify endpoint
3. Manager chooses direct, relay, or SSH tunnel path
4. Browser establishes noVNC session
5. `POST /console/<vm_name>/disconnect` tears down bridge/tunnel state
6. Stop/delete paths also stop direct TCP proxies for that VM
