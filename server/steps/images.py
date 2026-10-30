#!/usr/bin/env python3
"""Builds the locally built images, only when their inputs changed or an image is missing.

The inputs are the files of each build context. Their hash is kept in DATA_DIR/.state/images.sha256.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, Stack, env_file_arg, read_env, status  # noqa: E402

BUILD_CONTEXTS = ["dashboard", "apt-cache", "url-proxy", "backup", "immich/db"]
BUILD_SERVICES = ["dashboard", "apt-cache", "url-proxy", "backup", "immich-db"]


def fingerprint():
    digest = hashlib.sha256()
    for context in BUILD_CONTEXTS:
        for path in sorted((ROOT / context).rglob("*")):
            if path.is_file():
                digest.update(str(path.relative_to(ROOT)).encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


def images_present(stack):
    """True when every locally built service has an image. Checked by image name, not by container."""
    r = stack("config", "--format", "json")
    try:
        config = json.loads(r.stdout)
    except ValueError:
        return False
    for service in BUILD_SERVICES:
        name = config["services"].get(service, {}).get("image") or f"{config['name']}-{service}"
        if subprocess.run(["docker", "image", "inspect", name], capture_output=True).returncode != 0:
            return False
    return True


def main():
    env_path = env_file_arg()
    env = read_env(env_path)
    state_file = Path(env["DATA_DIR"]) / ".state" / "images.sha256"
    current = fingerprint()
    previous = state_file.read_text().strip() if state_file.exists() else ""
    stack = Stack(env_path)
    if current == previous and images_present(stack):
        status("skipped", "images are up to date")
        return 0
    r = stack("build", *BUILD_SERVICES)
    if r.returncode != 0:
        status("failed", "docker compose build: " + r.stderr[-400:].replace("\n", " "))
        return 1
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(current + "\n")
    status("changed", "built " + ", ".join(BUILD_SERVICES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
