#!/usr/bin/env bash
# Staging: run a commit on a separate copy of AutoGMap before it goes to
# production (DEPLOYMENT.md).
#
#   cd /home/mansi/AUTOGMAP && bash scripts/staging.sh            # the newest main
#   cd /home/mansi/AUTOGMAP && bash scripts/staging.sh <commit>   # a commit or branch
#
# The copy lives in /home/mansi/AUTOGMAP-staging (a git worktree of this folder),
# with its own .env, containers, database and data/. Nothing in it can message
# anyone or reach a real service (docker-compose.staging.yml). It answers only
# on the server itself, port 8100; from a laptop, through an SSH tunnel:
#
#   ssh -p 2222 -L 8100:127.0.0.1:8100 mansi@indev.eko.in     then open http://localhost:8100
#
# Never deletes anything. To stop it:  bash scripts/staging.sh --stop
set -euo pipefail

cd "$(dirname "$0")/.."
PROD="$(pwd)"
STAGE="${STAGING_DIR:-$(dirname "$PROD")/AUTOGMAP-staging}"
COMPOSE=(docker compose -p autogmap-staging -f docker-compose.yml -f docker-compose.staging.yml)
stop() { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }

if [ "${1:-}" = "--stop" ]; then
  [ -d "$STAGE" ] || stop "No staging copy at $STAGE."
  cd "$STAGE" && "${COMPOSE[@]}" stop
  echo "Staging stopped. Its database and files are kept; run the script again to start it."
  exit 0
fi

REF="${1:-origin/main}"
git fetch -q origin
COMMIT="$(git rev-parse "$REF^{commit}")" || stop "No such commit or branch: $REF"

# -- The copy of the code ----------------------------------------------------------------
if [ ! -d "$STAGE" ]; then
  git worktree add -q --detach "$STAGE" "$COMMIT"
  echo "Made the staging copy at $STAGE."
else
  git -C "$STAGE" checkout -q --detach "$COMMIT"
fi
cd "$STAGE"
echo "Staging: ${COMMIT:0:7} $(git log -1 --format=%s | cut -c1-70)"

# -- Its own settings, made once: new secrets, its own ports, no real keys -------------------
if [ ! -f .env ]; then
  read -r -s -p "Choose a password for the staging admin (mansi.kanchan.intern@eko.co.in): " ADMIN_PW; echo
  [ ${#ADMIN_PW} -ge 10 ] || stop "Use at least 10 characters."
  umask 077
  cat > .env <<EOF
# Staging only (scripts/staging.sh). Not production's: its own database and secrets.
POSTGRES_PASSWORD=$(openssl rand -hex 24)
AUTH_JWT_SECRET=$(openssl rand -hex 32)
BOOTSTRAP_ADMIN_PASSWORD=$ADMIN_PW
BACKEND_HOST_PORT=8100
POSTGRES_HOST_PORT=5433
N8N_HOST_PORT=5679
VITE_BASE_PATH=/
BACKEND_MEMORY_LIMIT=2g
EOF
  unset ADMIN_PW
  echo "Wrote $STAGE/.env (new secrets; production's .env is not used)."
fi

# -- Build, migrate, start -----------------------------------------------------------------------
"${COMPOSE[@]}" build backend
"${COMPOSE[@]}" up -d postgres
"${COMPOSE[@]}" run --rm backend alembic upgrade head
"${COMPOSE[@]}" up -d backend
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:8100/health" 2>/dev/null | grep -q '"status":"healthy"'; then
    echo
    echo "Staging is up on ${COMMIT:0:7}. From your laptop:"
    echo "  ssh -p 2222 -L 8100:127.0.0.1:8100 mansi@indev.eko.in"
    echo "then open http://localhost:8100 and sign in as mansi.kanchan.intern@eko.co.in."
    exit 0
  fi
  sleep 4
done
stop "Staging did not report healthy within 2 minutes. See: cd $STAGE && ${COMPOSE[*]} logs backend --since 5m"
