"""Named-product connectors: guided sign-in, discovery and incremental reads for hosted systems.

Credentials entered in the app are sealed with AES-GCM under a per-connection key derived from
``LIFESCI_CONNECTOR_KEY`` and kept in a separate ``connector_credential`` record. They are never
returned by the API. Adapters follow the vendors' public API documentation; they have not been
qualified against live customer tenants.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import secrets
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .connector_contracts import PullBatch, SourceRecord
from .ids import iso, utc_now

CREDENTIAL_KIND = "connector_credential"


class SourceError(ValueError):
    """A source refused or failed a request; the message is safe to show to the person configuring it."""


# --------------------------------------------------------------------------- credentials


def _master_key() -> bytes:
    raw = os.environ.get("LIFESCI_CONNECTOR_KEY", "").strip()
    if raw:
        key = base64.b64decode(raw, validate=True)
        if len(key) != 32:
            raise ValueError("LIFESCI_CONNECTOR_KEY must be 32 bytes, base64-encoded")
        return key
    development = (os.environ.get("LIFESCI_AUTH_MODE", "development") == "development"
                   and not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
    if not development:
        raise SourceError("Credential storage is not configured on this server. "
                          "An administrator must set LIFESCI_CONNECTOR_KEY.")
    path = Path(__file__).resolve().parents[2] / ".cache" / "connector-key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(base64.b64encode(secrets.token_bytes(32)).decode())
    return base64.b64decode(path.read_text().strip(), validate=True)


def _connection_key(tenant: str, cid: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"sievance-connector-credential-v1",
                info=f"{tenant}/{cid}".encode()).derive(_master_key())


class CredentialStore:
    """Sealed per-connection credentials. Only field names are ever exposed."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def save(self, tx: Any, tenant: str, cid: str, values: dict[str, str]) -> None:
        current = tx.get(tenant, CREDENTIAL_KIND, cid)
        merged = {**(self._open(tenant, cid, current.state) if current else {}), **values}
        nonce = os.urandom(12)
        sealed = AESGCM(_connection_key(tenant, cid)).encrypt(
            nonce, json.dumps(merged).encode(), f"{tenant}/{cid}".encode())
        tx.put(tenant, CREDENTIAL_KIND, cid, {
            "connector_id": cid, "fields": sorted(merged), "sealed": base64.b64encode(nonce + sealed).decode(),
            "scheme": "aes-256-gcm/hkdf-sha256/v1", "updated_at": iso(utc_now())},
            expected_revision=current.revision if current else None, action="store_connector_credential")

    def load(self, tenant: str, cid: str) -> dict[str, str]:
        rec = self.store.read().get(tenant, CREDENTIAL_KIND, cid)
        return self._open(tenant, cid, rec.state) if rec else {}

    def fields(self, tenant: str, cid: str) -> list[str]:
        rec = self.store.read().get(tenant, CREDENTIAL_KIND, cid)
        return list(rec.state["fields"]) if rec else []

    @staticmethod
    def _open(tenant: str, cid: str, state: dict[str, Any]) -> dict[str, str]:
        blob = base64.b64decode(state["sealed"])
        try:
            data = AESGCM(_connection_key(tenant, cid)).decrypt(blob[:12], blob[12:], f"{tenant}/{cid}".encode())
        except Exception as exc:
            raise SourceError("Saved credentials cannot be read on this server. Enter them again.") from exc
        return json.loads(data)


# --------------------------------------------------------------------------- network policy


def _allowed_hosts() -> set[str]:
    return {h.strip().lower() for h in os.environ.get("LIFESCI_CONNECTOR_ALLOWED_HOSTS", "").split(",") if h.strip()}


def checked_url(url: str, domains: tuple[str, ...] = ()) -> str:
    """Accept vendor domains, administrator-approved hosts, or public HTTPS hosts; never private networks."""
    url = (url or "").strip().rstrip("/")
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not host or parts.username or parts.password or parts.query or parts.fragment:
        raise SourceError("Enter the address as https://host/path, without a username, ? or #.")
    if host in _allowed_hosts():
        if parts.scheme == "https" or (parts.scheme == "http" and host in {"localhost", "127.0.0.1", "::1"}):
            return url
        raise SourceError("Use an https:// address.")
    if parts.scheme != "https":
        raise SourceError("Use an https:// address.")
    if domains:
        if any(host == d or host.endswith("." + d) for d in domains):
            return url
        raise SourceError(f"This address should end in {' or '.join(domains)}.")
    if os.environ.get("LIFESCI_CONNECTOR_PUBLIC_HOSTS", "1") != "1":
        raise SourceError("Your administrator must approve this address before it can be used.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, parts.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise SourceError(f"Could not find {host}. Check the address.") from exc
    if not addresses or not all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addresses):
        raise SourceError(f"{host} is on a private network, so it cannot be reached from the cloud. "
                          "Use file upload for now.")
    return url


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SourceError("The system redirected to another address. Enter the final address instead.")


_OPENER = build_opener(_NoRedirect())


def _message(body: bytes) -> str:
    try:
        doc = json.loads(body)
    except Exception:
        return ""
    if isinstance(doc, dict):
        for key in ("message", "detail", "error_description"):
            if isinstance(doc.get(key), str):
                return doc[key]
        if isinstance(doc.get("error"), dict) and isinstance(doc["error"].get("message"), str):
            return doc["error"]["message"]
        if isinstance(doc.get("errors"), list) and doc["errors"] and isinstance(doc["errors"][0], dict):
            return str(doc["errors"][0].get("message", ""))
        if isinstance(doc.get("Errors"), list) and doc["Errors"]:
            return str(doc["Errors"][0])
    return ""


