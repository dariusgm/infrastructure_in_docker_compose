# immich

Immich, the photo library, used here as a **read-only archive** of the year folders on the NAS.
Search by content uses CLIP (CPU, no GPU), faces are recognised, and the original files are
never modified: the originals are mounted read-only.

This is a separate Compose project in `immich/`. It has its own database, its own Valkey
cache, its own network and its own volumes. It does not touch the root `compose.yaml` stack,
its database, its volumes or its backup job.

## Version

Pinned to **Immich v3.3.5** (`IMMICH_VERSION` in `immich/.env`).

- Release: https://github.com/immich-app/immich/releases/tag/v3.3.5
- Compose file of that tag, which the images below are taken from:
  https://github.com/immich-app/immich/blob/v3.3.5/docker/docker-compose.yml

The database image `ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0` (with the
VectorChord and pgvectors extensions) and the Valkey image `valkey/valkey:9` are taken from that
file, including their digests. Immich needs the vector extension for search, so the stock
`postgres` image cannot be used.

To upgrade, read the release notes, back up the database (section "Database backup"), then set
`IMMICH_VERSION` and, if the release file changed them, the `immich-db` and `immich-redis` image
lines in `docker-compose.yml`, and run `docker compose up -d` again.

## Existing PostgreSQL instance (not used here)

The root stack has a PostgreSQL instance for Paperless (`paperless-db`, image
`postgres:18.6-trixie`, see `compose.yaml`). Immich does **not** use it. This stack has its own
database with the vector extension. The existing instance was not checked for the vector
extension, and it was not changed. If that is needed later, check it read-only on the server:
`SELECT name FROM pg_available_extensions WHERE name LIKE 'vector%';`

## Containers

| Service | Image | Purpose | Published |
| --- | --- | --- | --- |
| `immich-server` | `immich-server:v3.3.5` | Web UI, API, reads the originals, writes the thumbnails | `HOST_IP:2283` |
| `immich-machine-learning` | `immich-machine-learning:v3.3.5` (CPU) | CLIP embeddings and face recognition | no |
| `immich-db` | `ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0` | Database | no |
| `immich-redis` | `valkey/valkey:9` | Cache and job queue, no volume | no |

## Networks

- `default`: only `immich-server` joins it. Its port is published on `HOST_IP`. The host firewall
  (ufw) limits access to the LAN, as for every other published port.
- `backend`: `internal: true`, no route to the internet. `immich-server`, `immich-db`,
  `immich-redis` and `immich-machine-learning` join it.

Exception: `immich-machine-learning` also joins `default`, because it downloads its CLIP and
face models from the internet on first use. After the models are downloaded, it can be moved to
`backend` only, by removing `default` from its `networks:` list. Then the models must already be in
the model cache.

## Volumes and backups

All host paths come from `immich/.env`. They must exist before the first start.

| Variable | Container path | Access | Content | Backup needed |
| --- | --- | --- | --- | --- |
| `IMMICH_ORIGINALS_HOST_PATH` | `/mnt/originals` | **read-only** | The year folders (originals) | **Yes, separately, not by this stack.** A read-only mount does not protect against a failing disk. Back up the NAS folder with its own job. |
| `IMMICH_UPLOAD_DIR` | `/data` | read-write | Thumbnails, transcoded videos, Immich's own database dumps (`backups/`), and **files uploaded through the app** (`upload/`) | See below |
| `IMMICH_DB_DIR` | `/var/lib/postgresql/data` | read-write | PostgreSQL database: albums, faces, search index, file paths | **Yes.** Daily `pg_dump` to a second, independent target, see "Database backup". |
| `IMMICH_MODEL_CACHE_DIR` | `/cache` | read-write | CLIP and face models | No. Downloaded again on demand. |
| Valkey | no volume | none | Cache and job queue | No. Rebuilt by Immich. |

### Decision: the upload directory is not backed up by default

Thumbnails, transcoded videos and Immich's built-in database dumps in `${IMMICH_UPLOAD_DIR}` are
regenerable. They can be rebuilt from the originals and the database.

**Exception:** `${IMMICH_UPLOAD_DIR}/upload/` holds every file that someone uploads through the app
or the mobile client. Those files are not regenerable. This setup is meant as a read-only archive,
so uploads should not happen. If someone uploads through the app anyway, those files need a backup
(the directory `upload/` only), or they must be moved to the originals folder on the NAS.

Immich also writes its own database dumps to `${IMMICH_UPLOAD_DIR}/backups/`, if its built-in backup
is enabled (check the settings and the docs of v3.3.5 for schedule and retention). They live on the
same disk, so they are not a substitute for the off-site copy below.

## Database backup

The database is the only state that is not regenerable and not in the originals. Immich's own
dumps (see above) are on the same disk. The off-site copy below is the real backup.

**Method:** `pg_dump` in custom format, taken from the running container. Do not copy the files of
`${IMMICH_DB_DIR}` while the database runs.

