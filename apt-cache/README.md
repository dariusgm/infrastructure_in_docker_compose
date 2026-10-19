# apt-cache

apt-cacher-ng, the Ubuntu package cache, on port 3142 of `HOST_IP`. Cached packages are stored in
`${DATA_DIR}/apt-cache/apt-cacher-ng` on the host, so they survive rebuilds.

## Use the cache on a client

Easiest: `sudo python3 client.py install` in the repository root (reads `APT_CACHE_HOST` and
`APT_CACHE_PORT` from `.env`). Remove it again with `sudo python3 client.py remove`.

Manually, create `/etc/apt/apt.conf.d/02apt-cache`:

```
Acquire::http::Proxy "http://192.168.178.82:3142";
Acquire::https::Proxy "DIRECT";
```

The statistics page is at `http://<HOST_IP>:3142/acng-report.html`.
