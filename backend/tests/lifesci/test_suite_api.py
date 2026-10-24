"""Suite workflows through HTTP, with real domain services and isolated SQLite."""
import pytest
from fastapi.testclient import TestClient

from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.ownership import Ownership
from src.lifesci.store import RecordStore


@pytest.fixture
def suite():
    p = Platform(RecordStore(), providers={})
    for actor, role, site in [("designer", "manufacturing_systems", "S1"), ("op", "operator", "S1"),
                              ("qa", "qa", "S1"), ("other", "operator", "S2")]:
        p.identity.assign_role("T", actor, role, site_id=site)
    for kind in ("batch_record", "lab_record", "procedure"):
        p.ownership.assign("T", Ownership(kind, "S1", "native", None, (), True, "POC", "test-qualification"),
                           by="test", reason="isolated fixture")
    return p, TestClient(create_app(p))


def headers(actor, key=None):
    return {"X-Tenant-Id": "T", "X-Actor-Id": actor, **({"Idempotency-Key": key} if key else {})}


def post(c, path, body=None, actor="designer", key=None):
    response = c.post(path, json=body, headers=headers(actor, key))
    assert response.status_code in (200, 201), response.text
    return response.json()


def published(c):
    definition = {"steps": [{"step_id": "check", "title": "Check pH", "kind": "data_entry",
                              "parameters": [{"name": "ph", "unit": "pH", "low": 6.8, "high": 7.4}]}]}
    draft = {"procedure_id": "REC", "name": "POC recipe", "site_id": "S1", "category": "recipe", "definition": definition}
    post(c, "/v1/procedures", draft)
    proposal = post(c, "/v1/procedures/REC/submit", {"rationale": "Review this POC revision"})
    post(c, f"/v1/proposals/{proposal['proposal_id']}/decisions", {
        "expected_revision": 1, "decision": "approved", "role": "qa", "authentication": {"method": "sso_reauth"}}, actor="qa")
    post(c, "/v1/procedures/REC/publish", {"approved_proposal_id": proposal["proposal_id"]})
    return draft


def test_http_recipe_to_execution_to_exception_review(suite):
    p, c = suite
    published(c)
    post(c, "/v1/manufacturing/batches", {"batch_id": "B1", "product": "POC", "modality": "mAb", "site_id": "S1"})
    instance = post(c, "/v1/manufacturing/instances", {"procedure_id": "REC", "batch_id": "B1", "site_id": "S1"}, actor="op")
    iid = instance["instance_id"]
    post(c, f"/v1/manufacturing/instances/{iid}/start", actor="op")
    body = {"values": {"ph": 7.1}}
    path = f"/v1/manufacturing/instances/{iid}/steps/check"
    first = post(c, path, body, actor="op", key="step-key-0001")
    assert post(c, path, body, actor="op", key="step-key-0001") == first
    assert len(p.store.read().list("T", "step_execution")) == 1
    review = c.get(f"/v1/manufacturing/instances/{iid}/exceptions", headers=headers("qa")).json()
    assert review["open_exception_count"] == 0 and review["release_authorized"] is False
    assert c.get(f"/v1/manufacturing/instances/{iid}/batch-record", headers=headers("other")).status_code == 403
    assert c.post(path, json=body, headers=headers("other", "step-key-0001")).status_code == 403


def test_preview_and_drafts_do_not_enable_native_operations(suite):
    p, c = suite
    definition = {"steps": [{"step_id": "one", "title": "Observe", "kind": "instruction"}]}
    r = post(c, "/v1/procedures/preview", {"definition": definition}, actor="op")
    assert not r["writes"] and not p.store.read().list("T", "procedure")
    body = {"procedure_id": "DRAFT", "name": "Unapproved", "category": "recipe", "site_id": "S1", "definition": definition}
    assert post(c, "/v1/procedures", body, key="draft-key-0001") == post(c, "/v1/procedures", body, key="draft-key-0001")
    assert c.get("/v1/procedures/DRAFT/effective", headers=headers("op")).status_code == 404
    assert c.post("/v1/procedures/DRAFT/draft", headers=headers("designer"), json={"definition": definition, "expected_revision": 99}).status_code == 409
    assert c.post("/v1/procedures", headers=headers("designer"), json={**body, "procedure_id": "unauthorized", "site_id": "S2"}).status_code == 403
    assert c.post("/v1/procedures", headers=headers("designer"), json={**body, "approved": True}).status_code == 422


def test_sample_result_custody_and_site_boundaries(suite):
    _, c = suite
    post(c, "/v1/manufacturing/batches", {"batch_id": "B1", "product": "POC", "modality": "mAb", "site_id": "S1"})
    body = {"batch_id": "B1", "sample_type": "QC", "idempotency_key": "collect-key-01", "volume": 2}
    sample = post(c, "/v1/laboratory/samples", body, actor="op", key="http-sample-01")
    assert post(c, "/v1/laboratory/samples", body, actor="op", key="http-sample-01") == sample
    sid = sample["sample_id"]
    post(c, f"/v1/laboratory/samples/{sid}/results", {"analyte": "pH", "value": 7.1, "unit": "pH"}, actor="op")
    post(c, f"/v1/laboratory/samples/{sid}/custody", {"from_actor": "op", "to_actor": "qa", "reason": "QC review"}, actor="op")
    chain = c.get(f"/v1/laboratory/samples/{sid}/custody", headers=headers("qa")).json()
    assert chain["current_custodian"] == "qa" and len(chain["raw_entries"]) == 2
    assert c.get(f"/v1/laboratory/samples/{sid}/custody", headers=headers("other")).status_code == 403
    sites = c.get("/v1/network/sites", headers=headers("other")).json()
    assert "S1" not in sites["sites"]


