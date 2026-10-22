from __future__ import annotations

import hashlib
import json
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


URL = "https://zenodo.org/records/20829178/files/Dataset.zip?download=1"
MD5 = "71b2a35b7df2ed11644ec9f177453772"
ROOT = Path(__file__).resolve().parent


def download_and_extract() -> dict:
    archive = ROOT / "raw/Dataset.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        urllib.request.urlretrieve(URL, archive)
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            md5.update(chunk); sha.update(chunk)
    if md5.hexdigest() != MD5:
        raise ValueError(f"archive MD5 mismatch: {md5.hexdigest()} != {MD5}")
    previous_manifest = ROOT / "source_manifest.json"
    previous = json.loads(previous_manifest.read_text(encoding="utf-8")) if previous_manifest.exists() else {}
    members = []
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename)
            if name.is_absolute() or ".." in name.parts:
                raise ValueError(f"unsafe archive path: {info.filename}")
            if name.suffix.lower() not in {".xlsx", ".csv", ".pdf", ".txt", ".md"}:
                continue
            dest = ROOT / ("raw/workbooks" if name.suffix.lower() == ".xlsx" else "reference/aligned") / name.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            source_hash = hashlib.sha256()
            with bundle.open(info) as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    source_hash.update(chunk)
            if not dest.exists():
                with bundle.open(info) as source, dest.open("wb") as sink:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        sink.write(chunk)
            installed_hash = hashlib.sha256(dest.read_bytes()).hexdigest()
            if installed_hash != source_hash.hexdigest():
                raise ValueError(f"extracted file differs from immutable archive: {dest}")
            members.append({"archive_path": info.filename, "installed_path": str(dest.relative_to(ROOT)),
                            "bytes": info.file_size, "crc32": f"{info.CRC:08x}",
                            "sha256": installed_hash})
    result = {"manifest_version": "cho-source-v2", "source_version": "Zenodo record 20829178 v1",
              "publication_date": "2026-08-11", "source_url": URL, "doi": "10.5281/zenodo.20829178", "published_md5": MD5,
              "archive_md5": md5.hexdigest(), "archive_sha256": sha.hexdigest(),
              "downloaded_at": previous.get("downloaded_at") or datetime.now(timezone.utc).isoformat(), "members": members,
              "license": "CC-BY-4.0 (Zenodo record API metadata.license.id); attribution required for redistribution"}
    (ROOT / "source_manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(download_and_extract(), indent=2))
