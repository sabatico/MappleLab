# Gold Images Feature — Implementation Plan

## Implementation Status

| Phase | Status | Notes |
|-------|--------|-------|
| 1. Database Models | ✅ Done | `GoldImage`, `GoldImageNode` in `app/models.py` |
| 2. Agent Image Endpoints | ✅ Done | `pull_image_only()`, `POST /images/pull`, `GET /images/<op_key>/op` |
| 3. TartClient Methods | ✅ Done | `pull_image()`, `get_image_op_status()` |
| 4. Admin Make Gold Route | ✅ Done | `GET|POST /admin/vms/<vm_id>/make-gold` |
| 5. Poller & Distribution | ✅ Done | `_advance_async_op` gold detection, `trigger_gold_distribution()`, `GET /api/gold-images/<id>/distribution` |
| 6. Admin Gold Images Page | ✅ Done | `gold_images.html`, distribution partial, list/redistribute/delete routes |
| 7. UI Integration | ✅ Done | `icon_gold_image`, `vm_btn_make_gold`, Gold button in overview, nav link |
| 8. Create VM Dropdown | ✅ Done | Optgroup with Gold Images first, then Base Images |

---

## Context

MAppleLab currently has no concept of reusable base images beyond the hardcoded vanilla list in `config.TART_IMAGES`. The save/archive flow is VM-specific — each VM pushes to its own registry tag and can only be resumed by the same VM record.

**Goal**: Admin-only "Gold Images" feature — capture a running/stopped VM as a reusable base image, store it in a dedicated `gold-images/` registry namespace, distribute it to all nodes, and make it available in the "Create VM" image dropdown for all users.

## Design Decisions (from user)
- **Capture mode**: Like archive — stop VM, push to registry, VM becomes archived
- **Registry namespace**: `gold-images/<name>:latest`
- **Naming**: Admin picks a name; re-using same name overwrites
- **Distribution**: Pre-cache on all active nodes (async with progress)
- **Admin page**: Dedicated "Gold Images" tab in admin area

---

## Implementation Steps

### Phase 1: Database Models

**File: `app/models.py`** — Add two new models after `AppSettings`:

- **`GoldImage`** table: `id`, `name` (unique), `registry_tag`, `base_image`, `disk_size_gb`, `created_at`, `updated_at`, `created_by_id` (FK users), `source_vm_name`, `description`
- **`GoldImageNode`** table: `id`, `gold_image_id` (FK gold_images), `node_id` (FK nodes), `status` (pending/pulling/ready/failed), `status_detail`, `started_at`, `completed_at`. Unique constraint on (gold_image_id, node_id). Cascade delete from GoldImage.

**File: `app/__init__.py`** — Import `GoldImage, GoldImageNode` alongside existing model imports so `db.create_all()` creates the new tables.

### Phase 2: Agent — Image Pre-Cache Endpoint

**File: `tart_agent/tart_runner.py`** — Add `pull_image_only(registry_tag, progress_cb)`:
- Extracted Stage 1 of existing `pull_vm()` — runs `tart pull <tag> [--insecure]` only
- No clone, no start — just populates TART's OCI layer cache
- Same insecure/secure retry pattern as `push_vm()`

**File: `tart_agent/agent.py`** — Add two endpoints:
- `POST /images/pull` — accepts `{registry_tag, op_key, expected_disk_gb}`, spawns daemon thread calling `pull_image_only()`, tracks progress in new `_image_ops` dict (separate from VM `_ops`)
- `GET /images/<path:op_key>/op` — polls image pull progress from `_image_ops`

Uses same `_set_op` pattern with a separate `_image_ops` dict + `_image_ops_lock` to avoid collision with VM ops.

### Phase 3: TartClient Methods

**File: `app/tart_client.py`** — Add two methods:
- `pull_image(node, registry_tag, op_key, expected_disk_gb)` → `POST /images/pull`
- `get_image_op_status(node, op_key)` → `GET /images/<op_key>/op`

### Phase 4: Admin "Make Gold Image" Route

**File: `app/admin/routes.py`** — Add route `POST /admin/vms/<vm_id>/make-gold`:
1. GET: render form template for admin to enter gold image name + description
2. POST: build `gold-images/<name>:latest` registry tag, check registry space (reuse `_check_registry_space_for_save`), call `tart.save_vm()` with gold tag, set `vm.status = 'pushing'` and `vm.status_detail = 'gold:<name>'` (marker for the poller), upsert `GoldImage` record

### Phase 5: Poller — Gold Push Completion + Distribution Trigger

**File: `app/api/routes.py`** — Modify `_advance_async_op()`:
- In the `pushing` + `done` branch, BEFORE the existing migration target check, detect `gold:` prefix in `status_detail`
- On gold push done: transition VM to `archived`, call new `_trigger_gold_distribution(gold_name)`

Add `_trigger_gold_distribution(gold_name)`:
- Create/reset `GoldImageNode` records for each active node
- Call `tart.pull_image()` on each node, update `GoldImageNode.status` to `pulling`

Add `GET /api/gold-images/<gold_id>/distribution` endpoint:
- Polls each node's `get_image_op_status()`, advances `GoldImageNode` status (pulling→ready or pulling→failed)
- Returns HTMX partial for the admin Gold Images page

### Phase 6: Admin Gold Images Page

