#!/usr/bin/env python3
"""Smoke test: boots the whole stack with throwaway data, checks it, and removes it again.

What it does:
  1. Preflight: Docker, free memory and disk, no other stack of this project running.
  2. Writes a temporary .env (secrets generated, HOST_IP 127.0.0.2, DATA_DIR inside smoke/.run) and a
     local CA with certificates for Vaultwarden and Stalwart.
  3. Starts every service and waits for the health checks (docker compose --wait).
  4. Does the one-time setup that the READMEs describe: Stalwart bootstrap, certificate and metrics,
     the Paperless metrics user.
  5. Checks each endpoint, that Prometheus scrapes every target, that the exporters deliver data, and runs
     the mail end-to-end test.
  6. Removes the containers and the temporary data, also when a check fails.

Run from the repository root: python3 smoke/smoke.py   (exit 0 means every check passed)
Set SMOKE_KEEP=1 to keep the stack and data running after the test, for debugging.
"""
import json
import os
import secrets
import shutil
import ssl
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "smoke" / ".run"
PROJECT = "smoke"
HOST = "127.0.0.2"          # loopback, not the LAN address: no port clashes with a running stack
MAIL_HOST = "mail.home.lan"
ONE_SHOT = {"monitoring-init", "stalwart-init", "paperless-db-setup", "immich-db-setup"}
KEEP = os.environ.get("SMOKE_KEEP") == "1"

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail and not ok else ""), flush=True)
    return ok


def run(cmd, **kw):
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    return subprocess.run(cmd, cwd=ROOT, **kw)


def compose(*args, **kw):
    cmd = ["docker", "compose", "-p", PROJECT, "--env-file", str(RUN / "smoke.env"),
           "-f", "compose.yaml", "-f", str(RUN / "override.yaml"), *args]
    return run(cmd, **kw)


def compose_exec(service, *cmd, input_text=None):
    args = ["exec", "-T", service, *cmd]
    return compose(*args, input=input_text)


def curl_code(url, *extra):
    r = run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "10", *extra, url])
    return r.stdout.strip() or "000"


def ca_args():
    return ["--cacert", str(RUN / "data" / "vaultwarden-tls" / "ca.pem"),
            "--resolve", f"{MAIL_HOST}:443:{HOST}"]


def env_value(name):
    for line in (RUN / "smoke.env").read_text().splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1]
    return ""


def set_env(name, value):
    path = RUN / "smoke.env"
    lines = path.read_text().splitlines()
    out, found = [], False
    for line in lines:
        if line.startswith(name + "="):
            out.append(f"{name}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{name}={value}")
    path.write_text("\n".join(out) + "\n")


def wait_until(fn, timeout, interval=5):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(interval)
    return last


# ---------- 1. preflight ----------

def preflight():
    print("1. preflight")
    mem_kb = 0
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            mem_kb = int(line.split()[1])
    check("memory available >= 4 GiB", mem_kb >= 4 * 1024 * 1024, f"{mem_kb // 1024} MiB")
    disk = shutil.disk_usage(ROOT).free
    check("disk free >= 15 GiB", disk >= 15 * 1024 ** 3, f"{disk // 1024 ** 3} GiB")
    check("docker reachable", run(["docker", "info"]).returncode == 0)
    running = run(["docker", "ps", "--format", "{{.Names}}"]).stdout.split()
    others = [n for n in running if n.startswith("infrastructure-")]
    check("no full stack running (only one stack at a time)", not others, ", ".join(others[:3]))
    return all(r[1] for r in results)


# ---------- 2. temporary configuration ----------

FIXED = {
    "HOST_IP": HOST,
    "PAPERLESS_ADMIN_USER": "admin",
    "MAIL_ADMIN_USER": "admin@home.lan",
    "VAULTWARDEN_URL": f"https://{HOST}:8084",
}


def write_env():
    print("2. temporary configuration")
    data = RUN / "data"
    lines = []
    for raw in (ROOT / ".env.example").read_text().splitlines():
        if raw.startswith("#") or "=" not in raw:
            lines.append(raw)
            continue
        key, value = raw.split("=", 1)
        if key in FIXED:
            value = FIXED[key]
        elif key == "DATA_DIR":
            value = str(data)
        elif value.startswith("<"):
            value = "unused"                      # SMB values are used by host scripts only
        elif value == "" and any(s in key for s in ("PASSWORD", "SECRET", "TOKEN", "KEY")):
            value = secrets.token_hex(24)
        lines.append(f"{key}={value}")
    (RUN / "smoke.env").write_text("\n".join(lines) + "\n")
    # Recovery administrator for the Stalwart bootstrap only, see override.yaml.
    (RUN / "override.yaml").write_text(
        "services:\n  stalwart:\n    environment:\n"
        "      STALWART_RECOVERY_ADMIN: admin:${SMOKE_RECOVERY_PASSWORD}\n")
    set_env("SMOKE_RECOVERY_PASSWORD", secrets.token_hex(16))
    check("temporary .env written", True)


