from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .domain import EvidenceRecord


class FileEvidenceStore:
    """Content-addressed immutable evidence store for local and test deployments."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.records: dict[tuple[str, str], EvidenceRecord] = {}

    def put(
        self, content: bytes, *, tenant_id: str, source_system: str, source_record_id: str,
        media_type: str, event_time: datetime, site_id: str | None = None,
        classification: str = "internal", metadata: dict[str, Any] | None = None,
    ) -> EvidenceRecord:
        digest = hashlib.sha256(content).hexdigest()
        evidence_id = f"evd-{digest}"
        target = self.root / tenant_id / digest[:2] / digest
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError("immutable evidence hash collision")
        if not target.exists():
            target.write_bytes(content)
        record = EvidenceRecord(
            evidence_id=evidence_id, tenant_id=tenant_id, source_system=source_system,
            source_record_id=source_record_id, content_sha256=digest, uri=target.as_uri(),
            media_type=media_type, event_time=event_time, ingested_at=datetime.now(timezone.utc),
            site_id=site_id, classification=classification, size_bytes=len(content),
            metadata=metadata or {},
        )
        self.records[(tenant_id, evidence_id)] = record
        return record

    def read(self, evidence_id: str, tenant_id: str) -> bytes:
        record = self.records.get((tenant_id, evidence_id))
        if record is None:
            raise KeyError(evidence_id)
        return Path(record.uri.removeprefix("file://")).read_bytes()


class S3EvidenceStore:
    """S3/MinIO immutable adapter using content hashes as object keys."""

    def __init__(self, bucket: str, *, endpoint_url: str | None = None, region: str = "us-east-1") -> None:
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError as exc:  # pragma: no cover - optional service
            raise RuntimeError("Install the 'knowledge' extra to use S3 evidence storage") from exc
        self.bucket = bucket
        self._client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)
        self._client_error = ClientError

    def put(
        self, content: bytes, *, tenant_id: str, source_system: str, source_record_id: str,
        media_type: str, event_time: datetime, site_id: str | None = None,
        classification: str = "internal", metadata: dict[str, Any] | None = None,
    ) -> EvidenceRecord:
        digest = hashlib.sha256(content).hexdigest()
        evidence_id = f"evd-{digest}"
        key = f"{tenant_id}/{digest[:2]}/{digest}"
        try:
            existing = self._client.head_object(Bucket=self.bucket, Key=key)
            if existing.get("Metadata", {}).get("sha256") != digest:
                raise RuntimeError("immutable evidence object exists with a different digest")
        except self._client_error as exc:
            if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey", "NotFound"}:
                raise
            self._client.put_object(
                Bucket=self.bucket, Key=key, Body=content, ContentType=media_type,
                Metadata={"sha256": digest, "source-system": source_system,
                          "source-record-id": source_record_id},
            )
        return EvidenceRecord(
            evidence_id=evidence_id, tenant_id=tenant_id, source_system=source_system,
            source_record_id=source_record_id, content_sha256=digest,
            uri=f"s3://{self.bucket}/{key}", media_type=media_type, event_time=event_time,
            ingested_at=datetime.now(timezone.utc), site_id=site_id,
            classification=classification, size_bytes=len(content), metadata=metadata or {},
        )

    def read(self, evidence_id: str, tenant_id: str) -> bytes:
        digest = evidence_id.removeprefix("evd-")
        key = f"{tenant_id}/{digest[:2]}/{digest}"
        return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
