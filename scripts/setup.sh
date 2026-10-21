#!/usr/bin/env bash
# One-time setup on macOS, Linux or Windows (inside WSL): the settings file,
# the database, Python and web packages, and the database tables.
# Safe to run again; it skips what is already done.
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n==> %s\n' "$1"; }
fail() { printf '\n%s\n' "$1" >&2; exit 1; }

command -v uv >/dev/null || fail "uv is missing. Install it from https://docs.astral.sh/uv/getting-started/installation/"
command -v node >/dev/null || fail "Node is missing. Install Node 24 LTS from https://nodejs.org"
node -e '
  const [a, b, c] = process.versions.node.split(".").map(Number);
  process.exit(a > 22 || (a === 22 && (b > 22 || (b === 22 && c >= 2))) ? 0 : 1);
' || fail "Node $(node -v) is too old for the web app's tools. Install Node 24 LTS (or 22.22.2 or newer)."
command -v pnpm >/dev/null || fail "pnpm is missing. Run 'corepack enable' (or 'npm install -g pnpm@10'), then run this again."

if [ ! -f .env ]; then
  cp .env.example .env
  step "Created .env from .env.example (API keys are optional; add them there later)"
fi

step "Starting PostgreSQL"
if [ "${SLATE_LOCAL_POSTGRES:-}" = "1" ] || ! command -v docker >/dev/null; then
  echo "Using the PostgreSQL at DATABASE_URL in .env."
elif ! docker info >/dev/null 2>&1; then
  fail "Docker is installed but not running. Start Docker Desktop and run this again.
To use your own PostgreSQL instead, run: SLATE_LOCAL_POSTGRES=1 scripts/setup.sh"
else
  docker compose up -d --wait postgres || fail "Couldn't start PostgreSQL in Docker. If another PostgreSQL
is already using port 5432, stop it, or use it instead (see 'Without Docker' in the README)."
  # A database volume from before slate_test was added doesn't have it yet.
  docker compose exec -T postgres psql -U slate -d slate -tAc "SELECT 1 FROM pg_database WHERE datname = 'slate_test'" \
    | grep -q 1 || docker compose exec -T postgres createdb -U slate slate_test
fi

step "Installing Python packages"
uv sync --all-packages

step "Installing web packages"
pnpm --dir apps/web install

step "Creating the database tables"
uv run --env-file .env alembic -c apps/api/alembic.ini upgrade head || fail "Couldn't set up the database.
With Docker: start Docker Desktop and run scripts/setup.sh again.
Without Docker: make sure PostgreSQL 16 is running and has the role and database
in DATABASE_URL (see 'Without Docker' in the README)."

step "Done. Start Slate with: scripts/start.sh"
