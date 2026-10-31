import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from src.lifesci.api import create_app
from src.lifesci.connectors import FAMILIES
from src.lifesci.container import Platform
from src.lifesci.integrations import sign_payload
from src.lifesci.store import RecordStore


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("LIFESCI_CONNECTOR_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("LIFESCI_CONNECTOR_FILE_ROOT", str(tmp_path))
    monkeypatch.setenv("TEST_READ_TOKEN", "read-secret")
    monkeypatch.setenv("TEST_WRITE_TOKEN", "write-secret")
    monkeypatch.setenv("TEST_WEBHOOK_SECRET", "a signing secret for testing")
    p = Platform(RecordStore(), providers={})
    for actor, role, site in [("admin", "admin", "S1"), ("op", "operator", "S1"),
                              ("other", "admin", "S2"), ("sup", "supervisor", "S1"),
                              ("exec", "system_executor", "S1")]:
        p.identity.assign_role("T", actor, role, site_id=site)
    c = TestClient(create_app(p))
    h = lambda actor="admin": {"X-Tenant-Id": "T", "X-Actor-Id": actor}
    yield p, c, h, tmp_path
    p.connectors.close()


@pytest.fixture
def server():
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            requests.append((self.path, self.headers.get("Authorization")))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if self.path.startswith("/lookup"):
                self.wfile.write(json.dumps({"status": "delivered", "receipt": {"id": "ack"}}).encode())
            else:
                self.wfile.write(json.dumps({"records": [{"id": "r1", "timestamp": "2026-10-24T00:00:00Z",
                    "value": 7.1, "status": "ready"}], "next_checkpoint": "1", "has_more": False}).encode())
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, self.headers.get("Authorization"), body))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"id": "ack", "timestamp": "2026-10-24T00:00:00Z"}).encode())
    s = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=s.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{s.server_port}", requests
    s.shutdown(); s.server_close(); thread.join()


def config(family="MES", transport="rest", **options):
    return {"connector_id": f"test-{family.lower()}", "family": family, "transport": transport,
            "site_id": "S1", "owner": "admin", "options": options}


@pytest.mark.parametrize("family", FAMILIES)
def test_rest_families_preview_sync_duplicate_cursors_and_auth(env, server, family):
    p, c, h, _ = env
    url, requests = server
    cfg = config(family, base_url=url, events_path="/records", auth_env="TEST_READ_TOKEN")
    r = c.post("/v1/connectors", headers=h(), json=cfg)
    assert r.status_code == 201, r.text
    cid = r.json()["connector_id"]
    preview = c.post(f"/v1/connectors/{cid}/preview", headers=h()).json()
    assert preview["records_sampled"] == 1 and preview["wrote"] is False
    assert p.store.read().list("T", "evidence") == []
    first = c.post(f"/v1/connectors/{cid}/sync", headers=h())
    assert first.status_code == 200, first.text
    assert first.json()["ingested"] == 1
    assert c.post(f"/v1/connectors/{cid}/sync", headers=h()).json()["duplicates"] == 1
    assert requests[-1][0].endswith("checkpoint=1")
    assert requests[-1][1] == "Bearer read-secret"
    record = p.store.read().require("T", "evidence", f"{family}@{cid}:r1")
    assert c.get(f"/v1/records/evidence/{family}@{cid}:r1", headers=h("op")).status_code == 200
    assert record.state["source_revision"] is None and record.state["site_id"] == "S1"
    assert c.get("/v1/connectors", headers=h()).json()["items"][0]["qualification"] == "simulated"
    assert "read-secret" not in c.get("/v1/connectors", headers=h()).text
    assert c.get("/v1/connectors", headers=h("other")).json()["items"] == []
    assert c.post(f"/v1/connectors/{cid}/sync", headers=h("other")).status_code == 403
    assert c.post("/v1/connectors", headers=h("op"), json=cfg).status_code == 403


@pytest.mark.parametrize("suffix", ["json", "jsonl", "csv"])
def test_file_exports_and_source_corrections(env, suffix):
    p, c, h, root = env
    row = {"id": "sample1", "timestamp": "2026-10-24T00:00:00Z", "value": 4}
    path = root / f"records.{suffix}"
    def write():
        path.write_text(json.dumps([row]) if suffix == "json" else json.dumps(row) + "\n" if suffix == "jsonl"
                        else "id,timestamp,value\nsample1,2026-10-24T00:00:00Z," + str(row["value"]) + "\n")
    write()
    assert c.post("/v1/connectors", headers=h(), json=config("LIMS", "file", directory=str(root))).status_code == 201
    assert c.post("/v1/connectors/test-lims/sync", headers=h()).json()["ingested"] == 1
    row["value"] = 5; write()
    assert c.post("/v1/connectors/test-lims/sync", headers=h()).json()["corrections"] == 1
    assert p.store.read().require("T", "evidence", "LIMS@test-lims:sample1").revision == 2


