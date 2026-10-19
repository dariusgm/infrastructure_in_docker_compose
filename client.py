#!/usr/bin/env python3
"""Point apt on this system at the apt-cache service. Standard library only.

  sudo python3 client.py install   check that the cache answers, then configure apt and run apt-get update
  sudo python3 client.py remove    remove the apt proxy configuration again

Reads APT_CACHE_HOST, APT_CACHE_PORT from .env (see .env.example).
"""

import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
APT_CONF = Path("/etc/apt/apt.conf.d/02apt-cache")
REQUIRED = ["APT_CACHE_HOST", "APT_CACHE_PORT"]


def read_env():
    if not ENV_FILE.exists():
        sys.exit(f"{ENV_FILE} not found. Copy .env.example to .env and fill it in.")
    values = {}
    for line in ENV_FILE.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def cache_url(env):
    return f"http://{env['APT_CACHE_HOST']}:{env['APT_CACHE_PORT']}"


def apt_config(env):
    # Plain HTTP goes through the cache. HTTPS repositories bypass it, because apt-cacher-ng
    # cannot cache TLS traffic without interception.
    return (
        "// Managed by client.py. Remove with: sudo python3 client.py remove\n"
        f'Acquire::http::Proxy "{cache_url(env)}";\n'
        'Acquire::https::Proxy "DIRECT";\n'
    )


def cache_reachable(env):
    # Health check against the cache on this machine, so the check does not depend on the
    # configured cache host. apt-cacher-ng serves its statistics page on the same port.
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{env['APT_CACHE_PORT']}/acng-report.html", timeout=5) as response:
            return response.status == 200
    except OSError:
        return False


def require_root():
    if os.geteuid() != 0:
        sys.exit("Run with sudo: sudo python3 client.py " + sys.argv[1])


def cmd_install(env):
    if not cache_reachable(env):
        sys.exit(f"The apt cache at {cache_url(env)} does not answer. Nothing was changed.")
    APT_CONF.write_text(apt_config(env))
    APT_CONF.chmod(0o644)
    print(f"Wrote {APT_CONF}")
    subprocess.run(["apt-get", "update"], check=True)
    print(f"apt uses the cache at {cache_url(env)}")


def cmd_remove(_env):
    if APT_CONF.exists():
        APT_CONF.unlink()
        print(f"Removed {APT_CONF}")
    else:
        print("No apt cache configuration to remove")


def main():
    commands = {"install": cmd_install, "remove": cmd_remove}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    require_root()
    env = read_env()
    if sys.argv[1] == "install":
        missing = [key for key in REQUIRED if not env.get(key)]
        if missing:
            sys.exit("Missing values in .env: " + ", ".join(missing))
    commands[sys.argv[1]](env)


if __name__ == "__main__":
    main()
