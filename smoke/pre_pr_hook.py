#!/usr/bin/env python3
"""Claude Code PreToolUse hook: runs the smoke test before `gh pr create`.

Only one stack runs at a time: if the full stack is up, it is stopped (data kept), the smoke test runs,
and the full stack is started again, also when the test fails. A failing smoke test blocks the PR
(exit 2 is shown to Claude). Set SMOKE_SKIP=1 to skip the test for one run.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)


def compose(*args):
    return subprocess.run(["docker", "compose", "-f", "compose.yaml", *args], cwd=ROOT)


def full_stack_running():
    out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True).stdout
    return any(name.startswith("infrastructure-") for name in out.split())


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    command = (data.get("tool_input") or {}).get("command", "")
    if "gh pr create" not in command or os.environ.get("SMOKE_SKIP") == "1":
        return 0

    was_running = full_stack_running()
    if was_running:
        print("smoke: stopping the full stack for the test (data is kept)", file=sys.stderr)
        compose("down", "--timeout", "60")
    try:
        result = subprocess.run([sys.executable, "smoke/smoke.py"], cwd=ROOT)
    finally:
        if was_running:
            print("smoke: starting the full stack again", file=sys.stderr)
            compose("up", "-d", "--build")
    if result.returncode != 0:
        print("smoke test failed: the PR was not created. Fix the stack, then retry.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
