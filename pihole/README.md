# pihole

Pi-hole, a DNS server that blocks ads and trackers for the whole network. It listens for DNS
queries on port 53 of `HOST_IP` (TCP and UDP) and serves its admin UI on port 8082 of `HOST_IP`.
Its state (settings, query log, block lists) lives in `${DATA_DIR}/pihole` on the host, so it
survives rebuilds and re-deploys.

## Setup

1. Set `PIHOLE_PASSWORD` in `.env` (the admin UI password). `PIHOLE_UPSTREAM_DNS` and
   `PIHOLE_TIMEZONE` are optional, see `.env.example`.
2. Deploy as usual (`python3 deploy.py deploy`). `server/bootstrap.sh` allows rootless Docker to
   publish port 53.
3. In the router, set the DNS server that it hands out by DHCP to `HOST_IP`. Clients that renew
   their lease then use Pi-hole without any per-device change.
   - Add a second DNS server (for example the router itself) only if you accept that clients
     fall back to it when Pi-hole is down. Otherwise, a Pi-hole outage stops name resolution on
     the whole network.
4. Open the admin UI at `http://<HOST_IP>:8082/admin` and log in with `PIHOLE_PASSWORD`.

## Limits

- Pi-hole sees the source address of the containers' network proxy, not the address of each
  client. The rootless Docker network does not keep client addresses. The query log therefore
  does not show which device made a query, and per-client rules do not work. Blocking works
  for all clients.
- Pi-hole is reachable only from `ALLOWED_NETWORK`, like everything else on the host.
  Never forward port 53 or 8082 on the router.

## Changing the configuration

Most settings are environment variables in `compose.yaml` (`FTLCONF_*`), which are fed from
`.env`. Change them there and run `python3 deploy.py deploy`. Block lists and other changes made
in the admin UI are kept in `${DATA_DIR}/pihole` and do not need a redeploy.
