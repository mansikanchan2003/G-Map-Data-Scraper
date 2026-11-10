#!/bin/sh
# The bot coach, once a day: the app writes Claude's brief (anonymised counts,
# the bot's own messages, Eko's FAQ and the questions people asked with names
# and numbers taken out), Claude answers, and the app checks the answer and
# adds the sound proposals to the learning loop for the admin to accept.
# Nothing reaches a candidate until the admin accepts it.
#
# Runs from mansi's own crontab (she can use docker; 2026-11-10), 05:00 IST daily:
#   0 5 * * * /home/mansi/AUTOGMAP/scripts/run_bot_coach.sh >> $HOME/autogmap_bot_coach.log 2>&1
# Claude runs with COACH_USER's own Claude CLI login (default mansi). Run as
# root, the Claude step still runs as COACH_USER, so root never signs in.
# Claude may only answer: no tools (no shell, no files, no web), one turn, in
# an empty folder.
set -e
COACH_USER="${COACH_USER:-mansi}"
CONTAINER="${COACH_CONTAINER:-autogmap-backend-1}"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
brief="$work/brief.txt" answer="$work/answer.json"

# docker exec, not docker compose: compose reads .env, which only root may read.
docker exec -i "$CONTAINER" python -m src.services.bot_coach brief < /dev/null > "$brief"

ask_claude='
  export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
  cd "$(mktemp -d)"
  claude -p --output-format json --max-turns 1 \
    --disallowedTools "Bash Edit Write MultiEdit NotebookEdit Read Glob Grep WebFetch WebSearch Task TodoWrite"
'
if [ "$(id -un)" = "$COACH_USER" ]; then
  sh -c "$ask_claude" < "$brief" > "$answer"
else
  # Root opens the files; Claude only reads its prompt on stdin and writes its answer on stdout.
  sudo -u "$COACH_USER" -H sh -c "$ask_claude" < "$brief" > "$answer"
fi

docker exec -i "$CONTAINER" python -m src.services.bot_coach ingest < "$answer"
echo "$(date '+%F %T') bot coach done"
