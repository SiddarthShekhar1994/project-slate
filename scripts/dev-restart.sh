#!/usr/bin/env bash
# Restart the local API and/or web dev servers in the background.
#   scripts/dev-restart.sh api|web|all
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/var"
target="${1:-all}"

wait_for() {
  for _ in $(seq 1 40); do
    curl -s -o /dev/null -w "%{http_code}" "$1" 2>/dev/null | grep -q 200 && return 0
    sleep 1
  done
  echo "timed out waiting for $1" >&2
  return 1
}

if [[ "$target" == api || "$target" == all ]]; then
  pkill -f "[u]vicorn slate_api.main:app" || true
  sleep 1
  (cd "$ROOT" && nohup uv run uvicorn slate_api.main:app --host 127.0.0.1 --port 8000 > var/api.log 2>&1 &)
  wait_for http://127.0.0.1:8000/api/health && echo "api up"
fi
if [[ "$target" == web || "$target" == all ]]; then
  pkill -f "[n]ext dev" || true
  pkill -f "[n]ext-server" || true
  sleep 1
  (cd "$ROOT/apps/web" && nohup pnpm dev --port 3000 > ../../var/web.log 2>&1 &)
  wait_for http://127.0.0.1:3000/login && echo "web up"
fi
