# Registry Setup

The Docker registry stores saved VM disk images. It runs as a Docker container on the manager Mac and must be started before any VM save or resume operations can work.

---

## 1. Start the Registry

Run the setup script from your Orchard UI install directory:

```bash
cd /Users/Shared/TART_Manager
bash scripts/setup_registry.sh
```

This starts a Docker container named `tart-registry` that:
- Listens on port `5001`
- Stores data in `/Users/Shared/tart-registry`
- Has the delete API enabled (required for cleanup operations)
- Restarts automatically after a reboot

---

## 2. Verify the Registry is Running

```bash
curl http://localhost:5001/v2/
```

Expected output:

```
{}
```

If you see a connection error, wait 10 seconds and try again. If it still fails, check Docker:

```bash
docker ps -a | grep tart-registry
```

If the container shows `Exited`, restart it:

```bash
docker start tart-registry
```

---

## 3. Configure the Manager

Open `.env` and make sure `REGISTRY_URL` points to the manager Mac's **actual IP address**, not `localhost`. Nodes need to reach this address too.

```bash
nano /Users/Shared/TART_Manager/.env
```

Set:

```bash
REGISTRY_URL=http://192.168.1.195:5001/v2/
```

Replace `192.168.1.195` with your manager Mac's actual IP address.

To find your manager Mac's IP:

```bash
ipconfig getifaddr en0
```

or

```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```

> **Warning:** If you use `localhost` or `127.0.0.1` as the registry address in a multi-node setup, node Macs will not be able to reach the registry during save and resume operations.

> **Note:** Registry connectivity is separate from native `.vncloc` connectivity. `.vncloc` requires manager direct TCP proxy ports (`VNC_DIRECT_PORT_MIN/MAX`) to be reachable from client Macs.

> **Note:** Admin usage analytics (`/admin/usage`) are independent of registry state and continue to operate from VM + VNC telemetry tables.

---

## 4. Optionally Set Registry Capacity

The Admin → Registry Storage page shows a storage usage bar. Set its total to match the actual disk space available at `/Users/Shared/tart-registry`:

```bash
df -h /Users/Shared/tart-registry
```

Note the "Size" column. Set the value (in GB) in `.env`:

```bash
REGISTRY_STORAGE_TOTAL_GB=500
```

---

## 5. If You Need to Recreate the Registry Container

If you need to delete and recreate the container (for example after a Docker reset), always use the **same data path** to preserve existing VM images:

```bash
docker stop tart-registry || true
docker rm tart-registry || true
docker run -d \
  -p 5001:5000 \
  -v /Users/Shared/tart-registry:/var/lib/registry \
  -e REGISTRY_STORAGE_DELETE_ENABLED=true \
  --restart always \
  --name tart-registry \
  registry:2
```

Then verify:

```bash
curl http://localhost:5001/v2/_catalog
```

You should see the list of repositories (saved VM names) that were previously stored.

> **Warning:** If you mount a different path (for example `/var/lib/registry` without the volume), all previously saved VMs will be invisible to the manager and cannot be resumed.

---

## 6. Check Registry Status

To see the list of stored images at any time:

```bash
curl http://localhost:5001/v2/_catalog
```

To see tags for a specific VM (replace `username` and `vmname`):

```bash
curl http://localhost:5001/v2/username/vmname/tags/list
```