def test_webhook_signed_intake_and_replay_protection(env):
    p, c, h, _ = env
    cfg = config("QMS", "webhook", secret_env="TEST_WEBHOOK_SECRET")
    assert c.post("/v1/connectors", headers=h(), json=cfg).status_code == 201
    body = json.dumps({"id": "case1", "timestamp": "2026-10-24T00:00:00Z", "status": "open"}).encode()
    ts = str(int(time.time()))
    headers = {"X-Timestamp": ts, "X-Delivery-Id": "delivery1",
               "X-Signature": sign_payload("a signing secret for testing", ts, body)}
    assert c.post("/v1/webhooks/T/test-qms", content=body, headers={}).status_code == 403
    assert c.post("/v1/webhooks/T/test-qms", content=body, headers=headers).status_code == 202
    assert c.post("/v1/webhooks/T/test-qms", content=body, headers=headers).status_code == 403
    assert c.post("/v1/connectors/test-qms/sync", headers=h()).json()["ingested"] == 1


def test_connector_scope_cannot_change_and_secrets_and_hosts_are_restricted(env, server):
    _, c, h, root = env
    url, _ = server
    cfg = config(base_url=url)
    assert c.post("/v1/connectors", headers=h(), json=cfg).status_code == 201
    assert c.post("/v1/connectors", headers=h(), json={**cfg, "site_id": "S2"}).status_code == 403
    assert c.post("/v1/connectors", headers=h(), json=config(base_url="https://unauthorized.example")).status_code == 403
    assert c.post("/v1/connectors", headers=h(), json=config(base_url=url, headers={"Authorization": "secret"})).status_code == 400
    assert c.post("/v1/connectors", headers=h(), json=config("LIMS", "file", directory=str(root.parent))).status_code == 403


def test_writeback_requires_approved_intent_matching_site_and_separate_credentials(env, server):
    from src.lifesci.ownership import Ownership
    p, c, h, _ = env
    url, requests = server
    cfg = {**config(base_url=url, auth_env="TEST_READ_TOKEN", write_auth_env="TEST_WRITE_TOKEN",
                    write_path="/actions", lookup_path="/lookup"), "write_operations": ["place_hold"]}
    assert c.post("/v1/connectors", headers=h(), json=cfg).status_code == 201
    c.post("/v1/connectors/test-mes/sync", headers=h())
    p.ownership.assign("T", Ownership("place_hold", "S1", "external", "MES", ("place_hold",)), by="admin", reason="test")
    proposal = c.post("/v1/proposals", headers=h("op"), json={"target_system": "MES", "operation": "place_hold",
        "target_id": "B1", "payload": {"reason": "review"}, "basis": [{"kind": "evidence", "id": "MES@test-mes:r1", "revision": 1, "site_id": "S1"}],
        "rationale": "review", "expected_result": "hold", "owner_id": "sup", "site_id": "S1"}).json()
    approved = c.post(f"/v1/proposals/{proposal['proposal_id']}/decisions", headers=h("sup"),
        json={"expected_revision": 1, "role": "supervisor", "decision": "approved"}).json()
    iid = approved["intent"]["intent_id"]
    route = f"/v1/connectors/test-mes/intents/{iid}/dispatch"
    assert c.post(route, headers=h("op")).status_code == 403
    assert c.post(route, headers=h("exec")).json()["status"] == "delivered"
    assert requests[-1][1] == "Bearer write-secret"
    assert requests[-1][2]["approval_ids"]
    assert c.post(route, headers=h("exec")).json()["status"] == "blocked"


def test_schedule_and_pause_preserve_last_sync_status(env, server):
    p, client, headers, _ = env
    url, _ = server
    cfg = config(base_url=url)
    assert client.post('/v1/connectors', headers=headers(), json=cfg).status_code == 201
    assert client.post('/v1/connectors/test-mes/sync', headers=headers()).status_code == 200
    before = client.get('/v1/connectors', headers=headers()).json()['items'][0]
    assert before['last_sync'] and before['last_result']
    for enabled in (False, True):
        cfg = {**cfg, 'enabled': enabled, 'options': {**cfg['options'], 'poll_seconds': 300}}
        response = client.post('/v1/connectors', headers=headers(), json=cfg)
        assert response.status_code == 201
        after = response.json()
        assert after['last_sync'] == before['last_sync']
        assert after['last_result'] == before['last_result']
        assert after['last_error'] == before['last_error']
    cfg['options']['events_path'] = '/different'
    changed = client.post('/v1/connectors', headers=headers(), json=cfg).json()
    assert changed['last_sync'] is None


def test_runtime_polls_configured_source_and_honors_pause(env, server):
    p, client, headers, _ = env
    url, requests = server
    cfg = config(base_url=url, poll_seconds=60)
    assert client.post('/v1/connectors', headers=headers(), json=cfg).status_code == 201
    p.runtime.tick()
    state = client.get('/v1/connectors', headers=headers()).json()['items'][0]
    assert state['last_result']['ingested'] == 1
    assert state['last_sync']
    count = len(requests)
    p.runtime.tick()
    assert len(requests) == count  # interval has not elapsed
    assert client.post('/v1/connectors', headers=headers(), json={**cfg, 'enabled': False}).status_code == 201
    p.runtime.tick()
    assert len(requests) == count


def test_catalog_does_not_offer_persistent_transports_on_lambda(env, monkeypatch):
    _, client, headers, _ = env
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', 'test-api')
    catalog = client.get('/v1/connectors/catalog', headers=headers()).json()
    available = {item['transport']: item['available'] for item in catalog['transports']}
    assert available['rest'] is True
    assert available['mqtt'] is False and available['opcua'] is False
