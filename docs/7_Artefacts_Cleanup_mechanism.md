# 7. Artefacts Cleanup Mechanism

> **Status**: Code implementation complete; live E2E validation pending  
> **Goal**: Ensure VM artefacts are cleaned consistently on nodes and in Docker registry after successful lifecycle operations.

---

## Functional Scope

### 1) Node cleanup (local Tart VM artefacts on nodes)

Cleanup is required after **successful**:

- VM deletion
- VM migration
- VM archiving (save)

### 2) Docker registry cleanup (OCI artefacts)

Cleanup is required after **successful**:

- pull
- migration
- resume
- re-pull

---

## Current Problem

- UI state and local node state can be cleaned, but registry artefacts may remain.
- Repeated retries/migrations can accumulate stale registry blobs/tags.
- Failure recovery paths can leave mixed state (node + registry + DB not aligned).

Related operational finding already addressed in node agent:

- Re-pull lock contention was caused by orphaned `tart pull` processes holding Tart locks.
- Node agent now logs active Tart processes on lock waits and terminates stale matching pulls before new pull attempts.
- This is complementary to this plan: it addresses pull execution stability, while this document focuses on post-success artefact cleanup guarantees.

---

## Design Principles

- **Success-gated cleanup**: cleanup runs only after operation is confirmed successful.
- **Idempotent operations**: repeated cleanup calls must be safe.
- **Digest-first registry delete**: resolve tag -> digest -> delete manifest by digest.
- **Observability**: expose cleanup stage, result, and error details in logs/op status.
- **Non-blocking UX**: cleanup can run async after success state transition, but must be tracked.
- **No data loss on ambiguous state**: if verification fails, keep artefact and report warning.

---

## Lifecycle Matrix

| Operation | Node cleanup | Registry cleanup |
|---|---|---|
| Delete VM (success) | Remove local VM from node | Delete `<registry_tag>` if present |
| Archive VM (success push) | Local VM removed (already in save flow) | Keep tag (archive is persistence target) |
| Resume VM (success) | No extra node cleanup beyond normal run prep | Delete source archived tag after VM starts successfully |
| Re-pull VM (success) | Replace/refresh local VM as needed | Delete source archived tag after VM starts successfully |
| Migration (success) | Remove source local VM after push/restore success | Delete migration transfer tag after target starts successfully |

> Note: Archive keeps registry artefact intentionally (it is the saved state).  
> Pull/resume/re-pull/migration success should consume and then clean transfer artefact.

---

## Proposed Architecture Changes

### A) Registry cleanup service (manager-side)

Create a dedicated service (e.g. `app/registry_cleanup.py`) with:

- `resolve_manifest_digest(registry_tag)`:
  - `HEAD/GET /v2/<repo>/manifests/<tag>`
  - read `Docker-Content-Digest`
- `delete_manifest(registry_repo, digest)`:
  - `DELETE /v2/<repo>/manifests/<digest>`
- `cleanup_tag(registry_tag)`:
  - parse/normalize tag, resolve digest, delete manifest
  - return structured result `{ok, digest, status_code, error}`

Requirements:

- support local insecure registry
- configurable timeout + retries
- auth-ready design (future)

### B) Async cleanup orchestration

Add a lightweight cleanup task runner:

- trigger cleanup from operation completion points in manager API flow
- persist cleanup result in DB fields (or structured status detail)
- include correlation IDs in logs for VM + operation + cleanup step

### C) Completion hooks in state machine

Add explicit post-success hooks:

- `resume/re-pull -> running` => queue registry cleanup
- `migration -> target running` => queue registry cleanup of transfer tag
- `delete -> db row removal` => queue registry cleanup first when tag exists

---

## Data Model Additions (minimal)

Add optional VM fields (or equivalent event log table):

- `cleanup_status` (`pending|done|warning|failed`)
- `cleanup_last_error`
- `cleanup_last_run_at`
- `cleanup_target_digest`

These fields are operational metadata only.

---

## API/UX Notes

- VM details page can show a small cleanup badge after successful resume/migration/delete.
- Admin Dashboard may include a cleanup warning indicator for rows with `cleanup_status=failed`.
- Keep user-facing messaging simple: “VM resumed. Registry artefact cleanup scheduled.”

---

## Failure Handling Rules

- If registry delete fails:
  - do **not** rollback successful VM operation
  - mark cleanup as warning/failed
  - allow manual retry from admin tooling
- Runtime prerequisite: Docker registry must run with delete enabled
  (`REGISTRY_STORAGE_DELETE_ENABLED=true`) and a stable persistent mount
  (`/Users/Shared/tart-registry`) for consistent artefact visibility.
- If digest resolution fails due to missing tag:
  - treat as idempotent success (already cleaned)
