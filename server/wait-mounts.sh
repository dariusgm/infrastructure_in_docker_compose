#!/usr/bin/env bash
# Waits up to 120 s until every CIFS mount listed in /etc/fstab is mounted. The rootless Docker daemon
# runs this before it starts, so containers with bind mounts into the shares do not start on empty folders.
# Always exits 0: a share that stays unavailable must not keep Docker from starting.
set -u

targets() {
  awk '$3 == "cifs" { print $2 }' /etc/fstab
}

for _ in $(seq 120); do
  missing=0
  while read -r target; do
    mountpoint -q "$target" || missing=1
  done < <(targets)
  [ "$missing" -eq 0 ] && exit 0
  sleep 1
done
echo "Some CIFS shares are still not mounted after 120 s; starting Docker anyway" >&2
exit 0