def write_certs():
    data = RUN / "data"
    vw = data / "vaultwarden-tls"
    mail = data / "mail" / "tls"
    for d in (vw, mail, data / "mail" / "etc", data / "mail" / "data", data / "monitoring" / "secrets"):
        d.mkdir(parents=True, exist_ok=True)
    openssl = lambda *a: run(["openssl", *a], check=True)
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "30", "-keyout", str(vw / "ca-key.pem"),
            "-out", str(vw / "ca.pem"), "-subj", "/CN=Smoke Local CA")
    ext = RUN / "ext.cnf"
    ext.write_text(f"subjectAltName=DNS:localhost,DNS:{MAIL_HOST},IP:{HOST}\n"
                   "extendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n")
    for name, cn in (("vaultwarden", "localhost"), ("mail", MAIL_HOST)):
        target = vw if name == "vaultwarden" else mail
        openssl("req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", str(target / "key.pem" if name == "vaultwarden" else target / "privkey.pem"),
                "-subj", f"/CN={cn}", "-out", str(RUN / f"{name}.csr"))
        cert = target / ("cert.pem" if name == "vaultwarden" else "cert.pem")
        openssl("x509", "-req", "-in", str(RUN / f"{name}.csr"), "-CA", str(vw / "ca.pem"),
                "-CAkey", str(vw / "ca-key.pem"), "-CAcreateserial", "-days", "30", "-sha256",
                "-extfile", str(ext), "-out", str(cert))
    shutil.copy(vw / "ca.pem", mail / "ca.pem")
    (mail / "fullchain.pem").write_text((mail / "cert.pem").read_text() + (vw / "ca.pem").read_text())
    check("local CA and certificates written", True)


# ---------- 3. start ----------

def service_states():
    r = compose("ps", "-a", "--format", "json")
    text = r.stdout.strip()
    if not text:
        return None
    items = json.loads(text) if text.startswith("[") else [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    return items


def problems(items):
    """Services that are not (yet) in their final state. A crashed service is reported at once."""
    pending, broken = [], []
    for it in items:
        svc, state, health = it.get("Service", ""), it.get("State", ""), it.get("Health", "")
        if svc in ONE_SHOT:
            if state != "exited" or it.get("ExitCode") != 0:
                (broken if state == "exited" else pending).append(f"{svc}:{state}")
        elif state in ("exited", "dead", "restarting") or health == "unhealthy":
            broken.append(f"{svc}:{state}/{health}")
        elif state != "running" or health not in ("", "healthy"):
            pending.append(f"{svc}:{health or state}")
    return pending, broken


def start():
    print("3. start all services, then wait until every health check passes")
    r = compose("up", "-d", "--build")
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-3000:])
        return check("docker compose up", False, f"exit {r.returncode}")
    check("docker compose up", True)
    deadline = time.time() + 1500
    last = []
    while time.time() < deadline:
        items = service_states() or []
        pending, broken = problems(items)
        if broken:
            check("all services healthy", False, "broken: " + ", ".join(broken))
            return False
        if items and not pending:
            return check(f"all {len(items)} services healthy", True)
        last = pending
        time.sleep(10)
    return check("all services healthy in time", False, "still starting: " + ", ".join(last))


# ---------- 4. one-time setup, as in the READMEs ----------

def stalwart_bootstrap():
    print("4. one-time setup")
    # The bootstrap object is only accepted in bootstrap mode, over the recovery listener on 8080.
    body = {"methodCalls": [["x:Bootstrap/set", {"update": {"singleton": {
        "defaultHostname": MAIL_HOST, "defaultDomain": "home.lan",
        "requestTlsCertificate": False, "generateDkimKeys": False}}}, "c1"]],
        "using": ["urn:ietf:params:jmap:core", "urn:stalwart:jmap"]}
    r = compose_exec("stalwart", "sh", "-c",
                     'curl -s -u "$STALWART_RECOVERY_ADMIN" -H "Content-Type: application/json" '
                     '-X POST http://127.0.0.1:8080/jmap/ -d @-', input_text=json.dumps(body))
    try:
        created = json.loads(r.stdout)["methodResponses"][0][1]["updated"]["singleton"]
        set_env("MAIL_ADMIN_PASSWORD", created["secret"])
        check("stalwart bootstrap", True)
        return True
    except (ValueError, KeyError, IndexError):
        check("stalwart bootstrap", False, r.stdout[:300])
        return False


