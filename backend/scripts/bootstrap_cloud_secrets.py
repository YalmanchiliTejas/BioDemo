"""Create droplet secret files without putting credentials in CLI args or logs.

Run as root on the droplet, from the checkout on the unlocked encrypted volume.
This refuses to overwrite any secret or initialize storage.
"""
import argparse
import base64
import getpass
import json
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("deploy/cloud/secrets"))
    args = parser.parse_args()
    if os.geteuid() != 0 or not os.path.ismount("/srv/biodemo"):
        raise SystemExit("Run as root after mounting the encrypted volume at /srv/biodemo")
    root = args.directory.resolve()
    if Path("/srv/biodemo") not in root.parents:
        raise SystemExit("Secrets must live on the encrypted volume")
    if root.exists() and any(root.iterdir()):
        raise SystemExit("Secret directory is nonempty; rotation requires a separate reviewed procedure")
    access_key = getpass.getpass("Restricted Spaces access key: ")
    secret_key = getpass.getpass("Restricted Spaces secret key: ")
    backup_access = getpass.getpass("Separate backup-bucket Spaces access key: ")
    backup_secret = getpass.getpass("Separate backup-bucket Spaces secret key: ")
    provider_key = getpass.getpass("Approved model endpoint credential: ")
    if not all((access_key, secret_key, provider_key, backup_access, backup_secret)):
        raise SystemExit("All credentials are required")
    root.mkdir(parents=True, mode=0o750, exist_ok=True)
    os.chown(root, 0, 10001)

    def write(name, value, uid=0, gid=0, mode=0o600):
        fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, "w") as out:
            out.write(value + "\n")
        os.chown(root / name, uid, gid)

    passwords = {name: secrets.token_urlsafe(36) for name in ("migration_admin", "cloud_api", "cloud_dispatcher")}
    write("migration_password", passwords["migration_admin"])
    for role, file, uid in (("cloud_api", "api_database_url", 10001), ("cloud_dispatcher", "dispatcher_database_url", 0)):
        dsn = f"postgresql://{role}:{quote(passwords[role], safe='')}@db:5432/investigations?sslmode=verify-full&sslrootcert=/run/secrets/db_ca"
        write(file, dsn, uid=uid, gid=uid)
    # psql includes this once after the schema/role migration, then remove it.
    # Generated passwords use URL-safe characters; no untrusted SQL text is interpolated.
    write("initialize_passwords.sql", "\n".join(f"ALTER ROLE {role} PASSWORD '{passwords[role]}';"
                                               for role in ("cloud_api", "cloud_dispatcher")))
    write("spaces_credentials.json", json.dumps({"access_key": access_key, "secret_key": secret_key}), 10001, 10001)
    write("object_master_key", base64.b64encode(secrets.token_bytes(32)).decode(), 10001, 10001)
    write("model_secret", provider_key)
    write("backup_credentials.json", json.dumps({"access_key": backup_access, "secret_key": backup_secret}))
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:3072", "-nodes", "-days", "90",
                    "-subj", "/CN=db", "-addext", "subjectAltName=DNS:db",
                    "-keyout", str(root / "db_server.key"), "-out", str(root / "db_server.crt")],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.chown(root / "db_server.key", 0, 999)
    os.chmod(root / "db_server.key", 0o640)
    os.chmod(root / "db_server.crt", 0o644)
    print("Secret files created. Back up the object master key separately; initialize DB passwords and rotate the DB certificate before 90 days.")


if __name__ == "__main__":
    main()
