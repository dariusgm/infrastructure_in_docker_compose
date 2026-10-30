# mail

Stalwart Mail Server: a mailbox service that stays on the LAN. Alertmanager (once it is set up)
sends alerts to it, and family members read their mail from it on WiFi or through WireGuard. Nothing
is relayed to the internet: the server does not deliver mail to other domains.

## Addresses

- **Mail domain:** `home.lan`. The server name is `mail.home.lan`.
- **Admin UI and account manager:** `https://mail.home.lan/admin` (administrators) and
  `https://mail.home.lan/account` (each user changes their own password). Port 443 of `HOST_IP`.
- **IMAPS for mail apps:** `mail.home.lan`, port 993, TLS.
- **Sending (submission):** port 465, implicit TLS, with a login. Alertmanager uses this port with an account
  of its own. Port 25 is not used for clients: it refuses them, because they are not other mail servers.
- **Name resolution:** phones and the admin need `mail.home.lan` to resolve. Add it as a local DNS
  record in Pi-hole (Local DNS, DNS records), pointing to `HOST_IP`.

## Certificate

`${DATA_DIR}/mail/tls/` holds `fullchain.pem` (certificate and local CA) and `privkey.pem`, issued by
the local CA (`${DATA_DIR}/vaultwarden-tls/ca.pem`). Install that CA on the phones once, so they trust
the mail connection.

## First-time setup (done once)

1. Start the container: `docker compose up -d stalwart`. With no configuration it starts in bootstrap
   mode and listens on port 8080 for setup.
2. Configure the server over JMAP with a temporary recovery administrator, passed as
   `STALWART_RECOVERY_ADMIN` in the environment. `x:Bootstrap/set` with `defaultHostname`
   `mail.home.lan`, `defaultDomain` `home.lan`, `requestTlsCertificate` `false` and `generateDkimKeys`
   `false`. The server returns the generated password of `admin@home.lan` once. Store it in `.env` as
   `MAIL_ADMIN_PASSWORD` and `MAIL_ADMIN_USER`.
3. Restart the container, then remove `STALWART_RECOVERY_ADMIN` and the setup port from `compose.yaml`
   (done in this repository). From then on only the administrator account signs in.
4. Enable metrics for Prometheus: `x:Metrics/set` with `prometheus` set to `Enabled`, `authUsername`
   `prometheus` and `authSecret` the value of `STALWART_METRICS_PASSWORD`.
5. Create the TLS certificate object: `x:Certificate/set` with `/etc/stalwart/tls/fullchain.pem` and
   `/etc/stalwart/tls/privkey.pem`, then restart.

The `stalwart-init` service sets the ownership of the data directories to the user the server runs as
(UID 2000) on every start.

## Accounts

Create one account per family member in the admin UI, under Management, Directory, Accounts. Each
account gets the role `User`. Users change their own password under `/account`.

## Metrics and alerting

- Metrics: `/metrics/prometheus` on the HTTPS listener, with basic auth. Prometheus job `stalwart`.
- The Grafana dashboard "Mail (Stalwart)" shows accounts, connections, queue, deliveries, failed
  logins and memory.
- Failed logins are the security signal to watch: `stalwart_auth_failed_total`.

## Checks

```bash
docker compose ps stalwart                                                      # healthy
curl -sk -o /dev/null -w '%{http_code}\n' https://mail.home.lan/healthz/live   # 200
```

## End-to-end test

`mail/e2e-test.sh` creates a throwaway account, sends a message over 465, reads it back over JMAP as that
account, and deletes the account. It prints PASS or FAIL. Run it on the server after any change to the mail
service.

## Notes

- The web interface is downloaded from GitHub on the first start (see the log). That needs internet once.
- Remote delivery is off: the domain does not allow relaying (`allowRelaying` is false), so mail is
  accepted only for `home.lan`.
