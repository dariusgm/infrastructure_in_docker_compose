#!/usr/bin/env bash
# Idempotent stack start. Runs as the deploy user, never as root.
# Installs and starts the rootless Docker daemon if needed, then starts the compose stack.
#
# Usage: bash server/up.sh
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "up.sh must run as the deploy user, not root" >&2
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SETUP_TOOL=/usr/bin/dockerd-rootless-setuptool.sh
UNIT="$HOME/.config/systemd/user/docker.service"

# Non-login SSH sessions do not set these, and the user systemd manager needs them.
USER_UID="$(id -u)"
export XDG_RUNTIME_DIR="/run/user/${USER_UID}"
export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"
export DOCKER_HOST="unix://${XDG_RUNTIME_DIR}/docker.sock"

echo "==> Rootless Docker"
# A unit left over from an older install points at files that no longer exist, so replace it.
if [ -f "$UNIT" ] && ! grep -q "^ExecStart=/usr/bin/dockerd-rootless.sh" "$UNIT"; then
  echo "Replacing rootless unit from an older install"
  systemctl --user disable --now docker.service || true
  rm -f "$UNIT"
  systemctl --user daemon-reload
fi
if [ ! -f "$UNIT" ]; then
  "$SETUP_TOOL" install
fi
systemctl --user enable --now docker.service
for _ in $(seq 30); do
  docker info >/dev/null 2>&1 && break
  sleep 1
done
docker info >/dev/null

echo "==> Stack"
cd "$PROJECT_DIR"
if [ -z "$(docker compose config --services)" ]; then
  echo "No services defined in compose.yaml yet, nothing to start"
  exit 0
fi
docker compose up -d --build --remove-orphans
docker compose ps
