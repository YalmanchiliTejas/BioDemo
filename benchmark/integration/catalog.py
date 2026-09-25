from __future__ import annotations

import os
from collections.abc import Mapping

from .connectors import RESTConnector
from .models import ConnectorConfig


SYSTEM_CONNECTORS = {
    "MES": ("MES", "/api/events", "/api/actions"),
    "EBR": ("MES/eBR", "/api/events", "/api/actions"),
    "PAT": ("PAT", "/api/events", None),
    "LIMS": ("LIMS", "/api/events", "/api/actions"),
    "CDS": ("CDS", "/api/events", None),
    "QMS": ("QMS", "/api/events", "/api/actions"),
    "SCADA": ("SCADA", "/api/events", None),
    "HISTORIAN": ("Historian", "/api/events", None),
    "CMMS": ("CMMS", "/api/events", "/api/actions"),
    "ERP": ("ERP", "/api/events", "/api/actions"),
    "WMS": ("WMS", "/api/events", "/api/actions"),
    "ELN": ("ELN", "/api/events", "/api/actions"),
}


def connectors_from_settings(settings: Mapping[str, str] | None = None) -> dict[str, RESTConnector]:
    """Create connectors for systems whose `<NAME>_BASE_URL` setting is present."""
    values = settings if settings is not None else os.environ
    connectors: dict[str, RESTConnector] = {}
    for prefix, (source_system, default_events, default_write) in SYSTEM_CONNECTORS.items():
        base_url = values.get(f"{prefix}_BASE_URL")
        if not base_url:
            continue
        token = values.get(f"{prefix}_API_TOKEN")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        write_path = values.get(f"{prefix}_WRITE_PATH", default_write)
        if str(write_path).lower() in {"", "none", "false"}:
            write_path = None
        config = ConnectorConfig(
            connector_id=values.get(f"{prefix}_CONNECTOR_ID", prefix.lower()),
            source_system=source_system, base_url=base_url,
            events_path=values.get(f"{prefix}_EVENTS_PATH", default_events),
            write_path=write_path, site_id=values.get(f"{prefix}_SITE_ID"),
            classification=values.get(f"{prefix}_CLASSIFICATION", "internal"),
            headers=headers,
        )
        connectors[prefix.lower()] = RESTConnector(config)
    return connectors
