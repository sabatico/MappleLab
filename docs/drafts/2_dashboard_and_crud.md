# Module 2: Dashboard + VM CRUD + API Endpoints

> **Status**: ✅ Complete (refurbished 2026-02-21)

**Original scope**: Phases 3–5 from PLANNING.md — dashboard + CRUD via OrchardClient
**Current state**: Fully transitioned to TART-Direct architecture (see `refurbish_plan.md`)
**Output**: DB-backed dashboard with VM list, create/start/stop/save/resume/delete + HTMX auto-refresh + login required
**Depends on**: Module 1 (scaffold + TartClient + DB models)
**Other modules depend on this**: Module 3 (console) links from here

---

## ⚠️ Architecture Note

This module originally used `OrchardClient` for all VM data (live API calls). It has been **fully rewritten** to use:
- **SQLite DB** (Flask-SQLAlchemy) as the source of truth for VM state
- **TartClient** for issuing commands to TART agents on Mac nodes
- **NodeManager** for automatic node selection
- **Flask-Login** (`@login_required`) on all routes
- New VM states: `creating`, `running`, `stopped`, `pushing`, `archived`, `pulling`, `failed`
- New actions: **Start**, **Stop**, **Save & Shutdown** (push to registry), and **Resume** (pull from registry)

---

## Tasks

### Original dashboard tasks (complete)
- [x] Write `app/main/routes.py` (dashboard, create_vm, vm_detail, delete_vm)
- [x] Write `app/api/routes.py` (list_vms, vm_status)
- [x] Write `app/templates/base.html`
- [x] Write `app/templates/_partials/flash_messages.html`
- [x] Write `app/templates/_partials/vm_status_badge.html`
- [x] Write `app/templates/_partials/vm_table.html`
- [x] Write `app/templates/main/dashboard.html`
- [x] Write `app/templates/main/vm_detail.html`
- [x] Write `app/templates/main/create_vm.html`
- [x] Write `app/static/css/style.css`
- [x] Write `app/static/js/app.js`

### Refurbishment rewrites (complete)
- [x] Rewrite `app/main/routes.py` — DB-based, `@login_required`, start_vm + stop_vm + save_vm + resume_vm
- [x] Rewrite `app/api/routes.py` — DB query + agent status reconciliation + op polling for push/pull progress
- [x] Update `base.html` — auth nav (user dropdown, login link, admin Nodes link)
- [x] Update `_partials/vm_status_badge.html` — new states (stopped, archived, pushing, pulling, creating)
- [x] Update `_partials/vm_table.html` — context-aware buttons (Console+Stop+Save for running; Start for stopped; Resume for archived; spinner for in-progress)
- [x] Update `main/dashboard.html` — "Worker" → "Node" column header
- [x] Update `main/vm_detail.html` — Save&Shutdown/Resume buttons, async progress banner, Registry info card
- [x] Update `main/create_vm.html` — removed node selection (auto), minor text updates
- [x] Verify: dashboard loads and shows VMs from DB (login required)
- [x] Verify: HTMX polling refreshes table every 5s
- [x] Verify: create VM form picks best node automatically
- [x] Verify: running VM exposes Stop action; stopped VM exposes Start action
- [x] Verify: save_vm triggers async push (status → pushing)
- [x] Verify: resume_vm triggers async pull (status → pulling)
- [x] Verify: delete VM removes from agent + DB
- [x] Verify: status badge on vm_detail polls and transitions archived/running on op completion
- [x] Verify: `/api/vms` reconciliation corrects stale DB status based on agent-reported VM status

---

## Files

| File | Status | Notes |
|------|--------|-------|
| `app/main/routes.py` | ✅ | REWRITTEN: DB-based, @login_required, start_vm, stop_vm, save_vm, resume_vm |
| `app/api/routes.py` | ✅ | REWRITTEN: DB + agent status reconciliation + op status polling |
| `app/templates/base.html` | ✅ | UPDATED: auth nav, Nodes admin link |
| `app/templates/_partials/flash_messages.html` | ✅ | Unchanged |
| `app/templates/_partials/vm_status_badge.html` | ✅ | UPDATED: all new VM states |
| `app/templates/_partials/vm_table.html` | ✅ | UPDATED: save/resume/delete buttons |
| `app/templates/main/dashboard.html` | ✅ | UPDATED: Node column, new VM states |
| `app/templates/main/vm_detail.html` | ✅ | UPDATED: progress banner, Registry card, save/resume |
| `app/templates/main/create_vm.html` | ✅ | UPDATED: auto node selection, minor text |
| `app/static/css/style.css` | ✅ | Unchanged |
| `app/static/js/app.js` | ✅ | Unchanged |

**Status key**: ⬜ Not started · 🔄 In progress · ✅ Complete

---

## Route Table

| Method | URL | Handler | Purpose |
|--------|-----|---------|---------|
| GET | / | main.dashboard | List user's VMs (from DB) |
| GET | /vms/create | main.create_vm | Show create form |
| POST | /vms/create | main.create_vm | Clone VM on best node |
| GET | /vms/\<vm_name\> | main.vm_detail | VM detail page |
| POST | /vms/\<vm_name\>/start | main.start_vm | Start a stopped VM on its assigned node |
| POST | /vms/\<vm_name\>/stop | main.stop_vm | Stop a running VM and close console tunnel |
| POST | /vms/\<vm_name\>/save | main.save_vm | Trigger async save (push to registry) |
| POST | /vms/\<vm_name\>/resume | main.resume_vm | Trigger async restore (pull from registry) |
| POST | /vms/\<vm_name\>/delete | main.delete_vm | Stop VNC, delete from agent + DB |
| GET | /api/vms | api.list_vms | HTMX poll or JSON |
| GET | /api/vms/\<vm_name\>/status | api.vm_status | Status badge + reconciliation + op completion check |

