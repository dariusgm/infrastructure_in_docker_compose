#!/bin/bash
# Health check helper, mounted into the Postgres containers. Succeeds when the metrics endpoint
# answers HTTP 200. Usage: check-metrics.sh <host> <port>
# Bash is used for the TCP connection, because the Postgres images have no curl or wget.
set -eu
host=$1
port=$2
exec 3<>"/dev/tcp/$host/$port"
printf 'GET /metrics HTTP/1.0\r\nHost: %s\r\n\r\n' "$host" >&3
read -r status <&3
case "$status" in
  *" 200"*) exit 0 ;;
  *) exit 1 ;;
esac
