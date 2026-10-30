#!/usr/bin/env python3
"""Runs the lifecycle steps in order: host check, secrets, certificates, images, Stalwart, Paperless, stack.

  python3 server/steps/run.py <env-file>

Each step checks what is already in place and changes only what is missing. Values a step generates
(RESULT lines) are written into the env file, so the next steps and docker compose see them. The same
runner is used on the server by deploy.py and locally by the test.
Stops at the first failed step.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import env_file_arg  # noqa: E402

STEPS = ["host_check", "credentials", "tls", "images", "stalwart", "paperless_token", "stack"]


def write_values(env_path, values):
    lines = env_path.read_text().splitlines()
    for key, value in values.items():
        for i, line in enumerate(lines):
            if line.partition("=")[0].strip() == key:
                lines[i] = f"{key}={value}"
                break
        else:
            lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n")
    env_path.chmod(0o600)


def main():
    env_path = env_file_arg()
    for step in STEPS:
        print(f"== {step}", flush=True)
        proc = subprocess.run([sys.executable, str(HERE / f"{step}.py"), str(env_path)],
                              capture_output=True, text=True)
        for line in proc.stdout.splitlines():
            if line.startswith("STATUS "):
                print("   " + line[7:], flush=True)
            elif line.startswith("RESULT "):
                values = json.loads(line[7:])
                write_values(env_path, values)
                print("RESULT " + line[7:], flush=True)
        if proc.returncode != 0:
            print(f"   step {step} failed", flush=True)
            if proc.stderr.strip():
                print(proc.stderr[-1500:], flush=True)
            return 1
    print("all steps finished", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
