# Architecture Overview

MAppleLab uses a manager-and-agents architecture for TART VM lifecycle control.

## System Diagram

```text
Browser
  -> Reverse Proxy (Caddy/nginx TLS)
  -> Flask UI (manager)
  -> TART Agent on node(s)
  -> TART VM runtime

Manager also uses:
  -> Local Docker Registry (save/resume artefacts)
  -> SQL database (users, nodes, VM state, settings)
```

## Core Components

- Flask app with modular blueprints (`main`, `api`, `console`, `auth`, `admin`, `nodes`)
- `TartClient` for node-agent HTTP API
- `NodeManager` for best-node selection
- `TunnelManager` for optional SSH VNC routing
- `DirectTcpProxyManager` for native `.vncloc` raw TCP proxy routing
- Usage telemetry pipeline (`VMStatusEvent`, `VMVncSession`, `usage_metrics`) for admin analytics
- Registry inventory/cleanup services for artefact management
- Gold image management — capture VMs as reusable base images, distribute to nodes, expose in Create VM dropdown

## Design Goals

- Multi-user isolation with quotas
- Portable VM lifecycle via registry persistence
- Operational safety through status reconciliation and cleanup metadata
- Secure browser VNC path under HTTPS
- Optional native macOS Screen Sharing path via manager direct TCP ports
- Cross-user observability via admin Usage page (lifetime composition per VM)