def http_json(method: str, url: str, *, headers: dict[str, str] | None = None, body: bytes | None = None,
              timeout: float = 30) -> tuple[int, Any]:
    host = urlsplit(url).hostname
    req = Request(url, data=body, method=method, headers={
        "Accept": "application/json", "User-Agent": "Sievance-Connector/1", **(headers or {})})
    try:
        with _OPENER.open(req, timeout=timeout) as response:
            status, raw = response.status, response.read(20_000_001)
    except HTTPError as exc:
        detail = _message(exc.read(200_000))
        if exc.code in (401, 403):
            raise SourceError(f"{host} rejected the sign-in (HTTP {exc.code}). Check the credentials and that "
                              f"this account has read access.{' ' + detail if detail else ''}") from exc
        if exc.code == 404:
            raise SourceError(f"{host} returned 'not found'. Check the address.{' ' + detail if detail else ''}") from exc
        raise SourceError(f"{host} returned an error (HTTP {exc.code}).{' ' + detail if detail else ''}") from exc
    except URLError as exc:
        raise SourceError(f"Could not reach {host}. Check the address and that it is reachable from the internet.") from exc
    except TimeoutError as exc:
        raise SourceError(f"{host} did not respond in time.") from exc
    if len(raw) > 20_000_000:
        raise SourceError("The response was too large. Choose a smaller table or fewer tags.")
    try:
        return status, json.loads(raw) if raw else {}
    except ValueError as exc:
        raise SourceError(f"{host} did not return JSON. Check the address.") from exc


# --------------------------------------------------------------------------- helpers

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,254}$")
_NAME = re.compile(r"^[^\"`\x00-\x1f]{1,255}$")
_FRACTION = re.compile(r"(\.\d{6})\d+")


