# Registry and Cleanup

Orchard UI uses a Docker registry as persistence for VM save/resume and migration workflows.

## Lifecycle Pattern

- Save/archive: node pushes VM artefact to registry
- Resume: node restores from registry artefact
- Migration: save on source, restore on target

## Cleanup Strategy

Cleanup is best-effort and idempotent.

Automatic cleanup is triggered after successful restore/delete milestones. Failures are recorded without rolling back successful lifecycle outcomes.
VNC transport cleanup is handled separately: direct TCP proxies for `.vncloc` sessions are stopped on disconnect/stop/delete and on manager shutdown.
Usage telemetry capture is also separate: VM/VNC time events are retained for analytics and are not registry artefacts.

## Metadata Tracking

Each VM stores cleanup metadata:

- status
- last error
- last run timestamp
- target digest

## Admin Controls

- Registry Storage page shows trackable vs orphaned objects
- Admin can manually delete orphaned digests
- Retry cleanup action is available from admin operations views
