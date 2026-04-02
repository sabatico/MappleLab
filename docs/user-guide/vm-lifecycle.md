# VM Lifecycle

This page explains the end-user lifecycle.

## State Flow

```text
creating -> running -> stopped -> pushing -> archived -> pulling -> running
                                 \-> failed
```

## Create VM

- Open **Create VM**
- Select base image (Gold Images or Base Images optgroup)
- Set optional CPU/memory
- Submit and wait for `running`

## Gold Images (Admin)

Admins can capture a running or stopped VM as a **Gold Image** — a reusable base image stored in `gold-images/<name>:latest`. The VM is stopped, pushed to the registry, and archived. The image is distributed to all nodes for fast VM creation. Gold images appear in the Create VM dropdown under "Gold Images".

## Start and Stop

- `stopped -> running`: Start
- `running -> stopped`: Stop
- Stop also tears down active browser tunnel and native `.vncloc` direct proxy mapping for that VM

## Save and Shutdown

- Use Save/Archive action
- VM transitions to `pushing`
- On success becomes `archived`

## Resume

- Resume pulls artefact to an available node
- `archived -> pulling -> running`

## Migrate

- Save from source node
- Restore to selected target node
- Source VM state is cleaned up

## Delete

- VM is stopped/cleaned on node
- Registry cleanup is attempted
- VM record removed from dashboard
- Active direct TCP proxy mapping is closed before deletion

## Failure Recovery

- `failed` state exposes **Re-pull** for restore/pull failures
- Re-pull behaviour depends on whether the VM has ever been saved:
  - **Never saved** (`last_saved_at` is empty): re-pulls from the VM's `base_image` (the gold image it was created from, already cached on nodes)
  - **Previously saved**: re-pulls from `registry_tag` (the last snapshot pushed to the registry)
- Both user and admin Re-pull use the same shared logic (`do_repull_vm` helper in `app/main/routes.py`)
- Review the operation panel status detail before retrying

## Usage Telemetry Note

Lifecycle transitions are recorded in `vm_status_events` and feed admin Usage lifetime bars.
