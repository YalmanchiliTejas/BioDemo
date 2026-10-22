"""Stream a consistent PostgreSQL dump into encryption, then off-host storage."""
import os
import tempfile
import time
import uuid
from pathlib import Path

import docker
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .crypto import master_key, object_key, spaces_client


def main():
    os.umask(0o077)
    tenant = os.environ["DEPLOYMENT_TENANT"]
    key = f'{tenant}/backups/{int(time.time())}-{uuid.uuid4().hex}.dump.enc'
    engine = docker.from_env()
    matches = engine.containers.list(filters={"label": ["com.docker.compose.project=biodemo-cloud",
                                                        "com.docker.compose.service=db"]})
    if len(matches) != 1:
        raise RuntimeError("Exactly one database container is required")
    task = engine.api.exec_create(matches[0].id, ["pg_dump", "-U", "migration_admin", "-d", "investigations", "--format=custom"])
    nonce = os.urandom(12)
    encryptor = Cipher(algorithms.AES(object_key(master_key(), key)), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(key.encode())
    with tempfile.TemporaryDirectory(dir="/backups") as folder:
        path = Path(folder) / "database.enc"
        with path.open("wb") as out:
            out.write(b"BIO1" + nonce)
            for stdout, _stderr in engine.api.exec_start(task["Id"], stream=True, demux=True):
                if stdout:
                    out.write(encryptor.update(stdout))
            out.write(encryptor.finalize())
            out.write(encryptor.tag)
        if engine.api.exec_inspect(task["Id"])["ExitCode"] != 0:
            raise RuntimeError("Database backup failed")
        spaces_client().upload_file(str(path), os.environ["ARTIFACT_BUCKET"], key)
    print('{"event":"encrypted_backup_uploaded"}', flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print('{"event":"backup_failed"}', flush=True)
        raise SystemExit(1)