def _ident(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENT.fullmatch(value):
        raise SourceError(f"{label} may only contain letters, numbers and underscores.")
    return value


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise SourceError(f"Choose a valid {label}.")
    return value


def parse_time(value: Any) -> datetime:
    text = _FRACTION.sub(r"\1", str(value).strip().replace("Z", "+00:00"))
    moment = datetime.fromisoformat(text)
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


# --------------------------------------------------------------------------- catalog

Field = dict[str, Any]


def _f(key: str, label: str, *, secret: bool = False, credential: bool = False, placeholder: str = "",
       help: str = "", required: bool = True, choices: list[list[str]] | None = None,
       when: dict[str, list[str]] | None = None) -> Field:
    out: Field = {"key": key, "label": label, "secret": secret, "credential": credential or secret,
                  "placeholder": placeholder, "help": help, "required": required}
    if choices:
        out["choices"] = choices
    if when:
        out["when"] = when
    return out


PRODUCTS: dict[str, dict[str, Any]] = {
    "veeva_vault": {
        "name": "Veeva Vault", "category": "Quality and documents", "family": "QMS",
        "description": "Deviations, CAPAs, change controls and other records from Vault QMS or QualityDocs.",
        "domains": ("veevavault.com",), "resource": "Vault object", "multiple": False, "table": False,
        "help": "Use a dedicated Vault user with read-only access to the objects you need.",
        "fields": [
            _f("base_url", "Vault address", placeholder="https://yourcompany.veevavault.com"),
            _f("username", "Username", credential=True, placeholder="integration.user@yourcompany.com"),
            _f("password", "Password", secret=True),
        ]},
    "pi_web_api": {
        "name": "AVEVA PI (PI Web API)", "category": "Process historian", "family": "HISTORIAN",
        "description": "Recorded values for selected PI tags through PI Web API.",
        "domains": (), "resource": "PI tags", "multiple": True, "table": False,
        "help": "PI Web API must be reachable from the internet with Basic sign-in enabled. "
                "If PI is only on your plant network, use file upload for now.",
        "fields": [
            _f("base_url", "PI Web API address", placeholder="https://pi.yourcompany.com/piwebapi"),
            _f("username", "Username", credential=True, placeholder="DOMAIN\\username"),
            _f("password", "Password", secret=True),
            _f("history_days", "Days of history on first sync", placeholder="7", required=False),
        ]},
    "snowflake": {
        "name": "Snowflake", "category": "Data warehouse", "family": None,
        "description": "Rows from a table or view your team already keeps in Snowflake.",
        "domains": ("snowflakecomputing.com",), "resource": "table or view", "multiple": False, "table": True,
        "help": "Create a programmatic access token for a user with a read-only role.",
        "fields": [
            _f("account", "Account identifier", placeholder="myorg-myaccount",
               help="The part before .snowflakecomputing.com in your Snowflake address."),
            _f("token", "Programmatic access token", secret=True),
            _f("warehouse", "Warehouse", placeholder="ANALYTICS_WH"),
            _f("database", "Database", placeholder="MANUFACTURING"),
            _f("schema", "Schema", placeholder="PUBLIC"),
            _f("role", "Role", placeholder="READ_ONLY", required=False),
        ]},
    "databricks": {
        "name": "Databricks", "category": "Data warehouse", "family": None,
        "description": "Rows from a table or view in a Databricks SQL warehouse.",
        "domains": ("cloud.databricks.com", "azuredatabricks.net", "gcp.databricks.com"),
        "resource": "table or view", "multiple": False, "table": True,
        "help": "Use a personal access token or service principal token with read access to the schema.",
        "fields": [
            _f("base_url", "Workspace address", placeholder="https://dbc-1234abcd-5678.cloud.databricks.com"),
            _f("token", "Access token", secret=True),
            _f("warehouse_id", "SQL warehouse ID", placeholder="1234567890abcdef",
               help="Shown under SQL Warehouses → your warehouse → Connection details."),
            _f("catalog", "Catalog", placeholder="main"),
            _f("schema", "Schema", placeholder="manufacturing"),
        ]},
    "benchling": {
        "name": "Benchling", "category": "Lab notebook and registry", "family": "ELN",
        "description": "Registry entities and results from a Benchling schema.",
        "domains": ("benchling.com",), "resource": "schema", "multiple": False, "table": False,
        "help": "Create an API key under your Benchling settings for an account with read access.",
        "fields": [
            _f("base_url", "Benchling address", placeholder="https://yourcompany.benchling.com"),
            _f("api_key", "API key", secret=True),
        ]},
    "rest_api": {
        "name": "Other system (REST API)", "category": "Any system", "family": None,
        "description": "Any system that returns records as JSON over HTTPS.",
        "domains": (), "resource": None, "multiple": False, "table": False,
        "help": "The endpoint should return JSON with a list of records. Your IT team can help with these details.",
        "fields": [
            _f("base_url", "API address", placeholder="https://api.yourcompany.com"),
            _f("events_path", "Records path", placeholder="/v1/records"),
            _f("auth_type", "Sign-in method", choices=[["none", "No sign-in"], ["bearer", "Bearer token"],
                                                       ["api_key", "API key header"], ["basic", "Username and password"]]),
            _f("token", "Token", secret=True, when={"auth_type": ["bearer"]}),
            _f("api_key_header", "Header name", placeholder="X-API-Key", when={"auth_type": ["api_key"]}),
            _f("api_key", "API key", secret=True, when={"auth_type": ["api_key"]}),
            _f("username", "Username", credential=True, when={"auth_type": ["basic"]}),
            _f("password", "Password", secret=True, when={"auth_type": ["basic"]}),
            _f("records_field", "Field holding the list of records", placeholder="records", required=False),
            _f("id_field", "Record ID field", placeholder="id", required=False),
            _f("timestamp_field", "Timestamp field", placeholder="timestamp", required=False),
        ]},
}
PRODUCT_OPTIONS = {"base_url", "events_path", "records_field", "next_checkpoint_field", "id_field", "timestamp_field",
                   "cursor_parameter", "limit_parameter", "auth_type", "api_key_header", "history_days", "account",
                   "warehouse", "database", "schema", "role", "warehouse_id", "catalog", "resource", "resources",
                   "resource_labels", "id_column", "updated_column", "api_version", "poll_seconds", "batch_size"}


def catalog() -> list[dict[str, Any]]:
    return [{"product": key, **{k: v for k, v in spec.items() if k != "domains"},
             "domains": list(spec["domains"])} for key, spec in PRODUCTS.items()]


def _active(field: Field, options: dict[str, Any]) -> bool:
    return all(options.get(k) in values for k, values in field.get("when", {}).items())


def credential_fields(product: str) -> set[str]:
    return {f["key"] for f in PRODUCTS[product]["fields"] if f["credential"]}


def prepare(product: str, options: dict[str, Any], credentials: dict[str, str], stored: list[str]) -> dict[str, Any]:
    """Validate a product configuration. Returns options with derived values (such as base_url) filled in."""
    spec = PRODUCTS[product]
    options = {k: v for k, v in options.items() if v not in ("", None)}
    if set(options) - PRODUCT_OPTIONS:
        raise ValueError("unknown connector options")
    if product == "snowflake":
        account = str(options.get("account", "")).strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,120}", account):
            raise SourceError("Enter the account identifier, for example myorg-myaccount.")
        options["account"], options["base_url"] = account, f"https://{account}.snowflakecomputing.com"
    for field in spec["fields"]:
        if not field["required"] or not _active(field, options):
            continue
        key = field["key"]
        present = key in credentials or key in stored if field["credential"] else options.get(key)
        if not present:
            raise SourceError(f"Enter the {field['label'].lower()}.")
    unknown = set(credentials) - credential_fields(product)
    if unknown or any(not isinstance(v, str) or len(v) > 8192 for v in credentials.values()):
        raise ValueError("unknown or invalid credential fields")
    options["base_url"] = checked_url(str(options.get("base_url", "")), spec["domains"])
    if product in {"snowflake", "databricks"}:
        for key in ("warehouse", "database", "schema", "role", "catalog"):
            if options.get(key):
                _ident(options[key], key.capitalize())
        if product == "databricks" and not re.fullmatch(r"[A-Za-z0-9]{6,64}", str(options["warehouse_id"])):
            raise SourceError("Enter the SQL warehouse ID shown in the warehouse's connection details.")
    if product == "rest_api":
        from .connectors import _path
        options["events_path"] = _path(str(options["events_path"]))
        if options.get("auth_type") not in {"none", "bearer", "api_key", "basic"}:
            raise SourceError("Choose a sign-in method.")
        if options["auth_type"] == "api_key" and not re.fullmatch(r"[A-Za-z0-9-]{1,64}", str(options.get("api_key_header", ""))):
            raise SourceError("Enter a valid header name, for example X-API-Key.")
    if "history_days" in options:
        try:
            options["history_days"] = max(1, min(int(options["history_days"]), 3650))
        except (TypeError, ValueError):
            raise SourceError("Days of history must be a whole number.")
    if "resources" in options and (not isinstance(options["resources"], list) or len(options["resources"]) > 200):
        raise SourceError("Choose up to 200 tags.")
    return options


