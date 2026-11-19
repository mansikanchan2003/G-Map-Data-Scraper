#!/bin/sh
# Claude CLI answers the questions the bot could not (19 Nov 2026). Every minute, the app lists
# the waiting ones (each with its prompt: the question with names and numbers taken out, the
# language, SBI or ESAF, and Eko's confirmed facts); Claude answers each; the app checks the
# answer against Eko's word rules, sends it, solves the ticket "by Claude CLI" and learns it.
# An unsound answer or "cannot answer" leaves the question with the team.
#
# Runs from mansi's own crontab, like the bot coach:
#   * * * * * $HOME/bin/run_claude_answers.sh >> $HOME/autogmap_claude_answers.log 2>&1
# Claude runs with ASK_USER's own Claude CLI login (default mansi). It may only answer: no
# tools (no shell, no files, no web), one turn, in an empty folder. One run at a time.
set -e
ASK_USER="${ASK_USER:-mansi}"
CONTAINER="${ASK_CONTAINER:-autogmap-backend-1}"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
exec 9>"${TMPDIR:-/tmp}/autogmap_claude_answers.lock"
flock -n 9 || exit 0

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
docker exec -i "$CONTAINER" python -m src.services.claude_answers pending < /dev/null > "$work/pending.json"
[ "$(cat "$work/pending.json")" = "[]" ] && exit 0

ask_claude='
  export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
  cd "$(mktemp -d)"
  claude -p --output-format json --max-turns 1 \
    --disallowedTools "Bash Edit Write MultiEdit NotebookEdit Read Glob Grep WebFetch WebSearch Task TodoWrite"
'
# One line per question: its id, then its prompt (JSON-escaped), read with python3 on the host.
python3 -c 'import json,sys; [print(q["id"]+"\t"+json.dumps(q["prompt"])) for q in json.load(open(sys.argv[1]))]' \
  "$work/pending.json" > "$work/list.tsv"
while IFS="$(printf '\t')" read -r id prompt; do
  printf '%s' "$prompt" | python3 -c 'import json,sys; sys.stdout.write(json.loads(sys.stdin.read()))' > "$work/prompt.txt"
  if [ "$(id -un)" = "$ASK_USER" ]; then
    sh -c "$ask_claude" < "$work/prompt.txt" > "$work/answer.json" || echo '{"result":"{\"can_answer\": false, \"why\": \"Claude CLI failed\"}"}' > "$work/answer.json"
  else
    sudo -u "$ASK_USER" -H sh -c "$ask_claude" < "$work/prompt.txt" > "$work/answer.json" || echo '{"result":"{\"can_answer\": false, \"why\": \"Claude CLI failed\"}"}' > "$work/answer.json"
  fi
  docker exec -i "$CONTAINER" python -m src.services.claude_answers answer "$id" < "$work/answer.json"
done < "$work/list.tsv"
echo "$(date '+%F %T') claude answers done"
