# backup

The `backup` container makes regular copies of the databases and files of the stack. It runs
once a day (`BACKUP_INTERVAL_SECONDS`, default 86400) and once when it starts.

## What is backed up

| What | How | Where on the host |
| --- | --- | --- |
| Paperless PostgreSQL database | `pg_dump` in custom format, checked with `pg_restore --list` | `${DATA_DIR}/backup/paperless/database/paperless-<stamp>.dump` |
| Paperless files (documents, thumbnails, archive, index, settings) | `rsync` snapshot. Unchanged files are hardlinks, so every snapshot is complete but takes space only for changes | `${DATA_DIR}/backup/paperless/files/<stamp>/` (subfolders `data/` and `media/`) |
| Pi-hole databases (`gravity.db`, `pihole-FTL.db`) | SQLite online backup, consistent while Pi-hole runs | `${DATA_DIR}/backup/pihole/<stamp>-gravity.db`, `<stamp>-pihole-FTL.db` |

Not backed up, on purpose:

- The PostgreSQL data files and the Valkey queue. Copying live database files is unsafe, so the
  dump is the backup. The queue holds only pending tasks.
- `.env`. It holds the secrets and lives in the repository checkout on the server, not in the
  data directory. Keep a copy somewhere safe, outside this server.

One run writes all copies with the same `<stamp>` (UTC, `YYYYMMDDTHHMMSSZ`). A database dump
and a file snapshot with the same stamp belong together.

Retention: the newest `BACKUP_KEEP_COUNT` copies of each kind are kept (default 14, so about
two weeks of daily backups). Older copies are deleted after a successful run only.

## Where backups live, and what is missing

Backups are on the same disk as the data. That protects against mistakes and broken
containers, but **not against a failing disk or a stolen or burnt server.** Copy
`${DATA_DIR}/backup` regularly to a second machine or disk, for example with `rsync` to a NAS
or an external drive. This copy is the step that makes the backup a real backup. Test a
restore from the copy now and then.

## Status and health

- The `backup` container is `healthy` when the last successful run is less than 48 hours old.
  Check it with `docker compose ps`.
- The last successful run is recorded in `${DATA_DIR}/backup/status/last-success`.
- Logs: `docker compose logs backup`. A failed step prints `ERROR:`.

## Run a backup now

```bash
docker compose exec backup backup.sh once
```

## Restore

Restore into a system that is stopped or freshly deployed, from copies made in the same run.
Replace `<stamp>` with the stamp of the copies to restore.

### Paperless

1. Stop the web UI and the other services that use the database, but keep the database running:
   ```bash
   docker compose stop paperless
   ```
2. Restore the database. The dump replaces the existing tables:
   ```bash
   docker compose exec -T paperless-db pg_restore --clean --if-exists --no-owner \
     --username=paperless --dbname=paperless \
     < "${DATA_DIR}/backup/paperless/database/paperless-<stamp>.dump"
   ```
3. Restore the files from the snapshot. The files belong to the container's user, not to your
   login user, so the copy needs `sudo`. `cp -a` keeps the owners. Move the current folders aside
   instead of deleting them:
   ```bash
   cd "${DATA_DIR}/paperless"
   sudo mv data data.before-restore && sudo cp -a "${DATA_DIR}/backup/paperless/files/<stamp>/data" data
   sudo mv media media.before-restore && sudo cp -a "${DATA_DIR}/backup/paperless/files/<stamp>/media" media
   ```
   Delete `data.before-restore` and `media.before-restore` once Paperless works.
4. Start Paperless and check that the documents show up:
   ```bash
   docker compose up -d paperless
   ```
5. Rebuild the search index if it looks wrong: `docker compose exec paperless document_index reindex`.

### Pi-hole

Stop Pi-hole, replace the database files in `${DATA_DIR}/pihole/etc-pihole` with the backup
copies (rename `<stamp>-gravity.db` to `gravity.db` and `<stamp>-pihole-FTL.db` to
`pihole-FTL.db`), then start Pi-hole again. Remove any `gravity.db-wal` or `-shm` files first.

## Changing the schedule or retention

Set `BACKUP_KEEP_COUNT` in `.env` and run `python3 deploy.py deploy`. The interval is set by
`BACKUP_INTERVAL_SECONDS`, which defaults to 86400 (daily). To change it, add the variable to the
`backup` service's `environment` in `compose.yaml`.
