# User Management

MAppleLab uses an invitation-based system. Admin users create accounts for others and send invite links. Users cannot register themselves.

---

## Creating a New User

1. Log in as an admin
2. Click your email/username in the top-right corner
3. Select **Manage Users**
4. Click **Create User**
5. Fill in the form:
   - **Email** — the user's email address (used as their login)
   - **Role** — choose `User` for normal access or `Admin` for full admin access
   - **Max Active VMs** — how many VMs this user can run simultaneously (default: `1`)
   - **Max Saved VMs** — how many stopped/archived VMs this user can keep (default: `2`)
   - **Disk Quota (GB)** — total registry disk this user can consume for saved VMs (default: `100`)
6. Click **Create**

If SMTP is configured, an invite email is sent automatically. If not, you will see a warning that the email was not sent — copy the invite link manually from the user table.

---

## What the User Receives

The user gets an email with a link to:

```
https://<manager-address>/auth/set-password/<token>
```

The token expires after **72 hours**. When they open the link:

1. They choose a password (minimum 8 characters)
2. They are logged in immediately after setting it
3. They land on their personal **My VMs** dashboard

---

## Resending an Invite

If the user did not receive their email, or the token expired:

1. Go to **Manage Users**
2. Find the user row
3. Click **Resend Invite**

This generates a fresh token and sends a new email.

---

## Editing a User

To change role or quotas:

1. Go to **Manage Users**
2. Click **Edit** next to the user
3. Adjust role, active VM limit, saved VM limit, or disk quota
4. Click **Save**

Changes take effect immediately.

---

## Deleting a User

1. Go to **Manage Users**
2. Click **Delete** next to the user
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

## Native VNC Access and User Scope

- Users can download `.vncloc` only for their own VMs through `GET /console/<vm_name>/vncloc`.
- The VM must be in `running` state and have an assigned node.
- Admins can still inspect/operate cross-user VMs in admin views, but `.vncloc` download ownership checks remain strict.

## Gold Images

- Admin navbar includes **Gold Images** (`/admin/gold-images`) for capturing VMs as reusable base images.
- From **Dashboard**, click **Gold** on a running or stopped VM to capture it. The image is stored in `gold-images/<name>:latest` and distributed to all nodes.
- Gold images appear in the Create VM dropdown for all users.

See [Gold Images](gold-images.md) for full details.

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
| Password | Mail account password |
| From Address | Sender email shown in outgoing messages |
| Security | Match to your provider: STARTTLS, SSL, or None |

Click **Save**, then send a **Test Email** to confirm.

> **Note:** If SMTP is not configured, invite links still work — admins just need to share the `/auth/set-password/<token>` URL manually.
