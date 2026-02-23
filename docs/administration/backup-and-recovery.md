# Backup and Recovery

---

## What to Back Up

| Item | Location | Why |
|---|---|---|
| App database | `instance/orchard_ui.db` | Users, VMs, nodes, settings |
| Environment config | `.env` | Secrets and runtime settings |
| Registry data | `/Users/Shared/tart-registry` | Saved VM disk images |
| Logs (optional) | `logs/` | Incident investigation |
| Direct VNC port range policy | firewall/proxy config | Required for native `.vncloc` reachability |
| Usage telemetry rows | inside app DB (`instance/orchard_ui.db`) | Required for admin usage history |

---

## Regular Backup

Run this on the **manager Mac** from your install directory:

```bash
cd /Users/Shared/TART_Manager

# Back up app data (database + config + logs)
tar -czf ~/Desktop/orchard_backup_$(date +%Y%m%d_%H%M%S).tar.gz \
  .env \
  instance/ \
  logs/
```

To back up the registry (this may be large — VMs are typically 20–60 GB each):

```bash
tar -czf ~/Desktop/tart_registry_backup_$(date +%Y%m%d_%H%M%S).tar.gz \
  /Users/Shared/tart-registry
```

> **Tip:** Schedule these with `cron` or a launchd calendar entry for regular automated backups.

---

## Restore Sequence

### Step 1: Install the app on the new machine

Follow [Prerequisites](../getting-started/prerequisites.md) and [Installation](../getting-started/installation.md) up to and including the virtual environment and noVNC steps.

Do **not** run `./run.sh` yet.

### Step 2: Restore .env

```bash
cp /path/to/backup/.env /Users/Shared/TART_Manager/.env
```

Verify it contains the correct `SECRET_KEY`, `AGENT_TOKEN`, and `REGISTRY_URL` for the new environment.

### Step 3: Restore the database

```bash
mkdir -p /Users/Shared/TART_Manager/instance
cp /path/to/backup/instance/orchard_ui.db \
   /Users/Shared/TART_Manager/instance/orchard_ui.db
```

### Step 4: Restore the registry data

```bash
sudo mkdir -p /Users/Shared/tart-registry
sudo tar -xzf /path/to/tart_registry_backup_*.tar.gz \
  -C / \
  --strip-components=1
```

Or if your backup was a directory copy:

```bash
sudo rsync -av /path/to/backup/tart-registry/ /Users/Shared/tart-registry/
```

### Step 5: Start the registry container

```bash
cd /Users/Shared/TART_Manager
bash scripts/setup_registry.sh
```

Verify:

```bash
curl http://localhost:5001/v2/_catalog
```

You should see the same list of VM repositories that existed before the restore.

### Step 6: Start Orchard UI

```bash
./run.sh
```

### Step 7: Validate

Run through this checklist:

- [ ] Admin login works at `https://<manager-address>`
- [ ] Nodes table shows all previously added nodes
- [ ] VM dashboard shows users' VMs with correct statuses
- [ ] Pick one `archived` VM and click **Resume** — confirm it reaches `running`
- [ ] Open **Admin → Registry Storage** and confirm artefacts are visible

---

## Migrating to a New Manager Mac

To move the whole setup to a different Mac:

1. Complete Restore Steps 1–6 above on the new Mac
2. Update `REGISTRY_URL` in `.env` to the new Mac's IP address
3. Update `AGENT_TOKEN` if rotating it as part of the migration
4. Re-deploy the agent to each node with the new registry URL:

```bash
# On each node, update the token
ssh admin@192.168.1.196 'echo NEW_TOKEN > ~/.agent_token'

# Restart the agent
ssh admin@192.168.1.196 '~/tart_agent/start_agent.sh'
```

5. Point Caddy or nginx on the new Mac at `127.0.0.1:5000`
6. Update DNS or user bookmarks to the new manager IP
