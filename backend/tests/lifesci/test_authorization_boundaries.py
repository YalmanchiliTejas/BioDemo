"""Authorization boundaries: approval policy follows content, evidence writes need write authority,
sign-in assertions come from the token, and connector settings cannot reach server secrets."""
from __future__ import annotations

import http.client
import subprocess
import sys
import time
from dataclasses import replace

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from src.lifesci.actions import DeliveryUnknown  # noqa: E402
from src.lifesci.api import create_app  # noqa: E402
from src.lifesci.container import Platform  # noqa: E402
from src.lifesci.identity import Authentication, authentication_assertion  # noqa: E402
from src.lifesci.store import RecordStore  # noqa: E402

T = "tenant-a"
BASIS = [{"kind": "evidence", "id": "LIMS:R1", "revision": 1, "site_id": "S1"}]


@pytest.fixture
def api():
    p = Platform(RecordStore(), providers={})
    for actor, role in [("op1", "operator"), ("sup1", "supervisor"), ("sup2", "supervisor"), ("qa1", "qa"),
                        ("rev1", "qa_reviewer")]:
        p.identity.assign_role(T, actor, role, site_id="S1")
    p.identity.assign_role(T, "op2", "operator", site_id="S2")
    client = TestClient(create_app(p))
    h = lambda actor, **extra: {"X-Tenant-Id": T, "X-Actor-Id": actor, **extra}  # noqa: E731
    made = client.post("/v1/evidence", headers=h("op1"), json={
        "source_system": "LIMS", "source_record_id": "R1", "content_text": "pH=7.1", "site_id": "S1"})
    assert made.status_code == 201
    return client, h, p


def _propose(client, h, operation="send_notification", actor="op1"):
    made = client.post("/v1/proposals", headers=h(actor), json={
        "target_system": "MES", "operation": operation, "target_id": "B1", "basis": BASIS,
        "rationale": "r", "expected_result": "e", "owner_id": "sup1", "site_id": "S1"})
    assert made.status_code in (200, 201), made.text
    return made.json()


def _revise(client, h, proposal, changes, actor="op1", revision=1):
    return client.post(f"/v1/proposals/{proposal['proposal_id']}/revisions", headers=h(actor),
                       json={"expected_revision": revision, "changes": changes, "reason": "update"})


def test_revising_the_operation_applies_that_operations_approval_policy(api):
    client, h, _ = api
    proposal = _propose(client, h)
    assert (proposal["risk"], proposal["required_roles"]) == ("low", ["supervisor"])
    revised = _revise(client, h, proposal, {"operation": "release_batch"})
    assert revised.status_code == 200, revised.text
    assert (revised.json()["risk"], revised.json()["required_roles"]) == ("critical", ["qa", "qa_reviewer"])
    # The approver who would have sufficed for the original operation no longer does.
    denied = client.post(f"/v1/proposals/{proposal['proposal_id']}/decisions", headers=h("sup1"),
                         json={"expected_revision": 2, "decision": "approved", "role": "supervisor"})
    assert denied.status_code == 403


def test_a_person_who_rewrote_a_proposal_cannot_approve_it(api):
    client, h, _ = api
    proposal = _propose(client, h)
    revised = _revise(client, h, proposal, {"target_id": "B2"}, actor="sup1")
    assert revised.status_code == 200 and revised.json()["revised_by"] == ["sup1"]
    decide = lambda actor: client.post(  # noqa: E731
        f"/v1/proposals/{proposal['proposal_id']}/decisions", headers=h(actor),
        json={"expected_revision": 2, "decision": "approved", "role": "supervisor"})
    assert decide("sup1").status_code == 403
    assert decide("sup2").status_code == 200


def test_revision_cannot_move_a_proposal_to_an_unauthorized_site_or_unreadable_basis(api):
    client, h, p = api
    proposal = _propose(client, h)
    assert _revise(client, h, proposal, {"site_id": "S2"}).status_code == 403
    assert _revise(client, h, proposal, {"basis": []}).status_code in (400, 422)
    other = client.post("/v1/evidence", headers=h("op2"), json={
        "source_system": "LIMS", "source_record_id": "R2", "content_text": "x", "site_id": "S2"})
    assert other.status_code == 201
    unreadable = [{"kind": "evidence", "id": "LIMS:R2", "revision": 1, "site_id": "S2"}]
    assert _revise(client, h, proposal, {"basis": unreadable}).status_code == 403
    assert p.store.read().require(T, "proposal", proposal["proposal_id"]).revision == 1


def test_reading_evidence_is_not_authority_to_write_it(api):
    client, h, _ = api
    body = {"source_system": "LIMS", "source_record_id": "R9", "content_text": "pH=2", "site_id": "S1"}
    assert client.post("/v1/evidence", headers=h("rev1"), json=body).status_code == 403
    made = client.post("/v1/evidence", headers=h("op1"), json=body)
    assert made.status_code == 201
    assert made.json()["metadata"] == {"intake": "manual", "submitted_by": "op1"}


