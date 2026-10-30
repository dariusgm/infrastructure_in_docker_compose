# infrastructure_in_docker_compose

Deploys the stack in this repository to a single Ubuntu server on the local network.

The deployment is: clone this repository on the server, install the dependencies, and run
`docker compose up -d`. Only Python 3 and OpenSSH are needed on the local machine.

## Setup

1. Make the repository available at `REPO_URL` (the server clones it without credentials).
2. Create the configuration:
   ```bash
   cp .env.example .env
   ```
   Fill in `HOST_IP`, `HOST_USERNAME`, `HOST_PASSWORD` and `REPO_URL`, and the required values of
   each service (see `.env.example`, for example `PIHOLE_PASSWORD` and the `PAPERLESS_*` secrets).
3. Create the SSH key pair and install it on the server (uses the password once):
   ```bash
   python3 deploy.py keys
   ```
   If `HOST_PRIVATE_KEY` and `HOST_PUBLIC_KEY` are already set in `.env`, those keys are used.
4. Deploy:
   ```bash
   python3 deploy.py deploy
   ```
   This clones or updates the repository on the server, uploads `.env`, installs Docker, Compose
   and ufw, sets the firewall to allow only `ALLOWED_NETWORK` (`192.0.0.0/8`), and runs
   `docker compose up -d`. Run it again for every update.

## Layout

| Path | Purpose |
| --- | --- |
| `.env.example` | Template for the full configuration (committed) |
| `.env` | Real configuration and secrets (git-ignored, back it up) |
| `deploy.py` | Local orchestration: keys, upload, remote run |
| `server/bootstrap.sh` | Idempotent host preparation as root: packages, rootless prerequisites, firewall, data dir |
| `server/up.sh` | Idempotent start as the deploy user: rootless Docker and `docker compose up` |
| `compose.yaml` | The stack. Add components here. |
| `apt-cache/` | Image for the Ubuntu package cache (apt-cacher-ng). See `apt-cache/README.md`. |
| `url-proxy/` | Image for the generic nginx URL proxy and its cache. See `url-proxy/README.md`. |
| `pihole/` | Notes for Pi-hole, the network-wide DNS server with ad blocking. See `pihole/README.md`. |
| `paperless/` | Notes for Paperless-ngx, the document management system, and its services. See `paperless/README.md`. |
| `dashboard/` | Static start page on port 8080 with links to the web interfaces (Paperless, Immich, Pi-hole, Vaultwarden, Grafana). |
| `mail/` | Stalwart mail server, LAN only: alerts and family mailboxes. Admin UI and IMAPS. See `mail/README.md`. |
| `smoke/` | Smoke test that boots the whole stack with throwaway data and checks it, and a hook that runs it before `gh pr create`. See "Smoke test" below. |
| `monitoring/` | Prometheus (metrics) and Grafana (graphs). Grafana on port 3000. See `monitoring/README.md`. |
| `vaultwarden/` | Notes for Vaultwarden, the Rust server for the Bitwarden clients (password manager). See `vaultwarden/README.md`. |
| `immich/` | Notes for Immich, the photo archive (read-only originals, smart search, face recognition). The services are in `compose.yaml`. See `immich/README.md`. |
| `backup/` | Image and notes for the daily backup of the databases and files. See `backup/README.md`. |
| `server/consume-mount.sh` | Mounts the consume share of the NAS on the host at `/mnt/paperless-consume`. Run by `deploy.py`. |

## Data

Every component stores its data in a bind mount below `DATA_DIR` (default
`/srv/infrastructure/data`). That directory is outside the repository checkout, so updating
the repository or the compose file does not touch the data.

Paperless imports new documents from an SMB share on the NAS (`SMB_*` in `.env`). The host mounts
it at `/mnt/paperless-consume`, outside `DATA_DIR`. See `paperless/README.md`.

Backups go to `${DATA_DIR}/backup` every day. They are on the same disk as the data, so copy
them to another machine regularly. See `backup/README.md` for what is backed up and how to
restore it.

## Network rules

- The firewall (ufw) denies all inbound traffic except from `ALLOWED_NETWORK` (`192.0.0.0/8`,
  every `192.x.x.x` address). `server/bootstrap.sh` sets this up.
- Published container ports are bound to `HOST_IP` in `compose.yaml`, so they listen on the LAN
  address only. Docker runs rootless here. Rootless Docker publishes ports through sockets on the
  host, so ufw filters them. Client addresses are not visible inside the containers, so
  restrictions by client IP must be done in ufw, not in a service's configuration.
- Nothing is meant to be exposed to the internet. Do not add a router port forward.

Check on the server (as the deploy user, and with sudo for ufw):

```bash
ss -tln | grep -E ':(53|445|3000|3142|8081|8082|8083|8084)\b'   # every listener shows HOST_IP, not 0.0.0.0
sudo ufw status verbose                                # default deny incoming, allow from ALLOWED_NETWORK
```

## Smoke test

`smoke/smoke.py` boots the whole stack on this machine with throwaway data, checks it, and removes it
again. Run it from the repository root:

```bash
python3 smoke/smoke.py
```

What it does:

1. Preflight: Docker, at least 4 GiB of memory and 15 GiB of disk free, and no full stack running.
2. Writes a temporary `.env` with generated secrets. It binds to `127.0.0.2`, so the ports don't clash
   with the LAN address of a running stack. A local CA issues the certificates for Vaultwarden and Stalwart.
3. Starts every service and waits until all of them are healthy.
4. Does the one-time setup from the READMEs: the Stalwart bootstrap, its certificate and metrics, and the
   Paperless metrics user.
5. Checks each endpoint, that every Prometheus target is up, that the exporters deliver data, the Grafana
   data source, and sends and reads back a mail (`mail/e2e-test.sh`).
6. Removes the containers and the temporary data, also when a check fails.

Only one stack runs at a time. The smoke test refuses to start while the full stack is running. Set
`SMOKE_KEEP=1` to keep the smoke stack running for debugging.

It takes roughly 15 to 20 minutes, mostly the first start of Immich, Paperless and Stalwart.

### Pre-PR hook

`smoke/pre_pr_hook.py` runs the smoke test before `gh pr create`. If the full stack is up, the hook
stops it, runs the smoke test, and starts the full stack again, also when the test fails. A failing
test blocks the pull request. Set `SMOKE_SKIP=1` to skip the test once.

Register the hook in `.claude/settings.json` (create the file if it does not exist):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/smoke/pre_pr_hook.py",
            "timeout": 2400
          }
        ]
      }
    ]
  }
}
```

The `timeout` is in seconds. A full run needs up to 40 minutes, so keep it at 2400 or more.