**New file: `app/templates/admin/gold_images.html`** — Lists all gold images as cards with:
- Name, registry tag, base image, size, source VM, updated timestamp, description
- Per-node distribution status table (HTMX-polled every 5s)
- Re-Distribute and Delete action buttons

**New file: `app/templates/admin/_partials/gold_image_distribution.html`** — HTMX partial for node distribution table rows with status badges.

**New file: `app/templates/admin/make_gold_image.html`** — Form: gold image name input, optional description, VM info summary, capture button with confirm.

**File: `app/admin/routes.py`** — Add routes:
- `GET /admin/gold-images` — list page
- `POST /admin/gold-images/<id>/redistribute` — re-trigger distribution to all active nodes
- `POST /admin/gold-images/<id>/delete` — delete DB records (registry artifact left for manual cleanup)

### Phase 7: UI Integration

**File: `app/templates/_macros/action_buttons.html`** — Add `vm_btn_make_gold(url, size)` macro (link-based, `btn-outline-warning`, `bi-award` icon).

**File: `app/templates/admin/overview.html`** — Add "Gold" button for running and stopped VMs in the actions column.

**File: `app/templates/base.html`** — Add "Gold Images" nav link (after Registry Storage, inside admin `{% if %}` block at line 60-76). Import `icon_gold_image` from icons macro.

**File: `app/templates/_macros/icons.html`** — Add `icon_gold_image()` macro (`bi-award`).

### Phase 8: Create VM Dropdown

**File: `app/main/routes.py`** — In `create_vm()` GET handler (line ~335), query `GoldImage.query.order_by(GoldImage.updated_at.desc()).all()` and pass as `gold_images=` to template. Also pass in all validation-failure re-renders.

**File: `app/templates/main/create_vm.html`** — Replace flat `<select>` with `<optgroup>` structure:
- "Gold Images" optgroup first (newest first, displaying name + truncated description)
- "Base Images" optgroup second (existing vanilla `TART_IMAGES`)

No backend change needed for the POST — `base_image` already stores whatever tag string the user selects, and `tart clone` works with both remote OCI tags and local pre-cached images.

---

## Files Modified (in implementation order)

| # | File | Change |
|---|------|--------|
| 1 | `app/models.py` | Add `GoldImage` and `GoldImageNode` models |
| 2 | `app/__init__.py` | Import new models for `db.create_all()` |
| 3 | `tart_agent/tart_runner.py` | Add `pull_image_only()` function |
| 4 | `tart_agent/agent.py` | Add `POST /images/pull` + `GET /images/<key>/op` |
| 5 | `app/tart_client.py` | Add `pull_image()` + `get_image_op_status()` |
| 6 | `app/templates/_macros/icons.html` | Add `icon_gold_image` macro |
| 7 | `app/templates/_macros/action_buttons.html` | Add `vm_btn_make_gold` macro |
| 8 | `app/templates/admin/make_gold_image.html` | **New** — capture form |
| 9 | `app/admin/routes.py` | Add 4 routes: make_gold_image, gold_images, redistribute, delete |
| 10 | `app/api/routes.py` | Modify `_advance_async_op` + add distribution trigger + distribution poll endpoint |
| 11 | `app/templates/admin/gold_images.html` | **New** — admin list page |
| 12 | `app/templates/admin/_partials/gold_image_distribution.html` | **New** — HTMX partial |
| 13 | `app/templates/admin/overview.html` | Add "Gold" button to running/stopped VMs |
| 14 | `app/templates/base.html` | Add Gold Images nav link |
| 15 | `app/main/routes.py` | Pass `gold_images` to create_vm template |
| 16 | `app/templates/main/create_vm.html` | Optgroup dropdown with gold + vanilla images |

## Key Functions Reused
- `_check_registry_space_for_save(vm)` — from `app/main/routes.py` (already imported by admin routes)
- `_registry_authority_from_config()` — from `app/main/routes.py:112`
- `_agent_vm_name()`, `_agent_vm_size_on_disk_gb()` — from `app/main/routes.py` (already imported by admin routes)
- `set_vm_status()`, `ensure_vm_status_baseline()` — from `app/usage_events.py`
- `_set_op()` pattern — from `tart_agent/agent.py` (duplicated for image ops)
- `pull_vm()` Stage 1 logic — from `tart_agent/tart_runner.py` (extracted into `pull_image_only()`)

## Verification

1. **Start the app** — confirm `gold_images` and `gold_image_nodes` tables are created in SQLite
2. **Navigate to admin overview** — confirm "Gold" button appears on running/stopped VMs
3. **Click "Gold"** — confirm form renders with VM info, name input, description
4. **Submit capture** — confirm VM transitions to `pushing`, `GoldImage` record created
5. **Wait for push completion** — confirm VM transitions to `archived`, `GoldImageNode` records created with `pulling` status
6. **Navigate to admin Gold Images page** — confirm gold image card appears with node distribution table
7. **Wait for distribution** — confirm node statuses advance from `pulling` to `ready`
8. **Navigate to Create VM** — confirm gold image appears in dropdown under "Gold Images" optgroup
9. **Create VM from gold image** — confirm `tart clone <gold-images/name:latest> <vm-name>` succeeds on node
10. **Re-distribute** — confirm button re-triggers pulls on all active nodes
11. **Delete gold image** — confirm DB records removed, gold image no longer in Create VM dropdown
