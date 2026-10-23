# paperless

Paperless-ngx, the document management system: scan or upload documents, and it extracts the
text (OCR), indexes it and files it by tags, correspondents and document types. Web UI on port
8083 of `HOST_IP`: `http://<HOST_IP>:8083`.

## Containers

Every supporting service runs in its own container. Only the web UI is published on the LAN.

| Service | Image | Purpose | Published |
| --- | --- | --- | --- |
| `paperless` | `paperless-ngx` | Web UI, API, OCR and consumer (consumes documents from the consume folder) | `HOST_IP:8083` |
| `paperless-db` | `postgres` 18 | Database for all metadata | no |
| `paperless-broker` | `valkey` 9 | Task queue between the web UI and the consumer | no |
| `paperless-gotenberg` | `gotenberg` 8 | Converts Office documents and e-mails to PDF | no |
| `paperless-tika` | `apache/tika` 3 | Reads text and metadata from Office documents | no |
| `backup` | built from `backup/` | Daily copies of the database, the files and the Pi-hole databases, see `backup/README.md` | no |

The internal services are on the `backend` network, which has no route to the internet. Only
`paperless` also joins the normal network to serve the web UI.

Data (all bind mounts, below `DATA_DIR`):

| Path | Content |
| --- | --- |
| `${DATA_DIR}/paperless/media` | The documents (originals, archive PDFs, thumbnails). **The most important data.** |
| `${DATA_DIR}/paperless/data` | Search index, classification model, logs, settings files |
| `${DATA_DIR}/paperless/postgres` | PostgreSQL database files. Backed up by dump, never copy these files while running. |
| `${DATA_DIR}/paperless/valkey` | Broker persistence (queued tasks) |
| `/mnt/paperless-consume` (host) | Consume folder: the SMB share on the NAS, mounted by `server/consume-mount.sh` |
| `${DATA_DIR}/paperless/export` | Target for manual exports (`document_exporter`) |

## 1. Configure `.env`

Copy the new entries from `.env.example` (section "Document management") into `.env` and fill
them in. Required, without them the stack does not start:

| Variable | What to put in | How |
| --- | --- | --- |
| `PAPERLESS_SECRET_KEY` | A long random key for sessions and signing | `openssl rand -hex 64` |
| `PAPERLESS_DB_PASSWORD` | Password of the database user `paperless` | `openssl rand -hex 24` |
| `PAPERLESS_BROKER_PASSWORD` | Password of the internal Valkey broker | `openssl rand -hex 24` |
| `PAPERLESS_ADMIN_USER` | Name of the first administrator, for example `admin` | free choice |
| `PAPERLESS_ADMIN_PASSWORD` | Password of that administrator | `openssl rand -hex 24` |

Optional:

| Variable | Default | Meaning |
| --- | --- | --- |
| `PAPERLESS_URL` | `http://<HOST_IP>:8083` | Address used in the browser. Must match the address you type, otherwise login is refused. Set it when you use a host name. |
| `PAPERLESS_ADMIN_MAIL` | empty | E-mail address of the administrator |
| `PAPERLESS_TIMEZONE` | `UTC` | Time zone for timestamps, for example `Europe/Berlin` |
| `PAPERLESS_OCR_LANGUAGE` | `deu+eng` | OCR languages, ISO 639-2 codes joined by `+`. German and English are installed in the image. Other languages: see `PAPERLESS_OCR_LANGUAGES` in the Paperless docs. |
| `BACKUP_KEEP_COUNT` | `14` | Number of backups kept per kind (about two weeks of daily backups) |

Rules for all these values: no quotes, no spaces around `=`. Keep `.env` backed up, because the
`PAPERLESS_SECRET_KEY` and `PAPERLESS_DB_PASSWORD` are needed to use the copied database.

Changing `PAPERLESS_SECRET_KEY` signs every user out. Changing `PAPERLESS_DB_PASSWORD` needs two
steps: set the same new password for the database user (`ALTER USER paperless PASSWORD '...';`,
run with `docker compose exec paperless-db psql -U paperless`), then change the value in `.env` and
redeploy. In the other order, Paperless cannot connect to the database.

## 2. Deploy

```bash
python3 deploy.py deploy
```

