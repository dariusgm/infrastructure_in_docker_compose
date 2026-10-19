#!/usr/bin/env bash
# Idempotent host preparation. Runs as root before anything else is deployed.
# Every step checks the current state first, so it is safe to run again and again.
#
# Usage: sudo bash server/bootstrap.sh <run_user> <allowed_network> <data_dir> <relax_apparmor yes|no>
set -euo pipefail

RUN_USER="${1:?usage: bootstrap.sh <run_user> <allowed_network> <data_dir> <relax_apparmor>}"
ALLOWED_NETWORK="${2:?usage: bootstrap.sh <run_user> <allowed_network> <data_dir> <relax_apparmor>}"
DATA_DIR="${3:?usage: bootstrap.sh <run_user> <allowed_network> <data_dir> <relax_apparmor>}"
RELAX_APPARMOR="${4:?usage: bootstrap.sh <run_user> <allowed_network> <data_dir> <relax_apparmor>}"

if [ "$(id -u)" -ne 0 ]; then
  echo "bootstrap.sh must run as root" >&2
  exit 1
fi
if ! id "$RUN_USER" >/dev/null 2>&1; then
  echo "user $RUN_USER does not exist" >&2
  exit 1
fi
case "$RELAX_APPARMOR" in
  yes|no) ;;
  *) echo "relax_apparmor must be yes or no" >&2; exit 1 ;;
esac

RUN_UID="$(id -u "$RUN_USER")"
APPARMOR_SYSCTL=/etc/sysctl.d/60-rootless-docker-userns.conf
export DEBIAN_FRONTEND=noninteractive

echo "==> Base packages"
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  ca-certificates curl git gnupg ufw \
  uidmap rootlesskit slirp4netns dbus-user-session

echo "==> Remove Ubuntu's Docker packages (replaced by Docker's official packages)"
legacy=()
for pkg in docker.io docker-compose-v2 containerd runc; do
  if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
    legacy+=("$pkg")
  fi
done
if [ "${#legacy[@]}" -gt 0 ]; then
  apt-get purge -y -qq "${legacy[@]}"
fi

echo "==> Docker official apt repository"
KEYRING=/etc/apt/keyrings/docker.asc
DOCKER_KEY_FPR=9DC858229FC7DD38854AE2D88D81803C0EBFCD88
install -d -m 0755 /etc/apt/keyrings
if [ ! -f "$KEYRING" ]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o "$KEYRING.tmp"
  if ! gpg --show-keys --with-colons "$KEYRING.tmp" | grep -q "^fpr:::::::::${DOCKER_KEY_FPR}:"; then
    rm -f "$KEYRING.tmp"
    echo "Docker signing key fingerprint does not match $DOCKER_KEY_FPR" >&2
    exit 1
  fi
  chmod a+r "$KEYRING.tmp"
  mv "$KEYRING.tmp" "$KEYRING"
fi
# shellcheck source=/dev/null
. /etc/os-release
printf '%s\n' \
  "Types: deb" \
  "URIs: https://download.docker.com/linux/ubuntu" \
  "Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}" \
  "Components: stable" \
  "Architectures: $(dpkg --print-architecture)" \
  "Signed-By: $KEYRING" \
  > /etc/apt/sources.list.d/docker.sources
apt-get update -qq

echo "==> Docker Engine, Compose and rootless extras"
apt-get install -y -qq --no-install-recommends \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras

echo "==> Subordinate UID/GID ranges for $RUN_USER"
grep -q "^${RUN_USER}:" /etc/subuid || usermod --add-subuids 100000-165535 "$RUN_USER"
grep -q "^${RUN_USER}:" /etc/subgid || usermod --add-subgids 100000-165535 "$RUN_USER"

echo "==> System Docker daemon off (rootless Docker replaces it)"
systemctl disable --now docker.service docker.socket >/dev/null 2>&1 || true

echo "==> $RUN_USER is not in the docker group"
if id -nG "$RUN_USER" | tr ' ' '\n' | grep -qx docker; then
  gpasswd -d "$RUN_USER" docker >/dev/null
fi

echo "==> AppArmor restriction on unprivileged user namespaces (relax: $RELAX_APPARMOR)"
if [ "$RELAX_APPARMOR" = yes ]; then
  if [ ! -f "$APPARMOR_SYSCTL" ]; then
    echo 'kernel.apparmor_restrict_unprivileged_userns = 0' > "$APPARMOR_SYSCTL"
    sysctl -q -p "$APPARMOR_SYSCTL"
  fi
else
  if [ -f "$APPARMOR_SYSCTL" ]; then
    rm -f "$APPARMOR_SYSCTL"
    sysctl -q -w kernel.apparmor_restrict_unprivileged_userns=1
  fi
fi

echo "==> Unprivileged ports from 53 (rootless Docker publishes the DNS port of pihole)"
PORT_SYSCTL=/etc/sysctl.d/60-rootless-dns-port.conf
if [ "$(sysctl -n net.ipv4.ip_unprivileged_port_start)" -gt 53 ]; then
  echo 'net.ipv4.ip_unprivileged_port_start = 53' > "$PORT_SYSCTL"
  sysctl -q -p "$PORT_SYSCTL"
fi

echo "==> Lingering for $RUN_USER (user services run without a login session)"
if [ "$(loginctl show-user "$RUN_USER" -p Linger --value 2>/dev/null || true)" != yes ]; then
  loginctl enable-linger "$RUN_USER"
fi
systemctl start "user@${RUN_UID}.service"

echo "==> Firewall: deny inbound, allow $ALLOWED_NETWORK only"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow from "$ALLOWED_NETWORK" comment 'LAN only' >/dev/null
ufw --force enable >/dev/null

echo "==> Data directory $DATA_DIR owned by $RUN_USER"
mkdir -p "$DATA_DIR"
chown "$RUN_USER:$RUN_USER" "$DATA_DIR"

echo "==> Host preparation done"
