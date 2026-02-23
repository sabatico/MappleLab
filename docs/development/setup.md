# Development Setup

## Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
bash scripts/setup_novnc.sh
cp .env.example .env
```

## Run in Development

```bash
source .venv/bin/activate
python run.py
```

Or:

```bash
./run.sh
```

## Useful Paths

- App factory: `app/__init__.py`
- Config: `config.py`
- Entry: `run.py`
- Tests: `tests/`

## Test and Validation

- Route smoke checks via browser and Flask logs
- VM lifecycle checks in dashboard
- Console checks with running VM
- Validate `GET /console/<vm_name>/vncloc` returns an attachment for running, owned VMs
- Confirm manager direct TCP range (`VNC_DIRECT_PORT_MIN/MAX`) is reachable from client Macs when using native Screen Sharing
- Validate admin usage page (`GET /admin/usage`) renders grouped VM lifetime bars
- Confirm status transitions and websocket connect/disconnect generate `vm_status_events` and `vm_vnc_sessions` rows
