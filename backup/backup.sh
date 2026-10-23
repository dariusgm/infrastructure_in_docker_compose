#!/usr/bin/env bash
# Backup job for the stack. Runs in its own container, never on the host.
#
# Each run uses one timestamp for all of its copies, so a database dump and a file snapshot
# from the same run belong together:
#   /backup/paperless/database/paperless-<stamp>.dump   PostgreSQL dump (custom format)
#   /backup/paperless/files/<stamp>/                    Paperless data and media (hardlinked)
#   /backup/pihole/<stamp>-gravity.db                   Pi-hole databases (SQLite)
#   /backup/pihole/<stamp>-pihole-FTL.db
#
# Order within a run: database first, files second. A document that arrives in between then
# exists as a file without a database row, which is harmless. The reverse order could leave a
# database row whose file is missing from the snapshot.
#
# Usage: backup.sh [loop|once]   (default: loop, one run per BACKUP_INTERVAL_SECONDS)
set -uo pipefail

BACKUP_DIR=/backup
KEEP_COUNT="${BACKUP_KEEP_COUNT:-14}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
STATUS_FILE="$BACKUP_DIR/status/last-success"
STAMP=""

shopt -s nullglob

log() {
  echo "$(date -u +%FT%TZ) $*"
}

dump_database() {
  local dir="$BACKUP_DIR/paperless/database"
  local file="$dir/paperless-$STAMP.dump"
  mkdir -p "$dir"
  # Custom format is compressed and lets pg_restore pick single objects. pg_restore --list
  # reads the whole archive, so a truncated dump fails here and is not kept.
  pg_dump --format=custom --no-owner --file="$file.partial" "$PGDATABASE" &&
    pg_restore --list "$file.partial" >/dev/null &&
    mv "$file.partial" "$file" ||
    { rm -f "$file.partial"; return 1; }
}

snapshot_files() {
  local root="$BACKUP_DIR/paperless/files"
  local new="$root/$STAMP"
  local -a snapshots=("$root"/[0-9]*Z)
  local -a link=()
  # Files that did not change since the previous snapshot are hardlinks, so each snapshot
  # is complete but only the changes take extra space.
  if [ "${#snapshots[@]}" -gt 0 ]; then
    link=(--link-dest="${snapshots[-1]}")
  fi
  mkdir -p "$root"
  # /source/paperless holds the data and media directories. The trailing slash copies their
  # contents, so the snapshot has the layout data/ and media/.
  rsync -a --delete "${link[@]}" /source/paperless/ "$new.partial/" &&
    mv "$new.partial" "$new" ||
    { rm -rf "$new.partial"; return 1; }
}

backup_pihole() {
  local dir="$BACKUP_DIR/pihole"
  local db tmp
  mkdir -p "$dir"
  for db in gravity.db pihole-FTL.db; do
    [ -f "/source/pihole/$db" ] || continue
    tmp="$dir/$STAMP-$db.partial"
    # .backup uses SQLite's online backup API, so the copy is consistent while Pi-hole runs.
    sqlite3 "/source/pihole/$db" ".timeout 10000" ".backup '$tmp'" &&
      mv "$tmp" "$dir/$STAMP-$db" ||
      { rm -f "$tmp"; return 1; }
  done
}

# prune <pattern>: keeps the newest $KEEP_COUNT matches and deletes the rest. Stamps sort
# by name, so reverse sorting puts the newest first.
prune() {
  local -a found=("$@")
  local item
  [ "${#found[@]}" -gt 0 ] || return 0
  while IFS= read -r item; do
    rm -rf -- "$item"
  done < <(printf '%s\n' "${found[@]}" | sort -r | tail -n +"$((KEEP_COUNT + 1))")
}

prune_all() {
  prune "$BACKUP_DIR"/paperless/database/paperless-*.dump
  prune "$BACKUP_DIR"/paperless/files/[0-9]*Z
  prune "$BACKUP_DIR"/pihole/*-gravity.db
  prune "$BACKUP_DIR"/pihole/*-pihole-FTL.db
}

run_once() {
  local failed=0
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  log "backup $STAMP started"

  dump_database || { log "ERROR: database dump failed"; failed=1; }
  snapshot_files || { log "ERROR: file snapshot failed"; failed=1; }
  backup_pihole || { log "ERROR: Pi-hole database backup failed"; failed=1; }

  # Old copies are removed only after a run that completed, so a failing run never deletes
  # the last good backups.
  if [ "$failed" -eq 0 ]; then
    prune_all
    mkdir -p "$(dirname "$STATUS_FILE")"
    date -u +%FT%TZ > "$STATUS_FILE"
    log "backup $STAMP finished"
  else
    log "backup $STAMP finished with errors"
  fi
  return "$failed"
}

case "${1:-loop}" in
  once)
    run_once
    ;;
  loop)
    while true; do
      run_once || true
      sleep "$INTERVAL"
    done
    ;;
  *)
    echo "usage: backup.sh [loop|once]" >&2
    exit 2
    ;;
esac
