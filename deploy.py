#!/usr/bin/env python3
"""Deploy this repository to the target host. Standard library only.

  python3 deploy.py keys    create an SSH key pair (if missing) and install it on the host
  python3 deploy.py deploy  clone/update the repo on the host, upload .env, run server/deploy.sh

All configuration lives in .env (git-ignored).
"""

import base64
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
REQUIRED_KEYS = ["HOST_IP", "HOST_USERNAME", "HOST_PASSWORD"]
REQUIRED_DEPLOY = REQUIRED_KEYS + ["ALLOWED_NETWORK", "REPO_URL", "DEPLOY_DIR", "DATA_DIR"]
# Secrets that stay on the local machine; the host gets a copy of .env without them.
LOCAL_ONLY = ["HOST_PASSWORD", "HOST_PRIVATE_KEY", "HOST_PUBLIC_KEY"]


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


def write_env_value(key, value):
    lines = ENV_FILE.read_text().splitlines()
    for i, line in enumerate(lines):
        if "=" in line and line.partition("=")[0].strip() == key:
            lines[i] = f"{key}={value}"
            break
    else:
        # New key: place it at the end of the HOST_ group so related values stay together.
        host_lines = [i for i, line in enumerate(lines) if line.startswith("HOST_")]
        position = host_lines[-1] + 1 if host_lines else len(lines)
        lines.insert(position, f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n")
    ENV_FILE.chmod(0o600)


def target_of(env):
    return f"{env['HOST_USERNAME']}@{env['HOST_IP']}"


def ssh_command(key_file=None):
    opts = ["-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15"]
    if key_file:
        opts += ["-i", str(key_file), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes"]
    return ["ssh", *opts]


def ssh_run(target, command, key_file, stdin=None):
    subprocess.run([*ssh_command(key_file), target, command], input=stdin, check=True)


def write_private_key(directory, env):
    path = Path(directory) / "id_ed25519"
    path.write_bytes(base64.b64decode(env["HOST_PRIVATE_KEY"]))
    path.chmod(0o600)
    return path


def ensure_keypair(env):
    """Make sure HOST_PRIVATE_KEY and HOST_PUBLIC_KEY exist in .env. Returns the public key."""
    private, public = env.get("HOST_PRIVATE_KEY", ""), env.get("HOST_PUBLIC_KEY", "")
    if private and public:
        return public
    with tempfile.TemporaryDirectory() as tmp:
        if private:
            # Only the public half is missing: derive it from the private key.
            key_file = write_private_key(tmp, env)
            public = subprocess.run(
                ["ssh-keygen", "-y", "-f", str(key_file)], check=True, capture_output=True, text=True
            ).stdout.strip()
        else:
            key_file = Path(tmp) / "id_ed25519"
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "infrastructure-deploy", "-f", str(key_file)],
                check=True,
            )
            public = Path(f"{key_file}.pub").read_text().strip()
            private = base64.b64encode(key_file.read_bytes()).decode()
            write_env_value("HOST_PRIVATE_KEY", private)
            print("Generated a new SSH key pair and stored it in .env")
    write_env_value("HOST_PUBLIC_KEY", public)
    return public


def install_public_key(env, public_key):
    """Append the public key to the host's authorized_keys, logging in with the password once."""
    remote = (
        "umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; "
        'k=$(cat); grep -qxF "$k" ~/.ssh/authorized_keys || printf "%s\\n" "$k" >> ~/.ssh/authorized_keys'
    )
    with tempfile.TemporaryDirectory() as tmp:
        # ssh asks this helper for the password; the password itself only lives in the environment.
        askpass = Path(tmp) / "askpass.sh"
        askpass.write_text('#!/bin/sh\nprintf "%s\\n" "$HOST_PASSWORD"\n')
        askpass.chmod(0o700)
        env_vars = {
            **os.environ,
            "SSH_ASKPASS": str(askpass),
            "SSH_ASKPASS_REQUIRE": "force",
            "HOST_PASSWORD": env["HOST_PASSWORD"],
        }
        cmd = [
            *ssh_command(),
            "-o", "PubkeyAuthentication=no",
            "-o", "PreferredAuthentications=password",
            target_of(env), remote,
        ]
        subprocess.run(cmd, input=(public_key + "\n").encode(), env=env_vars, check=True)


def cmd_keys(env):
    public = ensure_keypair(env)
    install_public_key(env, public)
    env = read_env()
    with tempfile.TemporaryDirectory() as tmp:
        key_file = write_private_key(tmp, env)
        ssh_run(target_of(env), "echo 'SSH key login works'", key_file)


def host_env_content():
    """The .env copy uploaded to the host, without the secrets the host does not need."""
    lines = ENV_FILE.read_text().splitlines()
    kept = [line for line in lines if "=" not in line or line.partition("=")[0].strip() not in LOCAL_ONLY]
    return ("\n".join(kept) + "\n").encode()


def cmd_deploy(env):
    if not (env.get("HOST_PRIVATE_KEY") and env.get("HOST_PUBLIC_KEY")):
        sys.exit("No SSH key in .env yet. Run: python3 deploy.py keys")
    target = target_of(env)
    deploy_dir = shlex.quote(env["DEPLOY_DIR"])
    repo_url = shlex.quote(env["REPO_URL"])
    with tempfile.TemporaryDirectory() as tmp:
        key_file = write_private_key(tmp, env)

        print("==> Cloning or updating the repository on the host")
        ssh_run(
            target,
            f"if [ -d {deploy_dir}/.git ]; then git -C {deploy_dir} pull --ff-only; "
            f"else git clone {repo_url} {deploy_dir}; fi",
            key_file,
        )

        print("==> Uploading .env")
        ssh_run(target, f"cat > {deploy_dir}/.env && chmod 600 {deploy_dir}/.env", key_file, stdin=host_env_content())

        print("==> Installing dependencies, applying firewall, starting the stack")
        # sudo reads the password from the first line of stdin; the script itself is already on the host.
        ssh_run(
            target,
            f"sudo -S -p '' bash {deploy_dir}/server/deploy.sh "
            f"{shlex.quote(env['ALLOWED_NETWORK'])} {shlex.quote(env['DATA_DIR'])}",
            key_file,
            stdin=(env["HOST_PASSWORD"] + "\n").encode(),
        )
    print("Deployment finished.")


def main():
    commands = {"keys": cmd_keys, "deploy": cmd_deploy}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    env = read_env()
    required = REQUIRED_KEYS if sys.argv[1] == "keys" else REQUIRED_DEPLOY
    missing = [key for key in required if not env.get(key)]
    if missing:
        sys.exit("Missing values in .env: " + ", ".join(missing))
    commands[sys.argv[1]](env)


if __name__ == "__main__":
    main()