# --------------------------------------------------------------------------- mapping suggestions

SYNONYMS: dict[str, tuple[str, ...]] = {
    "order_id": ("order", "order_number", "process_order", "work_order"),
    "batch_id": ("batch", "batch_number", "batch_no", "lot", "lot_number", "lot_id"),
    "equipment_id": ("equipment", "equipment_number", "asset", "asset_id", "unit"),
    "product": ("product_name", "material", "material_name"),
    "sample_id": ("sample", "sample_number", "sample_no"),
    "test": ("test_name", "analysis", "method", "parameter"),
    "value": ("result", "result_value", "numeric_value", "reading", "measurement"),
    "unit": ("units", "uom", "unit_of_measure", "units_abbreviation"),
    "case_id": ("name", "record_number", "document_number", "number"),
    "record_type": ("object", "object_type", "type", "category"),
    "status": ("state", "lifecycle_state", "record_status"),
    "description": ("details", "summary", "short_description", "title"),
    "owner": ("assigned_to", "owner_id", "responsible", "created_by"),
    "lot_number": ("lot", "lot_id", "batch", "batch_number"),
    "material_code": ("material", "material_number", "item", "sku"),
    "expiry": ("expiry_date", "expiration", "expiration_date", "best_before"),
    "qty": ("quantity", "amount"),
    "uom": ("unit", "units", "unit_of_measure"),
    "tag": ("tag_name", "point", "signal"),
    "quality": ("status", "good"),
    "experiment_id": ("id", "entry_id", "registry_id", "entity_registry_id"),
    "title": ("name", "display_name"),
    "work_order": ("order", "work_order_number", "wo"),
    "location": ("bin", "storage_location", "warehouse_location"),
    "elapsed_h": ("elapsed_hours", "hours", "process_time_h", "age_h"),
}


def _normal(name: str) -> str:
    base = re.sub(r"__(v|c|sys|qdm|rim)$", "", name.lower())
    return re.sub(r"[^a-z0-9]", "", base)


def suggest_mapping(template: dict[str, Any], source_fields: list[str]) -> dict[str, Any]:
    """Match canonical fields to source fields by name; unmatched fields stay empty ("not in this source")."""
    normalized = {_normal(f): f for f in source_fields}
    fields = []
    for field in template["fields"]:
        canonical = field["canonical"]
        choice = next((normalized[_normal(c)] for c in (canonical, *SYNONYMS.get(canonical, ()))
                       if _normal(c) in normalized), "")
        fields.append({**field, "source": choice})
    return {**template, "fields": fields}


_BENCHLING_METADATA = ("id", "createdAt", "modifiedAt", "entityRegistryId", "registryId", "folderId", "schema",
                       "creator", "webURL", "apiURL", "archiveRecord", "aliases", "authors", "customFields",
                       "registrationOrigin", "projectId", "isReviewed", "validationStatus", "validationComment")


def envelope(product: str, options: dict[str, Any]) -> list[str]:
    """Record identity and bookkeeping fields: retained with the evidence, but not data awaiting a mapping."""
    if product == "veeva_vault":
        return ["id", "modified_date__v"]
    if product == "pi_web_api":
        return ["web_id", "timestamp"]
    if product in {"snowflake", "databricks"}:
        return [str(options[k]) for k in ("id_column", "updated_column") if options.get(k)]
    if product == "benchling":
        return list(_BENCHLING_METADATA)
    return [str(options.get("id_field", "id")), str(options.get("timestamp_field", "timestamp"))]


def mapped_sources(config: dict[str, Any]) -> list[str]:
    return [f["source"] for f in (config.get("mapping") or {}).get("fields", []) if f.get("source")]


# --------------------------------------------------------------------------- adapters


