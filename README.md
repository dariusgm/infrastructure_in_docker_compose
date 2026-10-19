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
   Fill in `HOST_IP`, `HOST_USERNAME`, `HOST_PASSWORD` and `REPO_URL`.
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

## Data

Every component stores its data in a bind mount below `DATA_DIR` (default
`/srv/infrastructure/data`). That directory is outside the repository checkout, so updating
the repository or the compose file does not touch the data.

## Network rules

- The firewall (ufw) denies all inbound traffic except from `ALLOWED_NETWORK`.
- Published container ports are bound to `HOST_IP` in `compose.yaml`. Docker bypasses ufw for
  published ports, so this binding is required.
- Nothing is meant to be exposed to the internet. Do not add a router port forward.