- If network to registry fails:
  - retry with backoff; then surface operational warning

---

## Rollout Plan

### Phase 1 — Registry cleanup service

- Implement tag parse + digest resolve + manifest delete module
- Unit tests with mocked registry responses

### Phase 2 — Integrate into operation success hooks

- Wire cleanup calls into:
  - resume success
  - re-pull success
  - migration success
  - delete success

### Phase 3 — Tracking + visibility

- Add cleanup status metadata
- Show operational warnings in admin view

### Phase 4 — Safe retry + manual controls

- Admin action: “Retry cleanup” for failed cleanup records

---

## Implementation Checklist

Use this checklist as the execution plan for implementation PRs.

### A. Manager: Registry cleanup service

- [x] Create `app/registry_cleanup.py`
- [x] Implement `parse_registry_tag(registry_tag)` -> `host`, `repo`, `tag`
- [x] Implement `resolve_manifest_digest(registry_tag)` using `HEAD/GET /v2/<repo>/manifests/<tag>`
- [x] Implement `delete_manifest(host, repo, digest)` using `DELETE /v2/<repo>/manifests/<digest>`
- [x] Implement `cleanup_tag(registry_tag)` with structured result `{ok, digest, status_code, error}`
- [x] Add retry/backoff policy and request timeouts
- [x] Add idempotent handling for missing tags/manifests
- [x] Add unit tests for parser + digest resolution + delete responses

### B. Manager: Hook cleanup into VM state transitions

- [x] `app/api/routes.py`: after `pulling -> running` (resume/re-pull), schedule `cleanup_tag(vm.registry_tag)`
- [x] `app/api/routes.py`: after migration target `running`, schedule cleanup of migration transfer tag
- [x] `app/main/routes.py`: on successful delete of archived VM, invoke cleanup before DB row removal (or mark deferred cleanup if async)
- [x] Ensure cleanup failure does not rollback successful VM start/migration/delete
- [x] Add structured log entries with VM name, operation type, registry tag, digest, cleanup result

### C. Manager: Data model and visibility

- [x] Add DB fields (or equivalent table): `cleanup_status`, `cleanup_last_error`, `cleanup_last_run_at`, `cleanup_target_digest`
- [x] Update migration files for schema changes
- [x] Update admin dashboard to show cleanup warning/failure indicators
- [x] Add optional VM detail message: “Registry artefact cleanup scheduled/completed/failed”

### D. Manager: Admin controls

- [x] Add admin endpoint for manual cleanup retry (e.g. `POST /admin/vms/<id>/cleanup-retry`)
- [x] Add admin button/action in dashboard row for failed cleanup retries
- [x] Add server-side guardrails to avoid duplicate concurrent retries

### E. Node cleanup verification (safety checks)

- [ ] Verify `save` success path removes local VM on source node
- [ ] Verify migration success path removes local VM on source node after target starts
- [ ] Verify delete success path leaves no local VM on assigned node
- [x] Add explicit post-action verification logs (`vm_exists=false`) for node cleanup confirmations

### F. End-to-end test checklist

- [ ] Archive VM -> confirm local node cleanup + archived tag remains in registry
- [ ] Resume VM -> confirm VM running + source archived tag removed
- [ ] Re-pull from failed -> confirm VM running + source archived tag removed
- [ ] Migration success -> confirm source local VM removed + transfer tag removed
- [ ] Delete archived VM -> confirm DB row removed + registry manifest deleted
- [ ] Registry unavailable during cleanup -> operation still succeeds, cleanup marked warning/failed
- [ ] Manual retry -> cleanup status transitions to done after registry recovers

### G. Documentation updates

- [x] Update `README.md` with cleanup behavior and guarantees
- [x] Add troubleshooting section for cleanup failures and retry workflow
- [x] Document registry GC expectations (manifest delete vs blob compaction timing)

---

## Acceptance Criteria

1. After successful **delete** of archived VM, DB row is removed **and** registry manifest for tag is deleted.
2. After successful **resume/re-pull**, VM is `running` and source archived tag is deleted from registry.
3. After successful **migration**, target VM is `running`, source transfer artefact is deleted from registry, and source node no longer has local VM.
4. Cleanup operations are idempotent and safe on retries.
5. Failures in cleanup are visible in logs and admin operational views.

---

## Test Plan (high level)

- Unit:
  - tag parser normalization
  - digest resolution success/fail
  - delete by digest success/404/500
- Integration:
  - archive -> resume -> verify registry artefact removed
  - failed re-pull then successful re-pull -> verify cleanup
  - migration success -> verify source node + registry cleanup
- Operational:
  - simulate registry outage during cleanup -> verify warning status + retry path

