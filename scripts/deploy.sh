#!/usr/bin/env bash
# Deploy AutoGMap on the R730, the same way every time (DEPLOYMENT.md).
#
#   cd /home/mansi/AUTOGMAP && bash scripts/deploy.sh
#
# 1. Stops unless GitHub's CI is green for the commit being deployed.
# 2. Waits for the gap between scraping batches (no job running).
# 3. Notes the commit running now, for scripts/rollback.sh.
# 4. Pulls, builds, and runs the golden set on the new image: stops if it fails.
# 5. Backs the database up (backups/), then runs the migrations.
# 6. Starts the new backend and waits for /health to say healthy.
#
# Touches only this folder and its own containers. Never deletes anything.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
REPO="mansikanchan2003/G-Map-Data-Scraper"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p .deploy backups
say() { printf '\n== %s\n' "$*"; }
stop() { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }
# One setting from .env, read as text (never run: a value may hold spaces or $).
envval() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"'"; }

# -- What is running now, and what would be deployed ------------------------------
CURRENT="$(git rev-parse HEAD)"
git checkout -q main 2>/dev/null || true
git fetch -q origin main
TARGET="$(git rev-parse origin/main)"
say "Running: ${CURRENT:0:7}   Deploying: ${TARGET:0:7}"
if [ "$CURRENT" = "$TARGET" ] && [ "${1:-}" != "--again" ]; then
  echo "Already on the newest commit. Nothing to do (add --again to rebuild anyway)."
  exit 0
fi

# -- 1. CI must be green for it ------------------------------------------------------
say "1/6 CI for ${TARGET:0:7}"
CI="$(curl -fsS "https://api.github.com/repos/$REPO/commits/$TARGET/check-runs?per_page=50" 2>/dev/null \
  | python3 -c 'import json,sys
runs=[r for r in json.load(sys.stdin).get("check_runs",[]) if r["name"] in ("Tests and golden set","Frontend build")]
print("missing" if len(runs)<2 else "running" if any(r["status"]!="completed" for r in runs)
      else "green" if all(r["conclusion"]=="success" for r in runs) else "red")' 2>/dev/null || echo unknown)"
case "$CI" in
  green) echo "CI is green." ;;
  running) stop "CI is still running for this commit. Try again in a few minutes." ;;
  red) stop "CI failed for this commit: https://github.com/$REPO/commit/$TARGET/checks" ;;
  *) if [ "${1:-}" = "--without-ci" ]; then echo "CI not checked ($CI): going on, as asked."
     else stop "Could not read CI ($CI). Check https://github.com/$REPO/actions, then run with --without-ci."; fi ;;
esac

# -- 2. Not in the middle of a scraping batch ------------------------------------------
say "2/6 Scraping"
RUNNING="$(timeout 60 docker compose exec -T backend python -c '
from src.database import SessionLocal
from src.models import Job
db = SessionLocal(); print(db.query(Job).filter(Job.status == "RUNNING").count())' < /dev/null 2>/dev/null | tail -1 || echo "?")"
if [ "$RUNNING" != "0" ] && [ "$RUNNING" != "?" ]; then
  stop "$RUNNING scraping job(s) running. Deploy in the gap between batches (try again in a few minutes)."
fi
echo "No scraping job running."

# The settings hold every key: readable by their owner only.
chmod 600 .env 2>/dev/null || true

# -- 3. Remember what was running ---------------------------------------------------------
echo "$CURRENT" > .deploy/previous
echo "$STAMP ${CURRENT:0:7} -> ${TARGET:0:7} started" >> .deploy/history

# -- 4. Pull, build, golden set -------------------------------------------------------------
say "3/6 Pull and build"
git pull -q --ff-only origin main
docker compose build backend
say "4/6 Golden set on the new image"
docker compose run --rm --name "autogmap-golden-$STAMP" backend python -m src.evals.golden --save \
  || stop "The golden set failed. Nothing was changed: the old backend is still running."

# -- 5. Back up, migrate ------------------------------------------------------------------------
say "5/6 Database backup and migrations"
PGUSER_="$(envval POSTGRES_USER)"; PGDB_="$(envval POSTGRES_DB)"
BACKUP="backups/before-${TARGET:0:7}-$STAMP.sql.gz"
docker compose exec -T postgres pg_dump -U "${PGUSER_:-gmap_user}" "${PGDB_:-gmap_scraper}" < /dev/null \
  | gzip > "$BACKUP"
[ -s "$BACKUP" ] || stop "The database backup is empty. Nothing was migrated."
echo "Backed up to $BACKUP ($(du -h "$BACKUP" | cut -f1))."
docker compose run --rm --name "autogmap-migrate-$STAMP" backend alembic upgrade head

# -- 6. Start and check ---------------------------------------------------------------------------
say "6/6 Start"
docker compose up -d backend
PORT="$(envval BACKEND_HOST_PORT)"; PORT="${PORT:-8000}"
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"status":"healthy"'; then
    echo "$STAMP ${CURRENT:0:7} -> ${TARGET:0:7} healthy" >> .deploy/history
    say "Deployed ${TARGET:0:7}. Healthy. To go back: bash scripts/rollback.sh"
    exit 0
  fi
  sleep 4
done
echo "$STAMP ${CURRENT:0:7} -> ${TARGET:0:7} NOT healthy" >> .deploy/history
stop "The new backend did not report healthy within 2 minutes. See: docker compose logs backend --since 5m
To go back to ${CURRENT:0:7}: bash scripts/rollback.sh"
