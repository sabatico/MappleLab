# Changelog

All notable changes to this project should be documented in this file.

## [Unreleased]

- Documentation refurbishment: migrated legacy markdown to `docs/drafts/`
- Introduced audience-based docs structure:
  - `getting-started`
  - `administration`
  - `user-guide`
  - `architecture`
  - `development`
- Added consolidated `docs/troubleshooting.md`
- Added direct TCP native VNC download flow:
  - new `GET /console/<vm_name>/vncloc` route
  - in-memory `DirectTcpProxyManager` on manager (`VNC_DIRECT_PORT_MIN/MAX`)
  - VM detail button for running VMs: **Download .vncloc**
  - proxy cleanup now runs on disconnect/stop/delete and at app shutdown
- Added admin usage analytics:
  - new `vm_status_events` and `vm_vnc_sessions` telemetry tables
  - `app/usage_events.py` transition/session helpers with baseline backfill
  - `GET /admin/usage` segmented VM lifetime view grouped by user
  - warning thresholds for long running and long VNC-active time
