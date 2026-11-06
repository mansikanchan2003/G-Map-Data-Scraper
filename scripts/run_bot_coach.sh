#!/bin/sh
# The bot coach, once a day: the app writes Claude's brief (anonymised counts,
# the bot's own messages, Eko's FAQ and the questions people asked with names
# and numbers taken out), Claude answers through Mansi's Claude CLI login on
# this server, and the app checks the answer and adds the sound proposals to
# the learning loop for the admin to accept. Nothing reaches a candidate
# until the admin accepts it.
#
# Runs as the user whose Claude CLI is signed in (`claude` must work for them)
# and who can run docker (root, like the deploy). From that user's crontab,
# 05:00 IST daily:
#   0 5 * * * /home/mansi/AUTOGMAP/scripts/run_bot_coach.sh >> /root/autogmap_bot_coach.log 2>&1
set -e
# cron starts with a short PATH; Claude Code installs to ~/.local/bin or the npm global bin.
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
cd "$(dirname "$0")/.."
brief=$(mktemp) answer=$(mktemp)
trap 'rm -f "$brief" "$answer"' EXIT
docker compose exec -T backend python -m src.services.bot_coach brief < /dev/null > "$brief"
# --max-turns 1: one answer, no tools. Claude's own reply only.
claude -p --output-format json --max-turns 1 < "$brief" > "$answer"
docker compose exec -T backend python -m src.services.bot_coach ingest < "$answer"
echo "$(date '+%F %T') bot coach done"
