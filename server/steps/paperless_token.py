#!/usr/bin/env python3
"""Paperless metrics user and its API token. Skipped when the token from .env already works.

The token is PAPERLESS_METRICS_TOKEN from .env. If .env has none, a token is generated and returned as RESULT.
"""
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, Stack, env_file_arg, read_env, result, status  # noqa: E402


def token_works(stack, token):
    r = stack.exec("paperless", "sh", "-c",
                   'curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Token $T" http://localhost:8000/api/statistics/',
                   env={"T": token})
    return r.stdout.strip() == "200"


def main():
    env_path = env_file_arg()
    env = read_env(env_path)
    generated = {}
    if not env.get("PAPERLESS_METRICS_TOKEN"):
        generated["PAPERLESS_METRICS_TOKEN"] = secrets.token_hex(20)
        env["PAPERLESS_METRICS_TOKEN"] = generated["PAPERLESS_METRICS_TOKEN"]
    if len(env["PAPERLESS_METRICS_TOKEN"]) > 40:
        status("failed", "PAPERLESS_METRICS_TOKEN is longer than 40 characters; Paperless cannot store it. "
                         "Remove it from .env so a new one is generated.")
        return 1

    stack = Stack(env_path)
    # Order: the database and its exporter first (the database health check also asks the exporter for
    # /metrics), then the database role setup, then Paperless. Each step waits for the one before.
    r = stack("up", "-d", "paperless-db", "paperless-db-exporter")
    if r.returncode != 0 or not stack.wait_healthy("paperless-db", 900):
        status("failed", "Paperless database did not become healthy: " + r.stderr[-300:].replace("\n", " "))
        return 1
    stack("up", "-d", "paperless-db-setup")
    r = stack("up", "-d", "paperless")
    if r.returncode != 0 or not stack.wait_healthy("paperless", 1200):
        status("failed", "Paperless did not become healthy: " + r.stderr[-300:].replace("\n", " "))
        return 1

    if token_works(stack, env["PAPERLESS_METRICS_TOKEN"]):
        status("skipped", "metrics token works")
        if generated:
            result(generated)
        return 0

    script = (ROOT / "monitoring" / "paperless" / "create-metrics-user.py").read_text()
    r = stack.exec("paperless", "python3", "/usr/src/paperless/src/manage.py", "shell", input_text=script,
                   env={"PAPERLESS_METRICS_TOKEN": env["PAPERLESS_METRICS_TOKEN"]})
    if "TOKEN=" not in r.stdout or not token_works(stack, env["PAPERLESS_METRICS_TOKEN"]):
        status("failed", "metrics user or token failed: " + r.stderr[-300:].replace("\n", " "))
        return 1
    if generated:
        result(generated)
    status("changed", "metrics user and token created")
    return 0


if __name__ == "__main__":
    sys.exit(main())
