# Node Setup

Prepare each Mac node before adding it to MAppleLab. These steps must be done on **every node Mac**, not the manager.

---

## 1. Disable Keychain Auto-Lock

TART needs access to credentials at any time, including after a reboot. Prevent macOS from locking the login keychain:

Open Terminal on the **node Mac** and run:

```bash
security set-keychain-settings -t 0 login.keychain
```

No output means the command succeeded.

---

## 2. Enable Automatic Login

Tart and the agent need to run under a logged-in user session after a reboot.

1. Open **System Settings** (Apple menu → System Settings)
2. Click **Users & Groups**
3. Next to **Automatic Login**, click the dropdown and select the user account that runs Tart
4. Enter that user's password when prompted
5. Click **OK**

---

## 3. Grant Local Network Access (macOS Ventura and later)

On macOS Ventura, Sonoma, and Tahoe, `tart pull` can fail with:

```
Error: The Internet connection appears to be offline.
```

even when the registry is reachable. This is caused by macOS blocking Local Network access for the runtime process.

### Fix

1. Open **System Settings** → **Privacy & Security** → **Local Network**
2. Enable the toggle for each of the following entries (add them if they are missing):
   - `Terminal`
   - `sshd-session`
   - `Python` (the venv or system Python used by the agent)

### Trigger the permission prompt (if the entries don't appear)

Run this on the **node Mac**, as the same user that runs Tart, replacing the placeholders:

```bash
tart pull <manager-ip>:5001/anyuser/anyvm:latest --insecure
```

Example:

```bash
tart pull 192.168.1.195:5001/testuser/testvm:latest --insecure
```

A system dialog should appear asking **"Allow to find devices on local network?"**. Click **Allow**.

After clicking Allow, retry any save/resume/migrate operations from the MAppleLab.

---

## 4. Install TART

If TART is not already installed on the node:

```bash
brew install cirruslabs/cli/tart
```

Verify:

```bash
tart --version
```

---

## 5. Deploy the Agent

The TART agent is a small HTTP service that the manager talks to in order to manage VMs on this node.

Run these commands from the **manager Mac**, replacing the placeholders:

```bash
bash scripts/deploy_agent.sh <node-ip> <ssh-user>
```

Example:

```bash
bash scripts/deploy_agent.sh 192.168.1.196 admin
```

This copies the agent files to `~/tart_agent/` on the node over SSH.

---

## 6. Set the Agent Token on the Node

The agent token is a shared password used to authenticate API calls between the manager and this node. It must match the `AGENT_TOKEN` value in the manager's `.env` file.

```bash
ssh <ssh-user>@<node-ip> 'echo YOUR_TOKEN > ~/.agent_token'
```

Example (replace `YOUR_TOKEN` with your actual token from the manager `.env`):

```bash
ssh admin@192.168.1.196 'echo abc123xyz > ~/.agent_token'
```

> **Warning:** If this token does not match the `AGENT_TOKEN` in the manager `.env`, all operations on this node will fail with authentication errors.

---

## 7. Start the Agent

```bash
ssh <ssh-user>@<node-ip> '~/tart_agent/start_agent.sh'
```

Example:

```bash
ssh admin@192.168.1.196 '~/tart_agent/start_agent.sh'
```

The agent runs on port `7000` by default.

---

## 8. Validate in the UI

1. Log in to MAppleLab as admin
2. Click **Nodes** in the navigation bar
3. Click **Add Node** and fill in the node's details
4. After adding, the node row should show current health stats (CPU, RAM, disk, free slots)

If the **Health** column shows an error or blank values:
- Confirm the agent is running: `ssh admin@<node-ip> 'pgrep -f agent.py'`
- Confirm the agent port is reachable: run `curl http://<node-ip>:7000/health` from the manager
- Confirm the token matches on both sides

---

## Repeat for Every Node

These steps must be completed for each Mac node you want to add to the cluster.

## Native `.vncloc` Compatibility Notes

- Manager-side `.vncloc` uses agent `start_vnc()` data and now supports `vnc_port` from `/vnc/<name>/start`.
- Older agents are still supported because manager falls back to `5900` if `vnc_port` is missing.
- Manager also resolves VM IP via agent `/vms/<name>/ip`; ensure agent and node networking allow manager -> VM IP connectivity.

## Usage Metrics Compatibility Notes

- Usage session tracking is manager-side and records websocket bridge sessions from `console_ws`.
- No node-side schema changes are required for usage metrics.
