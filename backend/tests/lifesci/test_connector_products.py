import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from src.lifesci import connector_products as products
from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.store import RecordStore

SECRET = "correct horse battery staple"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("LIFESCI_CONNECTOR_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("LIFESCI_CONNECTOR_KEY", base64.b64encode(b"k" * 32).decode())
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role("T", "admin", "admin", site_id="S1")
    p.identity.assign_role("T", "op", "operator", site_id="S1")
    c = TestClient(create_app(p))
    yield p, c, lambda actor="admin": {"X-Tenant-Id": "T", "X-Actor-Id": actor}
    p.connectors.close()


ROUTES = {}


@pytest.fixture
def server():
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _reply(self, method):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            parts = urlsplit(self.path)
            seen.append({"method": method, "path": parts.path, "query": parse_qs(parts.query),
                         "auth": self.headers.get("Authorization"),
                         "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
            handler = ROUTES.get((method, parts.path))
            status, doc = handler(seen[-1]) if handler else (404, {"message": "no route"})
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(doc).encode())

        def do_GET(self):
            self._reply("GET")

        def do_POST(self):
            self._reply("POST")

    s = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=s.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{s.server_port}", seen
    ROUTES.clear()
    s.shutdown(); s.server_close(); thread.join()


def connect(c, h, product, family, options, credentials=None, cid=None, **extra):
    body = {"connector_id": cid or f"{product.replace('_', '-')}-1", "family": family, "transport": product,
            "site_id": "S1", "owner": "admin", "options": options, **extra}
    if credentials is not None:
        body["credentials"] = credentials
    return c.post("/v1/connectors", headers=h(), json=body)


def test_credentials_are_sealed_and_never_returned(env, server):
    p, c, h = env
    url, _ = server
    r = connect(c, h, "veeva_vault", "QMS", {"base_url": url}, {"username": "svc", "password": SECRET})
    assert r.status_code == 201, r.text
    assert SECRET not in r.text and "credentials" not in r.json()
    listed = c.get("/v1/connectors", headers=h()).json()["items"][0]
    assert listed["credential_fields"] == ["password", "username"] and SECRET not in json.dumps(listed)
    raw = p.store.read().get("T", products.CREDENTIAL_KIND, "veeva-vault-1")
    assert SECRET not in json.dumps(raw.state)
    assert c.get(f"/v1/records/{products.CREDENTIAL_KIND}", headers=h()).status_code == 404
    assert c.get(f"/v1/records/{products.CREDENTIAL_KIND}/veeva-vault-1", headers=h()).status_code == 404
    assert p.connectors.credentials.load("T", "veeva-vault-1")["password"] == SECRET
    # Saving again without credentials keeps the stored ones; a missing password on a new connection is refused.
    assert connect(c, h, "veeva_vault", "QMS", {"base_url": url, "resource": "x__c"}).status_code == 201
    assert p.connectors.credentials.load("T", "veeva-vault-1")["password"] == SECRET
    missing = connect(c, h, "veeva_vault", "QMS", {"base_url": url}, {"username": "svc"}, cid="other")
    assert missing.status_code == 400 and "password" in missing.json()["detail"]
    # Ciphertext is bound to its connection.
    with pytest.raises(products.SourceError):
        products.CredentialStore._open("T", "another-connection", raw.state)
    assert connect(c, h, "veeva_vault", "QMS", {"base_url": url}, {"token": "x"}, cid="bad").status_code == 400


def test_operator_cannot_configure_guided_connections(env, server):
    _, c, h = env
    url, _ = server
    body = {"connector_id": "v", "family": "QMS", "transport": "veeva_vault", "site_id": "S1", "owner": "op",
            "options": {"base_url": url}, "credentials": {"username": "a", "password": "b"}}
    assert c.post("/v1/connectors", headers=h("op"), json=body).status_code == 403


def test_veeva_discovery_mapping_preview_and_incremental_sync(env, server):
    p, c, h = env
    url, seen = server
    rows = [{"id": "V1", "name__v": "DEV-001", "status__v": ["open__c"], "modified_date__v": "2026-10-01T10:00:00.000Z"},
            {"id": "V2", "name__v": "DEV-002", "status__v": ["closed__c"], "modified_date__v": "2026-10-02T10:00:00.000Z"}]
    ROUTES[("POST", "/api/v24.1/auth")] = lambda r: (200, {"responseStatus": "SUCCESS", "sessionId": "S-123"}
        if b"password=" + SECRET.replace(" ", "+").encode() in r["body"] else {"responseStatus": "FAILURE",
        "errors": [{"type": "USERNAME_OR_PASSWORD_INCORRECT", "message": "Authentication failed"}]})
    ROUTES[("GET", "/api/v24.1/metadata/vobjects")] = lambda r: (200, {"responseStatus": "SUCCESS", "objects": [
        {"name": "deviation__qdm", "label": "Deviation", "status": "active"},
        {"name": "old__c", "label": "Old", "status": "inactive"}]})
    ROUTES[("GET", "/api/v24.1/metadata/vobjects/deviation__qdm")] = lambda r: (200, {"responseStatus": "SUCCESS",
        "object": {"fields": [{"name": n, "type": t} for n, t in [("id", "ID"), ("name__v", "String"),
            ("status__v", "Picklist"), ("modified_date__v", "DateTime"), ("attachments", "Component")]]}})
    ROUTES[("POST", "/api/v24.1/query")] = lambda r: (200, {"responseStatus": "SUCCESS", "responseDetails": {
        "next_page": "/api/v24.1/query/page2"}, "data": rows[:1]})
    ROUTES[("GET", "/api/v24.1/query/page2")] = lambda r: (200, {"responseStatus": "SUCCESS", "responseDetails": {},
        "data": rows[1:]})

    bad = connect(c, h, "veeva_vault", "QMS", {"base_url": url}, {"username": "svc", "password": "wrong"})
    assert bad.status_code == 201
    failed = c.post("/v1/connectors/veeva-vault-1/discover", headers=h(), json={})
    assert failed.status_code == 400 and "Authentication failed" in failed.json()["detail"]

    connect(c, h, "veeva_vault", "QMS", {"base_url": url}, {"password": SECRET})
    found = c.post("/v1/connectors/veeva-vault-1/discover", headers=h(), json={}).json()
    assert found["resources"] == [{"id": "deviation__qdm", "label": "Deviation", "detail": "deviation__qdm"}]
    fields = c.post("/v1/connectors/veeva-vault-1/discover", headers=h(), json={"resource": "deviation__qdm"}).json()
    mapping = {f["canonical"]: f["source"] for f in fields["suggested_mapping"]["fields"]}
    assert mapping["case_id"] == "name__v" and mapping["status"] == "status__v" and mapping["record_type"] == "object"

    configured = connect(c, h, "veeva_vault", "QMS", {"base_url": url, "resource": "deviation__qdm"},
                         mapping=fields["suggested_mapping"], mapping_confirmed=True)
    assert configured.status_code == 201, configured.text
    preview = c.post("/v1/connectors/veeva-vault-1/preview", headers=h()).json()
    assert preview["ok"] and preview["preview"]["rows"][0]["fields"]["case_id"] == "DEV-001"
    query = [s for s in seen if s["path"] == "/api/v24.1/query"][-1]
    assert query["auth"] == "S-123"
    q = parse_qs(query["body"].decode())["q"][0]
    assert "FROM deviation__qdm" in q and "attachments" not in q and "ORDER BY modified_date__v ASC" in q

    assert q.startswith("SELECT id, modified_date__v, name__v, status__v ")
    first = c.post("/v1/connectors/veeva-vault-1/sync", headers=h()).json()
    assert first["ingested"] == 2
    # Identity and timestamp fields are envelope, so fully mapped records are not held for unmapped data.
    assert "UNMAPPED_FIELD" not in c.get("/v1/connectors/veeva-vault-1/verification", headers=h()).text
    second = c.post("/v1/connectors/veeva-vault-1/sync", headers=h()).json()
    q = parse_qs([s for s in seen if s["path"] == "/api/v24.1/query"][-1]["body"].decode())["q"][0]
    assert ">= '2026-10-02T10:00:00.000Z'" in q and second["ingested"] == 0 and second["duplicates"] >= 1


def test_pi_web_api_tags_read_recorded_values(env, server):
    _, c, h = env
    url, seen = server
    ROUTES[("GET", "/piwebapi/dataservers")] = lambda r: (200, {"Items": [{"WebId": "DS1", "Name": "PI-PLANT"}]})
    ROUTES[("GET", "/piwebapi/dataservers/DS1/points")] = lambda r: (200, {"Items": [
        {"WebId": "P1", "Name": "BR01.PH", "Descriptor": "Bioreactor pH", "EngineeringUnits": "pH"}]})
    ROUTES[("GET", "/piwebapi/streams/P1/recorded")] = lambda r: (200, {"Items": [
        {"Timestamp": "2026-10-01T00:00:00.1234567Z", "Value": 7.01, "UnitsAbbreviation": "pH", "Good": True},
        {"Timestamp": "2026-10-01T00:01:00Z", "Value": {"Name": "Bad Input", "Value": 307}, "Good": False}]})
    opts = {"base_url": f"{url}/piwebapi", "history_days": "3"}
    assert connect(c, h, "pi_web_api", "HISTORIAN", opts, {"username": "DOM\\svc", "password": SECRET}).status_code == 201
    found = c.post("/v1/connectors/pi-web-api-1/discover", headers=h(), json={"search": "PH"}).json()["resources"]
    assert found[0]["id"] == "P1" and "Bioreactor pH" in found[0]["detail"]
    assert [s for s in seen if s["path"].endswith("/points")][-1]["query"]["nameFilter"] == ["*PH*"]
    assert connect(c, h, "pi_web_api", "HISTORIAN", {**opts, "resources": ["P1"], "resource_labels": ["BR01.PH"]},
                   mapping_confirmed=True).status_code == 201
    preview = c.post("/v1/connectors/pi-web-api-1/preview", headers=h()).json()
    assert preview["ok"], preview
    rows = preview["preview"]["rows"]
    assert rows[0]["fields"]["tag"] == "BR01.PH" and rows[1]["fields"]["quality"] == "bad"
    assert rows[1]["fields"]["value"] == "Bad Input"
    recorded = [s for s in seen if s["path"].endswith("/recorded")][-1]
    assert recorded["query"]["startTime"] == ["*-3d"]
    assert recorded["auth"] == "Basic " + base64.b64encode(f"DOM\\svc:{SECRET}".encode()).decode()
    c.post("/v1/connectors/pi-web-api-1/sync", headers=h())
    c.post("/v1/connectors/pi-web-api-1/sync", headers=h())
    assert [s for s in seen if s["path"].endswith("/recorded")][-1]["query"]["startTime"] == ["2026-10-01T00:01:00Z"]


def test_snowflake_reads_tables_incrementally_with_bindings(env, server, monkeypatch):
    _, c, h = env
    url, seen = server
    monkeypatch.setattr(products.SnowflakeSource, "__init__", lambda self, config, creds: (
        products.ProductSource.__init__(self, {**config, "options": {**config["options"], "base_url": url}}, creds)))

    def statements(r):
        body = json.loads(r["body"])
        sql = body["statement"]
        if "INFORMATION_SCHEMA.TABLES" in sql:
            return 200, {"resultSetMetaData": {"rowType": [{"name": "TABLE_NAME"}, {"name": "TABLE_TYPE"},
                         {"name": "ROW_COUNT"}]}, "data": [["BATCH_RESULTS", "BASE TABLE", "1200"]]}
        if "INFORMATION_SCHEMA.COLUMNS" in sql:
            return 200, {"resultSetMetaData": {"rowType": [{"name": "COLUMN_NAME"}, {"name": "DATA_TYPE"}]},
                         "data": [["LOT_ID", "TEXT"], ["RESULT", "NUMBER"], ["UPDATED_AT", "TIMESTAMP_NTZ"]]}
        return 202, {"statementHandle": "H1"}

    ROUTES[("POST", "/api/v2/statements")] = statements
    ROUTES[("GET", "/api/v2/statements/H1")] = lambda r: (200, {"statementHandle": "H1", "resultSetMetaData": {
        "rowType": [{"name": n} for n in ("LOT_ID", "RESULT", "UPDATED_AT", "__sievance_ts", "__sievance_id")]},
        "data": [["L-1", "4.2", "1759312800.000000000", "2026-10-01 10:00:00.000000+00:00", "L-1"]]})
    opts = {"account": "MyOrg-Acct", "warehouse": "WH", "database": "MFG", "schema": "PUBLIC"}
    created = connect(c, h, "snowflake", "LIMS", opts, {"token": SECRET})
    assert created.status_code == 201, created.text
    assert created.json()["options"]["base_url"] == "https://myorg-acct.snowflakecomputing.com"
    assert c.post("/v1/connectors/snowflake-1/discover", headers=h(), json={}).json()["resources"][0]["detail"] == "Base Table · 1,200 rows"
    fields = c.post("/v1/connectors/snowflake-1/discover", headers=h(), json={"resource": "BATCH_RESULTS"}).json()
    assert {f["name"] for f in fields["fields"]} == {"LOT_ID", "RESULT", "UPDATED_AT"}
    assert {f["canonical"]: f["source"] for f in fields["suggested_mapping"]["fields"]}["batch_id"] == "LOT_ID"
    missing = connect(c, h, "snowflake", "LIMS", {**opts, "resource": "BATCH_RESULTS"})
    assert missing.status_code == 201
    assert "ID column" in c.post("/v1/connectors/snowflake-1/preview", headers=h()).json()["error"]
    connect(c, h, "snowflake", "LIMS", {**opts, "resource": "BATCH_RESULTS", "id_column": "LOT_ID",
                                         "updated_column": "UPDATED_AT"})
    assert c.post("/v1/connectors/snowflake-1/sync", headers=h()).json()["ingested"] == 1
    c.post("/v1/connectors/snowflake-1/sync", headers=h())
    last = json.loads([s for s in seen if s["path"] == "/api/v2/statements"][-1]["body"])
    assert 'FROM MFG.PUBLIC."BATCH_RESULTS"' in last["statement"] and "LIMIT 100" in last["statement"]
    assert last["statement"].startswith('SELECT "LOT_ID", "UPDATED_AT", TO_VARCHAR(')
    assert last["bindings"]["3"] == {"type": "TEXT", "value": "L-1"} and last["parameters"] == {"timezone": "UTC"}
    sent = [s for s in seen if s["path"] == "/api/v2/statements"][-1]
    assert sent["auth"] == f"Bearer {SECRET}"
    assert sent["headers"]["x-snowflake-authorization-token-type"] == "PROGRAMMATIC_ACCESS_TOKEN"


def test_databricks_statement_api_and_parameters(env, server, monkeypatch):
    _, c, h = env
    url, seen = server
    ROUTES[("POST", "/api/2.0/sql/statements")] = lambda r: (200, {"statement_id": "s1", "status": {"state": "PENDING"}})
    ROUTES[("GET", "/api/2.0/sql/statements/s1")] = lambda r: (200, {"statement_id": "s1", "status": {"state": "SUCCEEDED"},
        "manifest": {"schema": {"columns": [{"name": n} for n in ("batch", "ph", "__sievance_ts", "__sievance_id")]}},
        "result": {"data_array": [["B1", "7.0", "2026-10-01 10:00:00.000000Z", "B1"]],
                   "next_chunk_internal_link": "/api/2.0/sql/statements/s1/result/chunks/1"}})
    ROUTES[("GET", "/api/2.0/sql/statements/s1/result/chunks/1")] = lambda r: (200, {"data_array": [
        ["B2", "7.1", "2026-10-01 11:00:00.000000Z", "B2"]]})
    monkeypatch.setattr(products.time, "sleep", lambda s: None)
    opts = {"base_url": url, "warehouse_id": "abc123def456", "catalog": "main", "schema": "mfg",
            "resource": "readings", "id_column": "batch", "updated_column": "updated_at"}
    assert connect(c, h, "databricks", "HISTORIAN", opts, {"token": SECRET}).status_code == 201
    assert c.post("/v1/connectors/databricks-1/sync", headers=h()).json()["ingested"] == 2
    c.post("/v1/connectors/databricks-1/sync", headers=h())
    body = json.loads([s for s in seen if s["path"] == "/api/2.0/sql/statements"][-1]["body"])
    assert "FROM `main`.`mfg`.`readings`" in body["statement"] and ":p1" in body["statement"]
    assert body["parameters"][1] == {"name": "p1", "value": "B2", "type": "STRING"}
    assert body["warehouse_id"] == "abc123def456"


def test_benchling_entities_flatten_fields(env, server):
    _, c, h = env
    url, seen = server
    ROUTES[("GET", "/api/v2/entity-schemas")] = lambda r: (200, {"entitySchemas": [{"id": "ts_1", "name": "Cell line"}]})
    ROUTES[("GET", "/api/v2/assay-result-schemas")] = lambda r: (200, {"assayResultSchemas": [{"id": "rs_1", "name": "Titer"}]})
    ROUTES[("GET", "/api/v2/custom-entities")] = lambda r: (200, {"customEntities": [
        {"id": "bfi_1", "name": "CHO-K1", "modifiedAt": "2026-10-01T10:00:00.000Z",
         "fields": {"Passage": {"value": 12, "displayValue": "12"}}}], "nextToken": ""})
    assert connect(c, h, "benchling", "ELN", {"base_url": url}, {"api_key": SECRET}).status_code == 201
    found = c.post("/v1/connectors/benchling-1/discover", headers=h(), json={}).json()["resources"]
    assert [i["id"] for i in found] == ["entity:ts_1", "result:rs_1"]
    connect(c, h, "benchling", "ELN", {"base_url": url, "resource": "entity:ts_1"})
    preview = c.post("/v1/connectors/benchling-1/preview", headers=h()).json()
    assert preview["records_sampled"] == 1
    assert "Passage" in preview["preview"]["rows"][0]["unmapped"]
    c.post("/v1/connectors/benchling-1/sync", headers=h())
    c.post("/v1/connectors/benchling-1/sync", headers=h())
    query = [s for s in seen if s["path"] == "/api/v2/custom-entities"][-1]["query"]
    assert query["modifiedAt"] == [">= 2026-10-01T10:00:00.000Z"] and query["sort"] == ["modifiedAt:asc"]
    assert [s for s in seen][-1]["auth"] == "Basic " + base64.b64encode(f"{SECRET}:".encode()).decode()


def test_guided_rest_uses_stored_api_key(env, server):
    _, c, h = env
    url, seen = server
    ROUTES[("GET", "/v1/records")] = lambda r: (200, {"items": [{"uid": "a", "at": "2026-10-01T00:00:00Z", "status": "ok"}]})
    opts = {"base_url": url, "events_path": "/v1/records", "auth_type": "api_key", "api_key_header": "X-API-Key",
            "records_field": "items", "id_field": "uid", "timestamp_field": "at"}
    assert connect(c, h, "rest_api", "MES", opts, {"api_key": SECRET}).status_code == 201
    fields = c.post("/v1/connectors/rest-api-1/discover", headers=h(), json={}).json()["fields"]
    assert {f["name"] for f in fields} == {"uid", "at", "status"}
    assert c.post("/v1/connectors/rest-api-1/preview", headers=h()).json()["ok"]
    assert seen[-1]["headers"]["x-api-key"] == SECRET
    no_auth = connect(c, h, "rest_api", "MES", {**opts, "auth_type": "bearer"}, cid="r2")
    assert no_auth.status_code == 400 and "token" in no_auth.json()["detail"]


def test_host_policy(monkeypatch):
    monkeypatch.delenv("LIFESCI_CONNECTOR_ALLOWED_HOSTS", raising=False)
    assert products.checked_url("https://acme.veevavault.com/", ("veevavault.com",)) == "https://acme.veevavault.com"
    for url, domains, text in [("https://acme.example.com", ("veevavault.com",), "veevavault.com"),
                               ("http://acme.veevavault.com", ("veevavault.com",), "https://"),
                               ("https://user:pw@acme.veevavault.com", ("veevavault.com",), "without"),
                               ("https://10.1.2.3/piwebapi", (), "private network"),
                               ("https://127.0.0.1/api", (), "private network"),
                               ("https://169.254.169.254/latest", (), "private network")]:
        with pytest.raises(products.SourceError, match=text):
            products.checked_url(url, domains)
    monkeypatch.setattr(products.socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("93.184.216.34", 443))])
    assert products.checked_url("https://pi.example.com/piwebapi") == "https://pi.example.com/piwebapi"
    monkeypatch.setenv("LIFESCI_CONNECTOR_PUBLIC_HOSTS", "0")
    with pytest.raises(products.SourceError, match="administrator"):
        products.checked_url("https://pi.example.com/piwebapi")


