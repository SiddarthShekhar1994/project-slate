#!/usr/bin/env bash
# Run Slate: the API on http://localhost:8000 and the web app on
# http://localhost:3000, with the settings in .env. Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Run scripts/setup.sh first." >&2; exit 1; }

# After a reboot, bring back the Docker database if setup created one.
if command -v docker >/dev/null && docker info >/dev/null 2>&1 \
  && [ -n "$(docker compose ps --all --quiet postgres 2>/dev/null)" ]; then
  docker compose up -d --wait postgres >/dev/null
fi

in_use() { command -v curl >/dev/null && curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$1/"; }
for port in 8000 3000; do
  if in_use "$port"; then
    echo "Port $port is already in use, maybe by Slate in another terminal. Stop that first." >&2
    exit 1
  fi
done

uv run --env-file .env uvicorn slate_api.main:app --host 127.0.0.1 --port 8000 &
api=$!
trap 'kill "$api" 2>/dev/null || true; wait "$api" 2>/dev/null || true' EXIT

# Start the web app once the API answers, so its first requests don't fail.
if command -v curl >/dev/null; then
  for _ in $(seq 1 120); do
    kill -0 "$api" 2>/dev/null || {
      echo "The API stopped while starting (see above). Is the database running? With Docker, start" >&2
      echo "Docker Desktop and run scripts/start.sh again." >&2
      exit 1
    }
    curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break
    sleep 1
  done
fi

echo
echo "Slate is running. Open http://localhost:3000 (Ctrl-C stops it)."
echo
pnpm --dir apps/web dev --port 3000
