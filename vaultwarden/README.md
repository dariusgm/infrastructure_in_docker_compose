# vaultwarden

Vaultwarden is a server for the Bitwarden protocol, written in Rust. The Bitwarden apps, browser
extensions and the web vault connect to it unchanged. Data is stored in a SQLite database below
`${DATA_DIR}/vaultwarden`.

Image: `docker.io/vaultwarden/server`, pinned to a version in `compose.yaml`. Port 80 in the
container is published as `http://<HOST_IP>:8084`. The admin page is at `/admin`.

## First start

1. Generate the admin token and put it in `.env`:
   ```bash
   openssl rand -hex 48
   ```
   Set it as `VAULTWARDEN_ADMIN_TOKEN`. The stack does not start without it.
2. Create the first account. Signups are disabled by default:
   - set `VAULTWARDEN_SIGNUPS_ALLOWED=true` in `.env`, run `python3 deploy.py deploy`,
   - open `http://<HOST_IP>:8084`, click "Create account", register,
   - set `VAULTWARDEN_SIGNUPS_ALLOWED=false` again and deploy again.
3. Optional: `VAULTWARDEN_URL` sets the address the clients use. Empty means `http://<HOST_IP>:8084`.

## Known limits of this setup

- **HTTPS is required.** The web vault's crypto (Web Crypto API) only works in a secure context,
  which means HTTPS or `localhost`. Over plain HTTP it fails. Vaultwarden serves TLS itself
  (`ROCKET_TLS` in `compose.yaml`) with a certificate from a local CA:
  - The CA and the server certificate live in `${DATA_DIR}/vaultwarden-tls`. They are not in the
    repository. `ca-key.pem` is the CA's private key: keep it off the clients, and only use it to
    sign new certificates.
  - Create them with `openssl` (CA, then a server certificate whose SAN is `IP:<HOST_IP>`).
    Sign the server certificate with the CA and place `cert.pem` and `key.pem` in that folder.
  - Import `ca.pem` as trusted CA on every client. On Linux, Chrome uses the system or NSS
    store, Firefox has its own store (Settings, Privacy & Security, Certificates, Import).
  - `VAULTWARDEN_URL` must be `https://<HOST_IP>:8084`, otherwise the API links use HTTP.
  - Plain HTTP is switched off by TLS. Only `https://` answers on port 8084.
  - A certificate for a host name instead of an IP is better, when there is a DNS name.
- **Not backed up yet.** The daily backup in `backup/` does not cover this database. Before the
  vault holds real passwords, add a backup of `${DATA_DIR}/vaultwarden/db.sqlite3` (SQLite online
  backup, like the Pi-hole databases in `backup/backup.sh`) and copy it off the server.
- **Keep the data.** `${DATA_DIR}/vaultwarden` holds the encrypted vault and the attachments
  (`attachments/`). Losing it loses every password stored there. The master passwords are not
  stored on the server, so they cannot be recovered by the admin.

## Admin page

`http://<HOST_IP>:8084/admin`, logged in with `VAULTWARDEN_ADMIN_TOKEN`. It lists the users and
the diagnostics, and it can invite or delete users. Invitations send e-mail, which needs SMTP
(not configured here).

## Connect a client

In the Bitwarden app, the browser extension or the desktop app, choose "self-hosted" and enter
the server URL (`VAULTWARDEN_URL` or `http://<HOST_IP>:8084`). Then log in with the account
created above.

## Upgrade

Change the tag in `compose.yaml`, read the release notes at
https://github.com/dani-garcia/vaultwarden/releases, take a backup of `${DATA_DIR}/vaultwarden`
first, then deploy.

## Firewall

Like every service, it is reachable only from `ALLOWED_NETWORK` (see `README.md`, "Network
rules").
