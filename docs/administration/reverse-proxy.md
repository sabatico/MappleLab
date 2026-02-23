# Reverse Proxy and TLS

A reverse proxy (Caddy or nginx) provides HTTPS access to Orchard UI. **HTTPS is required for remote VNC console access** — Apple's VNC authentication uses browser cryptography APIs that only work on secure (`https://`) pages.

This guide covers **Caddy**, which is the simplest option for a private network or LAN setup. A ready-to-use example with internal (`192.168.1.195`) and external (`108.194.55.108`) hosts is in `config/Caddyfile.example`.

---

## Why a Reverse Proxy

- Provides a valid TLS certificate so browsers trust the connection
- Makes the VNC console work from any device on the network
- Keeps all traffic on a single address and port
- Handles WebSocket upgrades for the VNC bridge automatically

---

## Part 1: Caddy Setup (Recommended for LAN/VPN)

Caddy automatically generates and manages a local CA and certificate — no external domain or certificate purchase required.

### Step 1: Install Caddy

On the **manager Mac**:

```bash
brew install caddy
```

### Step 2: Find Your Caddyfile Location

Homebrew installs Caddy with a default config file. Find its path:

```bash
brew info caddy | grep Caddyfile
```

On Apple Silicon (M1/M2/M3) the path is usually:

```
/opt/homebrew/etc/Caddyfile
```

On Intel Macs:

```
/usr/local/etc/Caddyfile
```

### Step 3: Write the Caddyfile

Open the Caddyfile in a text editor:

```bash
nano /opt/homebrew/etc/Caddyfile
```

Replace all existing content with:

```caddy
192.168.1.195 {
    tls internal
    reverse_proxy 127.0.0.1:5000
}
```

Replace `192.168.1.195` with the **actual IP address of the manager Mac**.

**External access behind NAT:** If users connect from outside via port forwarding (e.g. `108.194.55.108:5443` → `192.168.1.195:443`), add the external host so Caddy matches the incoming `Host` header. Example with public IP `108.194.55.108`:

```caddy
192.168.1.195 {
    tls internal
    reverse_proxy 127.0.0.1:5000
}

108.194.55.108 {
    tls internal
    reverse_proxy 127.0.0.1:5000
}
```

A full example is in `config/Caddyfile.example`. Without the external block, Caddy serves a default empty site — TLS works but the page is blank.

Save with **Control + O**, Enter, then **Control + X**.

### Step 4: Validate and Start Caddy

Validate the config:

```bash
caddy validate --config /opt/homebrew/etc/Caddyfile
```

Expected output ends with `Valid configuration`. If you see errors, check the IP address is correct and there are no extra characters.

Start Caddy and set it to start automatically at login:

```bash
brew services start caddy
```

Verify it is running:

```bash
brew services list | grep caddy
```

Expected: `caddy started`.

### Step 5: Update Your .env for Production

Open `.env`:

```bash
nano /Users/Shared/TART_Manager/.env
```

Make sure these lines are set (and not commented out):

```bash
FLASK_ENV=production
TRUST_PROXY=true
FORCE_HTTPS=true
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Lax
```

Restart Orchard UI:

```bash
cd /Users/Shared/TART_Manager
./run.sh
```

### Step 6: Test Access

Open a browser on any Mac on the network and go to:

```
https://192.168.1.195
```

Replace the IP with your manager's address.

You will see a **certificate warning** the first time because the browser does not yet trust Caddy's local certificate authority. Complete Step 7 to fix this permanently.

### Step 7: Trust Caddy's Local CA on Client Macs

Do this once on each Mac that will access Orchard UI.

**Find the CA root certificate on the manager Mac:**

```bash
ls /opt/homebrew/var/lib/caddy/pki/authorities/local/
```

You should see `root.crt`.

**Copy it to the client Mac** (or open a Finder window on the client Mac and drag it from the manager's share):

From the client Mac's Terminal:

```bash
scp admin@192.168.1.195:/opt/homebrew/var/lib/caddy/pki/authorities/local/root.crt ~/Desktop/caddy-root.crt
```

**Import it into the macOS Keychain:**

1. Open **Keychain Access** on the client Mac (use Spotlight: `Cmd + Space`, type `Keychain Access`)
2. Drag `caddy-root.crt` from your Desktop into the **System** keychain (not Login)
3. Double-click the imported certificate (named something like `Caddy Local Authority`)
4. Expand **Trust**
5. Set **When using this certificate** to **Always Trust**
6. Close the dialog — enter your password when prompted

Close Keychain Access and restart the browser. The next time you visit `https://192.168.1.195` you should see the connection as trusted (padlock icon, no warning).

### Step 8: Reload Caddy After Config Changes

Any time you edit the Caddyfile:

```bash
caddy fmt --overwrite /opt/homebrew/etc/Caddyfile
caddy validate --config /opt/homebrew/etc/Caddyfile
brew services restart caddy
```

---

## Part 2: nginx (Advanced)

Use nginx if you already have it deployed or need more control.

### nginx Config

Create `/etc/nginx/sites-available/orchard-ui`:

```nginx
server {
    listen 443 ssl;
    server_name 192.168.1.195;

    ssl_certificate     /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    # Standard HTTP proxy
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }

    # WebSocket proxy for VNC console
    location /console/ws/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 3600s;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name 192.168.1.195;
    return 301 https://$host$request_uri;
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/orchard-ui /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Optional: Raw TCP for Native `.vncloc` Sessions

If users use **Download .vncloc**, nginx also needs a `stream` passthrough (or equivalent firewall exposure) for manager direct TCP proxy ports.
HTTP `server/location` blocks do not proxy raw VNC TCP streams.

Example (`nginx.conf` `stream {}`):

```nginx
stream {
    # One server block per port (57000..57099) is required in plain nginx.
    # Use templating/automation to generate these entries for your range.
    server { listen 57000; proxy_pass 127.0.0.1:57000; }
    server { listen 57001; proxy_pass 127.0.0.1:57001; }
    # ...
    server { listen 57099; proxy_pass 127.0.0.1:57099; }
}
```

Adjust the range to your configured `VNC_DIRECT_PORT_MIN` / `VNC_DIRECT_PORT_MAX`.

## Admin Usage Route

No extra reverse-proxy handling is required for admin usage analytics.
`GET /admin/usage` is standard authenticated HTML over the same HTTPS app upstream.

---

## Troubleshooting: Blank Page When Accessing via NAT

**Symptom:** Same-network access works, but from outside (via port forwarding `publicIP:5443` → `192.168.1.195:443`) you see a white/blank page even though the HTTPS certificate loads.

**Cause:** Caddy matches requests by the `Host` header. External requests have `Host: publicIP` (or `publicIP:5443`), which does not match a Caddyfile block for `192.168.1.195`. Caddy then serves its default site instead of proxying to Flask.

**Fix:** Add your public IP (or external hostname) as a second server block in the Caddyfile, as shown in Step 3 above.
