#!/usr/bin/env bash

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${VENV_DIR:-$REPO_DIR/.venv}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-5000}"
FLASK_ENV="${FLASK_ENV:-development}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}"
GUNICORN_THREADS="${GUNICORN_THREADS:-8}"

cd "$REPO_DIR"

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
    -b "${HOST}:${PORT}" \
    run:app
fi

echo "==> Starting Orchard UI with Flask on ${HOST}:${PORT}"
export PORT
exec "$VENV_DIR/bin/python" run.py