class ProductSource:
    def __init__(self, config: dict[str, Any], credentials: dict[str, str]) -> None:
        self.config, self.options, self.creds = config, config["options"], credentials
        self.connector_id = config["connector_id"]
        self.source_system = f"{config['family']}@{config['connector_id']}"
        self.site_id = config["site_id"]
        self.base_url = checked_url(self.options["base_url"], PRODUCTS[config["transport"]]["domains"])

    def discover(self, search: str | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    def fields(self, resource: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        raise NotImplementedError

    def resource(self) -> str:
        value = self.options.get("resource")
        if not value:
            raise SourceError("Choose what to collect before testing this connection.")
        return str(value)

    def record(self, payload: dict[str, Any], rid: Any, moment: Any) -> SourceRecord:
        if rid in (None, ""):
            raise SourceError("A record is missing its ID; choose a different ID column.")
        if moment in (None, ""):
            raise SourceError(f"Record {rid} has no timestamp.")
        return SourceRecord(str(rid), self.source_system, parse_time(moment), payload, self.site_id)

    def close(self) -> None:
        pass


def _matches(search: str | None, *values: Any) -> bool:
    return not search or any(search.lower() in str(v or "").lower() for v in values)


class VeevaVaultSource(ProductSource):
    def __init__(self, config: dict[str, Any], credentials: dict[str, str]) -> None:
        super().__init__(config, credentials)
        self.version = self.options.get("api_version", "v24.1")
        if not re.fullmatch(r"v\d{2}\.\d", self.version):
            raise SourceError("Invalid Vault API version.")
        self._session: str | None = None

    def _auth(self) -> dict[str, str]:
        if self._session is None:
            body = urlencode({"username": self.creds.get("username", ""), "password": self.creds.get("password", "")}).encode()
            _, doc = http_json("POST", f"{self.base_url}/api/{self.version}/auth", body=body,
                               headers={"Content-Type": "application/x-www-form-urlencoded"})
            if doc.get("responseStatus") != "SUCCESS" or not doc.get("sessionId"):
                raise SourceError("Vault rejected the sign-in. " + _vault_error(doc))
            self._session = doc["sessionId"]
        return {"Authorization": self._session}

    def _get(self, path: str) -> dict[str, Any]:
        _, doc = http_json("GET", f"{self.base_url}{path}", headers=self._auth())
        if doc.get("responseStatus") not in ("SUCCESS", None):
            raise SourceError("Vault returned an error. " + _vault_error(doc))
        return doc

    def discover(self, search: str | None = None) -> list[dict[str, Any]]:
        doc = self._get(f"/api/{self.version}/metadata/vobjects")
        items = [{"id": o["name"], "label": o.get("label") or o["name"], "detail": o["name"]}
                 for o in doc.get("objects", []) if o.get("status", "active") == "active"
                 and _matches(search, o.get("name"), o.get("label"))]
        return sorted(items, key=lambda i: i["label"].lower())[:500]

    def fields(self, resource: str) -> list[dict[str, Any]]:
        obj = _ident(resource, "Vault object")
        doc = self._get(f"/api/{self.version}/metadata/vobjects/{obj}")
        return [{"name": f["name"], "label": f.get("label") or f["name"], "type": f.get("type", "")}
                for f in doc.get("object", {}).get("fields", [])] + [{"name": "object", "label": "Vault object", "type": "String"}]

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        obj = _ident(self.resource(), "Vault object")
        state = json.loads(checkpoint) if checkpoint else {"since": "1970-01-01T00:00:00.000Z", "max": None, "next": None}
        if state.get("next"):
            if not str(state["next"]).startswith("/api/"):
                raise SourceError("Vault returned an unexpected next-page link.")
            doc = self._get(state["next"])
        else:
            # Read only the mapped fields: unmapped data would otherwise wait for review indefinitely.
            names = [n for n in mapped_sources(self.config) if n != "object" and _IDENT.fullmatch(n)]
            columns = list(dict.fromkeys(["id", "modified_date__v", *names]))[:60]
            since = state["since"].replace("'", "")
            query = (f"SELECT {', '.join(columns)} FROM {obj} WHERE modified_date__v >= '{since}' "
                     f"ORDER BY modified_date__v ASC PAGESIZE {max(1, min(limit, 1000))}")
            _, doc = http_json("POST", f"{self.base_url}/api/{self.version}/query", body=urlencode({"q": query}).encode(),
                               headers={**self._auth(), "Content-Type": "application/x-www-form-urlencoded"})
            if doc.get("responseStatus") != "SUCCESS":
                raise SourceError("Vault could not run the query. " + _vault_error(doc))
        records, latest = [], state.get("max")
        for row in doc.get("data", []):
            payload = {**row, "object": obj}
            records.append(self.record(payload, row.get("id"), row.get("modified_date__v")))
            if row.get("modified_date__v") and (latest is None or row["modified_date__v"] > latest):
                latest = row["modified_date__v"]
        following = doc.get("responseDetails", {}).get("next_page")
        if following:
            return PullBatch(tuple(records), json.dumps({**state, "max": latest, "next": following}), True)
        return PullBatch(tuple(records), json.dumps({"since": latest or state["since"], "max": None, "next": None}), False)


def _vault_error(doc: dict[str, Any]) -> str:
    errors = doc.get("errors") or []
    return str(errors[0].get("message", "")) if errors and isinstance(errors[0], dict) else ""


class PiWebApiSource(ProductSource):
    def _headers(self) -> dict[str, str]:
        return {"Authorization": _basic(self.creds.get("username", ""), self.creds.get("password", ""))}

    def _get(self, path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}" + (f"?{urlencode(query)}" if query else "")
        _, doc = http_json("GET", url, headers=self._headers())
        return doc

    def discover(self, search: str | None = None) -> list[dict[str, Any]]:
        out = []
        for server in self._get("/dataservers").get("Items", [])[:5]:
            points = self._get(f"/dataservers/{quote(server['WebId'], safe='')}/points",
                               {"nameFilter": f"*{search}*" if search else "*", "maxCount": 200})
            for p in points.get("Items", []):
                detail = " · ".join(x for x in (server.get("Name"), p.get("Descriptor"), p.get("EngineeringUnits")) if x)
                out.append({"id": p["WebId"], "label": p["Name"], "detail": detail})
        return out

    def fields(self, resource: str) -> list[dict[str, Any]]:
        return [{"name": n, "label": n, "type": "String"} for n in ("tag", "value", "unit", "quality", "timestamp")]

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        tags = list(self.options.get("resources") or [])
        labels = list(self.options.get("resource_labels") or tags)
        if not tags:
            raise SourceError("Choose at least one PI tag before testing this connection.")
        state: dict[str, str] = json.loads(checkpoint) if checkpoint else {}
        per = max(1, limit // len(tags))
        records, more = [], False
        for web_id, label in zip(tags, labels):
            start = state.get(web_id) or f"*-{int(self.options.get('history_days', 7))}d"
            doc = self._get(f"/streams/{quote(web_id, safe='')}/recorded",
                            {"startTime": start, "endTime": "*", "maxCount": per})
            items = doc.get("Items", [])
            for item in items:
                value = item.get("Value")
                if isinstance(value, dict):
                    value = value.get("Name", value.get("Value"))
                quality = "good" if item.get("Good", True) else "questionable" if item.get("Questionable") else "bad"
                ts = item["Timestamp"]
                records.append(self.record({"tag": label, "web_id": web_id, "timestamp": ts, "value": value,
                                            "unit": item.get("UnitsAbbreviation") or None, "quality": quality},
                                           f"{label}@{ts}", ts))
            if items:
                if len(items) >= per and items[-1]["Timestamp"] == start:
                    raise SourceError(f"{label} has more values at one timestamp than can be read at once.")
                state[web_id] = items[-1]["Timestamp"]
                more = more or len(items) >= per
        return PullBatch(tuple(records), json.dumps(state), more)


def _q(name: str, quote_char: str = '"') -> str:
    _name(name, "name")
    return quote_char + name + quote_char


class _WarehouseSource(ProductSource):
    """Shared incremental read: rows ordered by (updated time, id), resumed strictly after the last pair."""

    def sql(self, statement: str, params: list[str]) -> tuple[list[str], list[list[Any]]]:
        raise NotImplementedError

    def table(self) -> str:
        raise NotImplementedError

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        table = self.table()
        if not self.options.get("id_column") or not self.options.get("updated_column"):
            raise SourceError("Choose the ID column and the 'last updated' column for this table.")
        id_col = _name(self.options["id_column"], "ID column")
        ts_col = _name(self.options["updated_column"], "updated column")
        selected = list(dict.fromkeys([id_col, ts_col, *(_name(s, "column") for s in mapped_sources(self.config))]))
        statement, params = self.incremental(table, selected, id_col, ts_col,
                                             json.loads(checkpoint) if checkpoint else None, max(1, min(limit, 1000)))
        columns, rows = self.sql(statement, params)
        records, last = [], None
        for row in rows:
            data = dict(zip(columns, row))
            ts, rid = data.pop("__sievance_ts", None), data.pop("__sievance_id", None)
            records.append(self.record(data, rid, ts))
            last = {"ts": ts, "id": rid}
        return PullBatch(tuple(records), json.dumps(last) if last else checkpoint, len(rows) >= limit)

    def incremental(self, table: str, columns: list[str], id_col: str, ts_col: str, after: dict[str, str] | None,
                    limit: int) -> tuple[str, list[str]]:
        raise NotImplementedError


class SnowflakeSource(_WarehouseSource):
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.creds.get('token', '')}", "Content-Type": "application/json",
                "X-Snowflake-Authorization-Token-Type": "PROGRAMMATIC_ACCESS_TOKEN"}

    def sql(self, statement: str, params: list[str]) -> tuple[list[str], list[list[Any]]]:
        body = {"statement": statement, "timeout": 60, "warehouse": self.options["warehouse"],
                "database": self.options["database"], "schema": self.options["schema"],
                "parameters": {"timezone": "UTC"},
                "bindings": {str(i + 1): {"type": "TEXT", "value": v} for i, v in enumerate(params)}}
        if self.options.get("role"):
            body["role"] = self.options["role"]
        status, doc = http_json("POST", f"{self.base_url}/api/v2/statements", headers=self._headers(),
                                body=json.dumps(body).encode(), timeout=70)
        deadline = time.monotonic() + 60
        while status == 202 and time.monotonic() < deadline:
            time.sleep(1)
            status, doc = http_json("GET", f"{self.base_url}/api/v2/statements/{quote(doc['statementHandle'])}",
                                    headers=self._headers())
        if status == 202:
            raise SourceError("Snowflake is still running the query. Try a smaller table or a larger warehouse.")
        meta = doc.get("resultSetMetaData", {})
        columns = [c["name"] for c in meta.get("rowType", [])]
        rows = list(doc.get("data", []))
        for part in range(1, len(meta.get("partitionInfo", []))):
            _, page = http_json("GET", f"{self.base_url}/api/v2/statements/{quote(doc['statementHandle'])}?partition={part}",
                                headers=self._headers())
            rows += page.get("data", [])
        return columns, rows

    def _scope(self) -> str:
        return f"{_ident(self.options['database'], 'Database')}.{_ident(self.options['schema'], 'Schema')}"

    def table(self) -> str:
        return f"{self._scope()}.{_q(self.resource())}"

    def discover(self, search: str | None = None) -> list[dict[str, Any]]:
        db = _ident(self.options["database"], "Database")
        _, rows = self.sql(f"SELECT TABLE_NAME, TABLE_TYPE, ROW_COUNT FROM {db}.INFORMATION_SCHEMA.TABLES "
                           "WHERE UPPER(TABLE_SCHEMA) = UPPER(?) ORDER BY TABLE_NAME LIMIT 500", [self.options["schema"]])
        return [{"id": r[0], "label": r[0], "detail": f"{str(r[1]).title()}{f' · {int(r[2]):,} rows' if r[2] else ''}"}
                for r in rows if _matches(search, r[0])]

    def fields(self, resource: str) -> list[dict[str, Any]]:
        db = _ident(self.options["database"], "Database")
        _, rows = self.sql(f"SELECT COLUMN_NAME, DATA_TYPE FROM {db}.INFORMATION_SCHEMA.COLUMNS WHERE "
                           "UPPER(TABLE_SCHEMA) = UPPER(?) AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
                           [self.options["schema"], _name(resource, "table")])
        return [{"name": r[0], "label": r[0], "type": r[1]} for r in rows]

    def incremental(self, table, columns, id_col, ts_col, after, limit):
        ts, rid = f"{_q(ts_col)}::TIMESTAMP_TZ", f"TO_VARCHAR({_q(id_col)})"
        sql = (f"SELECT {', '.join(_q(c) for c in columns)}, TO_VARCHAR({ts}, 'YYYY-MM-DD HH24:MI:SS.FF6TZH:TZM') AS \"__sievance_ts\", "
               f"{rid} AS \"__sievance_id\" FROM {table} WHERE {_q(ts_col)} IS NOT NULL")
        params: list[str] = []
        if after:
            sql += f" AND ({ts} > ?::TIMESTAMP_TZ OR ({ts} = ?::TIMESTAMP_TZ AND {rid} > ?))"
            params = [after["ts"], after["ts"], str(after["id"])]
        return sql + f" ORDER BY {ts}, {rid} LIMIT {limit}", params


class DatabricksSource(_WarehouseSource):
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.creds.get('token', '')}", "Content-Type": "application/json"}

    def sql(self, statement: str, params: list[str]) -> tuple[list[str], list[list[Any]]]:
        body = {"warehouse_id": self.options["warehouse_id"], "statement": statement, "wait_timeout": "30s",
                "on_wait_timeout": "CONTINUE", "format": "JSON_ARRAY", "disposition": "INLINE",
                "catalog": self.options["catalog"], "schema": self.options["schema"],
                "parameters": [{"name": f"p{i}", "value": v, "type": "STRING"} for i, v in enumerate(params)]}
        _, doc = http_json("POST", f"{self.base_url}/api/2.0/sql/statements", headers=self._headers(),
                           body=json.dumps(body).encode(), timeout=45)
        deadline = time.monotonic() + 60
        while doc.get("status", {}).get("state") in ("PENDING", "RUNNING") and time.monotonic() < deadline:
            time.sleep(2)
            _, doc = http_json("GET", f"{self.base_url}/api/2.0/sql/statements/{quote(doc['statement_id'])}",
                               headers=self._headers())
        state = doc.get("status", {}).get("state")
        if state != "SUCCEEDED":
            reason = doc.get("status", {}).get("error", {}).get("message", "")
            raise SourceError(("The SQL warehouse is still starting or running the query. Try again in a minute."
                               if state in ("PENDING", "RUNNING") else f"Databricks could not run the query. {reason}").strip())
        columns = [c["name"] for c in doc.get("manifest", {}).get("schema", {}).get("columns", [])]
        result = doc.get("result", {}) or {}
        rows = list(result.get("data_array") or [])
        link = result.get("next_chunk_internal_link")
        while link:
            if not str(link).startswith("/api/2.0/sql/statements/"):
                raise SourceError("Databricks returned an unexpected result link.")
            _, chunk = http_json("GET", f"{self.base_url}{link}", headers=self._headers())
            rows += chunk.get("data_array") or []
            link = chunk.get("next_chunk_internal_link")
        return columns, rows

    def _scope(self) -> str:
        return f"{_q(_ident(self.options['catalog'], 'Catalog'), '`')}.{_q(_ident(self.options['schema'], 'Schema'), '`')}"

    def table(self) -> str:
        return f"{self._scope()}.{_q(self.resource(), '`')}"

    def discover(self, search: str | None = None) -> list[dict[str, Any]]:
        catalog_name = _q(_ident(self.options["catalog"], "Catalog"), "`")
        _, rows = self.sql(f"SELECT table_name, table_type FROM {catalog_name}.information_schema.tables "
                           "WHERE table_schema = :p0 ORDER BY table_name LIMIT 500", [self.options["schema"]])
        return [{"id": r[0], "label": r[0], "detail": str(r[1]).replace("_", " ").title()}
                for r in rows if _matches(search, r[0])]

    def fields(self, resource: str) -> list[dict[str, Any]]:
        catalog_name = _q(_ident(self.options["catalog"], "Catalog"), "`")
        _, rows = self.sql(f"SELECT column_name, data_type FROM {catalog_name}.information_schema.columns "
                           "WHERE table_schema = :p0 AND table_name = :p1 ORDER BY ordinal_position",
                           [self.options["schema"], _name(resource, "table")])
        return [{"name": r[0], "label": r[0], "type": r[1]} for r in rows]

    def incremental(self, table, columns, id_col, ts_col, after, limit):
        ts, rid = _q(ts_col, "`"), f"CAST({_q(id_col, '`')} AS STRING)"
        sql = (f"SELECT {', '.join(_q(c, '`') for c in columns)}, date_format({ts}, 'yyyy-MM-dd HH:mm:ss.SSSSSSXXX') AS __sievance_ts, "
               f"{rid} AS __sievance_id FROM {table} WHERE {ts} IS NOT NULL")
        params: list[str] = []
        if after:
            sql += f" AND ({ts} > CAST(:p0 AS TIMESTAMP) OR ({ts} = CAST(:p0 AS TIMESTAMP) AND {rid} > :p1))"
            params = [after["ts"], str(after["id"])]
        return sql + f" ORDER BY {ts}, {rid} LIMIT {limit}", params


