#!/usr/bin/env bash
# Mounts the SMB share that Paperless consumes from, at /mnt/paperless-consume on the host.
# Runs as root, called by deploy.py after bootstrap.sh. Idempotent: the managed fstab entry is
# replaced on every run, and the share is remounted with the new options.
#
# The values are read from the .env file with grep, not sourced, so passwords are never
# shell-expanded. The share is mounted with the owner UID of the Paperless user inside the
# rootless container. That user is the first subordinate UID of RUN_USER plus 999, because
# container UID 1000 maps to subuid start + 999.
#
# Usage: sudo bash server/consume-mount.sh <env file> <run_user>
set -euo pipefail

ENV_FILE="${1:?usage: consume-mount.sh <env file> <run_user>}"
RUN_USER="${2:?usage: consume-mount.sh <env file> <run_user>}"

MOUNT_POINT=/mnt/paperless-consume
CRED_DIR=/etc/infrastructure
CRED_FILE="$CRED_DIR/paperless-smb.cred"
FSTAB_BEGIN="# BEGIN infrastructure paperless-consume"
FSTAB_END="# END infrastructure paperless-consume"

if [ "$(id -u)" -ne 0 ]; then
  echo "consume-mount.sh must run as root" >&2
  exit 1
fi

# Reads one value from the env file. Prints nothing when the key is missing.
value() {
  grep -m1 "^$1=" "$ENV_FILE" | cut -d= -f2- || true
}

# Refuses empty values and the "<...>" placeholders from .env.example.
require() {
  local name="$1" val="$2"
  if [ -z "$val" ] || [[ "$val" == \<*\> ]]; then
    echo "$name is not set in $ENV_FILE" >&2
    exit 1
  fi
}

SMB_HOST="$(value SMB_HOST)"
SMB_SHARE="$(value SMB_SHARE)"
SMB_SUBPATH="$(value SMB_SUBPATH)"
SMB_USERNAME="$(value SMB_USERNAME)"
SMB_PASSWORD="$(value SMB_PASSWORD)"
require SMB_HOST "$SMB_HOST"
require SMB_SHARE "$SMB_SHARE"
require SMB_USERNAME "$SMB_USERNAME"
require SMB_PASSWORD "$SMB_PASSWORD"

# A share name with spaces would need escaping in fstab. Names are used as they are.
for name in SMB_HOST SMB_SHARE; do
  case "${!name}" in
    *[[:space:]]*|*/*) echo "$name must not contain spaces or slashes" >&2; exit 1 ;;
  esac
done

echo "==> Mount tools"
export DEBIAN_FRONTEND=noninteractive
if ! dpkg-query -W -f='${Status}' cifs-utils 2>/dev/null | grep -q "install ok installed"; then
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends cifs-utils
fi

echo "==> Owner of the mount: Paperless user inside the rootless container"
RUN_UID="$(id -u "$RUN_USER")"
SUBUID_START="$(grep "^${RUN_USER}:" /etc/subuid | head -n1 | cut -d: -f2)"
if [ -z "$SUBUID_START" ]; then
  echo "no subordinate UID range for $RUN_USER in /etc/subuid" >&2
  exit 1
fi
PAPERLESS_HOST_UID=$((SUBUID_START + 999))

echo "==> Credentials file (root only)"
install -d -m 0700 "$CRED_DIR"
umask 077
printf 'username=%s\npassword=%s\n' "$SMB_USERNAME" "$SMB_PASSWORD" > "$CRED_FILE"

SOURCE="//${SMB_HOST}/${SMB_SHARE}"
if [ -n "$SMB_SUBPATH" ]; then
  SOURCE="${SOURCE}/${SMB_SUBPATH}"
fi
# file_mode 0644 and dir_mode 0755: the owner (Paperless) can write, the rootless daemon can read
# and traverse the folder for the bind mount. The NAS permissions still decide what may be written.
OPTIONS="credentials=${CRED_FILE},uid=${PAPERLESS_HOST_UID},gid=${PAPERLESS_HOST_UID},file_mode=0644,dir_mode=0755,_netdev,nofail"
FSTAB_LINE="${SOURCE} ${MOUNT_POINT} cifs ${OPTIONS} 0 0"

echo "==> fstab entry"
tmp="$(mktemp)"
awk -v b="$FSTAB_BEGIN" -v e="$FSTAB_END" '$0==b{skip=1} !skip{print} $0==e{skip=0}' /etc/fstab > "$tmp"
{ echo "$FSTAB_BEGIN"; echo "$FSTAB_LINE"; echo "$FSTAB_END"; } >> "$tmp"
cat "$tmp" > /etc/fstab
rm -f "$tmp"

echo "==> Mount $SOURCE at $MOUNT_POINT"
mkdir -p "$MOUNT_POINT"
if mountpoint -q "$MOUNT_POINT"; then
  umount "$MOUNT_POINT"
fi
mount "$MOUNT_POINT"
findmnt -no SOURCE,FSTYPE "$MOUNT_POINT"
echo "==> Consume share mounted"
