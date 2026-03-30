# Configuration Reference

Source: `config.py`, `.env.example`

## Core

- `SECRET_KEY`: Flask secret
- `DATABASE_URL`: SQLAlchemy DB URI
- `AGENT_TOKEN`: shared manager-agent auth token

## Registry

- `REGISTRY_URL`: registry endpoint
- `REGISTRY_STORAGE_TOTAL_GB`: capacity used for UI storage graph

## Mail

- `MAIL_SERVER`
- `MAIL_PORT`
- `MAIL_USE_TLS`
- `MAIL_USE_SSL`
- `MAIL_USERNAME`
- `MAIL_PASSWORD`
- `MAIL_DEFAULT_SENDER`

> **Note:** SMTP settings (host, port, username, password, from address, security mode) can be configured and saved persistently via **Admin → Settings** in the UI. The password entered in the UI is stored in the `app_settings` database table. `MAIL_PASSWORD` in the environment is an alternative for deployments that prefer secrets outside the database; if both are set, the database value takes precedence (it is applied at send time via `_apply_mail_config`).

## VNC and Console

- `VNC_DEFAULT_USERNAME`
- `VNC_DEFAULT_PASSWORD`
- `VNC_USE_SSH_TUNNEL`
- `VNC_BROWSER_DIRECT_NODE_WS`
- `VNC_BROWSER_DIRECT_NODE_WS_SCHEME`
- `WEBSOCKIFY_PORT_MIN`
- `WEBSOCKIFY_PORT_MAX`
- `VNC_DIRECT_PORT_MIN` (default `57000`)
- `VNC_DIRECT_PORT_MAX` (default `57099`)
- `VNC_DIRECT_HOST` — override host in `.vncloc` when set (e.g. manager LAN IP if client uses external hostname)

## HTTPS and Proxy

- `SSL_CERT`
- `SSL_KEY`
- `TRUST_PROXY`
- `FORCE_HTTPS`
- `SESSION_COOKIE_SECURE`
- `SESSION_COOKIE_HTTPONLY`
- `SESSION_COOKIE_SAMESITE`

## UI Behavior

- `VM_POLL_INTERVAL_MS`
- `TART_IMAGES`

> **Note:** `.vncloc` generation currently embeds `VNC_DEFAULT_USERNAME`/`VNC_DEFAULT_PASSWORD` in the generated `vnc://` URL when those values are set.

> **Note:** Admin usage warning thresholds are currently hard-coded in `app/admin/usage_metrics.py` (`8h` running-without-VNC and `4h` VNC-active).
