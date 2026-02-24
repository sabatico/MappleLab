# Deployment and Operations

This guide covers how to run MAppleLab in the background as a persistent service that starts automatically after a reboot.

---

## Option A: Manual Start (Foreground)

Start MAppleLab manually in a terminal window:

```bash
cd /Users/Shared/TART_Manager
./run.sh
```

- In development mode (`FLASK_ENV=development`), this runs the Flask dev server
- In production mode (`FLASK_ENV=production`), this runs Gunicorn with multiple threads

To stop: press **Control + C** in the terminal.

This approach is fine for testing but the process stops when the terminal closes or the Mac reboots.

---

## Option B: macOS Launch Daemon (Recommended for Production)

A Launch Daemon runs as a system service at boot time, before anyone logs in, and keeps running in the background.

### Step 1: Create the Launch Daemon plist

```bash
sudo nano /Library/LaunchDaemons/com.orchard-ui.plist
```

Paste this content, replacing `/Users/admin` with your actual manager Mac username:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.orchard-ui</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/Shared/TART_Manager/run.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/Shared/TART_Manager</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>/Users/admin</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/Shared/TART_Manager/logs/orchard-ui.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/Shared/TART_Manager/logs/orchard-ui-error.log</string>
</dict>
</plist>
```

Save with **Control + O**, Enter, then **Control + X**.

### Step 2: Create the logs directory

```bash
mkdir -p /Users/Shared/TART_Manager/logs
```

### Step 3: Set correct permissions on the plist

```bash
sudo chown root:wheel /Library/LaunchDaemons/com.orchard-ui.plist
sudo chmod 644 /Library/LaunchDaemons/com.orchard-ui.plist
```

### Step 4: Load and start the service

```bash
sudo launchctl load -w /Library/LaunchDaemons/com.orchard-ui.plist
```

### Step 5: Verify it is running

```bash
sudo launchctl list | grep orchard-ui
```

Expected: a line with a PID number (not `-`) in the first column.

Check logs:

```bash
tail -f /Users/Shared/TART_Manager/logs/orchard-ui.log
```

---

## Managing the Service

### Stop

```bash
sudo launchctl stop com.orchard-ui
```

### Start

```bash
sudo launchctl start com.orchard-ui
```

### Restart

```bash
sudo launchctl kickstart -k system/com.orchard-ui
```

### Disable (stop + prevent auto-start)

```bash
sudo launchctl unload -w /Library/LaunchDaemons/com.orchard-ui.plist
```

### Re-enable

```bash
sudo launchctl load -w /Library/LaunchDaemons/com.orchard-ui.plist
```

---

## Updating MAppleLab

The `deploy.sh` script pulls the latest code and reinstalls dependencies:

```bash
cd /Users/Shared/TART_Manager
./deploy.sh
```

To also restart the service after updating:

```bash
RESTART_CMD='sudo launchctl kickstart -k system/com.orchard-ui' ./deploy.sh
```

---

## First-Time Git Setup on the Manager

If you are connecting an existing installation folder to Git for the first time:

```bash
cd /Users/Shared

# Back up current files
tar -czf TART_Manager_backup_$(date +%Y%m%d_%H%M%S).tar.gz TART_Manager

cd /Users/Shared/TART_Manager

# Preserve runtime data before git resets the folder
mkdir -p /tmp/tart_keep
cp -a .env instance logs /tmp/tart_keep/ 2>/dev/null || true

# Connect to git
git init
git remote add origin https://github.com/sabatico/orchard_ui.git
git fetch origin
git reset --hard origin/main
git branch -M main
git branch --set-upstream-to=origin/main main

# Restore runtime data
cp -a /tmp/tart_keep/.env /Users/Shared/TART_Manager/ 2>/dev/null || true
cp -a /tmp/tart_keep/instance /Users/Shared/TART_Manager/ 2>/dev/null || true
cp -a /tmp/tart_keep/logs /Users/Shared/TART_Manager/ 2>/dev/null || true
```

---

## Health Check

After any restart, confirm the system is healthy:

```bash
# Manager UI reachable
curl -sk https://192.168.1.195 | grep -o "<title>.*</title>"

# Registry reachable
curl http://localhost:5001/v2/

# Node health (replace with your node IP and token)
curl -H "Authorization: Bearer YOUR_TOKEN" http://192.168.1.196:7000/health
```

## Native `.vncloc` Operations Notes

- Ensure `VNC_DIRECT_PORT_MIN` / `VNC_DIRECT_PORT_MAX` are explicitly set in `.env` for predictable firewall policy.
- Ensure client Macs can reach manager raw TCP on that port range (default `57000-57099`).
- Direct TCP proxy state is in-memory and cleaned on process exit; long-running sessions are expected to reset during manager restarts.

## Usage Analytics Operations Notes

- Admin usage view is served at `GET /admin/usage`.
- Usage calculations are generated on request from DB telemetry (`vm_status_events`, `vm_vnc_sessions`).
- Baseline status events are auto-seeded for VMs missing history (`usage_tab_baseline`).
