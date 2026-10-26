# immich

Immich, the photo library, used as a **read-only archive** of the year folders on the NAS. Search by
content uses CLIP (CPU, no GPU), faces are recognised, and the original files are never modified:
the originals are mounted read-only.

The services are part of the root `compose.yaml` (`immich-server`, `immich-machine-learning`,
`immich-db`, `immich-redis`). Configuration is in the root `.env` (see `.env.example`, section
"Photo archive"). Start with the rest of the stack: `python3 deploy.py deploy`.

## Version and dependencies

Pinned to **Immich v3.3.5**, the latest stable release (21 Oct 2026):
https://github.com/immich-app/immich/releases/tag/v3.3.5

The images are the ones of that release's compose file, including digests:
https://github.com/immich-app/immich/blob/v3.3.5/docker/docker-compose.yml

| Image | Version | Why this one |
| --- | --- | --- |
| `immich-server`, `immich-machine-learning` | `v3.3.5` | Latest stable release |
| `immich-db` | `ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0` | Immich's own image with the vector extensions. Release v3.3.5 ships it. |
| `immich-redis` | `valkey/valkey:9` (digest of v3.3.5) | Valkey 9 as used by the release |

Not taken: VectorChord 1.1.1 is the newest VectorChord, but v3.3.5 does not ship with it. Newer
versions of the database image or Valkey would be an untested combination with Immich. The
`main` branch of Immich has a newer Valkey digest, which is not in a release yet.

**Open:** PostgreSQL 14 (in the image above) reaches end of life in November 2026. Immich v3.3.5
does not offer a newer PostgreSQL image, so the database stays on 14 for now. Moving to a newer major
version needs a dump and restore and a release of Immich that supports it. Check for that before
the stack goes to the server, and again after each Immich release.

## Existing PostgreSQL instance (not used here)

Paperless uses its own PostgreSQL (`paperless-db`, image `postgres:18.6-trixie`). Immich does not
use it. The vector extension is in Immich's own database image. Whether the Paperless database has
the extension was not checked, and it was not changed.

## Containers and networks

| Service | Published | Networks |
| --- | --- | --- |
| `immich-server` | `${HOST_IP}:2283` | `default` (published port) and `immich-backend` |
| `immich-machine-learning` | no | `immich-backend` and `default` (internet, to download its models) |
| `immich-db` | no | `immich-backend` only |
| `immich-redis` | no | `immich-backend` only |

`immich-backend` is `internal: true`, so the database and the cache have no route to the internet.
`immich-machine-learning` joins `default` only to download its CLIP and face models on first use.
After that, remove `default` from its `networks:` list in `compose.yaml`, which keeps it off the
internet.

## Volumes and backups

| Host path | Container path | Access | Content | Backup needed |
| --- | --- | --- | --- | --- |
| `IMMICH_ORIGINALS_DIR` | `/mnt/originals` | **read-only** | The original photos | **Yes, separately, not by this stack.** A read-only mount does not protect against a failing disk. |
| `${DATA_DIR}/immich/upload` | `/data` | read-write | Thumbnails, transcoded videos, Immich's own database dumps (`backups/`), files uploaded through the app (`upload/`) | See below |
| `${DATA_DIR}/immich/postgres` | `/var/lib/postgresql/data` | read-write | Database: albums, faces, search index, file paths | **Yes.** Daily `pg_dump` to a second, independent target. |
| `${DATA_DIR}/immich/model-cache` | `/cache` | read-write | CLIP and face models | No. Downloaded again on demand. |
| Valkey | none | none | Cache and job queue | No. Rebuilt by Immich. |

The root `backup` container does **not** cover Immich. It belongs to the Paperless and Pi-hole
stack and was not changed. Immich's backup is a separate decision (see "Open decisions").

### The upload directory is not regenerable in full

Thumbnails, transcoded videos and Immich's own database dumps can be rebuilt from the originals and
the database. But `${DATA_DIR}/immich/upload/upload/` holds every file uploaded through the app or
the mobile client, and those cannot be rebuilt. This setup is a read-only archive, so uploads should
not happen. If uploads are allowed, back up `upload/` as well.

Immich's own database dumps in `backups/` (if its built-in backup is enabled, check the settings and
the docs of v3.3.5) are on the same disk. They are not a substitute for the off-site copy.

## Database backup

