#!/usr/bin/env bash
# Go back to the commit that ran before the last deploy (or one you name)
# (DEPLOYMENT.md).
#
#   cd /home/mansi/AUTOGMAP && bash scripts/rollback.sh            # the one before the last deploy
#   cd /home/mansi/AUTOGMAP && bash scripts/rollback.sh 1f04fba    # a commit you name
#
# The code goes back; the database is left as it is. AutoGMap's migrations only
# add tables and columns, so older code runs on a newer database. If a
# migration itself is the problem, restore the backup the deploy took
# (DEPLOYMENT.md, "Restoring the database"): that is a separate, deliberate step.
#
# The next scripts/deploy.sh returns to main. Never deletes anything.
set -euo pipefail

cd "$(dirname "$0")/.."
STAMP="$(date +%Y%m%d-%H%M%S)"
stop() { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }

TO="${1:-$(cat .deploy/previous 2>/dev/null || true)}"
[ -n "$TO" ] || stop "No earlier deploy is recorded. Name a commit: bash scripts/rollback.sh <commit>"
git cat-file -e "$TO^{commit}" 2>/dev/null || stop "No such commit here: $TO"
NOW="$(git rev-parse HEAD)"
TO="$(git rev-parse "$TO")"
echo "Running: ${NOW:0:7}   Going back to: ${TO:0:7} ($(git log -1 --format=%s "$TO" | cut -c1-70))"

# Migrations added since then stay in the database: say so.
ADDED="$(git diff --name-only "$TO" "$NOW" -- alembic/versions | wc -l)"
if [ "$ADDED" != "0" ]; then
  echo "Note: $ADDED migration file(s) came after ${TO:0:7}. Their tables and columns stay in the database;"
  echo "the older code does not use them. Restore a backup only if a migration itself is the problem."
fi

read -r -p "Go back to ${TO:0:7}? [y/N] " OK
[ "$OK" = "y" ] || [ "$OK" = "Y" ] || stop "Nothing changed."

mkdir -p .deploy
echo "$STAMP rollback ${NOW:0:7} -> ${TO:0:7} started" >> .deploy/history
git checkout -q --detach "$TO"
docker compose build backend
docker compose up -d backend
# Read as text, never run: a .env value may hold spaces or $.
PORT="$(grep -E '^BACKEND_HOST_PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"'")"; PORT="${PORT:-8000}"
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"status":"healthy"'; then
    echo "$STAMP rollback ${NOW:0:7} -> ${TO:0:7} healthy" >> .deploy/history
    echo "Back on ${TO:0:7}. Healthy."
    exit 0
  fi
  sleep 4
done
echo "$STAMP rollback ${NOW:0:7} -> ${TO:0:7} NOT healthy" >> .deploy/history
stop "Not healthy within 2 minutes. See: docker compose logs backend --since 5m"
