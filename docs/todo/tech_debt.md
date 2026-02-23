# Technical Debt

## VNC Browser Console Credential Handling (Stability over Security for now)

### Current state (kept intentionally)

For browser console sessions, the manager currently injects VNC credentials into the page config:

- `app/console/routes.py` passes `vnc_password` to the template.
- `app/templates/console/vnc.html` places it in `window.VNC_CONFIG`.
- `app/static/js/console.js` uses that value to establish noVNC auth.

We are keeping this behavior for now because it is the only confirmed stable path in production at this moment.

### Why we are keeping it now

A previous hardening change removed server-side password injection and switched to runtime prompt-based credential entry in the browser. In live testing this caused the web console to open and close immediately for users, creating an operational outage for console access.

To restore service reliability quickly, we reverted to the known-good flow.

### Security downside (known debt)

This approach has a real security weakness:

- VNC password is present in page-rendered content and browser JS runtime.
- Any compromise of an authenticated browser session can expose the credential.

This is accepted temporarily as a risk tradeoff for operational continuity.

### Target end state (how it should be)

Replace static password injection with a safer, session-scoped mechanism:

1. No plaintext VNC password in HTML templates or JS globals.
2. No persistent storage of VNC credentials in browser storage.
3. Short-lived, one-time console auth flow for noVNC (server-mediated).
4. Graceful UX for credential retries (no immediate console teardown on cancel/error).
5. Backward-compatible rollout behind a feature flag with staged testing.

### Proposed implementation direction

- Add a dedicated console credential handshake endpoint (authenticated, owner-checked).
- Issue an ephemeral token tied to VM/user/session and short TTL.
- Use token exchange on connect path so browser never receives long-lived plaintext secret.
- Add explicit UI state handling for:
  - prompt cancelled
  - wrong credential
  - reconnect path
  - transient backend timing failures

### Rollout requirement before re-hardening

Do not re-enable prompt-only or token-only flows directly in production without:

- end-to-end staging validation on real running VMs,
- reconnect and error-path tests,
- user-acceptance testing for browser compatibility,
- rollback switch to current stable behavior.

### Owner / tracking

- Area: Console / VNC
- Priority: High (security debt), but blocked by stability requirements
- Status: Deferred intentionally until safe rollout path is implemented
