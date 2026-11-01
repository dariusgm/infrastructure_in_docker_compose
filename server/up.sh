#!/usr/bin/env bash
# Idempotent stack start. Runs as the deploy user, never as root.
# Installs and starts the rootless Docker daemon if needed, then starts the compose stack.
#
# Usage: bash server/up.sh [--no-stack]
#   --no-stack  start only the rootless Docker daemon; the stack is started by server/steps/run.py
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
# The daemon starts containers with a restart policy as soon as it is up. Their port bindings to
# HOST_IP fail while that address is not configured yet (seen after a reboot), so the daemon waits for it.
HOST_IP_VALUE="$(grep -m1 '^HOST_IP=' "$PROJECT_DIR/.env" | cut -d= -f2- || true)"
if [ -n "$HOST_IP_VALUE" ]; then
  DROPIN_DIR="$HOME/.config/systemd/user/docker.service.d"
  mkdir -p "$DROPIN_DIR"
  cat > "$DROPIN_DIR/wait-host-ip.conf" <<EOF
[Service]
ExecStartPre=/bin/sh -c 'for i in \$(seq 120); do /usr/sbin/ip -4 addr show | grep -q "inet ${HOST_IP_VALUE}/" && exit 0; sleep 1; done; echo "HOST_IP ${HOST_IP_VALUE} is not configured" >&2; exit 1'
EOF
  cat >> "$DROPIN_DIR/wait-host-ip.conf" <<EOF
ExecStartPre=-${PROJECT_DIR}/server/wait-mounts.sh
EOF
  systemctl --user daemon-reload
fi
systemctl --user enable --now docker.service
for _ in $(seq 30); do
  docker info >/dev/null 2>&1 && break
  sleep 1
done
docker info >/dev/null

if [ "${1:-}" = "--no-stack" ]; then
  echo "Rootless Docker is running; stack not started (--no-stack)"
  exit 0
fi

echo "==> Stack"
cd "$PROJECT_DIR"
if [ -z "$(docker compose config --services)" ]; then
  echo "No services defined in compose.yaml yet, nothing to start"
  exit 0
fi
docker compose up -d --build --remove-orphans
docker compose ps
