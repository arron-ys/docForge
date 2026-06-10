#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend/docforge-web"

BACKEND_HOST="${DOCFORGE_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${DOCFORGE_BACKEND_PORT:-8000}"
FRONTEND_HOST="${DOCFORGE_FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${DOCFORGE_FRONTEND_PORT:-5173}"

BACKEND_PID=""
FRONTEND_PID=""
CLEANED_UP=0

log() {
  printf "[dev] %s\n" "$*"
}

die() {
  printf "[dev] error: %s\n" "$*" >&2
  exit 1
}

cleanup() {
  if [ "$CLEANED_UP" -eq 1 ]; then
    return
  fi
  CLEANED_UP=1

  log "stopping services..."
  terminate_tree "$FRONTEND_PID"
  terminate_tree "$BACKEND_PID"
}

stop_and_exit() {
  cleanup
  exit 130
}

terminate_tree() {
  pid="$1"
  [ -n "$pid" ] || return
  kill -0 "$pid" >/dev/null 2>&1 || return

  if command -v pgrep >/dev/null 2>&1; then
    for child_pid in $(pgrep -P "$pid" 2>/dev/null || true); do
      terminate_tree "$child_pid"
    done
  fi

  kill "$pid" >/dev/null 2>&1 || true
  wait "$pid" 2>/dev/null || true
}

choose_bootstrap_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi

  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi

  die "Python not found. Install Python 3.11/3.12."
}

ensure_backend_env() {
  if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
    BOOTSTRAP_PYTHON="$(choose_bootstrap_python)"
    log "creating backend virtualenv with $BOOTSTRAP_PYTHON"
    "$BOOTSTRAP_PYTHON" -m venv "$ROOT_DIR/.venv"
  fi

  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  log "using Python: $PYTHON_BIN"

  if ! "$PYTHON_BIN" -c "import uvicorn, fastapi" >/dev/null 2>&1; then
    log "installing backend dependencies..."
    "$PYTHON_BIN" -m pip install --upgrade pip
    "$PYTHON_BIN" -m pip install -e "$ROOT_DIR"
  fi
}

wait_for_backend() {
  url="http://$BACKEND_HOST:$BACKEND_PORT/healthz"
  attempts=60

  while [ "$attempts" -gt 0 ]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "backend healthy: $url"
      return
    fi
    attempts=$((attempts - 1))
    sleep 1
  done

  log "backend health check did not pass yet: $url"
}

needs_pnpm_install() {
  [ ! -d "$FRONTEND_DIR/node_modules" ] && return 0
  [ "$FRONTEND_DIR/pnpm-lock.yaml" -nt "$FRONTEND_DIR/node_modules" ] && return 0
  [ "$FRONTEND_DIR/package.json" -nt "$FRONTEND_DIR/node_modules" ] && return 0
  return 1
}

trap cleanup EXIT
trap stop_and_exit INT TERM

[ -d "$FRONTEND_DIR" ] || die "frontend directory not found: $FRONTEND_DIR"

cd "$ROOT_DIR"

log "checking frontend toolchain..."
"$ROOT_DIR/scripts/check_frontend_env.sh"

ensure_backend_env

if needs_pnpm_install; then
  log "installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && pnpm install)
else
  log "frontend dependencies already installed."
fi

log "starting FastAPI on http://$BACKEND_HOST:$BACKEND_PORT"
"$PYTHON_BIN" -m uvicorn api.main:app --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT" &
BACKEND_PID="$!"

wait_for_backend

log "starting Vue on http://127.0.0.1:$FRONTEND_PORT/"
(cd "$FRONTEND_DIR" && pnpm exec vite --host "$FRONTEND_HOST" --port "$FRONTEND_PORT") &
FRONTEND_PID="$!"

cat <<EOF

DocForge dev services are running.

Backend health: http://$BACKEND_HOST:$BACKEND_PORT/healthz
Frontend:       http://127.0.0.1:$FRONTEND_PORT/
Workspace URL:  http://127.0.0.1:$FRONTEND_PORT/

Press Ctrl-C to stop both services.

EOF

while true; do
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    die "backend process exited."
  fi
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    die "frontend process exited."
  fi
  sleep 2
done