class BenchlingSource(ProductSource):
    def _get(self, path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/api/v2{path}" + (f"?{urlencode(query)}" if query else "")
        _, doc = http_json("GET", url, headers={"Authorization": _basic(self.creds.get("api_key", ""), "")})
        return doc

    def discover(self, search: str | None = None) -> list[dict[str, Any]]:
        entities = self._get("/entity-schemas", {"pageSize": 100}).get("entitySchemas", [])
        results = self._get("/assay-result-schemas", {"pageSize": 100}).get("assayResultSchemas", [])
        items = [{"id": f"entity:{s['id']}", "label": s["name"], "detail": "Registry entities"} for s in entities] + \
                [{"id": f"result:{s['id']}", "label": s["name"], "detail": "Results"} for s in results]
        return [i for i in items if _matches(search, i["label"])]

    def _split(self, resource: str) -> tuple[str, str]:
        kind, _, schema = resource.partition(":")
        if kind not in ("entity", "result") or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", schema):
            raise SourceError("Choose a Benchling schema.")
        return kind, schema

    def fields(self, resource: str) -> list[dict[str, Any]]:
        kind, schema = self._split(resource)
        doc = self._get(f"/{'entity-schemas' if kind == 'entity' else 'assay-result-schemas'}/{schema}")
        base = ["id", "name", "createdAt", "modifiedAt"] if kind == "entity" else ["id", "createdAt"]
        return [{"name": n, "label": n, "type": "String"} for n in base] + \
               [{"name": f["name"], "label": f.get("displayName") or f["name"], "type": f.get("type", "")}
                for f in doc.get("fieldDefinitions", [])]

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        kind, schema = self._split(self.resource())
        state = json.loads(checkpoint) if checkpoint else {"since": None, "max": None, "next": None}
        query: dict[str, Any] = {"schemaId": schema, "pageSize": max(1, min(limit, 100))}
        if state.get("next"):
            query["nextToken"] = state["next"]
        if kind == "entity":
            query["sort"] = "modifiedAt:asc"
            if state.get("since"):
                query["modifiedAt"] = f">= {state['since']}"
            doc, key, stamp = self._get("/custom-entities", query), "customEntities", "modifiedAt"
        else:
            if state.get("since"):
                query["minCreatedTime"] = int(parse_time(state["since"]).timestamp())
            doc, key, stamp = self._get("/assay-results", query), "assayResults", "createdAt"
        records, latest = [], state.get("max")
        for item in doc.get(key, []):
            payload = {k: v for k, v in item.items() if k != "fields"}
            for name, field in (item.get("fields") or {}).items():
                payload[name] = field.get("value") if isinstance(field, dict) else field
            records.append(self.record(payload, item.get("id"), item.get(stamp)))
            if item.get(stamp) and (latest is None or parse_time(item[stamp]) > parse_time(latest)):
                latest = item[stamp]
        if doc.get("nextToken"):
            return PullBatch(tuple(records), json.dumps({**state, "max": latest, "next": doc["nextToken"]}), True)
        return PullBatch(tuple(records), json.dumps({"since": latest or state.get("since"), "max": None, "next": None}), False)


class GuidedRestSource(ProductSource):
    """The existing REST polling contract, with credentials from the workspace instead of server variables."""

    def __init__(self, config: dict[str, Any], credentials: dict[str, str]) -> None:
        super().__init__(config, credentials)
        from .connectors import RestSource
        self.rest = RestSource.__new__(RestSource)
        self.rest.config, self.rest.connector_id, self.rest.source_system = config, self.connector_id, self.source_system
        self.rest.options, self.rest.base_url, self.rest.opener = self.options, self.base_url, _OPENER
        self.rest.request = self.request

    def request(self, method: str, path: str, *, query: dict[str, Any] | None = None,
                payload: dict[str, Any] | None = None, write: bool = False) -> dict[str, Any]:
        from .connectors import _path
        if write:
            raise PermissionError("guided connections are read-only")
        headers = {"Content-Type": "application/json"}
        auth = self.options.get("auth_type", "none")
        if auth == "bearer":
            headers["Authorization"] = f"Bearer {self.creds.get('token', '')}"
        elif auth == "api_key":
            headers[self.options["api_key_header"]] = self.creds.get("api_key", "")
        elif auth == "basic":
            headers["Authorization"] = _basic(self.creds.get("username", ""), self.creds.get("password", ""))
        url = self.base_url + _path(path) + (f"?{urlencode(query)}" if query else "")
        _, doc = http_json(method, url, headers=headers)
        if not isinstance(doc, dict):
            raise SourceError("The API must return a JSON object containing a list of records.")
        return doc

    def discover(self, search: str | None = None) -> list[dict[str, Any]]:
        return []

    def fields(self, resource: str) -> list[dict[str, Any]]:
        batch = self.pull(None, 5)
        names = list(dict.fromkeys(k for r in batch.records for k in r.payload))
        return [{"name": n, "label": n, "type": ""} for n in names]

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        try:
            return self.rest.pull(checkpoint, limit)
        except ValueError as exc:
            if isinstance(exc, SourceError):
                raise
            raise SourceError(f"The API response could not be read: {exc}") from exc


ADAPTERS = {"veeva_vault": VeevaVaultSource, "pi_web_api": PiWebApiSource, "snowflake": SnowflakeSource,
            "databricks": DatabricksSource, "benchling": BenchlingSource, "rest_api": GuidedRestSource}


def build(config: dict[str, Any], credentials: dict[str, str]) -> ProductSource:
    return ADAPTERS[config["transport"]](config, credentials)