def jmap_admin(body):
    user, pw = env_value("MAIL_ADMIN_USER"), env_value("MAIL_ADMIN_PASSWORD")
    cmd = ["curl", "-sk", "-u", f"{user}:{pw}", "-H", "Content-Type: application/json", "-X", "POST",
           "https://127.0.0.1/jmap/", "-d", "@-"]
    return compose_exec("stalwart", *cmd, input_text=json.dumps(body))


def stalwart_restart():
    """Recreates Stalwart and waits until its HTTPS listener answers (needed after bootstrap and after changes)."""
    compose("up", "-d", "--force-recreate", "stalwart")
    code = wait_until(lambda: compose_exec("stalwart", "sh", "-c",
                      "curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1/healthz/live").stdout.strip() == "200",
                      timeout=240, interval=5)
    return bool(code)


def stalwart_configure():
    if not stalwart_restart():
        check("stalwart HTTPS listener after restart", False)
        return
    using = ["urn:ietf:params:jmap:core", "urn:stalwart:jmap"]
    cert = {"methodCalls": [["x:Certificate/set", {"create": {"c1": {
        "certificate": {"@type": "File", "filePath": "/etc/stalwart/tls/fullchain.pem"},
        "privateKey": {"@type": "File", "filePath": "/etc/stalwart/tls/privkey.pem"}}}}, "c1"]], "using": using}
    metrics = {"methodCalls": [["x:Metrics/set", {"update": {"singleton": {"prometheus": {
        "@type": "Enabled", "authUsername": "prometheus",
        "authSecret": {"@type": "Value", "secret": env_value("STALWART_METRICS_PASSWORD")}}}}}, "c1"]],
        "using": using}
    ok_cert = "created" in jmap_admin(cert).stdout
    ok_metrics = "updated" in jmap_admin(metrics).stdout
    check("stalwart certificate object", ok_cert)
    check("stalwart metrics enabled", ok_metrics)
    # Certificate and metrics settings take effect after a restart (see mail/README.md).
    check("stalwart HTTPS listener after restart", stalwart_restart())


def paperless_metrics_user():
    script = (ROOT / "monitoring" / "paperless" / "create-metrics-user.py").read_text()
    r = compose_exec("paperless", "python3", "/usr/src/paperless/src/manage.py", "shell", input_text=script)
    token = next((ln.split("=", 1)[1] for ln in r.stdout.splitlines() if ln.startswith("TOKEN=")), "")
    check("paperless metrics user created", bool(token), r.stderr[-300:])
    if token:
        set_env("PAPERLESS_METRICS_TOKEN", token)
        compose("up", "-d", "--force-recreate", "paperless-app-exporter")


# ---------- 5. checks ----------

def check_services():
    print("5. services")
    r = compose("ps", "-a", "--format", "json")
    try:
        items = json.loads(r.stdout) if r.stdout.strip().startswith("[") else \
            [json.loads(line) for line in r.stdout.splitlines() if line.strip()]
    except ValueError:
        return check("compose ps readable", False, r.stdout[:200])
    bad = []
    for it in items:
        svc = it.get("Service", "")
        state, health = it.get("State", ""), it.get("Health", "")
        if svc in ONE_SHOT:
            good = state == "exited" and it.get("ExitCode") == 0
        else:
            good = state == "running" and health in ("", "healthy")
        if not good:
            bad.append(f"{svc}:{state}/{health}")
    check(f"all {len(items)} services running and healthy", not bad, ", ".join(bad))
    return not bad


def check_endpoints():
    print("6. endpoints")
    ca = str(RUN / "data" / "vaultwarden-tls" / "ca.pem")
    checks = [
        ("dashboard", f"http://{HOST}:8080/", {"200"}),
        ("grafana health", f"http://{HOST}:3000/api/health", {"200"}),
        ("paperless", f"http://{HOST}:8083/", {"200", "302"}),
        ("immich ping", f"http://{HOST}:2283/api/server/ping", {"200"}),
        ("pihole admin", f"http://{HOST}:8082/admin/", {"200", "302"}),
        ("url-proxy answers", f"http://{HOST}:8081/", {"404"}),
        ("apt-cache answers", f"http://{HOST}:3142/", {"200", "302", "301", "406"}),
    ]
    for name, url, ok_codes in checks:
        code = curl_code(url)
        check(f"{name} ({url})", code in ok_codes, f"HTTP {code}")
    code = curl_code(f"https://{HOST}:8084/alive", "--cacert", ca)
    check("vaultwarden over HTTPS", code == "200", f"HTTP {code}")
    code = curl_code(f"https://{MAIL_HOST}/healthz/live", *ca_args())
    check("stalwart HTTPS (mail.home.lan)", code == "200", f"HTTP {code}")
    tls = run(["openssl", "s_client", "-connect", f"{HOST}:993", "-servername", MAIL_HOST,
               "-CAfile", ca, "-verify_hostname", MAIL_HOST], input="")
    check("stalwart IMAPS handshake verifies", "Verify return code: 0 (ok)" in tls.stdout)


