# User Management

MAppleLab supports two ways for users to gain access:

1. **Admin-created accounts** — admin creates the account and sends an invite link directly.
2. **Self-service registration** — users submit a sign-up request from the login page; the admin reviews and approves or denies it.

---

## Self-Service Registration (User-Facing)

Users can request access without contacting an admin:

1. On the login page, click **Request access**
2. Enter their **full name** and **email address**
3. Click **Submit Request**

The request is queued for admin review. The user will receive an invite email once approved (or nothing if denied). Duplicate requests for the same email are blocked.

---

## Reviewing Registration Requests (Admin)

Pending requests appear at the top of **Manage Users** in a yellow-highlighted table.

- **Approve** — creates the user account with default quotas and sends them an invite email with a link to set their password. If SMTP is not configured, a warning is shown with the invite URL to share manually.
- **Deny** — deletes the request. No notification is sent to the requester.

Default quotas applied on approval:

| Quota | Default |
|---|---|
| Max Active VMs | 1 |
| Max Saved VMs | 2 |
| Disk Quota | 100 GB |

To change quotas after approval, use **Edit** on the user row.

---

## Creating a New User (Admin-Direct)

Admins can also create users directly without waiting for a request:

1. Log in as an admin
2. Click your username in the top-right corner → **Manage Users**
3. Fill in the **Create User** form:
   - **Email** — used as login
   - **Role** — `User` or `Admin`
   - **Active VM limit**, **Inactive VM limit**, **Disk quota**
4. Click **Create + Invite**

If SMTP is configured, an invite email is sent automatically. Otherwise copy the invite link from the user table.

---

## What the User Receives

After being created (via direct creation or approved request), the user gets an invite email with a link to:

```
https://<manager-address>/auth/set-password/<token>
```

The token expires after **72 hours**. When they open the link:

1. They choose a password (minimum 8 characters)
2. They are logged in immediately
3. They land on their **My VMs** dashboard

---

## Resending an Invite

If the token expired or the email was not received:

1. Go to **Manage Users**
2. Click the **envelope icon** next to the user
3. A fresh token is generated and a new email is sent

---

## Changing a Password (Any User)

Any logged-in user can change their own password:

1. Click your username in the top-right corner
2. Select **Change Password**
3. Enter current password, new password, and confirm
4. Click **Save Password**

---

## Editing a User (Admin)

To change role or quotas:

1. Go to **Manage Users**
2. Click the **sliders icon** next to the user
3. Adjust role, active VM limit, saved VM limit, or disk quota
4. Click **Save**

Changes take effect immediately.

---

## Deleting a User (Admin)

1. Go to **Manage Users**
2. Click the **trash icon** next to the user
3. Confirm the deletion

> **Warning:** Deleting a user also deletes all of their VM records. If those VMs have artefacts in the registry, the artefacts become orphaned. Clean them up from **Admin → Registry Storage**.

> **Warning:** You cannot delete the last admin account.

---

## Understanding Quotas

| Quota | What it controls |
|---|---|
| **Max Active VMs** | How many VMs can be `running` at the same time |
| **Max Saved VMs** | How many VMs can be `stopped` or `archived` at the same time |
| **Disk Quota (GB)** | Total registry disk used by this user's archived VMs |

When a user hits a quota, the relevant action is blocked with an error message in the dashboard.

---

## Native VNC Access and User Scope

- Users can download `.vncloc` only for their own VMs through `GET /console/<vm_name>/vncloc`.
- The VM must be in `running` state and have an assigned node.
- Admins can still inspect/operate cross-user VMs in admin views, but `.vncloc` download ownership checks remain strict.

---

## Gold Images

- Admin navbar includes **Gold Images** (`/admin/gold-images`) for capturing VMs as reusable base images.
- From **Dashboard**, click **Gold** on a running or stopped VM to capture it. The image is stored in `gold-images/<name>:latest` and distributed to all nodes.
- Gold images appear in the Create VM dropdown for all users.

See [Gold Images](gold-images.md) for full details.

---

## Admin Usage Page

- Admin navbar includes **Usage** (`/admin/usage`) for cross-user VM/VNC time analytics.
- Metrics are grouped by user and include per-VM lifetime composition bars:
  - grey: stopped
  - red: running without active VNC (browser or direct)
  - green: running with active VNC (browser noVNC or native .vncloc)

---

## Configuring SMTP

SMTP settings live in **Admin → Settings**. Fill in:

| Field | Description |
|---|---|
| SMTP Host | Mail server address, for example `smtp.gmail.com` |
| Port | `587` for STARTTLS, `465` for SSL/TLS, `25` for plain |
| Username | Mail account login |
| Password | Mail account password (saved persistently in the database) |
| From Address | Sender email shown in outgoing messages |
| Security | Match to your provider: STARTTLS, SSL, or None |

Click **Save**, then send a **Test Email** to confirm.

> **Note:** The SMTP password is stored in the database and persists across restarts. Leave the password field blank on subsequent saves to keep the existing saved value.

> **Note:** If SMTP is not configured, invite links still work — admins just need to share the `/auth/set-password/<token>` URL manually.
