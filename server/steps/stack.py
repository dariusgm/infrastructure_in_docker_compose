#!/usr/bin/env python3
"""Launches the full stack in daemon mode and waits until every service is healthy.

A container is recreated by compose only when its configuration changed. This step skips the
`up` when every running container already has the configuration hash that compose expects.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Stack, env_file_arg, status, wait_until  # noqa: E402

ONE_SHOT = {"monitoring-init", "stalwart-init", "paperless-db-setup", "immich-db-setup"}


def expected_hashes(stack):
    """service -> configuration hash that compose gives the container (one "service hash" line each)."""
    r = stack("config", "--hash=*")
    found = {}
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            found[parts[0]] = parts[1]
    return found


def running_hashes(stack):
    ids = stack("ps", "-a", "-q").stdout.split()
    if not ids:
        return {}
    fmt = ('{{index .Config.Labels "com.docker.compose.service"}} '
           '{{index .Config.Labels "com.docker.compose.config-hash"}} {{.State.Status}}')
    out = subprocess.run(["docker", "inspect", "--format", fmt, *ids], capture_output=True, text=True).stdout
    found = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3:
            found[parts[0]] = (parts[1], parts[2])
    return found


def up_to_date(stack):
    expected = expected_hashes(stack)
    if not expected:
        return False
    running = running_hashes(stack)
    for service, config_hash in expected.items():
        if service not in running:
            return False
        have, state = running[service]
        if have != config_hash:
            return False
        if service not in ONE_SHOT and state != "running":
            return False
    return True


def settled(stack):
    broken, pending = [], []
    for it in stack.service_items():
        svc, state, health = it.get("Service", ""), it.get("State", ""), it.get("Health", "")
        if svc in ONE_SHOT:
            if state != "exited" or it.get("ExitCode") != 0:
                pending.append(svc)
        elif state != "running" or health == "unhealthy":
            broken.append(f"{svc}:{state}/{health}")
        elif health not in ("", "healthy"):
            pending.append(svc)
    return broken, pending


def main():
    env_path = env_file_arg()
    stack = Stack(env_path)
    changed = False
    if not up_to_date(stack):
        r = stack("up", "-d", "--remove-orphans")
        if r.returncode != 0:
            status("failed", "docker compose up: " + r.stderr[-400:].replace("\n", " "))
            return 1
        changed = True

    ok = wait_until(lambda: not settled(stack)[0] and not settled(stack)[1], 1800, interval=10)
    broken, pending = settled(stack)
    if broken:
        status("failed", "not healthy: " + ", ".join(broken))
        return 1
    if not ok:
        status("failed", "still starting: " + ", ".join(pending))
        return 1
    status("changed" if changed else "skipped", "stack launched" if changed else "stack already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
