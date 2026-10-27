#!/usr/bin/env bash
# Mounts the SMB folders with the original photos for Immich on the host, read-only.
# One mount per folder, below /mnt/immich-originals/<name>. All folders use the same NAS user
# (IMMICH_SMB_USERNAME), which has read rights only. Separate from the Paperless consume share.
#
# Folders are the names in FOLDERS below. Each one needs IMMICH_SMB_<NAME>_SHARE and
# IMMICH_SMB_<NAME>_SUBPATH in the .env file.
#
# Runs as root, called by deploy.py after bootstrap.sh. Idempotent: the managed fstab block is
# replaced on every run, and each folder is remounted with the new options.
#
# The values are read from the .env file with grep, not sourced, so passwords are never
# shell-expanded. Usage: sudo bash server/immich-originals-mount.sh <env file> <run_user>
set -euo pipefail

ENV_FILE="${1:?usage: immich-originals-mount.sh <env file> <run_user>}"
RUN_USER="${2:?usage: immich-originals-mount.sh <env file> <run_user>}"

FOLDERS=(darius ela jaron)
BASE=/mnt/immich-originals
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
IMMICH_SMB_USERNAME="$(value IMMICH_SMB_USERNAME)"
IMMICH_SMB_PASSWORD="$(value IMMICH_SMB_PASSWORD)"
require IMMICH_SMB_HOST "$IMMICH_SMB_HOST"
require IMMICH_SMB_USERNAME "$IMMICH_SMB_USERNAME"
require IMMICH_SMB_PASSWORD "$IMMICH_SMB_PASSWORD"
case "$IMMICH_SMB_HOST" in
  *[[:space:]]*|*/*) echo "IMMICH_SMB_HOST must not contain spaces or slashes" >&2; exit 1 ;;
esac

echo "==> Mount tools"
export DEBIAN_FRONTEND=noninteractive
if ! dpkg-query -W -f='${Status}' cifs-utils 2>/dev/null | grep -q "install ok installed"; then
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends cifs-utils
fi

echo "==> Owner of the mounts: the deploy user (read access for the rootless container)"
RUN_UID="$(id -u "$RUN_USER")"
RUN_GID="$(id -g "$RUN_USER")"

echo "==> Credentials file (root only)"
install -d -m 0700 "$CRED_DIR"
umask 077
printf 'username=%s\npassword=%s\n' "$IMMICH_SMB_USERNAME" "$IMMICH_SMB_PASSWORD" > "$CRED_FILE"

# ro: nothing can be written through these mounts. file_mode/dir_mode 0444/0555: no write bits.
OPTIONS="ro,credentials=${CRED_FILE},uid=${RUN_UID},gid=${RUN_GID},file_mode=0444,dir_mode=0555,_netdev,nofail"

# Build the fstab lines and the list of mount points first, so a missing value stops the script
# before anything is changed.
FSTAB_LINES=()
for folder in "${FOLDERS[@]}"; do
  upper="$(echo "$folder" | tr '[:lower:]' '[:upper:]')"
  share="$(value "IMMICH_SMB_${upper}_SHARE")"
  subpath="$(value "IMMICH_SMB_${upper}_SUBPATH")"
  require "IMMICH_SMB_${upper}_SHARE" "$share"
  require "IMMICH_SMB_${upper}_SUBPATH" "$subpath"
  case "$share" in
    *[[:space:]]*|*/*) echo "IMMICH_SMB_${upper}_SHARE must not contain spaces or slashes" >&2; exit 1 ;;
  esac
  # fstab separates fields by whitespace, so spaces in the path are written as \040.
  source_path="//${IMMICH_SMB_HOST}/${share}/${subpath}"
  fstab_source="${source_path// /\\040}"
  FSTAB_LINES+=("${fstab_source} ${BASE}/${folder} cifs ${OPTIONS} 0 0")
done

echo "==> fstab entry"
tmp="$(mktemp)"
awk -v b="$FSTAB_BEGIN" -v e="$FSTAB_END" '$0==b{skip=1} !skip{print} $0==e{skip=0}' /etc/fstab > "$tmp"
{
  echo "$FSTAB_BEGIN"
  printf '%s\n' "${FSTAB_LINES[@]}"
  echo "$FSTAB_END"
} >> "$tmp"
cat "$tmp" > /etc/fstab
rm -f "$tmp"

# Earlier versions mounted one folder directly at $BASE. Unmount it, so the folders below can mount.
if mountpoint -q "$BASE"; then
  echo "==> Unmounting the single-folder mount at $BASE (older layout)"
  umount "$BASE"
fi

echo "==> Mount folders (read-only)"
mkdir -p "$BASE"
for folder in "${FOLDERS[@]}"; do
  mkdir -p "$BASE/$folder"
  if mountpoint -q "$BASE/$folder"; then
    umount "$BASE/$folder"
  fi
  mount "$BASE/$folder"
  findmnt -no TARGET,SOURCE,FSTYPE,OPTIONS "$BASE/$folder"
done
echo "==> Immich originals mounted"