`server/bootstrap.sh` and `server/up.sh` build the `backup` image and start all services. The
first start takes a few minutes. Paperless runs its database migrations at this point.

Check that everything is healthy:

```bash
ssh <HOST_USERNAME>@<HOST_IP> 'cd ~/<DEPLOY_DIR> && docker compose ps'
```

Every service shows `healthy` or `running`. `paperless-tika` needs about a minute before it is
healthy. If `paperless` stays in `starting` or `unhealthy`, see "Troubleshooting".

## 3. First login and checks

1. Open `http://<HOST_IP>:8083` and log in with `PAPERLESS_ADMIN_USER` and
   `PAPERLESS_ADMIN_PASSWORD`.
2. Change the administrator password in the UI. The `.env` value is then out of date and only
   matters when the admin user is missing. You can delete the `PAPERLESS_ADMIN_PASSWORD` line
   from `.env` afterwards, so that the password is not stored in plain text.
3. Check the status page (**Administration > System status** in the UI): database, broker and
   the consumer must be "OK".
4. Upload one test document (a PDF with text and one scanned image). Check that its title, text
   and date are recognised. Then delete it again.

## 4. Configure Paperless

Do this once, in the web UI:

1. **Users and permissions** (Administration > Users): create one account per person. Use the
   administrator account only for administration. Give users only the rights they need.
2. **Two-factor authentication**: enable it in your profile as soon as more than one person or
   device uses the instance (see the Paperless docs for your version).
3. **Tags, correspondents and document types**: create the basic structure first, for example
   `Rechnung`, `Versicherung`, `Vertrag`, plus your common senders. Automatic rules (matching)
   work much better when the entries exist.
4. **Storage paths**: optional. They define the folder-like file name for each kind of document.
   Changing the file name format of existing documents moves files, so back up before
   changing it.
5. **Workflows**: optional. A workflow sets tags, correspondent and document type on consumption
   when a condition matches, for example the file name or the sender.
6. **Mail import** (optional): add a mail account with IMAP access in the UI and a rule that
   imports attachments. This needs outbound access to your mail server, which the stack already
   has. The mail server's password is stored in the database.

## 5. Get documents in

### Network share on the NAS (consume folder)

New documents are imported from the SMB share on the NAS. The host mounts the share at
`/mnt/paperless-consume` and the `paperless` container uses it as its consume folder.

Set these values in `.env` (see `.env.example`):

| Variable | Meaning |
| --- | --- |
| `SMB_HOST` | IP address of the NAS |
| `SMB_SHARE` | Name of the share on the NAS |
| `SMB_SUBPATH` | Optional folder inside the share. Empty means the share root. |
| `SMB_USERNAME` | NAS user, here `paperless` |
| `SMB_PASSWORD` | Password of that user |

`python3 deploy.py deploy` refuses to run while a value still has a `<...>` placeholder.

The NAS user needs read and write access to the folder. Paperless deletes each file after it
imported it, so the user must be allowed to delete files there.

How it works:

- `deploy.py` runs `server/consume-mount.sh` as root on the host. It writes the mount
  credentials to `/etc/infrastructure/paperless-smb.cred` (root only), adds an `/etc/fstab` entry
  between the markers `BEGIN/END infrastructure paperless-consume` and mounts the share.
- The mount is `_netdev,nofail`, so the server still boots when the NAS is off. The stack then
  has an empty consume folder until the NAS is back. Mount it again with
  `sudo mount /mnt/paperless-consume`.
- Paperless polls the folder every 10 seconds (`PAPERLESS_CONSUMER_POLLING_INTERVAL`), because
  file notifications do not pass reliably through network shares. Files are imported once they
  have been unchanged for `PAPERLESS_CONSUMER_STABILITY_DELAY` seconds (default 5).

Check the mount on the server:

```bash
findmnt /mnt/paperless-consume
docker compose logs --tail 20 paperless
```

### Upload and scanner

- **Upload** in the web UI, or drag and drop onto the page. The upload works without the share.
- **Scanner**: point the scanner's "scan to folder" at the NAS share (for example
  `\\<SMB_HOST>\<SMB_SHARE>`) with the `paperless` user. Some scanners only support SMB 1, which
  the NAS may refuse. Check the scanner documentation first.

