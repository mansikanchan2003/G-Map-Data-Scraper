#!/bin/sh
# The bot coach, once a day: the app writes Claude's brief (anonymised counts,
# the bot's own messages, Eko's FAQ and the questions people asked with names
# and numbers taken out), Claude answers, and the app checks the answer and
# adds the sound proposals to the learning loop for the admin to accept.
# Nothing reaches a candidate until the admin accepts it.
#
# Who runs what (the user, 2026-11-06):
#   - root runs this script, for the docker steps (from root's crontab):
#       0 5 * * * /home/mansi/AUTOGMAP/scripts/run_bot_coach.sh >> /root/autogmap_bot_coach.log 2>&1
#   - Claude runs as COACH_USER (default mansi), with that user's own Claude
#     CLI login in their home folder. Root never signs in to Claude.
#   - Claude may only answer: no tools (no shell, no files, no web), one turn,
#     in an empty folder.
set -e
COACH_USER="${COACH_USER:-mansi}"
cd "$(dirname "$0")/.."
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
brief="$work/brief.txt" answer="$work/answer.json"

docker compose exec -T backend python -m src.services.bot_coach brief < /dev/null > "$brief"

# Root opens the files; Claude only reads its prompt on stdin and writes its answer on stdout.
sudo -u "$COACH_USER" -H sh -c '
  export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
  cd "$(mktemp -d)"
  claude -p --output-format json --max-turns 1 \
    --disallowedTools "Bash Edit Write MultiEdit NotebookEdit Read Glob Grep WebFetch WebSearch Task TodoWrite"
' < "$brief" > "$answer"

docker compose exec -T backend python -m src.services.bot_coach ingest < "$answer"
echo "$(date '+%F %T') bot coach done"
