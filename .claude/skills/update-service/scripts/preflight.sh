#!/usr/bin/env bash
# Read-only pre-flight checks for an update on the production host. Changes nothing.
# Reads HOST_IP, HOST_USERNAME, HOST_PRIVATE_KEY, DEPLOY_DIR, DATA_DIR from the local .env.
# Usage: bash .claude/skills/update-service/scripts/preflight.sh
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
get() { grep -E "^$1=" "$ROOT/.env" | head -1 | cut -d= -f2-; }
HOST_IP="$(get HOST_IP)"; USER_NAME="$(get HOST_USERNAME)"
DEPLOY_DIR="$(get DEPLOY_DIR)"; DATA_DIR="$(get DATA_DIR)"

KEY_DIR="$(mktemp -d)"; trap 'rm -rf "$KEY_DIR"' EXIT
get HOST_PRIVATE_KEY | base64 -d > "$KEY_DIR/k" && chmod 600 "$KEY_DIR/k"
SSH=(ssh -i "$KEY_DIR/k" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10 "$USER_NAME@$HOST_IP")

fail=0
ok()   { echo "[ok]   $*"; }
bad()  { echo "[FAIL] $*"; fail=1; }

echo "== containers"
states="$("${SSH[@]}" "cd ~/$DEPLOY_DIR && docker compose ps --format '{{.Service}} {{.State}} {{.Health}}'")" || { bad "ssh failed"; exit 1; }
while read -r svc state health; do
  case "$state:$health" in
    running:healthy|running:) ok "$svc running ${health:+($health)}" ;;
    *) bad "$svc state=$state health=$health" ;;
  esac
done <<< "$states"

echo "== disk"
free="$("${SSH[@]}" "df --output=pcent $DATA_DIR | tail -1 | tr -dc 0-9")"
[ "${free:-100}" -le 80 ] && ok "$DATA_DIR used ${free}%" || bad "$DATA_DIR used ${free}% (more than 80%)"

echo "== host checkout"
git_state="$("${SSH[@]}" "cd ~/$DEPLOY_DIR && git fetch -q origin && echo dirty=\$(git status --porcelain | wc -l) ahead=\$(git rev-list --count origin/main..HEAD) behind=\$(git rev-list --count HEAD..origin/main)")"
echo "$git_state"
case "$git_state" in *dirty=0*ahead=0*behind=0*) ok "clean and in sync with origin/main" ;;
  *) bad "host checkout differs from origin/main (see above). Ask the user before deploying." ;; esac

echo "== latest database dump"
newest="$("${SSH[@]}" "ls -t $DATA_DIR/backup/paperless/database/*.dump 2>/dev/null | head -1")"
if [ -z "$newest" ]; then bad "no paperless dump found"
else
  age_h="$("${SSH[@]}" "echo \$(( (\$(date +%s) - \$(stat -c %Y '$newest')) / 3600 ))")"
  [ "${age_h:-999}" -le 26 ] && ok "newest dump ${age_h}h old: $(basename "$newest")" || bad "newest dump is ${age_h}h old"
fi

echo "== running image versions"
"${SSH[@]}" "cd ~/$DEPLOY_DIR && docker compose config --format json | python3 -c 'import json,sys; [print(k, v.get(\"image\", \"-\")) for k, v in json.load(sys.stdin)[\"services\"].items()]' | grep -i paperless"

exit $fail
