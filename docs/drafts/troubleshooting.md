# Troubleshooting

## Re-pull Stuck at Waiting for Lock

Symptoms:

- Progress stalls
- Logs mention `waiting for lock`

Actions:

```bash
ps -ax | rg "tart pull"
kill <pid>
```

Then retry re-pull from UI.

## Cleanup Warning After Successful VM Action

Symptoms:

- VM action succeeds
- Cleanup status shows warning/failed

Actions:

- Use **Retry Cleanup** from admin actions
- Verify `REGISTRY_URL` reachability
- Confirm registry runs with delete API enabled

## Registry Storage Page Empty Unexpectedly

Most common cause: wrong registry data mount after container recreate.

Validate:

```bash
docker inspect tart-registry --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
curl http://localhost:5001/v2/_catalog
```

## Console Fails for Remote Browser

- Ensure manager UI is opened via `https://`
- Ensure reverse proxy supports websocket upgrade on `/console/ws/`
- Validate node VNC endpoint is reachable from manager

## `.vncloc` Download Works but Native Connect Times Out

- Confirm manager TCP direct-proxy range is reachable from the client Mac (`57000-57099` by default).
- Confirm VM is still running (proxy is torn down on stop/delete/disconnect flows).
- Validate manager host in the `.vncloc` file is routable from the client network/VPN.
- **No connection logs on manager**: If you never see `Direct proxy: client connected` in manager logs, the client is not reaching the manager. Check: (1) host in `.vncloc` — open the file and verify the host is reachable from your Mac; (2) firewall allows 57000-57099; (3) if accessing via external hostname, set `VNC_DIRECT_HOST` to the manager's LAN IP so the `.vncloc` uses an address reachable from your network.

## `.vncloc` Download Route Fails

- Route requires login + ownership: `/console/<vm_name>/vncloc`.
- VM must be `running` and assigned to a node.
- Manager must be able to resolve VM IP from agent (`/vms/<name>/ip`) and reach VM VNC port.
- If you see "No free direct TCP proxy ports available", increase `VNC_DIRECT_PORT_MAX` or close stale sessions.

## Admin Usage Page Empty Unexpectedly

- Usage includes only VMs with `status in ('running', 'stopped')` and `node_id` present.
- Archived/off-node VMs are excluded by design.
- Verify telemetry baselines exist in `vm_status_events` for older VMs.

## Usage Bars Look Wrong

- Ensure VM status transitions are being recorded via `set_vm_status(...)`.
- Ensure websocket console sessions open/close normally (`vm_vnc_sessions` rows).
- Open sessions (missing `disconnected_at`) are treated as active until report generation time.

## Node Operations Fail on Tahoe

If node cannot pull registry artefacts despite network access:

- Check Local Network privacy permissions for runtime process
- Trigger and accept local-network permission prompt on node

## TLS Error on tart pull (Re-pull / Resume / Gold Image Distribution)

Symptoms:

- `tart pull failed: Error: A TLS error caused the secure connection to fail.`
- Re-pull, Resume, or gold image distribution fails

Cause: Registry uses HTTPS with a self-signed or untrusted certificate. TART validates TLS by default.

Actions:

1. **Use `--insecure` for tart pull** — On the node, set `REGISTRY_INSECURE=true` in the tart_agent `.env` (or equivalent). The agent should pass `--insecure` to `tart pull` when this is set. See `tart_agent` docs.
2. **Use HTTP registry** — If the registry is on the LAN and TLS is not required, run it over HTTP (e.g. `REGISTRY_URL=http://192.168.1.195:5001/v2/`).
3. **Fix TLS on registry** — Use a valid certificate (e.g. Let's Encrypt) or add the registry CA to the node's trust store.