def test_quality_packages_use_real_case_and_authority(suite):
    _, c = suite
    post(c, "/v1/quality/cases", {"case_id": "C1", "owner_id": "op", "qa_reviewer_id": "qa", "site_id": "S1"}, actor="op")
    post(c, "/v1/quality/cases/C1/review-package", actor="qa")
    assert c.post("/v1/quality/cases/C1/review-package", headers=headers("other")).status_code == 403


def test_openapi_documents_explicit_commands_and_atomic_failure(suite):
    p, c = suite
    paths = c.get("/v1/openapi.json").json()["paths"]
    assert "/v1/laboratory/runs/{iid}/steps/{sid}" in paths
    assert "/v1/manufacturing/instances/{iid}/request-release" in paths
    response = c.post("/v1/network/transfers", headers=headers("designer", "failed-transfer"), json={
        "sending_site": "S1", "receiving_site": "S2", "product_id": "P", "procedure_refs": [{"kind": "procedure_revision", "id": "missing", "revision": 1}]})
    assert response.status_code in (400, 404)
    assert not p.store.read().list("T", "transfer_package")


def test_qualification_trace_distinguishes_submitted_evidence(suite):
    p, c = suite
    p.identity.assign_role("T", "assurance", "quality_systems")
    post(c, "/v1/assurance/requirements/R1", {"text": "Prevent unauthorized execution", "risk": "high", "tests": ["scope_check"], "intended_use": "POC"}, actor="assurance")
    result = post(c, "/v1/assurance/test-runs", {"junit_xml": '<testsuite><testcase name="scope_check"/></testsuite>', "build": "test-build", "environment": {"fixture": True}}, actor="assurance")
    assert result["independently_verified"] is False
    trace = c.get(f"/v1/assurance/test-runs/{result['run_id']}/trace", headers=headers("assurance")).json()
    assert not trace["gaps"]
    assert c.get(f"/v1/assurance/test-runs/{result['run_id']}/trace", headers=headers("op")).status_code == 403
    assert c.post("/v1/assurance/test-runs", headers=headers("assurance"), json={"junit_xml": "broken", "build": "x", "environment": {}}).status_code == 400


def test_remote_provider_is_explicit_and_unavailable_by_default(suite):
    p, c = suite
    post(c, "/v1/quality/cases", {"case_id": "C1", "owner_id": "op", "qa_reviewer_id": "qa", "site_id": "S1"}, actor="op")
    assert c.get("/v1/collaboration/providers", headers=headers("op")).json()["available"] is False
    body = {"case_id": "C1", "participants": ["op", "qa"], "media_provider": "enterprise"}
    assert c.post("/v1/collaboration/sessions", headers=headers("op"), json=body).status_code == 503
    from src.lifesci.collab import FakeMediaProvider
    p.media_providers["fixture"] = FakeMediaProvider()
    session = post(c, "/v1/collaboration/sessions", {**body, "media_provider": "fixture"}, actor="op")
    sid = session["session_id"]
    assert session["site_id"] == "S1"
    assert c.post(f"/v1/collaboration/sessions/{sid}/join", headers=headers("other")).status_code == 403
    post(c, f"/v1/collaboration/sessions/{sid}/consent", {"granted": True}, actor="op")
    assert post(c, f"/v1/collaboration/sessions/{sid}/join", actor="op")


def test_http_data_flow_replay_and_input_manifest(suite):
    _, c = suite
    post(c, "/v1/intelligence/flows/F", {"site_id": "S1", "nodes": [{"node_id": "summary", "task_kind": "short_summary"}]}, actor="op")
    run = post(c, "/v1/intelligence/flows/F/runs", {"inputs": []}, actor="op", key="flow-run-key-01")
    assert run == post(c, "/v1/intelligence/flows/F/runs", {"inputs": []}, actor="op", key="flow-run-key-01")
    assert run["inputs"][0]["kind"] == "flow_literal_input"
    done = post(c, f"/v1/intelligence/runs/{run['run_id']}/resume", actor="op")
    assert done["status"] == "blocked"
    assert c.post(f"/v1/intelligence/runs/{run['run_id']}/resume", headers=headers("other")).status_code == 403


def test_publication_rechecks_approver_authority(suite):
    p, c = suite
    post(c, "/v1/procedures", {"procedure_id": "R", "name": "Review me", "category": "recipe", "site_id": "S1",
        "definition": {"steps": [{"step_id": "a", "title": "Check", "kind": "instruction"}]}})
    prop = post(c, "/v1/procedures/R/submit", {"rationale": "POC"})
    post(c, f"/v1/proposals/{prop['proposal_id']}/decisions", {"expected_revision": 1, "decision": "approved", "role": "qa", "authentication": {"method": "sso_reauth"}}, actor="qa")
    p.identity.revoke_role("T", "qa", "qa", site_id="S1", reason="site reassignment")
    p.identity.assign_role("T", "qa", "qa", site_id="S2")
    response = c.post("/v1/procedures/R/publish", headers=headers("designer"), json={"approved_proposal_id": prop["proposal_id"]})
    assert response.status_code == 403
    assert c.get("/v1/procedures/R/effective", headers=headers("op")).status_code == 404