def test_production_requires_a_configured_key(monkeypatch):
    monkeypatch.delenv("LIFESCI_CONNECTOR_KEY", raising=False)
    monkeypatch.setenv("LIFESCI_AUTH_MODE", "supabase")
    with pytest.raises(products.SourceError, match="LIFESCI_CONNECTOR_KEY"):
        products._master_key()


def test_mapping_suggestions_strip_vendor_suffixes():
    template = {"fields": [{"source": "status", "canonical": "status"}, {"source": "owner", "canonical": "owner"},
                           {"source": "description", "canonical": "description"}]}
    out = products.suggest_mapping(template, ["status__v", "owner__v", "Short Description"])
    assert [f["source"] for f in out["fields"]] == ["status__v", "owner__v", "Short Description"]
    assert [f["source"] for f in products.suggest_mapping(template, ["unrelated"])["fields"]] == ["", "", ""]


def test_catalog_lists_products_without_secrets(env):
    _, c, h = env
    products_list = c.get("/v1/connectors/catalog", headers=h()).json()["products"]
    assert {p["product"] for p in products_list} == set(products.PRODUCTS)
    vault = next(p for p in products_list if p["product"] == "veeva_vault")
    assert next(f for f in vault["fields"] if f["key"] == "password")["secret"] is True
