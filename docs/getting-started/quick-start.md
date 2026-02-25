# Quick Start

This guide walks you through first-time setup after installation: creating your admin account, adding a node, and running your first VM.

---

## 1. Create the First Admin Account

MAppleLab uses invitation-based account creation. The very first admin account must be created from the command line once.

Open a new Terminal window, go to your install directory, and run:

```bash
cd /Users/Shared/TART_Manager
source .venv/bin/activate
flask shell
```

The prompt changes to `>>>`. Now paste the following lines one at a time, pressing Enter after each:

```python
from app.extensions import db, bcrypt
from app.models import User
u = User(
    username='admin@example.com',
    email='admin@example.com',
    password_hash=bcrypt.generate_password_hash('ChangeMeNow123!').decode('utf-8'),
    is_admin=True,
    must_set_password=False,
)
db.session.add(u)
db.session.commit()
```

Then exit the shell:

```python
exit()
```

> **Important:** Replace `admin@example.com` with your actual email and `ChangeMeNow123!` with a strong password. You can change the password again from the UI after login.

---

## 2. Log In

1. Open a browser and go to your manager address (for example `https://192.168.1.195`)
2. Enter the email and password you used above
3. You should land on the **My VMs** dashboard

---

## 3. Configure SMTP (Recommended)

SMTP lets MAppleLab send invite emails to new users. You can skip this and create user passwords manually, but setting it up now is easier.

1. Click your email address in the top-right corner
2. Select **Settings**
3. Fill in:
   - **SMTP Host** — your mail server address (for example `smtp.gmail.com`)
   - **Port** — typically `587` for STARTTLS or `465` for SSL
   - **Username** — your mail account login
   - **Password** — your mail account password
   - **From address** — the sender shown in invite emails
   - **Security** — choose STARTTLS, SSL, or None to match your provider
4. Click **Save**
5. Enter a test recipient email and click **Send Test Email**

If you receive the test email, SMTP is working correctly.

---

## 4. Set Up the Docker Registry

Before adding nodes, make sure the registry is running. In Terminal:

```bash
curl http://localhost:5001/v2/
```

Expected output: `{}`

If it fails, start it:

```bash
bash scripts/setup_registry.sh
```

See [Registry Setup](../administration/registry-setup.md) for full details.

---

## 5. Prepare the First Node Mac

Before adding a node in the UI, the node must have the agent deployed. See [Node Setup](../administration/node-setup.md) for the full steps.

Summary of what needs to happen on each node:

1. TART installed
2. SSH access from manager confirmed
3. Agent deployed via `scripts/deploy_agent.sh`
4. Agent token set to match `AGENT_TOKEN` in manager `.env`
5. Agent started

---

## 6. Add the First Node in the UI

1. Click **Nodes** in the top navigation bar
2. Click **Add Node**
3. Fill in the fields:
   - **Name** — a label for this node (for example `mac-mini-01`)
   - **Host** — the node's IP address (for example `192.168.1.196`)
   - **SSH User** — the login username on the node (for example `admin`)
   - **SSH Key Path** — full path to the private key on the manager (for example `/Users/admin/.ssh/id_ed25519`)
   - **Agent Port** — leave as `7000` unless you changed it during agent setup
   - **Max VMs** — how many VMs this node should run simultaneously (for example `2`)
4. Click **Add**

The node should appear in the table. The **Health** column shows CPU, RAM, disk, and free VM slots when the node is reachable.

---

## 7. Create Your First VM

1. Click **My VMs** in the navigation bar
2. Click **Create VM**
3. Select a **Base Image** from the dropdown — choose from **Gold Images** (admin-captured) or **Base Images** (for example `ghcr.io/cirruslabs/macos-sonoma-base:latest`)
4. Leave CPU and Memory at their defaults, or increase them
5. Give the VM a name (for example `my-first-vm`)
6. Click **Create**

The dashboard shows the VM with status `creating`, then `running` once ready. This can take a few minutes on first run because the base image must be downloaded.

---

## 8. Open the VNC Console

1. Wait for the VM status to show `running`
2. Click on the VM name to open the detail page
3. Click **Open Console** for browser-based noVNC access
4. Optional: click **Download .vncloc** for native macOS Screen Sharing access
5. The console opens — you should see the macOS desktop

> **Note:** Console from a remote browser requires HTTPS. If you see a "secure context" warning, make sure you accessed the manager over `https://` and that your reverse proxy is configured correctly.
>
> **Note:** `.vncloc` traffic uses raw TCP to manager direct-proxy ports (`57000-57099` by default), so that port range must be reachable from client Macs.

---

## 9. Save and Resume a VM

### Save

1. On the VM detail page, click **Save & Shutdown**
2. The status changes to `pushing` while the VM disk is uploaded to the registry
3. When done, status becomes `archived`

### Resume

1. Click **Resume**
2. Status changes to `pulling` while the VM is restored to a node
3. When done, status returns to `running`

---

## Next Steps

- Add more users: [User Management](../administration/user-management.md)
- For admins: capture VMs as gold images: [Gold Images](../administration/gold-images.md)
- Add more nodes: repeat Step 6 for each node Mac
- Set up production TLS: [Reverse Proxy](../administration/reverse-proxy.md)
- Run as a background service: [Deployment](../administration/deployment.md)
- For admins: review cross-user time analytics in **Usage** (`/admin/usage`)
