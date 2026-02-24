# Installation

This guide installs MAppleLab on the manager Mac.  
Complete [Prerequisites](prerequisites.md) first.

---

## 1. Clone the Repository

Open Terminal on the manager Mac and run:

```bash
cd /Users/Shared
git clone https://github.com/sabatico/orchard_ui.git TART_Manager
cd TART_Manager
```

> **Note:** `/Users/Shared` is the recommended install location because it survives user account changes and is accessible to background services. You can use any path you prefer.

---

## 2. Create the Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

When `pip install` finishes you should see a line like `Successfully installed Flask-...`. No red errors should appear.

---

## 3. Download noVNC (browser VNC client)

```bash
bash scripts/setup_novnc.sh
```

This downloads the noVNC JavaScript library into `app/static/novnc/`. It only needs to run once.

---

## 4. Create and Edit Your Environment File

Copy the example configuration file:

```bash
cp .env.example .env
```

Open it in a text editor:

```bash
nano .env
```

The file will look like this. Change the values highlighted below:

```bash
FLASK_ENV=production

# -------------------------------------------------------
# REQUIRED — change all three of these before first run
# -------------------------------------------------------

# Random string used to sign login sessions.
# Generate one with: openssl rand -hex 32
SECRET_KEY=change-me

# Shared password used between the manager and every node agent.
# Use the same value you will set on each node.
# Generate one with: openssl rand -hex 24
AGENT_TOKEN=change-me

# Address of the Docker registry running on this manager Mac.
# Replace 192.168.1.195 with the actual IP of the manager Mac.
# Do NOT use localhost — nodes need to reach this address too.
REGISTRY_URL=http://192.168.1.195:5001/v2/

# -------------------------------------------------------
# OPTIONAL — adjust if needed
# -------------------------------------------------------

# Total registry disk capacity shown in the Admin storage page.
# Set this to the actual GB available in /Users/Shared/tart-registry.
# REGISTRY_STORAGE_TOTAL_GB=600

# VNC credentials (Cirrus Labs base images default to admin/admin).
VNC_DEFAULT_USERNAME=admin
VNC_DEFAULT_PASSWORD=admin

# Native `.vncloc` direct TCP proxy range on manager.
VNC_DIRECT_PORT_MIN=57000
VNC_DIRECT_PORT_MAX=57099

# Production proxy settings — keep these as-is when using Caddy/nginx.
TRUST_PROXY=true
FORCE_HTTPS=true
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Lax
```

Save with **Control + O**, press Enter, then **Control + X** to exit.

---

## 5. Set Up the Docker Registry

The registry stores saved VM disk images.

```bash
bash scripts/setup_registry.sh
```

Verify it is running:

```bash
curl http://localhost:5001/v2/
```

Expected output: `{}`. If you get a connection error, wait a few seconds and try again — the container may still be starting.

---

## 6. Optional: TLS for Production (Caddy) or Development (Self-Signed)

**For production:** Use Caddy as a reverse proxy for HTTPS. A sample Caddyfile is in `config/Caddyfile.example` (internal IP `192.168.1.195`, external `108.194.55.108` — replace with your addresses). Full setup: [Reverse Proxy](../administration/reverse-proxy.md).

**For local development only:** Use a self-signed certificate. Skip if using Caddy:

```bash
bash scripts/generate_cert.sh
echo "SSL_CERT=cert.pem" >> .env
echo "SSL_KEY=key.pem" >> .env
```

---

## 7. First Run

```bash
./run.sh
```

You will see log output in the terminal. Look for a line like:

```
Serving on https://0.0.0.0:5000
```

or

```
Serving on http://0.0.0.0:5000
```

---

## 8. Verify in Browser

Open a browser on the same Mac and go to:

```
http://localhost:5000
```

or `https://localhost:5000` if TLS is configured.

You should see the MAppleLab login page.

If you see a certificate warning when using the self-signed cert, click **Advanced → Proceed** (this is expected for self-signed certs).

---

## 9. Next Step

Continue to [Quick Start](quick-start.md) to create your first admin account and VM.

> **Note:** The `.vncloc` download feature currently includes configured VNC defaults in the generated `vnc://` URL when username/password are set.
>
> **Note:** Admin Usage analytics (`/admin/usage`) are available after VM lifecycle and console telemetry is generated.
