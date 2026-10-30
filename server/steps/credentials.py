#!/usr/bin/env python3
"""Generates the secrets that compose needs before any service runs and that no application creates
itself. A value already in .env is kept. Generated values are returned as RESULT and stored in .env.

Values an application creates on its first start (the mail admin password, the Paperless token) are
handled by their own steps; they are generated here too, so compose can parse the file from the start.
"""
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env_file_arg, read_env, result, status  # noqa: E402

GENERATED = ["MAIL_ADMIN_PASSWORD", "STALWART_METRICS_PASSWORD", "PAPERLESS_METRICS_TOKEN"]


def main():
    env = read_env(env_file_arg())
    # Paperless stores API tokens in a 40-character field, so its token has 40 hex characters.
    length = {"PAPERLESS_METRICS_TOKEN": 20}
    new = {key: secrets.token_hex(length.get(key, 24)) for key in GENERATED if not env.get(key)}
    if new:
        result(new)
        status("changed", "generated " + ", ".join(sorted(new)))
    else:
        status("skipped", "all secrets are set")
    return 0


if __name__ == "__main__":
    sys.exit(main())
