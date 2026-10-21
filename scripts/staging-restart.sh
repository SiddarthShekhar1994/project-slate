#!/usr/bin/env bash
# A second, production-built copy of the app on ports 8001/3001 for testing
# without disturbing the dev servers on 8000/3000.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/var"
pkill -f "[u]vicorn slate_api.main:app --host 127.0.0.1 --port 8001" || true
pkill -f "[n]ext start -p 3001" || true
sleep 1
(cd "$ROOT" && TTS_PROVIDER="${TTS_PROVIDER:-silent}" nohup uv run uvicorn slate_api.main:app --host 127.0.0.1 --port 8001 > var/api-8001.log 2>&1 &)
(cd "$ROOT/apps/web" && API_ORIGIN=http://127.0.0.1:8001 pnpm build > ../../var/build-3001.log 2>&1) || { tail -20 "$ROOT/var/build-3001.log"; exit 1; }
(cd "$ROOT/apps/web" && nohup pnpm exec next start -p 3001 -H 127.0.0.1 > ../../var/web-3001.log 2>&1 &)
for _ in $(seq 1 40); do
  curl -s http://127.0.0.1:3001/api/health 2>/dev/null | grep -q ok && { echo "staging up"; exit 0; }
  sleep 1
done
echo "staging did not come up" >&2
exit 1
