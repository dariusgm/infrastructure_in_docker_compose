#!/bin/bash
# Starts apt-cacher-ng and the nginx URL proxy in one container.
# If either process exits, the container stops too, so the restart policy brings both back.
set -euo pipefail

ACNG_USER=apt-cacher-ng
NGINX_USER=www-data

# Bind mounts are created owned by root. Hand each cache directory to its service user.
# Only the top-level owner is checked, so the recursive chown runs once, not on every start.
own() {
  local dir=$1 user=$2
  mkdir -p "$dir"
  if [ "$(stat -c %U "$dir")" != "$user" ]; then
    chown -R "$user:$user" "$dir"
  fi
}
own /var/cache/apt-cacher-ng "$ACNG_USER"
own /var/cache/nginx/url_proxy "$NGINX_USER"
install -d -o "$ACNG_USER" -g "$ACNG_USER" /run/apt-cacher-ng

# apt-cacher-ng runs in the foreground as its own user. Its configuration stays the package default.
setpriv --reuid="$ACNG_USER" --regid="$ACNG_USER" --clear-groups \
  /usr/sbin/apt-cacher-ng -c /etc/apt-cacher-ng ForeGround=1 &

nginx -g 'daemon off;' &

trap 'kill -TERM $(jobs -p) 2>/dev/null || true' TERM INT

set +e
wait -n
status=$?
kill -TERM $(jobs -p) 2>/dev/null || true
wait
exit "$status"
