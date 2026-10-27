#!/usr/bin/env bash
# Start the whole app locally: the FastAPI backend and the Vite frontend, stopped together with Ctrl-C.
#
#   npm run dev                                   # from the repo root (or: bash scripts/dev.sh)
#   BACKEND_PORT=8400 FRONTEND_PORT=5400 npm run dev
#
# Defaults: backend http://127.0.0.1:8390, app http://localhost:5390 (chosen so they don't clash with other local
# projects). With a .env file the backend uses it (real Claude, voice); without one it runs GUIDE_LLM=offline.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8390}"
FRONTEND_PORT="${FRONTEND_PORT:-5390}"

for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "port $port is already in use; stop that process or set BACKEND_PORT / FRONTEND_PORT" >&2
    exit 1
  fi
done

cd "$ROOT"
uv sync --quiet
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install)
fi

if [ -f .env ]; then
  backend=(uv run --env-file .env uvicorn backend.api.app:app --port "$BACKEND_PORT")
else
  echo "no .env: the Guide runs offline (copy .env.example to .env for real Claude)"
  backend=(env GUIDE_LLM=offline uv run uvicorn backend.api.app:app --port "$BACKEND_PORT")
fi

stop_tree() {  # a process and everything it started (uv → uvicorn, npx → vite), deepest first
  local child
  [ -n "$1" ] || return 0
  for child in $(pgrep -P "$1"); do stop_tree "$child"; done
  kill "$1" 2>/dev/null || true
}
stop() {
  trap - INT TERM EXIT
  stop_tree "$backend_pid"
  stop_tree "$frontend_pid"
}
backend_pid="" frontend_pid=""
trap stop INT TERM EXIT  # Ctrl-C or one side exiting stops both; only our own processes, never the caller's group
"${backend[@]}" &
backend_pid=$!
(cd frontend && BACKEND_URL="http://127.0.0.1:$BACKEND_PORT" exec npx vite --port "$FRONTEND_PORT" --strictPort) &
frontend_pid=$!
echo "app: http://localhost:$FRONTEND_PORT   backend: http://127.0.0.1:$BACKEND_PORT"
while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
  sleep 1  # macOS ships bash 3.2, which has no `wait -n`
done
