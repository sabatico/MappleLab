#!/usr/bin/env bash

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${VENV_DIR:-$REPO_DIR/.venv}"
RUN_DIR="${RUN_DIR:-$REPO_DIR/run}"
PID_FILE="${PID_FILE:-$RUN_DIR/orchard_ui.pid}"
AUTO_STOP_EXISTING="${AUTO_STOP_EXISTING:-true}"

cd "$REPO_DIR"

# Load .env if present so FLASK_ENV/PORT and related vars are honored.
if [[ -f "$REPO_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_DIR/.env"
  set +a
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-5000}"
FLASK_ENV="${FLASK_ENV:-development}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}"
GUNICORN_THREADS="${GUNICORN_THREADS:-8}"

mkdir -p "$RUN_DIR"

is_orchard_process() {
  local pid="$1"
  local cmd
  cmd="$(ps -o command= -p "$pid" 2>/dev/null || true)"
  [[ "$cmd" == *"gunicorn"*run:app* || "$cmd" == *"python"*run.py* ]]
}

stop_pid_if_running() {
  local pid="$1"
  if ! kill -0 "$pid" 2>/dev/null; then
    return 0
  fi
  if ! is_orchard_process "$pid"; then
    return 1
  fi

  echo "==> Stopping existing Orchard UI process (pid=$pid)"
  kill "$pid" 2>/dev/null || true
  for _ in {1..20}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.25
  done
  echo "==> Existing process did not stop gracefully; forcing kill"
  kill -9 "$pid" 2>/dev/null || true
}

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${existing_pid:-}" ]]; then
    if [[ "$AUTO_STOP_EXISTING" == "true" ]]; then
      stop_pid_if_running "$existing_pid" || true
    fi
  fi
  rm -f "$PID_FILE"
fi

port_pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "${port_pids:-}" ]]; then
  if [[ "$AUTO_STOP_EXISTING" == "true" ]]; then
    for pid in $port_pids; do
      if is_orchard_process "$pid"; then
        stop_pid_if_running "$pid" || true
      fi
    done
  fi
fi

still_bound_pid="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "${still_bound_pid:-}" ]]; then
  echo "!! Port $PORT is already in use (pid(s): $still_bound_pid)."
  echo "   Set a different PORT, or free that port and retry."
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "==> Creating virtualenv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

echo "==> Ensuring dependencies are installed"
"$VENV_DIR/bin/pip" install -r requirements.txt

if [[ "$FLASK_ENV" == "production" ]]; then
  echo "==> Starting Orchard UI with gunicorn on ${HOST}:${PORT} (workers=${GUNICORN_WORKERS}, threads=${GUNICORN_THREADS})"
  exec "$VENV_DIR/bin/gunicorn" \
    -w "$GUNICORN_WORKERS" \
    --threads "$GUNICORN_THREADS" \
    --pid "$PID_FILE" \
    -b "${HOST}:${PORT}" \
    run:app
fi

echo "==> Starting Orchard UI with Flask on ${HOST}:${PORT}"
export PORT
exec "$VENV_DIR/bin/python" run.py
