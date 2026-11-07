# paperless (paperless-ngx)

Host `.82`, checkout `~/infrastructure_in_docker_compose` (deploy dir), web UI `http://192.168.178.82:8083`.
Full runbook: `paperless/README.md` on the host repo, section 7 (Updates).

## Where the version lives
- `compose.yaml`, service `paperless`: `image: ghcr.io/paperless-ngx/paperless-ngx:<tag>`
- Also check the exporter (`paperless-app-exporter`), it talks to the API and is version-independent.
- Other paperless images (`paperless-db` postgres 18, `paperless-broker` valkey 9, `paperless-gotenberg`,
  `paperless-tika`) are separate updates. Do not bundle them with the app update.

## Version history
- Running at the time of writing: 3.3.4. Latest release: 3.4.2 (Nov 2026).
- 3.4.0 notes: ImageMagick dropped as a dependency (PDF thumbnails now via poppler). Check that
  nothing in the stack relies on ImageMagick. New Celery and AI-chat features.
- 3.4.2 notes: Gotenberg dependency bump 8.37 → 8.38 (tracked by Dependabot upstream; update
  `paperless-gotenberg` separately after verifying conversions).

## Extra checks for paperless
- Migrations run on start. Watch `docker compose logs -f paperless` until the web server is up.
- Status page: Administration > System status, database, broker and consumer all OK.
- Consume folder: `findmnt /mnt/paperless-consume` must show the NAS mount. If the NAS is off, the
  consumer runs but imports nothing. That is not an update failure.
- Search: run a search for a document you know. If results are empty after the update, run
  `docker compose exec paperless document_index reindex`.
- One test upload (text PDF plus one scanned image), check OCR, delete it again.

## Rollback
Database and files are restored from the pre-update snapshot, per `backup/README.md` (Paperless
section). Restore into a stopped stack, set the old tag, deploy, verify.
