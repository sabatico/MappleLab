# Registry and Cleanup

MAppleLab uses a Docker registry as persistence for VM save/resume and migration workflows.

## Lifecycle Pattern

- Save/archive: node pushes VM artefact to registry
- Resume: node restores from registry artefact
- Migration: save on source, restore on target
- Gold images: admin captures VM to `gold-images/<name>:latest`, distributed to all nodes for fast VM creation

## Save Safety Rule

The local VM state and data are deleted **only after** a full saving success:

1. Push to registry completes
2. Manifest is verified present in registry (HTTP 200 on `/v2/<repo>/manifests/<tag>`)
3. Then and only then: local VM is deleted

This applies to save/archive, migrate, and make-gold-image. Distribution (restore to target node, or gold image pull to nodes) happens after the source VM is safely in the registry. The tart agent verifies the manifest before delete; on verification failure, the local VM is kept and the operation reports error.

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
