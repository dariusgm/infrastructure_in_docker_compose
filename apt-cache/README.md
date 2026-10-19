# apt-cache

One container with two services, both reachable on `HOST_IP` only:

| Port | Service | Use |
| --- | --- | --- |
| 3142 | apt-cacher-ng | Ubuntu package cache for `apt` |
| 8081 | nginx URL proxy | Cache for other HTTP(S) downloads |

Cached data is stored in `${DATA_DIR}/apt-cache/` on the host, so it survives rebuilds.

## Use the package cache on a client

Create `/etc/apt/apt.conf.d/02proxy` on each Ubuntu system (replace the address with `HOST_IP`):

```
Acquire::http::Proxy "http://192.168.1.10:3142";
```

Then run `sudo apt-get update` as usual. Packages fetched once are served from the cache afterwards.

Check that the proxy is working: `http://<HOST_IP>:3142/acng-report.html` shows the cache statistics.

## Use the URL proxy

Replace the upstream URL `https://<host>/<path>` with `http://<HOST_IP>:8081/proxy/https/<host>/<path>`:

```bash
curl -fLO http://192.168.1.10:8081/proxy/https/github.com/prometheus/node_exporter/releases/download/v1.8.1/node_exporter-1.8.1.linux-amd64.tar.gz
```

The response header `X-Cache-Status` shows `HIT` when the file came from the cache.

Any host can be reached through the URL proxy. That is why it is bound to `HOST_IP` and must not be exposed to the internet.
