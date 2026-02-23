# Registry Storage Management

The **Registry Storage** page (Admin → Registry Storage) gives you a view of what is inside the Docker registry and lets you clean up orphaned data.

---

## What You See on This Page

### Storage Bar

At the top of the page, a visual bar shows:

- **Trackable** — disk used by VM images that are linked to an active VM record in the database
- **Orphaned** — disk used by images that have no matching VM record (leftovers from deleted or failed operations)
- **Free** — remaining space

The total capacity shown is set by `REGISTRY_STORAGE_TOTAL_GB` in `.env`.

### Trackable Artefacts Table

Lists registry images that correspond to a known VM. Shows:

- User who owns the VM
- VM name and current status
- Registry tag and digest
- Image size
- Cleanup status

### Orphaned Artefacts Table

Lists registry images with no matching VM. These are safe to delete and free up disk space. Shows:

- Repository path
- Digest
- Size
- Reason it is considered orphaned

---

## Deleting Orphaned Artefacts

1. Go to **Admin → Registry Storage**
2. Scroll to the **Orphaned Artefacts** section
3. Review each row — confirm you do not need the image
4. Click **Delete** on any row you want to remove

> **Note:** Deleting a manifest removes the reference immediately. The underlying blob data may still occupy disk until the Docker registry runs garbage collection. If disk is not reclaimed after deletion, registry GC has not run yet — this is normal Docker registry behaviour.

---

## Retrying Failed Cleanups

When a VM lifecycle operation (delete, resume, migration) succeeds but the registry cleanup fails, the VM row shows a **Warning** badge in the admin overview.

To retry:

1. Go to **Admin → Dashboard** (the cross-user operational view)
2. Find the VM row showing the cleanup warning
3. Click **Retry Cleanup**

If retry fails again, check:

- Manager can reach the registry: `curl http://localhost:5001/v2/`
- Registry has delete API enabled: the container should have been started with `-e REGISTRY_STORAGE_DELETE_ENABLED=true`
- Registry data mount path is correct (see [Registry Setup](registry-setup.md))

> **Note:** This page tracks registry artefacts only. Native `.vncloc` direct TCP proxies are runtime transport objects and are not represented here.
>
> **Note:** VM usage analytics are available in **Admin → Usage** and are based on status/VNC telemetry, not registry inventory.

---

## When the Page Shows Empty / No Artefacts

If the page shows no artefacts and all free space despite VMs having been saved previously, the most common cause is the registry container was recreated with a different data mount path.

Diagnose:

```bash
docker inspect tart-registry --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
```

The source path should be `/Users/Shared/tart-registry`. If it shows something else (for example `/var/lib/registry`), the container is not pointing at the actual data.

Fix: stop and recreate the container using the correct path (see [Registry Setup — recreate container](registry-setup.md#5-if-you-need-to-recreate-the-registry-container)).
