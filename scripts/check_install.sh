#!/usr/bin/env bash
# One-command check that LabMeter Suite installs and runs.
# It uses a temporary database and leaves your real data alone.
#
# Usage (from the project root, with the virtual environment active):
#     bash scripts/check_install.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
TMP="$(mktemp -d)"
PORT="${CHECK_PORT:-8765}"
PASS="ephemeral-check-password-1"
API_PID=""
cleanup() {
  if [ -n "$API_PID" ]; then kill "$API_PID" 2>/dev/null || true; fi
  rm -rf "$TMP"
}
trap cleanup EXIT

step() { printf '\n==> %s\n' "$1"; }
fail() { printf '\nFAILED: %s\n' "$1" >&2; exit 1; }

step "Python version (3.11 to 3.14 supported)"
python3 -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 14) else 1)" \
  || fail "this project supports Python 3.11 to 3.14; you are running $(python3 --version)"
echo "$(python3 --version)"

step "Required packages import"
python3 -c "import fastapi, sqlalchemy, alembic, sklearn, joblib, psycopg, pandas, numpy, pydantic" \
  || fail "run: pip install -r requirements.txt"

step "Database migrations on a temporary SQLite database"
export DATABASE_URL="sqlite:///$TMP/check.db"
alembic upgrade head >/dev/null || fail "alembic upgrade head"

step "Create a temporary administrator"
LABMETER_ADMIN_PASSWORD="$PASS" python3 scripts/create_admin.py --email check@example.test >/dev/null \
  || fail "create_admin.py"

step "Start the API on port $PORT"
python3 -m uvicorn app.main:app --port "$PORT" >"$TMP/api.log" 2>&1 &
API_PID=$!
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -sf "http://127.0.0.1:$PORT/api/health" | grep -q '"ok"' \
  || { cat "$TMP/api.log"; fail "health check did not return ok"; }

step "Anonymous access is refused"
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/labs")
[ "$code" = "401" ] || fail "expected 401 for anonymous /api/labs, got $code"

step "Sign-in returns a token"
token=$(curl -sf -X POST "http://127.0.0.1:$PORT/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"check@example.test\",\"password\":\"$PASS\"}" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["token"])') || fail "sign-in failed"

step "A signed-in request is accepted"
curl -sf "http://127.0.0.1:$PORT/api/auth/me" -H "Authorization: Bearer $token" | grep -q 'check@example.test' \
  || fail "/api/auth/me did not return the signed-in user"

step "Frontend build (needs Node.js and frontend/node_modules)"
if command -v npm >/dev/null 2>&1 && [ -d frontend/node_modules ]; then
  (cd frontend && npm run build >/dev/null) || fail "frontend build"
  echo "frontend built"
else
  echo "skipped: run 'cd frontend && npm install' first, then this script again"
fi

printf '\nAll checks passed. The API installs, starts, enforces sign-in, and accepts a signed-in request.\n'
