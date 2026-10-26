#!/usr/bin/env bash
# Mounts the SMB share with the original photos for Immich at /mnt/immich-originals on the host.
# Read-only, with its own NAS user (IMMICH_SMB_*), separate from the Paperless consume share.
# Runs as root, called by deploy.py after bootstrap.sh. Idempotent: the managed fstab entry is
# replaced on every run, and the share is remounted with the new options.
#
# The values are read from the .env file with grep, not sourced, so passwords are never
# shell-expanded. Usage: sudo bash server/immich-originals-mount.sh <env file> <run_user>
set -euo pipefail

ENV_FILE="${1:?usage: immich-originals-mount.sh <env file> <run_user>}"
RUN_USER="${2:?usage: immich-originals-mount.sh <env file> <run_user>}"

MOUNT_POINT=/mnt/immich-originals
CRED_DIR=/etc/infrastructure
CRED_FILE="$CRED_DIR/immich-smb.cred"
FSTAB_BEGIN="# BEGIN infrastructure immich-originals"
FSTAB_END="# END infrastructure immich-originals"

if [ "$(id -u)" -ne 0 ]; then
  echo "immich-originals-mount.sh must run as root" >&2
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

IMMICH_SMB_HOST="$(value IMMICH_SMB_HOST)"
IMMICH_SMB_SHARE="$(value IMMICH_SMB_SHARE)"
IMMICH_SMB_SUBPATH="$(value IMMICH_SMB_SUBPATH)"
IMMICH_SMB_USERNAME="$(value IMMICH_SMB_USERNAME)"
IMMICH_SMB_PASSWORD="$(value IMMICH_SMB_PASSWORD)"
require IMMICH_SMB_HOST "$IMMICH_SMB_HOST"
require IMMICH_SMB_SHARE "$IMMICH_SMB_SHARE"
require IMMICH_SMB_USERNAME "$IMMICH_SMB_USERNAME"
require IMMICH_SMB_PASSWORD "$IMMICH_SMB_PASSWORD"

# A share name with spaces or slashes would need more escaping. Names are used as they are.
for name in IMMICH_SMB_HOST IMMICH_SMB_SHARE; do
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

echo "==> Owner of the mount: the deploy user (read access for the rootless container)"
RUN_UID="$(id -u "$RUN_USER")"
RUN_GID="$(id -g "$RUN_USER")"

echo "==> Credentials file (root only)"
install -d -m 0700 "$CRED_DIR"
umask 077
printf 'username=%s\npassword=%s\n' "$IMMICH_SMB_USERNAME" "$IMMICH_SMB_PASSWORD" > "$CRED_FILE"

SOURCE="//${IMMICH_SMB_HOST}/${IMMICH_SMB_SHARE}"
if [ -n "$IMMICH_SMB_SUBPATH" ]; then
  SOURCE="${SOURCE}/${IMMICH_SMB_SUBPATH}"
fi
# ro: nothing can be written through this mount. The NAS user should be read-only as well.
# file_mode/dir_mode 0444/0555: no write bits even for the owner.
OPTIONS="ro,credentials=${CRED_FILE},uid=${RUN_UID},gid=${RUN_GID},file_mode=0444,dir_mode=0555,_netdev,nofail"
# fstab separates fields by whitespace, so spaces in the path are written as \040.
FSTAB_SOURCE="${SOURCE// /\\040}"
FSTAB_LINE="${FSTAB_SOURCE} ${MOUNT_POINT} cifs ${OPTIONS} 0 0"

echo "==> fstab entry"
tmp="$(mktemp)"
awk -v b="$FSTAB_BEGIN" -v e="$FSTAB_END" '$0==b{skip=1} !skip{print} $0==e{skip=0}' /etc/fstab > "$tmp"
{ echo "$FSTAB_BEGIN"; echo "$FSTAB_LINE"; echo "$FSTAB_END"; } >> "$tmp"
cat "$tmp" > /etc/fstab
rm -f "$tmp"

echo "==> Mount $SOURCE at $MOUNT_POINT (read-only)"
mkdir -p "$MOUNT_POINT"
if mountpoint -q "$MOUNT_POINT"; then
  umount "$MOUNT_POINT"
fi
mount "$MOUNT_POINT"
findmnt -no SOURCE,FSTYPE,OPTIONS "$MOUNT_POINT"
echo "==> Immich originals mounted"
