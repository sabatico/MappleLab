# Gold Images Management

**Gold Images** are admin-captured reusable base images. Capture a running or stopped VM as a gold image, and it becomes available in the Create VM dropdown for all users.

---

## Capturing a Gold Image

1. Go to **Admin → Dashboard** (cross-user operational view)
2. Find a VM in `running` or `stopped` status
3. Click **Gold** in the actions column
4. Enter a **Gold Image Name** (for example `dev-base-sonoma`)
5. Optionally add a **Description**
6. Click **Capture**

The VM is stopped, pushed to the registry as `gold-images/<name>:latest`, and archived. Distribution to all active nodes starts automatically when the push completes.

---

## Gold Images Page

**Admin → Gold Images** shows all gold images with:

- Name, registry tag, base image, size, source VM
- Per-node distribution status (pending, pulling, ready, failed)
- **Re-Distribute** — re-trigger pulls on all active nodes
- **Delete** — remove DB records (registry artefact left for manual cleanup)

Distribution status updates every 5 seconds via HTMX polling.

---

## Create VM Dropdown

When creating a VM, the image dropdown has two optgroups:

- **Gold Images** — admin-captured images (newest first)
- **Base Images** — vanilla TART images from `TART_IMAGES` config

Gold images are pre-cached on nodes when distribution completes, so VM creation from a gold image is fast.

---

## Registry Namespace

Gold images are stored in `gold-images/<name>:latest`. Re-using the same name overwrites the previous gold image.
