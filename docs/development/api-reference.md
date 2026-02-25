# API and Route Reference

This file lists Flask routes by blueprint.

## Main (`app/main/routes.py`)

- `GET /` dashboard
- `GET|POST /vms/create`
- `GET /vms/<vm_name>`
- `POST /vms/<vm_name>/save`
- `POST /vms/<vm_name>/migrate`
- `POST /vms/<vm_name>/resume`
- `POST /vms/<vm_name>/repull`
- `POST /vms/<vm_name>/start`
- `POST /vms/<vm_name>/stop`
- `POST /vms/<vm_name>/delete`

## API (`app/api/routes.py`)

- `GET /api/vms`
- `GET /api/vms/<vm_name>/status`
- `GET /api/vms/<vm_name>/operation`
- `GET /api/gold-images/<gold_id>/distribution` (admin, HTMX partial for node distribution status)

## Console (`app/console/routes.py`)

- `GET /console/<vm_name>`
- `GET /console/<vm_name>/vncloc`
- `POST /console/<vm_name>/disconnect`
- `WS /console/ws/<vm_name>`

## Auth (`app/auth/routes.py`)

- `GET|POST /auth/login`
- `GET /auth/logout`
- `GET|POST /auth/register` (invitation-only redirect)
- `GET|POST /auth/set-password/<token>`

## Admin (`app/admin/routes.py`)

- `GET /admin/users`
- `GET /admin/overview`
- `GET /admin/gold-images`
- `POST /admin/gold-images/<id>/redistribute`
- `POST /admin/gold-images/<id>/delete`
- `GET /admin/registry-storage`
- `POST /admin/registry-storage/orphans/delete`
- `POST /admin/users/create`
- `GET|POST /admin/users/<id>/edit`
- `POST /admin/users/<id>/resend-invite`
- `POST /admin/users/<id>/delete`
- `GET|POST /admin/settings`
- `POST /admin/settings/test-email`
- `GET /admin/usage`
- VM actions under `/admin/vms/<id>/*`:
  - `start`, `stop`, `archive`, `make-gold`, `resume`, `repull`, `delete`, `cleanup-retry`

## Nodes (`app/nodes/routes.py`)

- `GET /nodes/`
- `GET|POST /nodes/add`
- `POST /nodes/<id>/toggle`
- `POST /nodes/<id>/deactivate/start`
- `GET /nodes/<id>/deactivate/status/<op_id>`
- `POST /nodes/<id>/delete`
- `GET /nodes/<id>/health`