def test_source_maintained_evidence_cannot_be_corrected_by_hand(api):
    client, h, p = api
    ctx = p.identity.context_for(T, "op1")
    p.evidence.ingest(ctx, source_system="MES", source_record_id="B7", content=b"hold=false", media_type="text/plain",
                      site_id="S1", event_time=None, metadata={"template": "mes-v1@1", "mapped": {"hold": False}})
    forged = client.post("/v1/evidence", headers=h("op1"), json={
        "source_system": "MES", "source_record_id": "B7", "content_text": "hold=true", "site_id": "S1"})
    assert forged.status_code == 403
    assert p.store.read().require(T, "evidence", "MES:B7").revision == 1
    for source in ("edge:gw1:MES", "scientific-model-catalog", "cmo-verified-delivery"):
        assert client.post("/v1/evidence", headers=h("op1"), json={
            "source_system": source, "source_record_id": "x", "content_text": "x", "site_id": "S1"}).status_code == 403
    # A person's own earlier submission stays correctable.
    assert client.post("/v1/evidence", headers=h("op1"), json={
        "source_system": "LIMS", "source_record_id": "R1", "content_text": "pH=7.2", "site_id": "S1"}).status_code == 201


def test_model_tasks_need_a_role_in_the_organization(api):
    client, h, _ = api
    denied = client.post("/v1/tasks", headers=h("stranger"), json={"task_kind": "short_summary", "prompt": "hi"})
    assert denied.status_code == 403


def test_development_sign_in_refuses_remote_callers(api, monkeypatch):
    _, h, p = api
    remote = TestClient(create_app(p), client=("203.0.113.9", 40000))
    assert remote.get("/v1/me", headers=h("op1")).status_code == 401
    monkeypatch.setenv("LIFESCI_DEV_AUTH_ALLOW_REMOTE", "1")
    assert remote.get("/v1/me", headers=h("op1")).status_code == 200


def test_webhook_rejects_an_oversized_body(api):
    client, _, _ = api
    reply = client.post(f"/v1/webhooks/{T}/any", content=b"x" * 1_000_001)
    assert reply.status_code == 413


# --- sign-in assertions -----------------------------------------------------------------------------
def test_required_reauthentication_uses_the_verified_sign_in_time_not_the_callers_word(api, monkeypatch):
    _, _, p = api
    ctx = p.identity.context_for(T, "qa1")
    stale = replace(ctx, authentication=Authentication("password", time.time() - 3600, "aal1"))
    with pytest.raises(PermissionError, match="recent sign-in"):
        authentication_assertion(stale, {"method": "mfa"}, purpose="high-risk approval")
    fresh = replace(ctx, authentication=Authentication("password", time.time() - 30, "aal1"))
    stated = authentication_assertion(fresh, {"method": "mfa", "assurance": "aal3"}, purpose="high-risk approval")
    assert (stated["method"], stated["assurance"], stated["verified"]) == ("password", "aal1", True)
    untimed = replace(ctx, authentication=Authentication("oidc"))
    with pytest.raises(PermissionError):
        authentication_assertion(untimed, {"method": "mfa"}, purpose="signature")
    assert authentication_assertion(untimed, None, purpose="approval", required=False)["verified"] is True
    # Without a verifying provider the stated method is kept, and labelled as unverified.
    assert authentication_assertion(ctx, {"method": "sso_reauth"}, purpose="signature") == {
        "method": "sso_reauth", "assurance": "unspecified", "verified": False}
    with pytest.raises(PermissionError, match="re-authentication"):
        authentication_assertion(ctx, None, purpose="high-risk approval")
    monkeypatch.setenv("LIFESCI_REAUTH_MAX_AGE_SECONDS", "10")
    with pytest.raises(PermissionError):
        authentication_assertion(fresh, None, purpose="signature")


def test_high_risk_approval_with_a_stale_verified_session_is_refused_and_recorded_when_fresh(api):
    client, h, p = api
    proposal = _propose(client, h, operation="close_deviation")
    qa = p.identity.context_for(T, "qa1")
    stale = replace(qa, authentication=Authentication("password", time.time() - 7200, "aal1"))
    with pytest.raises(PermissionError, match="recent sign-in"):
        p.actions.decide(stale, proposal["proposal_id"], expected_revision=1, decision="approved", role="qa",
                         authentication={"method": "anything"})
    fresh = replace(qa, authentication=Authentication("totp", time.time() - 5, "aal2"))
    p.actions.decide(fresh, proposal["proposal_id"], expected_revision=1, decision="approved", role="qa")
    approval = p.store.read().find(T, "approval", "proposal_id", proposal["proposal_id"])[0].state
    assert approval["authentication"]["method"] == "totp" and approval["authentication"]["verified"] is True


