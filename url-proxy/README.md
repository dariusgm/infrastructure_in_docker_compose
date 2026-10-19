# url-proxy

Generic nginx URL proxy with a shared cache on port 8081 of `HOST_IP`. Cached files are stored in
`${DATA_DIR}/apt-cache/url-proxy` on the host.

Replace `https://<host>/<path>` with `http://<HOST_IP>:8081/proxy/https/<host>/<path>`:

```bash
curl -fLO http://192.168.178.82:8081/proxy/https/github.com/prometheus/node_exporter/releases/download/v1.8.1/node_exporter-1.8.1.linux-amd64.tar.gz
```

The response header `X-Cache-Status` shows `HIT` when the file came from the cache. Redirects are
routed through the proxy as well.

Any host can be reached through the proxy. That is why it is bound to `HOST_IP` and must not be
exposed to the internet.
