# monitoring

Prometheus collects metrics and Grafana shows them as graphs. Both run as services in
`compose.yaml`.

- **Grafana**: web UI on port 3000 of `HOST_IP`, `http://<HOST_IP>:3000`. Sign in as `admin` with
  `GRAFANA_ADMIN_PASSWORD` from `.env`. Sign-up and anonymous access are off.
- **Prometheus**: no published port. Only Grafana reaches it, on the internal `monitoring`
  network. Prometheus keeps its data for `PROMETHEUS_RETENTION` (default 30d).

## Files

| Path | Purpose |
| --- | --- |
| `prometheus/prometheus.yml` | Scrape configuration. Targets are added here. |
| `grafana/provisioning/datasources/` | Prometheus data source, created at start. |
| `grafana/provisioning/dashboards/` | Loads the dashboards in `grafana/dashboards/`. |
| `grafana/dashboards/` | Dashboard JSON files. Empty for now. |

Data lives below `${DATA_DIR}/monitoring/` (`prometheus`, `grafana`). It is reproducible from the
configuration, so it is not part of the daily backup in `backup/`.

## Boot order

1. `monitoring-init` (busybox) runs once and hands the data directories to the UIDs the images run
   as: Prometheus 65534, Grafana 472. Under rootless Docker the deploy user cannot write to
   them otherwise.
2. `prometheus` starts. Its health check is `promtool check healthy`.
3. `grafana` starts after Prometheus is healthy.

## Versions

- Prometheus `v3.15.1`, the latest release on Docker Hub. Prometheus 3 reads the same
  `prometheus.yml` as 2.x, so the configuration does not depend on the minor version.
- Grafana `13.2.4`. Provisioning files use the `apiVersion: 1` format of Grafana 8 and later.
- busybox `1.37.0`, only for `monitoring-init`.

Upgrade by changing the tag, reading the release notes and taking a backup of `${DATA_DIR}/monitoring`
first.

## Checks on the server

```bash
docker compose ps prometheus grafana                  # both healthy
curl -s http://<HOST_IP>:3000/api/health              # Grafana answers
```

The Grafana data source "Prometheus" should show "Data source is working" under
Connections, Data sources.
