---
name: update-service
description: Clean, reversible update of one image in the production stack on the .82 server (192.168.178.82), e.g. paperless-ngx. Use when a service has a new release and it must be upgraded on the live host.
---

# Update a service on the production host (.82)

Scope: one service image per update. Never combine updates, never touch data directories.
Service-specific notes live in `reference/<service>.md` (paperless: `reference/paperless.md`).

## Hard rules

1. **Never upload the local `.env` to the host.** `deploy.py deploy` does exactly that. The host's
   `.env` holds secrets that the local `.env` does not have (see `reference/paperless.md`).
   Before any deploy, confirm the local `.env` contains every variable the host's `.env` has
   (compare names only: `grep -oE '^[A-Z_]+=' .env | sort`). If not, stop and ask the user.
2. Never print or copy secret values into chat, commits or logs. Compare names, not values.
3. Never run `docker compose down -v`, `docker volume rm`, or delete anything below `DATA_DIR`
   (default `/srv/infrastructure/data`).
4. Commit and push only with the user's explicit go-ahead. Deploy only after a verified backup.
5. Do not update `paperless-db` (PostgreSQL) to a new major version in a routine update. That needs
   a dump, restore and an explicit plan.

## Procedure

### 1. Decide the target
- Current running version: `docker compose ps` on the host, or the `image:` line in `compose.yaml`.
- Latest release: `gh api repos/<owner>/<repo>/releases/latest --jq .tag_name`.
- Read every release note between current and target. Note breaking changes, removed
  dependencies, new required variables, and manual steps. Record them for the user.

### 2. Pre-flight (read-only) on the host
Run `bash .claude/skills/update-service/scripts/preflight.sh`. It checks:
- all containers `running` or `healthy`, none restarting
- disk space on the `DATA_DIR` filesystem (at least 20% free)
- the host checkout is clean and in sync with `origin/main`
- the newest database dump is less than 26 hours old
- the image currently running

If any check fails, stop and report. Known issue on .82 at the time of writing: the host
checkout is one commit ahead of origin (`4c985d9 Add stopgap for CVE-2026-98432 to bootstrap`).
It is not pushed. Deploying from origin would lose it. Ask the user first.

### 3. Backup
```bash
ssh <user>@<host> 'cd ~/infrastructure_in_docker_compose && docker compose exec backup backup.sh once'
```
Verify the new dump: `pg_restore --list` on it must succeed, and it must be newer than the
update start time. Ask the user to copy `${DATA_DIR}/backup` off the server before deploying.
Copying off-host is their decision.

### 4. Change the version
- Edit only the `image:` tag of that service in `compose.yaml` (in the repo the host deploys from,
  which is `origin/main`).
- Keep the change to that line plus any required new variables (added to `.env.example` only,
  never with real values).
- Show the diff to the user. Commit with the required trailer:
  `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`. Push only when they say so.

### 5. Deploy
- Only after steps 1–4 pass and the `.env` check in rule 1 is green:
  `python3 deploy.py deploy`
- Watch for `Deployment finished.` If it fails, do not retry blindly. Read the failing step.

### 6. Verify
- `docker compose ps`: every service `healthy` or `running`.
- `docker compose logs --tail 200 <service>`: migrations finished, no tracebacks.
- The service's own checks from `reference/<service>.md`. For paperless: status page all OK,
  log in, search a known document, upload and delete one test PDF.
- Monitoring still scraping (Prometheus targets for the service's exporter are up).

### 7. Roll back (if verification fails)
- There is no automatic rollback. A newer app version can migrate the database.
- Restore the database dump from step 3 into the stopped service, following `backup/README.md`.
- Set the old image tag, deploy, verify. Tell the user what was restored and when.

## Report back

Give the user: version before and after, release-note items that applied, backup file name,
verification results, and anything left open (e.g. the unpushed host commit).
