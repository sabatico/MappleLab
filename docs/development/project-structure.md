# Project Structure

## Top-Level

- `app/` Flask application package
- `scripts/` deployment/setup helpers
- `tests/` test suite
- `config.py` configuration classes
- `run.py` application entry point
- `run.sh` runtime wrapper (dev/prod)
- `deploy.sh` update helper

## App Package

- `app/main/` end-user VM routes
- `app/api/` polling and operation endpoints
- `app/console/` VNC console routes + WebSocket bridge
- `app/auth/` login/invite password setup
- `app/admin/` user and operations administration
- `app/nodes/` node management and deactivation workflow

## Core Services

- `app/tart_client.py` node-agent API integration
- `app/node_manager.py` scheduling utilities
- `app/tunnel_manager.py` SSH tunnel management
- `app/direct_tcp_proxy.py` raw TCP manager-side proxy for native `.vncloc` sessions
- `app/usage_events.py` VM status/VNC session telemetry helpers
- `app/admin/usage_metrics.py` admin usage aggregation for segmented lifetime analytics
- `app/registry_inventory.py` registry cataloging
- `app/registry_cleanup.py` cleanup helpers

## Templates

- `app/templates/main/`
- `app/templates/admin/`
- `app/templates/auth/`
- `app/templates/console/`
- `app/templates/nodes/`
- `app/templates/_partials/`
