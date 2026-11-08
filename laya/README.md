# laya: local decision model for the fleetify judge

[Laya](https://github.com/NandhaKishorM/laya) is an open-weight decision model (Apache-2.0, Convai
Innovations). It answers typed questions in one forward pass on the CPU and runs entirely on this
host. fleetify uses it as the judge of a change (`level = "laya"`, see fleetify's README). The
judge answers over the same `/v1/systemone` protocol as TypeSafe's Jev, so fleetify's Jev code
calls it unchanged.

## Services

| Service | Image | Port | Role |
| --- | --- | --- | --- |
| `laya-init` | busybox | none | Runs once. Gives the model directory to the container's user (UID 10001). |
| `laya` | built from the laya repository at the pinned tag `v0.4.29` | none | The model server (`laya-serve`). |
| `laya-metrics` | `laya/metrics/` | `127.0.0.1:8100` | Proxy in front of `laya`: forwards every request unchanged and counts it. |

The model server publishes no port. The client port is bound to `127.0.0.1` only, because the
judge API has a bearer key but no TLS, and fleetify runs on this host. Nothing on the LAN reaches it.

Data: the checkpoint (`typed-decisions`, about 1.7 GB) is in `${DATA_DIR}/laya/models`. It is
reproducible, so it is not part of the daily backup.

## Settings

Set in `.env` (see `.env.example`):

- `LAYA_API_KEY`: the bearer key. fleetify sends it as `LAYA_API_KEY` in its own environment or
  `.env`. Required; the stack does not start without it.
- `LAYA_HOST_PORT` (default 8100), `LAYA_MEMORY` (default `4g`), `LAYA_CPUS` (default `4`).

Fixed in `compose.yaml`:

- **One execution context.** `LAYA_MAX_CONCURRENT=1` admits one request at a time. A second one gets
  `503` at once, and fleetify retries it like an overload. The model's worker is one thread anyway.
- **One checkpoint.** `LAYA_MODELS=typed-decisions`, loaded at start (`LAYA_PRELOAD=1`,
  `LAYA_MAX_LOADED=1`). The other checkpoints load on demand and would replace it.
- **Limits.** `mem_limit` and `memswap_limit` 4 GiB, `cpus` 4, `pids_limit` 256 for `laya`. The proxy
  has 128 MiB, a quarter CPU, a read-only root file system and no capabilities. The host runs about
  25 other containers, so these limits keep the host responsive.
- **Strict Jev contract** (`LAYA_JEV_STRICT=1`) and **reviewed revisions** (`LAYA_REVISION=reviewed`,
  only the checkpoint revisions listed in `laya/revisions.py` may load).
- The image is built from the git tag `3c346a2f`, not a branch. Upgrading means changing that hash in
  `compose.yaml`, reading the release notes, and rebuilding.

## Metrics

`laya-metrics` serves `/metrics` on the `monitoring` network. Prometheus job `laya`
(`monitoring/prometheus/prometheus.yml`) scrapes it.

| Metric | Meaning |
| --- | --- |
| `laya_requests_total{route,code}` | requests by route and HTTP status (503 = the one slot was busy) |
| `laya_request_seconds{route}` | time in the proxy, including the wait for the slot |
| `laya_inference_seconds{route}` | inference time that Laya reports in `Server-Timing` |
| `laya_in_flight_requests` | requests being served now |
| `laya_upstream_up` | 1 while Laya's `/health` answers 200 (polled every 15 s) |
| `laya_upstream_errors_total{kind}` | requests that failed before Laya answered (`timeout`, `connect`) |

Routes are fixed to a short list (`/v1/systemone`, `/v1/systemone/batch`, `/v1/route`, `/health`,
`/models`, and `other`), so the label set stays small.

## Start and checks

```bash
docker compose up -d --build laya laya-init laya-metrics   # first start downloads the checkpoint
docker compose ps laya laya-metrics                        # both healthy
curl -s http://127.0.0.1:8100/metrics | grep laya_upstream_up
```

The first start takes several minutes (PyTorch, then the checkpoint). `healthy` means `/health` answers
with the key; it does not prove that the model answers. Send the test request below for that.

An end-to-end check that does not need fleetify: send one request with the key (the key is read from
`.env`, not typed into the shell history):

```bash
KEY=$(grep '^LAYA_API_KEY=' .env | cut -d= -f2-)
curl -s http://127.0.0.1:8100/v1/systemone -H 'content-type: application/json' \
  -H "authorization: Bearer $KEY" \
  --data '{"model":"typed-decisions","state":"Diff: let x = 1 became let count = 1.","questions":{"verdict":{"type":"choice","instructions":"Judge.","criteria":{"pass":"fix","fail":"gamed","unsure":"unknown"}}}}'
```

## Known limits

- **Calibration.** Laya's own `confidence` is normalized entropy. fleetify computes Jev's formula from
  the `probabilities` instead. On a trivial, correct change the checkpoint gives `pass` at about 0.34,
  so a `min_confidence` of 0.5 sends such a change to review. Measure the threshold before relying on it.
- **Startup warning.** The log says the checkpoint "ships invalid temperatures" for choice questions with
  11 or more options, which the judge does not ask. It is clamped to 0.5 by Laya.
- **Input size.** `typed-decisions` is asked for up to 8192 tokens per question (`max_len`). A judge input above the recipe's context is answered
  `unsure` by fleetify before any call.
- **Not covered by the smoke test.** `smoke/smoke.py` boots the stack without these services yet.