def prom_query(expr):
    import urllib.parse
    url = "http://localhost:9090/api/v1/query?query=" + urllib.parse.quote(expr)
    r = compose_exec("prometheus", "wget", "-qO-", url)
    try:
        return json.loads(r.stdout)["data"]["result"]
    except (ValueError, KeyError):
        return None


def check_metrics():
    print("7. metrics and exporters")

    def all_targets_up():
        r = compose_exec("prometheus", "wget", "-qO-", "http://localhost:9090/api/v1/targets?state=active")
        try:
            targets = json.loads(r.stdout)["data"]["activeTargets"]
        except (ValueError, KeyError):
            return None
        down = [f"{t['labels'].get('job')}:{t['labels'].get('instance')}" for t in targets if t["health"] != "up"]
        return (len(targets), down) if not down else None

    targets = wait_until(all_targets_up, timeout=420, interval=15)
    check("every Prometheus target is up", targets is not None,
          "" if targets is None else "still down or unreachable")

    def count(expr, value=None):
        res = prom_query(expr) or []
        return len([r for r in res if value is None or float(r["value"][1]) == value])

    checks = [
        ("postgres exporters report the databases", "pg_up", 2),
        ("valkey exporters report the brokers", "redis_up", 2),
        ("nginx exporter reports url-proxy", "nginx_up", 1),
    ]
    for name, expr, want in checks:
        check(name, count(expr, 1) >= want, f"{count(expr, 1)} of {want} with value 1")
    def container_count():
        res = prom_query('count(container_memory_working_set_bytes{name!=""})') or []
        return int(float(res[0]["value"][1])) if res else 0

    n = wait_until(lambda: container_count() >= 20 and container_count(), timeout=180, interval=10) or container_count()
    check("cAdvisor reports every running container", n >= 20, f"{n} containers")
    check("node-exporter reports host memory pressure",
          count("node_pressure_memory_waiting_seconds_total") >= 1)
    check("Immich metrics arrive", count('up{job="immich"}', 1) >= 1)
    check("Paperless statistics arrive", count('up{job="paperless"}', 1) >= 1)
    check("Stalwart metrics arrive", count('stalwart_users') >= 1)


def check_grafana():
    print("8. grafana")
    user, pw = "admin", env_value("GRAFANA_ADMIN_PASSWORD")
    r = run(["curl", "-s", "--max-time", "20", "-u", f"{user}:{pw}",
             f"http://{HOST}:3000/api/datasources/uid/prometheus/health"])
    try:
        status = json.loads(r.stdout).get("status")
    except ValueError:
        status = None
    check("grafana data source Prometheus is working", status == "OK", r.stdout[:200])


def check_mail():
    print("9. mail end-to-end")
    r = run(["bash", "mail/e2e-test.sh"], env={**os.environ, "ENV_FILE": str(RUN / "smoke.env"),
                                                  "E2E_NETWORK": f"{PROJECT}_monitoring"})
    check("mail send and read back", r.returncode == 0 and "PASS" in r.stdout,
          (r.stdout + r.stderr)[-400:])


# ---------- teardown ----------

def dump_failed_logs():
    print("last log lines of all services (for the failed checks above):")
    logs = compose("logs", "--tail", "30", "--no-color")
    print(logs.stdout[-6000:])


def teardown():
    print("10. teardown")
    if KEEP:
        print("   SMOKE_KEEP=1: stack and data left running in", RUN)
        return
    compose("down", "--remove-orphans", "--timeout", "60")
    # Data is owned by container users, so remove it with a container, as the stack does.
    run(["docker", "run", "--rm", "-v", f"{RUN}:/w", "docker.io/library/busybox:1.37.0",
         "sh", "-c", "rm -rf /w/data"])
    shutil.rmtree(RUN, ignore_errors=True)
    print("   stack removed, temporary data deleted")


def main():
    RUN.mkdir(parents=True, exist_ok=True)
    try:
        if not preflight():
            return 2
        write_env()
        write_certs()
        if not start():
            dump_failed_logs()
            return 1
        if stalwart_bootstrap():
            stalwart_configure()
        paperless_metrics_user()
        check_services()
        check_endpoints()
        check_metrics()
        check_grafana()
        check_mail()
    except Exception as exc:  # report, then still tear down
        check("smoke test ran to the end", False, repr(exc))
    finally:
        failed = [r for r in results if not r[1]]
        if failed:
            dump_failed_logs()
        teardown()
    passed = len(results) - len(failed)
    print(f"\nRESULT: {passed}/{len(results)} checks passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
