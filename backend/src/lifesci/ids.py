from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def new_id(prefix: str = "") -> str:
    """Time-ordered, collision-resistant identifier (ULID layout)."""
    millis = int(time.time() * 1000)
    chars = []
    for _ in range(10):
        chars.append(_CROCKFORD[millis & 31])
        millis >>= 5
    head = "".join(reversed(chars))
    tail = "".join(_CROCKFORD[b & 31] for b in os.urandom(16))
    value = head + tail
    return f"{prefix}_{value}" if prefix else value


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_default)


def content_hash(value: Any) -> str:
    """Stable SHA-256 of canonical JSON; used to bind signatures and approvals to exact content."""
    if isinstance(value, (bytes, bytearray)):
        return hashlib.sha256(bytes(value)).hexdigest()
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _default(value: Any) -> Any:
    if isinstance(value, datetime):
        return iso(value)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, (set, frozenset, tuple)):
        return sorted(value) if isinstance(value, (set, frozenset)) else list(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")