def test_sign_in_assertion_reads_the_latest_token_entry():
    from src.lifesci.supabase_auth import sign_in_assertion
    found = sign_in_assertion({"aal": "aal2", "amr": [{"method": "password", "timestamp": 100},
                                                      {"method": "totp", "timestamp": 250}, "junk",
                                                      {"method": "x", "timestamp": True}]})
    assert found == Authentication("totp", 250.0, "aal2")
    assert sign_in_assertion({}) == Authentication("unknown", None, None)


# --- connectors -------------------------------------------------------------------------------------
def test_connector_settings_can_only_reference_operator_listed_secrets(monkeypatch):
    from src.lifesci import connectors
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@db/app")
    monkeypatch.setenv("MES_TOKEN", "token")
    monkeypatch.delenv("LIFESCI_CONNECTOR_SECRET_ENVS", raising=False)
    with pytest.raises(PermissionError, match="LIFESCI_CONNECTOR_SECRET_ENVS"):
        connectors._secret("MES_TOKEN")
    monkeypatch.setenv("LIFESCI_CONNECTOR_SECRET_ENVS", "MES_TOKEN, OTHER")
    assert connectors._secret("MES_TOKEN") == "token"
    with pytest.raises(PermissionError):
        connectors._secret("DATABASE_URL")
    with pytest.raises(ValueError):
        connectors._check_secret_name("not a name")


class _Connector:
    source_system = "MES"

    def __init__(self, failure):
        self.failure = failure

    def write(self, action):
        raise self.failure


INTENT = {"idempotency_key": "k1", "operation": "place_hold", "target_id": "B1", "payload": {}, "approvers": [],
          "approval_ids": [], "site_id": "S1"}


@pytest.mark.parametrize("failure", [ConnectionResetError("reset"), http.client.RemoteDisconnected("closed"),
                                     http.client.IncompleteRead(b"{"), TimeoutError("slow")])
def test_a_write_that_may_have_been_applied_is_never_recorded_as_rejected(failure):
    from src.lifesci.integrations import ConnectorWriter
    with pytest.raises(DeliveryUnknown):
        ConnectorWriter(_Connector(failure), lambda key: None).deliver(INTENT)


def test_a_refusal_before_sending_stays_a_definite_failure():
    from src.lifesci.integrations import ConnectorWriter
    with pytest.raises(PermissionError):
        ConnectorWriter(_Connector(PermissionError("operation is not enabled")), lambda key: None).deliver(INTENT)


# --- agent process cleanup --------------------------------------------------------------------------
@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX")
def test_timeout_stops_the_processes_the_agent_host_started(tmp_path):
    from src.prime_runtime.harness import _stream
    marker = tmp_path / "child.pid"
    script = f"sleep 60 & echo $! > {marker}; wait"
    with pytest.raises(subprocess.TimeoutExpired):
        _stream(["sh", "-c", script], cwd=str(tmp_path), env=None, input_text="", timeout=1.5)
    child = int(marker.read_text())
    for _ in range(40):
        if subprocess.run(["kill", "-0", str(child)], capture_output=True).returncode != 0:
            break
        time.sleep(0.05)
    else:
        subprocess.run(["kill", "-9", str(child)])
        pytest.fail("the child process outlived the timeout")


def test_saved_connector_credentials_do_not_follow_a_changed_address(monkeypatch):
    import base64
    monkeypatch.setenv("LIFESCI_CONNECTOR_ALLOWED_HOSTS", "127.0.0.1,localhost")
    monkeypatch.setenv("LIFESCI_CONNECTOR_KEY", base64.b64encode(b"k" * 32).decode())
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role("T", "admin", "admin", site_id="S1")
    client = TestClient(create_app(p))
    headers = {"X-Tenant-Id": "T", "X-Actor-Id": "admin"}
    options = {"base_url": "http://127.0.0.1:9", "events_path": "/v1/records", "auth_type": "api_key",
               "api_key_header": "X-API-Key", "records_field": "items", "id_field": "uid", "timestamp_field": "at"}
    body = {"connector_id": "rest-1", "family": "MES", "transport": "rest_api", "site_id": "S1", "owner": "admin"}
    try:
        made = client.post("/v1/connectors", headers=headers, json={**body, "options": options,
                                                                    "credentials": {"api_key": "s3cret-value"}})
        assert made.status_code == 201, made.text
        # Same address: the saved key is reused without re-entry.
        assert client.post("/v1/connectors", headers=headers, json={**body, "options": options}).status_code in (200, 201)
        moved = {**options, "base_url": "http://localhost:9"}
        refused = client.post("/v1/connectors", headers=headers, json={**body, "options": moved})
        assert refused.status_code == 400 and "address changed" in refused.json()["detail"]
        assert p.connectors.credentials.load("T", "rest-1") == {"api_key": "s3cret-value"}
        again = client.post("/v1/connectors", headers=headers, json={**body, "options": moved,
                                                                     "credentials": {"api_key": "new-value"}})
        assert again.status_code in (200, 201), again.text
        assert p.connectors.credentials.load("T", "rest-1") == {"api_key": "new-value"}
    finally:
        p.connectors.close()
