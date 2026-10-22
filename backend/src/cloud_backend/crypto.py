"""Application encryption with distinct keys per object and authenticated paths."""
import base64
import os
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def object_key(master: bytes, path: str) -> bytes:
    if len(master) != 32:
        raise ValueError("A 32-byte encryption master key is required")
    return HKDF(algorithm=hashes.SHA256(), length=32,
                salt=b"biodemo-object-key-v1", info=path.encode()).derive(master)


def seal(key: bytes, path: str, data: bytes) -> bytes:
    nonce = os.urandom(12)
    return b"BIO1" + nonce + AESGCM(key).encrypt(nonce, data, path.encode())


def unseal(key: bytes, path: str, data: bytes) -> bytes:
    if data[:4] != b"BIO1":
        raise ValueError("Invalid encrypted object")
    return AESGCM(key).decrypt(data[4:16], data[16:], path.encode())


def master_key() -> bytes:
    from pathlib import Path
    key = base64.b64decode(Path(os.environ["OBJECT_MASTER_KEY_FILE"]).read_text().strip(), validate=True)
    if len(key) != 32:
        raise ValueError("Invalid object master key")
    return key


def spaces_client():
    import boto3
    from botocore.config import Config
    from pathlib import Path
    endpoint = os.environ["SPACES_ENDPOINT"]
    if urlsplit(endpoint).scheme != "https":
        raise ValueError("Object storage must use HTTPS")
    credentials = __import__("json").loads(Path(os.environ["SPACES_CREDENTIALS_FILE"]).read_text())
    return boto3.client("s3", endpoint_url=os.environ["SPACES_ENDPOINT"],
                        region_name=os.environ["SPACES_REGION"],
                        aws_access_key_id=credentials["access_key"],
                        aws_secret_access_key=credentials["secret_key"],
                        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"},
                                      request_checksum_calculation="when_required",
                                      response_checksum_validation="when_required"))
