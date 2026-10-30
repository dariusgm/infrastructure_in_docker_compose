"""Shared helpers for the step scripts in server/steps/.

Every step script is run on the server (deploy user) as: python3 server/steps/<name>.py <env-file>

Output protocol, read by deploy.py:
  STATUS <done|skipped|changed|failed> <text>      one line per step
  RESULT <json>                                     optional: values the step generated, to store in .env
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USING = ["urn:ietf:params:jmap:core", "urn:stalwart:jmap"]


def read_env(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def env_file_arg():
    if len(sys.argv) < 2:
        sys.exit("usage: <step>.py <env-file>")
    return Path(sys.argv[1])


def status(state, text=""):
    print(f"STATUS {state} {text}".rstrip(), flush=True)


def result(values):
    print("RESULT " + json.dumps(values), flush=True)


def wait_until(fn, timeout, interval=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


class Stack:
    """docker compose for this repository. Reads the project name from the env file (COMPOSE_PROJECT_NAME)."""

    def __init__(self, env_file, extra_files=()):
        self.cmd = ["docker", "compose", "--env-file", str(env_file), "-f", str(ROOT / "compose.yaml")]
        for extra in extra_files:
            self.cmd += ["-f", str(extra)]

    def __call__(self, *args, input_text=None):
        return subprocess.run([*self.cmd, *args], cwd=ROOT, input=input_text, capture_output=True, text=True)

    def exec(self, service, *cmd, input_text=None, env=None):
        flags = []
        for key, value in (env or {}).items():
            flags += ["-e", f"{key}={value}"]
        return self("exec", "-T", *flags, service, *cmd, input_text=input_text)

    def service_items(self):
        r = self("ps", "-a", "--format", "json")
        text = r.stdout.strip()
        if not text:
            return []
        return json.loads(text) if text.startswith("[") else [json.loads(ln) for ln in text.splitlines() if ln.strip()]

    def is_healthy(self, service):
        return any(it.get("Service") == service and it.get("State") == "running"
                   and it.get("Health") in ("", "healthy") for it in self.service_items())

    def wait_healthy(self, service, timeout):
        return wait_until(lambda: self.is_healthy(service), timeout)


def jmap_admin(stack, env, body):
    """A JMAP call to Stalwart as the admin, made inside the container, so no port has to be reachable."""
    user, pw = env.get("MAIL_ADMIN_USER", ""), env.get("MAIL_ADMIN_PASSWORD", "")
    cmd = ["curl", "-sk", "-u", f"{user}:{pw}", "-H", "Content-Type: application/json", "-X", "POST",
           "https://127.0.0.1/jmap/", "-d", "@-"]
    return stack.exec("stalwart", *cmd, input_text=json.dumps(body))
