"""Metrics proxy in front of the Laya HTTP server (laya-serve).

Every request goes to Laya unchanged and is counted here, so the Laya container itself needs no
change. Prometheus reads /metrics on this port over the `monitoring` network. The client-facing
port is published on the loopback address only (see compose.yaml).

Metrics:
  laya_requests_total{route,code}          requests by route and HTTP status
  laya_request_seconds{route}              end-to-end time in this proxy, including Laya's queue
  laya_inference_seconds{route}            inference time Laya reports in its Server-Timing header
  laya_in_flight_requests                  requests being served now
  laya_upstream_up                         1 while Laya's /health answers 200 (polled)
  laya_upstream_errors_total{kind}         requests that failed before Laya answered (timeout, connect)

Route labels are fixed to a short list, so the label set stays small whatever clients send.
"""

import http.client
import logging
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

UPSTREAM = os.environ.get("LAYA_UPSTREAM", "laya:8000")
LISTEN_PORT = int(os.environ.get("LAYA_METRICS_PORT", "8100"))
UPSTREAM_TIMEOUT = float(os.environ.get("LAYA_UPSTREAM_TIMEOUT", "300"))
HEALTH_INTERVAL = float(os.environ.get("LAYA_HEALTH_INTERVAL", "15"))
MAX_BODY = int(os.environ.get("LAYA_MAX_BODY_BYTES", str(8 * 1024 * 1024)))
API_KEY = os.environ.get("LAYA_API_KEY", "")

ROUTES = {"/v1/systemone", "/v1/systemone/batch", "/v1/route", "/health", "/models"}
BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300)

REQUESTS = Counter("laya_requests_total", "Requests to Laya by route and HTTP status.", ["route", "code"])
LATENCY = Histogram(
    "laya_request_seconds",
    "Time from request to response in the proxy, including Laya's queue.",
    ["route"],
    buckets=BUCKETS,
)
INFERENCE = Histogram(
    "laya_inference_seconds",
    "Inference time Laya reports in its Server-Timing header.",
    ["route"],
    buckets=BUCKETS,
)
IN_FLIGHT = Gauge("laya_in_flight_requests", "Requests being served right now.")
UPSTREAM_UP = Gauge("laya_upstream_up", "1 while Laya's /health answers 200.")
UPSTREAM_ERRORS = Counter(
    "laya_upstream_errors_total", "Requests that failed before Laya answered.", ["kind"]
)


def _upstream_address():
    host, _, port = UPSTREAM.partition(":")
    return host, int(port or 8000)


def _auth_headers():
    return {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}


def _poll_health():
    """Sets laya_upstream_up every HEALTH_INTERVAL seconds, independent of client traffic."""
    host, port = _upstream_address()
    while True:
        up = 0
        try:
            conn = http.client.HTTPConnection(host, port, timeout=5)
            conn.request("GET", "/health", headers=_auth_headers())
            up = 1 if conn.getresponse().status == 200 else 0
            conn.close()
        except (OSError, http.client.HTTPException):
            up = 0
        UPSTREAM_UP.set(up)
        time.sleep(HEALTH_INTERVAL)


def _inference_seconds(server_timing):
    """Reads `inference;dur=12.34` (milliseconds) from Laya's Server-Timing header."""
    for part in server_timing.split(","):
        for field in part.split(";"):
            field = field.strip()
            if field.startswith("dur="):
                try:
                    return float(field[4:]) / 1000.0
                except ValueError:
                    return None
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "laya-metrics"

    def log_message(self, fmt, *args):  # request lines are counted in the metrics, not logged
        pass

    def do_GET(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self):
        path = urllib.parse.urlsplit(self.path).path
        if self.command == "GET" and path == "/metrics":
            self._send(200, generate_latest(REGISTRY), CONTENT_TYPE_LATEST)
            return

        route = path if path in ROUTES else "other"
        if self.headers.get("Transfer-Encoding"):
            REQUESTS.labels(route, "411").inc()
            self._send(411, b'{"detail":"send a Content-Length"}', "application/json")
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            REQUESTS.labels(route, "413").inc()
            self._send(413, b'{"detail":"request body too large"}', "application/json")
            return
        body = self.rfile.read(length) if length else None

        # Clients bring their own bearer token; the proxy only passes it on.
        headers = {}
        for name in ("Authorization", "Content-Type"):
            value = self.headers.get(name)
            if value:
                headers[name] = value

        status, payload, content_type = 502, b'{"detail":"laya unavailable"}', "application/json"
        inference = None
        host, port = _upstream_address()
        IN_FLIGHT.inc()
        started = time.perf_counter()
        try:
            conn = http.client.HTTPConnection(host, port, timeout=UPSTREAM_TIMEOUT)
            try:
                conn.request(self.command, self.path, body=body, headers=headers)
                response = conn.getresponse()
                payload = response.read()
                status = response.status
                content_type = response.getheader("Content-Type", "application/json")
                timing = response.getheader("Server-Timing")
                if timing:
                    inference = _inference_seconds(timing)
            finally:
                conn.close()
        except (OSError, http.client.HTTPException) as error:
            kind = "timeout" if isinstance(error, TimeoutError) else "connect"
            UPSTREAM_ERRORS.labels(kind).inc()
            logging.warning("laya upstream %s on %s: %s", kind, route, error)
        finally:
            IN_FLIGHT.dec()

        LATENCY.labels(route).observe(time.perf_counter() - started)
        REQUESTS.labels(route, str(status)).inc()
        if inference is not None:
            INFERENCE.labels(route).observe(inference)
        self._send(status, payload, content_type)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    threading.Thread(target=_poll_health, name="health", daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler)
    server.daemon_threads = True
    logging.info("laya metrics proxy on :%d for %s", LISTEN_PORT, UPSTREAM)
    server.serve_forever()


if __name__ == "__main__":
    main()
