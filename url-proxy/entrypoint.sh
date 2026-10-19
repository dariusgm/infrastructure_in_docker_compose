#!/bin/sh
# Hands the cache directory to the nginx worker user, then runs the command (nginx) in the
# foreground. exec makes nginx PID 1, so it receives stop signals directly.
set -eu

CACHE_DIR=/var/cache/nginx/url_proxy

# Bind mounts are created owned by root. Only the top-level owner is checked, so the
# recursive chown runs once, not on every start.
mkdir -p "$CACHE_DIR"
if [ "$(stat -c %U "$CACHE_DIR")" != "www-data" ]; then
  chown -R www-data:www-data "$CACHE_DIR"
fi

exec "$@"