The database is the only state that is neither regenerable nor in the originals. Immich's own dumps
are on the same disk, so the off-site copy is the real backup. Do not copy the files of
`${DATA_DIR}/immich/postgres` while the database runs.

```bash
cd ~/<DEPLOY_DIR>
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker compose exec -T immich-db pg_dump -U immich -d immich -Fc > "<backup-target>/immich-$STAMP.dump"
docker compose exec -T immich-db pg_restore --list < "<backup-target>/immich-$STAMP.dump" > /dev/null && echo "dump OK"
```

- **Target:** a second disk, an external drive or another machine, not the server's data disk.
  **Not set up yet**, see "Open decisions".
- **Frequency:** daily, in the same run as the originals copy.
- **Retention:** 14 daily dumps (about two weeks). Delete older dumps only after a new one succeeded.
- **Consistency:** keep each dump together with the originals copy of the same day.

**Restore test (once after the first backup, then every few months):**

```bash
# Restore into a separate, empty database, not the live one.
docker compose exec -T immich-db createdb -U immich restore_test
docker compose exec -T immich-db pg_restore -U immich -d restore_test --no-owner < "<backup-target>/immich-<stamp>.dump"
docker compose exec -T immich-db psql -U immich -d restore_test -c "SELECT count(*) FROM assets;"
docker compose exec -T immich-db dropdb -U immich restore_test
```

The count must match the number of photos Immich shows in the UI. For a full recovery, restore into a
stopped stack with the same Immich version and an empty `${DATA_DIR}/immich/postgres`.

## Setup

1. Add the Immich values to `.env` (copy them from `.env.example`, section "Photo archive"):
   `IMMICH_DB_PASSWORD` and `IMMICH_REDIS_PASSWORD` (generate each with `openssl rand -hex 24`),
   `IMMICH_ORIGINALS_DIR` (the host folder with the year folders). `IMMICH_TIMEZONE` is optional.
   **The stack does not start without the first three values**, and that includes the existing
   services. Set them before the next deploy.
2. Check the folder for the originals exists on the host.
3. Deploy: `python3 deploy.py deploy`. The data folders below `DATA_DIR` are created by Docker.
4. Open `http://<HOST_IP>:2283`.

## Manual steps after the first start

1. **Admin account:** the first user who signs up becomes the administrator. Keep its password in a
   password manager.
2. **External library:** Administration > External Libraries > Create library. Owner: the admin.
   Import path: `/mnt/originals`. Start the scan. Immich only reads there.
3. **Read-only check:** Immich may report that it cannot write a marker file into the import path.
   Check the Immich documentation for v3.3.5 for how to handle this. Any marker file is created on the
   NAS side, because the mount is read-only inside the container.
4. **Models:** the first scan downloads the CLIP and face models. Check that smart search returns
   results once the scan has finished.
5. **Uploads:** if the mobile app is used with this server, decide whether uploads are allowed (see
   "The upload directory is not regenerable in full").

## Operations

```bash
docker compose ps                                  # status of all services
docker compose logs -f immich-server               # web UI and import jobs
docker compose logs -f immich-machine-learning     # model download and indexing
```

After changing `.env` or `compose.yaml`, run `python3 deploy.py deploy`. A plain
`docker compose restart` does not apply changes to the environment or the compose file.

## Security

- The web UI is plain HTTP on the LAN, like Paperless. Do not forward port 2283 on the router.
- Only `immich-server` publishes a port. The database and the cache are not reachable from the LAN.
- The database and the cache have generated passwords, not reused ones.
- Photos are personal data. Every backup copy is as sensitive as the photos. Encrypt the off-site copy
  and limit who can read it.

## Open decisions

1. **PostgreSQL 14 end of life (November 2026):** when does the database move to a supported major
   version, and does a newer Immich release support it? Requires a dump and restore.
2. **Backup target** for the database dumps and the originals: which medium and who runs the copy.
3. **Backup job**: not in the root `backup` container. Options: a cron job on the host, or a separate
   backup service.
4. **Uploads through the app:** allowed or not. If allowed, `upload/` needs a backup.
5. **Model download:** the one-time internet access of `immich-machine-learning`. Alternative: download
   the models elsewhere, copy them into the model cache, then remove `default` from that service.
6. **Health checks** for `immich-server` and `immich-machine-learning` are not set. The image's HTTP
   endpoint was not verified. Add them after checking against the running image.
7. **Not tested here:** this machine had no Docker, so `docker compose config`, the start and the
   restore test have **not** been run.
