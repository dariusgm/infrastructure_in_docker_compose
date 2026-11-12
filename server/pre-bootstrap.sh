#!/usr/bin/env bash
# One-time host step, run by deploy.py before bootstrap.sh. Installs a sudoers allowlist, so that
# later deploys run the root steps without a password. Only these commands are allowed without a
# password, each by its full path:
#   - apt-get update -qq, and apt-get install of git and ca-certificates (only that package list)
#   - server/bootstrap.sh, server/consume-mount.sh and server/immich-originals-mount.sh of this repo
# The scripts are run directly, not through bash, so bash itself is not allowed.
#
# The scripts stay in the repository, so a change to them runs as root without a password. That is
# the trade-off this allowlist accepts: it limits what runs, not who may change the code.
#
# Usage: sudo bash server/pre-bootstrap.sh <run_user> <absolute deploy dir>
set -euo pipefail

RUN_USER="${1:?usage: pre-bootstrap.sh <run_user> <deploy dir>}"
DEPLOY_DIR="${2:?usage: pre-bootstrap.sh <run_user> <deploy dir>}"
SUDOERS=/etc/sudoers.d/infrastructure-deploy

if [ "$(id -u)" -ne 0 ]; then
  echo "pre-bootstrap.sh must run as root" >&2
  exit 1
fi
if ! id "$RUN_USER" >/dev/null 2>&1; then
  echo "user $RUN_USER does not exist" >&2
  exit 1
fi
case "$DEPLOY_DIR" in
  /*) ;;
  *) echo "the deploy dir must be absolute" >&2; exit 1 ;;
esac
for script in bootstrap.sh consume-mount.sh immich-originals-mount.sh; do
  if [ ! -x "$DEPLOY_DIR/server/$script" ]; then
    echo "$DEPLOY_DIR/server/$script is missing or not executable" >&2
    exit 1
  fi
done

APT_GET=/usr/bin/apt-get
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
cat > "$tmp" <<EOF
# Managed by server/pre-bootstrap.sh. Exact commands only, see the script for the trade-off.
$RUN_USER ALL=(root) NOPASSWD: $APT_GET update -qq, $APT_GET install -y -qq --no-install-recommends git ca-certificates, $DEPLOY_DIR/server/bootstrap.sh *, $DEPLOY_DIR/server/consume-mount.sh *, $DEPLOY_DIR/server/immich-originals-mount.sh *
EOF

# A broken sudoers file locks out sudo for everyone, so it is checked before it is installed.
visudo -cf "$tmp" >/dev/null
install -o root -g root -m 0440 "$tmp" "$SUDOERS"
echo "sudo allowlist installed: $SUDOERS"

# Embedding endpoint (compose service "embedding", host port 8090) for the LAN. bootstrap.sh already
# allows ALLOWED_NETWORK (192.0.0.0/8) on all ports, so this rule is a narrower duplicate that keeps
# the port open even if that broader rule is removed. ufw needs root, so it runs here.
ufw allow from 192.0.0.0/8 to any port 8090 proto tcp comment 'embedding (LAN)' >/dev/null
echo "ufw rule for port 8090 (LAN) present"