```bash
cd ~/<DEPLOY_DIR>/immich
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker compose exec -T immich-db pg_dump -U immich -d immich -Fc > "<backup-target>/immich-$STAMP.dump"
docker compose exec -T immich-db pg_restore --list < "<backup-target>/immich-$STAMP.dump" > /dev/null && echo "dump OK"
```

- **Second, independent target:** a second disk, an external drive or another machine, not the
  server's data disk. This is the target that protects against disk loss. It is **not yet set up**,
  see "Open decisions".
- **Frequency:** daily, in the same run as the originals backup.
- **Retention:** 14 daily dumps on the target (about two weeks). Older dumps are deleted only after
  a successful new dump.
- **Consistency:** a dump is a consistent snapshot of one point in time. Keep it together with the
  originals copy of the same day, so the photos and their database entries belong together.

**Restore test (do it once after the first backup, then every few months):**

```bash
# Restore into a separate, empty database, not the live one.
docker compose exec -T immich-db createdb -U immich restore_test
docker compose exec -T immich-db pg_restore -U immich -d restore_test --no-owner < "<backup-target>/immich-<stamp>.dump"
docker compose exec -T immich-db psql -U immich -d restore_test -c "SELECT count(*) FROM assets;"
docker compose exec -T immich-db dropdb -U immich restore_test
```

The count must be plausible (the number of photos Immich shows in the UI). For a full disaster
recovery, the database restore must be done in a stopped stack, with the same Immich version, into
an empty `${IMMICH_DB_DIR}`.

## Start

1. Create the host folders, for example:
   ```bash
   sudo mkdir -p /srv/infrastructure/data/immich/{upload,database,model-cache}
   ```
   Use paths below `DATA_DIR`, like the other services. The database folder must be writable by the
   container user. Let Docker create it, or set the owner as the image expects.
2. Create the configuration:
   ```bash
   cp .env.example .env
   ```
   Fill in every value: `HOST_IP`, the two generated passwords (`openssl rand -hex 24`), the host
   paths. Remove the placeholders `<...>`.
3. Check the configuration **before** starting:
   ```bash
   docker compose config --quiet && echo "config OK"
   ```
4. Start:
   ```bash
   docker compose up -d
   docker compose ps
   ```
5. Open `http://<HOST_IP>:2283`.

## Manual steps after the first start

1. **Admin account:** the first user who signs up becomes the administrator. Create it in the UI.
   Keep the password in a password manager.
2. **External library:** Administration > External Libraries > Create library. Owner: the admin.
   Import path: `/mnt/originals`. Enable the scan. Immich reads the year folders and never writes
   there.
3. **Read-only check:** Immich may report that it cannot write a marker file into the import
   path. Create the marker files on the NAS side, the mount is read-only inside the container.
   Check the Immich documentation for the version in use before doing this.
4. **Models:** the first scan downloads the CLIP and face models into `${IMMICH_MODEL_CACHE_DIR}`.
   This needs internet access (see "Networks"). Check that smart search returns results after the
   first scan finishes.
5. **Data safety:** turn off the phone upload in the mobile app for this server, if it is used
   (see the decision above).

## Operations

```bash
docker compose ps                       # status
docker compose logs -f immich-server    # web UI and import jobs
docker compose logs -f immich-machine-learning   # model download and search indexing
```

After changing `.env` or `docker-compose.yml`, run `docker compose up -d`. A plain `docker compose restart`
does not apply changes to the environment or the compose file.

## Security

- The web UI is plain HTTP on the LAN, like Paperless. Do not forward port 2283 on the router.
- Only `immich-server` publishes a port. The database and the cache are not reachable from the LAN.
- The cache has a password. The database has a password. Both are generated, not reused.
- Photos are personal data. Every backup copy is as sensitive as the photos. Encrypt the off-site
  copy and limit who can read it.

## Open decisions

These were not decided in this change. The stack works without them:

1. **Second backup target** for the database dumps and the originals: which medium (second disk,
   external drive, off-site location) and who runs the copy.
2. **Backup job for the database**: not added to the root `backup` container, because that
   container belongs to the Paperless and Pi-hole stack. Options: a cron job on the host, or a
   separate backup service in `immich/`.
3. **Upload directory**: whether uploads through the app are allowed. If yes, back up `upload/`.
4. **Model download**: the machine-learning container needs internet once. Alternative: download the
   models on a machine with internet access and copy them into the model cache, then remove the
   `default` network from `immich-machine-learning`.
5. **Healthchecks**: not set for `immich-server` and `immich-machine-learning`. The official compose
   file was not checked for an HTTP health endpoint in this version. Add one after checking it against
   the running image.
6. **Not tested here**: this environment has no Docker. `docker compose config`, the start and the
   restore test have **not** been run. They must run before the stack is deployed to the server.
