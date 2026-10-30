#!/usr/bin/env python3
"""Stalwart mail server: bootstrap, admin password, certificate and metrics. Each part is skipped when present.

- Fresh server (no admin yet): bootstrap with a temporary recovery administrator, then the admin password.
- Admin password: MAIL_ADMIN_PASSWORD from .env. If .env has none, it is generated and returned as RESULT.
- Certificate object from /etc/stalwart/tls (written by the tls step).
- Prometheus metrics with basic auth, password STALWART_METRICS_PASSWORD (generated if missing, as RESULT).
"""
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import USING, Stack, env_file_arg, jmap_admin, read_env, result, status, wait_until  # noqa: E402

MAIL_HOST = "mail.home.lan"


def https_answers(stack):
    r = stack.exec("stalwart", "sh", "-c", "curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1/healthz/live")
    return r.stdout.strip() == "200"


def restart(stack):
    stack("up", "-d", "--force-recreate", "stalwart")
    return wait_until(lambda: https_answers(stack), 300)


def configured(stack, env):
    if not env.get("MAIL_ADMIN_PASSWORD"):
        return False
    r = jmap_admin(stack, env, {"methodCalls": [["x:Domain/get", {"ids": None}, "c1"]], "using": USING})
    try:
        names = [d["name"] for d in json.loads(r.stdout)["methodResponses"][0][1]["list"]]
    except (ValueError, KeyError, IndexError):
        return False
    return "home.lan" in names


def bootstrap(stack, env):
    """Returns the admin password the server generated. Only valid on a server that was never configured."""
    recovery = secrets.token_hex(16)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
        handle.write("services:\n  stalwart:\n    environment:\n"
                     f"      STALWART_RECOVERY_ADMIN: admin:{recovery}\n")
        override = handle.name
    try:
        temporary = Stack(env_file_arg(), extra_files=[override])
        temporary("up", "-d", "stalwart")
        listener_up = wait_until(lambda: temporary.exec(
            "stalwart", "sh", "-c", "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/healthz/live"
        ).stdout.strip() == "200", 300)
        if not listener_up:
            raise RuntimeError("the bootstrap listener on port 8080 did not start")
        body = {"methodCalls": [["x:Bootstrap/set", {"update": {"singleton": {
            "defaultHostname": MAIL_HOST, "defaultDomain": "home.lan",
            "requestTlsCertificate": False, "generateDkimKeys": False}}}, "c1"]], "using": USING}
        r = temporary.exec("stalwart", "sh", "-c",
                           'curl -s -u "$STALWART_RECOVERY_ADMIN" -H "Content-Type: application/json" '
                           '-X POST http://127.0.0.1:8080/jmap/ -d @-', input_text=json.dumps(body))
    finally:
        os.unlink(override)
    try:
        return json.loads(r.stdout)["methodResponses"][0][1]["updated"]["singleton"]["secret"]
    except (ValueError, KeyError, IndexError):
        raise RuntimeError(f"bootstrap failed: {(r.stdout + r.stderr)[:300]}")


def main():
    env_path = env_file_arg()
    env = read_env(env_path)
    generated = {}
    if not env.get("MAIL_ADMIN_PASSWORD"):
        generated["MAIL_ADMIN_PASSWORD"] = secrets.token_hex(24)
        env["MAIL_ADMIN_PASSWORD"] = generated["MAIL_ADMIN_PASSWORD"]
    if not env.get("STALWART_METRICS_PASSWORD"):
        generated["STALWART_METRICS_PASSWORD"] = secrets.token_hex(24)
        env["STALWART_METRICS_PASSWORD"] = generated["STALWART_METRICS_PASSWORD"]
    env.setdefault("MAIL_ADMIN_USER", "admin@home.lan")

    stack = Stack(env_path)
    changed = []
    try:
        stack("up", "-d", "stalwart")
        if not wait_until(lambda: https_answers(stack) or stack.is_healthy("stalwart"), 300):
            raise RuntimeError("Stalwart did not start")

        if not configured(stack, env):
            changed.append("bootstrap")
            server_secret = bootstrap(stack, env)
            if not restart(stack):
                raise RuntimeError("Stalwart did not answer on HTTPS after the bootstrap restart")
            admin_login = {"MAIL_ADMIN_USER": env["MAIL_ADMIN_USER"], "MAIL_ADMIN_PASSWORD": server_secret}
            accounts = jmap_admin(stack, admin_login, {"methodCalls": [
                ["x:Account/get", {"ids": None, "properties": ["id", "name"]}, "c1"]], "using": USING})
            admin_id = next(a["id"] for a in json.loads(accounts.stdout)["methodResponses"][0][1]["list"]
                            if a["name"] == "admin")
            update = {"methodCalls": [["x:Account/set", {"update": {admin_id: {"credentials": {"0": {
                "@type": "Password", "secret": env["MAIL_ADMIN_PASSWORD"]}}}}}, "c1"]], "using": USING}
            if "updated" not in jmap_admin(stack, admin_login, update).stdout:
                raise RuntimeError("could not set the Stalwart admin password")
            if not configured(stack, env):
                raise RuntimeError("Stalwart admin login with the .env password does not work")

        cert_list = jmap_admin(stack, env, {"methodCalls": [["x:Certificate/get", {"ids": None}, "c1"]],
                                            "using": USING}).stdout
        if '"list":[]' in cert_list.replace(" ", ""):
            create = {"methodCalls": [["x:Certificate/set", {"create": {"c1": {
                "certificate": {"@type": "File", "filePath": "/etc/stalwart/tls/fullchain.pem"},
                "privateKey": {"@type": "File", "filePath": "/etc/stalwart/tls/privkey.pem"}}}}, "c1"]],
                "using": USING}
            if "created" not in jmap_admin(stack, env, create).stdout:
                raise RuntimeError("could not create the Stalwart certificate object")
            changed.append("certificate")

        metrics = jmap_admin(stack, env, {"methodCalls": [["x:Metrics/get", {"ids": ["singleton"]}, "c1"]],
                                          "using": USING}).stdout
        if '"authUsername":"prometheus"' not in metrics.replace(" ", ""):
            setm = {"methodCalls": [["x:Metrics/set", {"update": {"singleton": {"prometheus": {
                "@type": "Enabled", "authUsername": "prometheus",
                "authSecret": {"@type": "Value", "secret": env["STALWART_METRICS_PASSWORD"]}}}}}, "c1"]],
                "using": USING}
            if "updated" not in jmap_admin(stack, env, setm).stdout:
                raise RuntimeError("could not enable the Stalwart metrics")
            changed.append("metrics")

        if changed:
            if not restart(stack):
                raise RuntimeError("Stalwart did not answer on HTTPS after the restart")
    except RuntimeError as exc:
        status("failed", str(exc))
        return 1

    if generated:
        result(generated)
    if changed:
        status("changed", "stalwart: " + ", ".join(changed))
    else:
        status("skipped", "stalwart already configured")
    return 0


if __name__ == "__main__":
    sys.exit(main())
