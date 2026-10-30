#!/usr/bin/env python3
"""Local CA and certificates for Vaultwarden and Stalwart, issued only where missing or no longer valid.

A certificate is valid for this step when it exists, is not expiring within 30 days, and names HOST_IP.
Existing CA files are never replaced: clients already trust them.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env_file_arg, read_env, status  # noqa: E402

MAIL_HOST = "mail.home.lan"
MONTH = 30 * 24 * 3600


def openssl(*args, input_text=None):
    return subprocess.run(["openssl", *args], capture_output=True, text=True, input=input_text)


def valid(cert, host_ip):
    if not cert.exists():
        return False
    if openssl("x509", "-in", str(cert), "-noout", "-checkend", str(MONTH)).returncode != 0:
        return False
    san = openssl("x509", "-in", str(cert), "-noout", "-ext", "subjectAltName").stdout
    return f"IP Address:{host_ip}" in san


def issue(ca_cert, ca_key, key, cert, name, host_ip):
    ext = key.parent / f".{name}.ext"
    ext.write_text(f"subjectAltName=DNS:{name},DNS:localhost,IP:{host_ip}\n"
                   "extendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n")
    csr = key.parent / f".{name}.csr"
    openssl("req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-subj", f"/CN={name}", "-out", str(csr))
    openssl("x509", "-req", "-in", str(csr), "-CA", str(ca_cert), "-CAkey", str(ca_key), "-CAcreateserial",
            "-days", "825", "-sha256", "-extfile", str(ext), "-out", str(cert))
    csr.unlink(missing_ok=True)
    ext.unlink(missing_ok=True)
    key.chmod(0o600)
    cert.chmod(0o644)


def main():
    env = read_env(env_file_arg())
    host_ip, data = env["HOST_IP"], Path(env["DATA_DIR"])
    vw, mail = data / "vaultwarden-tls", data / "mail" / "tls"
    for d in (vw, mail, data / "mail" / "etc", data / "mail" / "data", data / "monitoring" / "secrets"):
        d.mkdir(parents=True, exist_ok=True)

    changed = []
    ca_cert, ca_key = vw / "ca.pem", vw / "ca-key.pem"
    if not (ca_cert.exists() and ca_key.exists()):
        openssl("req", "-x509", "-newkey", "rsa:4096", "-nodes", "-days", "3650", "-keyout", str(ca_key),
                "-out", str(ca_cert), "-subj", "/CN=Homelab Local CA")
        ca_key.chmod(0o600)
        ca_cert.chmod(0o644)
        changed.append("local CA")

    if not valid(vw / "cert.pem", host_ip):
        issue(ca_cert, ca_key, vw / "key.pem", vw / "cert.pem", Path("/etc/hostname").read_text().strip() or "vault", host_ip)
        changed.append("Vaultwarden certificate")

    if not valid(mail / "cert.pem", host_ip) or not (mail / "fullchain.pem").exists():
        issue(ca_cert, ca_key, mail / "privkey.pem", mail / "cert.pem", MAIL_HOST, host_ip)
        (mail / "fullchain.pem").write_text((mail / "cert.pem").read_text() + ca_cert.read_text())
        (mail / "ca.pem").write_text(ca_cert.read_text())
        changed.append("mail certificate")

    if changed:
        status("changed", "issued: " + ", ".join(changed))
    else:
        status("skipped", "CA and certificates are present and valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
