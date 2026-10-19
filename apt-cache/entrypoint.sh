#!/bin/sh
# Hands the cache directory to the apt-cacher-ng user, then runs apt-cacher-ng in the
# foreground as that user. exec makes apt-cacher-ng PID 1, so it receives stop signals directly.
set -eu

ACNG_USER=apt-cacher-ng
CACHE_DIR=/var/cache/apt-cacher-ng

# Bind mounts are created owned by root. Only the top-level owner is checked, so the
# recursive chown runs once, not on every start.
mkdir -p "$CACHE_DIR"
if [ "$(stat -c %U "$CACHE_DIR")" != "$ACNG_USER" ]; then
  chown -R "$ACNG_USER:$ACNG_USER" "$CACHE_DIR"
fi
install -d -o "$ACNG_USER" -g "$ACNG_USER" /run/apt-cacher-ng

exec setpriv --reuid="$ACNG_USER" --regid="$ACNG_USER" --clear-groups \
  /usr/sbin/apt-cacher-ng -c /etc/apt-cacher-ng ForeGround=1
