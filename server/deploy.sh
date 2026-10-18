#!/usr/bin/env bash
# Runs on the target host as root (started by deploy.py via sudo).
# Installs system dependencies, applies the firewall policy and starts the compose stack.
#
# Usage: sudo bash server/deploy.sh <allowed_network> <data_dir>
set -euo pipefail

ALLOWED_NETWORK="${1:?usage: deploy.sh <allowed_network> <data_dir>}"
DATA_DIR="${2:?usage: deploy.sh <allowed_network> <data_dir>}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_USER="${SUDO_USER:-root}"

export DEBIAN_FRONTEND=noninteractive

if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "Missing $PROJECT_DIR/.env" >&2
  exit 1
fi

echo "==> Installing system packages"
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl git ufw docker.io docker-compose-v2

echo "==> Enabling Docker"
systemctl enable --now docker
if [ "$TARGET_USER" != "root" ]; then
  usermod -aG docker "$TARGET_USER"
fi

echo "==> Firewall: deny all inbound, allow $ALLOWED_NETWORK only"
ufw default deny incoming
ufw default allow outgoing
ufw allow from "$ALLOWED_NETWORK" comment 'LAN only'
ufw --force enable

echo "==> Preparing data directory $DATA_DIR"
mkdir -p "$DATA_DIR"

cd "$PROJECT_DIR"
if [ -z "$(docker compose config --services)" ]; then
  echo "==> No services defined in compose.yaml yet, nothing to start"
  exit 0
fi

echo "==> Starting stack"
docker compose up -d --build --remove-orphans
docker compose ps