All routes require `@login_required`.

---

## VM State Machine

```
[creating] → [running] ── Stop ─→ [stopped] ── Start ─→ [running]
                │                                     │
                └──────── Save & Shutdown ────────────┘
                                  ↓
                              [pushing] → [archived] ── Resume ─→ [pulling] → [running]

Any state → [failed]   (on error)
Any state → deleted    (on delete)
```

| Status | Meaning |
|--------|---------|
| `creating` | Being cloned from base image on a Mac node |
| `running` | Active on `node_id`, can VNC in |
| `stopped` | Present on `node_id`, powered off locally |
| `pushing` | Save in progress: shutdown → `tart push` → `tart delete` |
| `archived` | In registry, not on any node; `node_id` = null |
| `pulling` | Resume in progress: `tart pull` → `tart run` |
| `failed` | Last operation failed; `status_detail` has error message |

---

## Create VM Flow

```
1. User submits form (name, base_image, cpu, memory)
2. NodeManager.find_best_node() → picks active node with most free slots
3. DB: INSERT vm (status=creating, node_id=chosen_node)
4. TartClient.create_vm(node, name, base_image) → tart clone on agent
5. TartClient.start_vm(node, name)
6. DB: UPDATE vm (status=running or stopped based on agent list result)
7. Flash success, redirect to dashboard
```

---

## Save & Shutdown Flow

```
1. User clicks "Save & Shutdown"
2. POST /vms/<name>/save
3. TartClient.save_vm(node, name, registry_tag) → agent starts async: stop + push + delete
4. DB: UPDATE vm (status=pushing)
5. Redirect to vm_detail (HTMX polling picks up pushing status)
6. HTMX polls /api/vms/<name>/status every 3s
7. api.vm_status polls agent /vms/<name>/op
8. When op.status == 'done': DB UPDATE (status=archived, node_id=null, last_saved_at=now)
```

---

## Resume Flow

```
1. User clicks "Resume"
2. POST /vms/<name>/resume
3. NodeManager.find_best_node() → picks node
4. TartClient.restore_vm(node, name, registry_tag) → agent starts async: pull + start
5. DB: UPDATE vm (status=pulling, node_id=chosen_node)
6. Redirect to vm_detail (HTMX polling picks up pulling status)
7. HTMX polls /api/vms/<name>/status every 3s
8. When op.status == 'done': DB UPDATE (status=running, last_started_at=now)
```

---

## Start/Stop Flow

```
Stop:
1. User clicks "Stop"
2. POST /vms/<name>/stop
3. Backend stops console tunnel + remote VNC proxy (best effort)
4. TartClient.stop_vm(node, name)
5. DB: UPDATE vm (status=stopped)

Start:
1. User clicks "Start"
2. POST /vms/<name>/start
3. TartClient.start_vm(node, name)
4. DB: UPDATE vm (status=running, last_started_at=now)
```

---

## HTMX Polling Pattern

Dashboard tbody auto-refreshes (DB-backed, with per-node agent reconciliation for local VM states):
```html
<tbody
  hx-get="/api/vms"
  hx-trigger="every 5s"
  hx-swap="innerHTML"
>
  {% include '_partials/vm_table.html' %}
</tbody>
```

Status badge on vm_detail (polls agent op status when pushing/pulling):
```html
<span hx-get="/api/vms/{{ vm.name }}/status"
      hx-trigger="every 3s"
      hx-swap="outerHTML">
  {% include '_partials/vm_status_badge.html' %}
</span>
```

The `/api/vms/<name>/status` endpoint:
- When `HX-Request` present → returns `_partials/vm_status_badge.html` (HTML)
- Otherwise → returns JSON `{name, status}`
- When status is `pushing` or `pulling` → polls agent op; transitions DB state on completion
- For local states (`creating`, `running`, `stopped`) → reconciles status from agent VM list

---

## Action Button Logic (`_partials/vm_table.html`)

| VM Status | Buttons shown |
|-----------|--------------|
| `running` | 🟢 Console · ⏹ Stop · 💾 Save & Shutdown · 🗑 Delete |
| `stopped` | ▶ Start · 🗑 Delete |
| `archived` | ▶ Resume · 🗑 Delete |
| `creating`, `pushing`, `pulling` | ⏳ spinner (disabled) |
| `failed` | 🗑 Delete |

---

## Verification

1. Navigate to `/` → redirected to `/auth/login` (login required)
2. Login → dashboard loads, shows VMs from DB
3. VM table auto-refreshes every 5s (watch network tab)
4. Create VM form submits → VM appears as "Creating" then "Running" (or "Stopped" if agent reports stopped)
5. "Save & Shutdown" → status flips to "Pushing..." spinner
6. Poll resolves → status becomes "Archived", Resume button appears
7. "Resume" → status flips to "Pulling..." spinner → resolves to "Running"
8. "Stop" on running VM changes state to "Stopped"; "Start" returns it to "Running"
9. Delete VM works with confirmation dialog
10. Status badge on vm_detail polls and updates