## 6. Backups

The backup runs daily inside the `backup` container and covers the PostgreSQL database, the
Paperless files and the Pi-hole databases. It is documented in `backup/README.md`, including the
restore steps.

Two things you must do yourself:

1. Copy `${DATA_DIR}/backup` to a second machine or disk regularly. Backups on the same disk do not
   protect against a failing disk.
2. Keep a copy of `.env` outside the server.

Check the backup at least once after the first start:

```bash
docker compose exec backup backup.sh once
ls -la "${DATA_DIR}/backup/paperless/database"
```

Optional, the documented export of Paperless itself. It writes documents, thumbnails and metadata
in a format that `document_importer` reads. It is the recommended way to move to another instance:

```bash
docker compose exec -T paperless document_exporter ../export --zip
```

The export goes to `${DATA_DIR}/paperless/export`. An export only imports into the same Paperless
version it was made with.

## 7. Updates

1. Read the release notes of the new version: https://github.com/paperless-ngx/paperless-ngx/releases.
   Note any breaking changes and required manual steps.
2. Take a backup: `docker compose exec backup backup.sh once`, and copy it off the server.
3. Change the image tag in `compose.yaml`, for example `paperless-ngx:3.3.4` to the new version.
   Upgrading `paperless-db` (PostgreSQL) to a new major version needs a dump and restore, the
   minor versions `18.x` are updated by changing the tag.
4. Run `python3 deploy.py deploy`. The migrations run at the start.
5. Check the status page and log in.

There is no automatic rollback. A new version can change the database layout, so an older version
cannot read it. To go back, restore the backup taken before the update (`backup/README.md`) and
use the image tag of the old version.

## 8. Operations

```bash
docker compose ps                         # status and health of all services
docker compose logs -f paperless          # web UI, consumer and scheduler
docker compose logs --tail 200 paperless-db
docker compose exec paperless document_index reindex   # rebuild the search index
docker compose restart paperless          # after changing .env
```

After changing `.env` or `compose.yaml`, run `python3 deploy.py deploy`. A plain
`docker compose restart` does not apply changes to the environment or the compose file.

## Security

- The web UI is reachable only from `ALLOWED_NETWORK`, like everything else on the host. Never
  forward port 8083 on the router, and never expose it to the internet.
- The UI runs over plain HTTP. Passwords and documents cross the LAN unencrypted. If that is not
  acceptable for your network, put a reverse proxy with TLS in front of it. That is a separate
  decision and is not set up here.
- Only `paperless` has a published port. The database, broker, Gotenberg and Tika have no published
  ports and no internet access.
- The broker has a password, the database has a password. Both passwords are required in `.env`.
- Documents contain personal data. Every backup copy is as sensitive as the documents
  themselves. Encrypt the off-site copy and limit who can read it.

## Troubleshooting

- **Login refused or "CSRF verification failed"**: the address in the browser differs from
  `PAPERLESS_URL`. Set `PAPERLESS_URL` to the address you use and redeploy.
- **`paperless` stays unhealthy**: `docker compose logs paperless`. A common cause is that the
  database is not ready yet. The container retries on its own. If the logs show a database error,
  check `docker compose logs paperless-db` and the `PAPERLESS_DB_PASSWORD` in `.env`.
- **Office documents fail to consume**: check `paperless-gotenberg` and `paperless-tika` with
  `docker compose ps`. They are reached over the `backend` network only.
- **Documents on the NAS share are not picked up**: check that the mount exists (`findmnt
  /mnt/paperless-consume`), that the NAS user can write to the folder, and the log of `paperless`.
  If the mount is missing, run `sudo mount /mnt/paperless-consume` and wait about 10 seconds
  for the next poll.
- **Search does not find recent documents**: run `docker compose exec paperless document_index reindex`.
- **Wrong OCR language**: set `PAPERLESS_OCR_LANGUAGE` in `.env` and redeploy. It applies to
  documents processed afterwards.

## Limits of this setup

- Single host, single instance. There is no high availability. A failure of the server stops
  Paperless until the server is back. Restores from the backups take time.
- Backups are only as good as the copy you make off the server (see section 6).
- Paperless is not reachable from the internet, so remote access needs VPN into the LAN.
