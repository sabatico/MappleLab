# VM Lifecycle

This page explains the end-user lifecycle.

## State Flow

```text
creating -> running -> stopped -> pushing -> archived -> pulling -> running
                                 \-> failed
```

## Create VM

- Open **Create VM**
- Select base image
- Set optional CPU/memory
- Submit and wait for `running`

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

- `failed` state may expose **Re-pull** for restore failures
- Review operation panel details before retry

## Usage Telemetry Note

Lifecycle transitions are recorded in `vm_status_events` and feed admin Usage lifetime bars.
