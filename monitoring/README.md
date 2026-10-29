# monitoring

Prometheus collects metrics and Grafana shows them as graphs. Both run as services in
`compose.yaml`.

- **Grafana**: web UI on port 3000 of `HOST_IP`, `http://<HOST_IP>:3000`. Sign in as `admin` with
  `GRAFANA_ADMIN_PASSWORD` from `.env`. Sign-up and anonymous access are off.
- **Prometheus**: no published port. Only Grafana reaches it, on the internal `monitoring`
  network. Prometheus keeps its data for `PROMETHEUS_RETENTION` (default 7d).

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

## Exporters and application metrics

Each service that is scraped has an exporter or its own metrics endpoint, and joins the
`monitoring` network so Prometheus can reach it. None publishes a port.

| Job | Reads | Notes |
| --- | --- | --- |
| `postgres-paperless`, `postgres-immich` | `paperless-db`, `immich-db` | postgres_exporter v0.20.1. Logs in as the read-only role `postgres_exporter` (pg_monitor). |
| `valkey-paperless`, `valkey-immich` | `paperless-broker`, `immich-redis` | redis_exporter v1.96.0 (works with Valkey). |
| `immich` | `immich-server:8081` | Immich's own metrics, `IMMICH_TELEMETRY_INCLUDE=all`. |
| `url-proxy` | `url-proxy:8090/stub_status` | nginx-prometheus-exporter 1.5.3. The stub_status server is in `url-proxy/nginx.conf`. |

### Postgres health checks

Each database's health check runs `pg_isready` and, in addition, asks its exporter for `/metrics`
(`monitoring/check-metrics.sh`). A database is healthy only when both answer. The exporters do not
wait for their database, so the check cannot deadlock at start.

### Roles

`monitoring/postgres/create-exporter-role.sql` creates or updates the role `postgres_exporter` with
the password from `PAPERLESS_EXPORTER_PASSWORD` / `IMMICH_EXPORTER_PASSWORD`. The `*-db-setup`
services run it once after the database is healthy. It is safe to run again.

Not yet covered: Paperless application metrics (needs an API token created in Paperless), Vaultwarden
(no native metrics endpoint), and Pi-hole (v6 exporter not verified yet).

### Checks on the server

Prometheus is not published, so check through Grafana: Explore, data source Prometheus. `pg_up`,
`redis_up`, `nginx_up` and `up{job="immich"}` should show 1 for every instance.

## Resources of every container and the host

- **cAdvisor** (`cadvisor`) reports, for every container on the host: CPU, memory (working set),
  disk I/O and network I/O. The label `name` is the container name, for example
  `infrastructure-paperless-1`. Job `containers`.
- **node-exporter** reports the host: memory pressure (PSI, `node_pressure_memory_*`), CPU, memory,
  disk and network. Job `host`.
- **paperless-app-exporter** reports Paperless statistics (documents, tags, storage, tasks). Job
  `paperless`. It reads the API with the token of the user `metrics`:
  `monitoring/paperless/create-metrics-user.py` creates that user with view permissions only. The
  user is set as staff, because the Paperless log endpoint answers 403 otherwise; it is not a
  superuser. The token is stored as `PAPERLESS_METRICS_TOKEN` in `.env`.

## Retention

Prometheus keeps 7 days (`PROMETHEUS_RETENTION`, default `7d`). Older data is removed automatically
when Prometheus compacts its storage. Change the value in `.env` and restart Prometheus.

## Debugging

Prometheus is not published on the network. Use Grafana: Explore, data source Prometheus, and
enter any PromQL query. Prometheus' own targets page is available inside the compose network only.

## Alerts (not yet set up)

Alert rules and notifications need Alertmanager, which is not in the stack yet. The rules will go
in `monitoring/prometheus/` and the notification channel (for example e-mail or a push service)
needs to be chosen first.
