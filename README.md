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
ss -tln | grep -E ':(53|445|3142|8081|8082|8083)\b'   # every listener shows HOST_IP, not 0.0.0.0
sudo ufw status verbose                                # default deny incoming, allow from ALLOWED_NETWORK
```
