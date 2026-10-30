#!/usr/bin/env python3
"""Checks that the host has what the stack needs: Docker (rootless), openssl, git, the firewall and the
data directory. Run as the deploy user. It changes nothing.

STATUS done      everything is in place
STATUS failed    something is missing: deploy.py runs server/bootstrap.sh (root) and checks again
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env_file_arg, read_env, status  # noqa: E402


def present(tool):
    return shutil.which(tool) is not None


def main():
    env = read_env(env_file_arg())
    problems = []
    for tool in ("openssl", "git", "docker", "ufw"):
        if not present(tool):
            problems.append(f"{tool} not installed")
    uid = os.getuid()
    xdg = f"/run/user/{uid}"
    # Rootless Docker on the server, the default socket on a development machine.
    docker_ok = any(subprocess.run(["docker", "info"], capture_output=True, env=e).returncode == 0
                    for e in ({**os.environ, "DOCKER_HOST": f"unix://{xdg}/docker.sock"}, dict(os.environ)))
    if not docker_ok:
        problems.append("rootless Docker is not running")
    data_dir = Path(env.get("DATA_DIR", ""))
    if not data_dir.is_dir() or not os.access(data_dir, os.W_OK):
        problems.append(f"data directory {data_dir} missing or not writable")
    # The NAS share the Paperless consumer reads from (server/consume-mount.sh, run as root).
    nas_configured = env.get("SMB_HOST", "") not in ("", "unused")
    if nas_configured and subprocess.run(["mountpoint", "-q", "/mnt/paperless-consume"]).returncode != 0:
        problems.append("/mnt/paperless-consume not mounted (server/consume-mount.sh, as root)")
    if problems:
        status("failed", "; ".join(problems))
        return 1
    status("done", "docker, openssl, git, ufw and the data directory are in place")
    return 0


if __name__ == "__main__":
    sys.exit(main())
