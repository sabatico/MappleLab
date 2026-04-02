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

- `app/main/` end-user VM routes — also exports shared helpers used by `app/admin/`
- `app/api/` polling and operation endpoints
- `app/console/` VNC console routes + WebSocket bridge
- `app/auth/` login/invite password setup
- `app/admin/` user and operations administration — imports shared helpers from `app/main/routes`
- `app/nodes/` node management and deactivation workflow

### Shared helpers in `app/main/routes.py`

`app/admin/routes.py` imports several helpers from `app/main/routes` to avoid duplication:

| Helper | Purpose |
|--------|---------|
| `do_repull_vm(vm)` | Shared repull logic for both user and admin routes. Selects pull source: `base_image` for never-saved VMs, `registry_tag` for previously saved ones. Calls `restore_vm` on the agent and sets status to `pulling`. Returns `(pull_tag, error_message)`. |
| `_sanitize_registry_tag(tag)` | Normalises OCI registry tag strings |
| `_check_registry_space_for_save(vm)` | Validates available registry capacity before a save |
| `_agent_vm_name(vm)` | Resolves the VM name used on the agent side |
| `_agent_vm_size_on_disk_gb(vm, node)` | Queries agent for current disk usage |
| `_verify_vm_absent_on_node(vm, node)` | Confirms a VM slot is free before restore |
| `_registry_authority_from_config()` | Returns the registry host:port from config |

## Core Services

- `app/tart_client.py` node-agent API integration
- `app/node_manager.py` scheduling utilities
- `app/tunnel_manager.py` SSH tunnel management
- `app/direct_tcp_proxy.py` raw TCP manager-side proxy for native `.vncloc` sessions
- `app/usage_events.py` VM status/VNC session telemetry helpers
- `app/admin/usage_metrics.py` admin usage aggregation for segmented lifetime analytics
- `app/registry_inventory.py` registry cataloging
- `app/registry_cleanup.py` cleanup helpers
- `app/gold_distribution.py` gold image distribution to nodes

## Templates

- `app/templates/main/`
- `app/templates/admin/` (includes `_partials/` for gold image distribution)
- `app/templates/auth/`
- `app/templates/console/`
- `app/templates/nodes/`
- `app/templates/_partials/`
