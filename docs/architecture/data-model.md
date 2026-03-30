# Data Model

Source: `app/models.py`

## User

Fields include:

- identity: `username`, `email`, `password_hash`
- access: `is_admin`
- quotas: `max_active_vms`, `max_saved_vms`, `disk_quota_gb`
- invite lifecycle: `must_set_password`, `invite_token`, `invited_at`, `last_login_at`

## RegistrationRequest

Holds pending self-service sign-up requests submitted from the login page, awaiting admin approval or denial.

Fields:

- `full_name` — submitted by the requester
- `email` — unique; blocked if an account or pending request already exists for this email
- `requested_at` — timestamp of submission

On **Approve**: a `User` record is created from this request and the `RegistrationRequest` row is deleted.
On **Deny**: the row is deleted with no further action.

## Node

Fields include:

- `name`, `host`, `agent_port`
- SSH metadata: `ssh_user`, `ssh_key_path`
- capacity and state: `max_vms`, `active`

## VM

Fields include:

- ownership and placement: `user_id`, `node_id`
- lifecycle: `status`, `status_detail`
- image/compute: `base_image`, `cpu`, `memory_mb`, `disk_size_gb`
- registry: `registry_tag`
- cleanup metadata: `cleanup_status`, `cleanup_last_error`, `cleanup_last_run_at`, `cleanup_target_digest`

## AppSettings

Stores runtime SMTP configuration used by Admin → Settings UI.

Fields include:

- `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`
- `smtp_from`, `smtp_use_tls`, `smtp_use_ssl`

The SMTP password is stored in plaintext in this table (same threat model as `.env`). Leave the password field blank when saving settings to retain the existing value.

## GoldImage

Admin-captured reusable base images. Fields include:

- `name` (unique), `registry_tag` (e.g. `gold-images/<name>:latest`)
- `base_image`, `disk_size_gb`, `description`, `source_vm_name`
- `created_at`, `updated_at`, `created_by_id` (FK users)

## GoldImageNode

Per-node distribution status for each gold image. Fields include:

- `gold_image_id`, `node_id`
- `status`: `pending`, `pulling`, `ready`, `failed`
- `status_detail`, `op_key`, `started_at`, `completed_at`

Unique constraint on `(gold_image_id, node_id)`. Cascade delete from GoldImage.

## VM Status Vocabulary

- `creating`, `running`, `stopped`
- `pushing`, `archived`, `pulling`
- `failed`

Status transitions are enforced through route logic in `app/main/routes.py` and async polling in `app/api/routes.py`.

## Usage Telemetry Tables

`vm_status_events`
- immutable VM status transitions (`from_status`, `to_status`, `changed_at`, `source`, `context`)
- indexed by VM/user and time for interval reconstruction

`vm_vnc_sessions`
- websocket VNC session intervals (`connected_at`, `disconnected_at`, `disconnect_reason`, `session_token`)
- open sessions are treated as active until `now` by usage aggregation

## Runtime-Only VNC Proxy State

Direct native `.vncloc` proxy mappings are intentionally not persisted in SQL tables.
They are maintained in memory by `DirectTcpProxyManager` (`app/direct_tcp_proxy.py`) and cleared on stop/delete/disconnect and process shutdown.
