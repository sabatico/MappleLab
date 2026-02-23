# Dashboard Guide

## Main Views

- **My VMs**: personal VM list and actions
- **Dashboard (admin)**: cross-user operational view
- **Usage (admin)**: cross-user VM/VNC lifetime analytics

## VM Status Values

- `creating`
- `running`
- `stopped`
- `pushing`
- `archived`
- `pulling`
- `failed`

## Auto Refresh

Dashboard tables poll VM status periodically (default `VM_POLL_INTERVAL_MS=5000`).

## Row Actions (Status-Aware)

Depending on state, available actions include:

- Start
- Stop
- Save/Archive
- Resume
- Re-pull
- Delete
- Open Console (browser noVNC)
- Download `.vncloc` (running VMs, native macOS path)

## Quotas

For non-admin users, action availability also depends on configured quotas:

- Active VM count
- Saved/inactive VM count
- Saved disk size
