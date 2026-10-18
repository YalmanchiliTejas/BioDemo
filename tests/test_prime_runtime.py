from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.manufacturing_data import ManufacturingStore, ingest_package
from src.prime_runtime.bridge import ManufacturingBridge
from src.prime_runtime.harness import PrimeManufacturingHarness
from src.state import BlackboardStore
from src.workflows import ManufacturingInvestigationWorkflow


def setup_case(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "lab.csv").write_text(
        "batch_id,available_at,status\n"
        "B1,2024-01-02T00:00:00Z,action\n"
        "B2,2024-04-02T00:00:00Z,critical\n"
    )
    historical = datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()
    os.utime(source / "lab.csv", (historical, historical))
    store = ManufacturingStore(tmp_path / "store")
    ingest_package(source, store, access_scope="tenant_a")
    boards = BlackboardStore(tmp_path / "boards")
    workflow = ManufacturingInvestigationWorkflow(tmp_path / "workflow", store,
                                                   scope="tenant_a", blackboards=boards)
    early = store.visible(as_of="2024-02-01T00:00:00Z", scopes=("tenant_a",))
    status = next(row for row in early if row["name"] == "status")
    future = next(row for row in store.visible(scopes=("tenant_a",))
                  if row["name"] == "status" and row["entity_id"] == "B2")
    return store, boards, workflow, status["id"], future["id"]


def test_prime_bridge_enforces_cutoff_scope_citations_and_persists_graph(tmp_path):
    store, boards, workflow, evidence_id, future_id = setup_case(tmp_path)
    bridge = ManufacturingBridge(store=store, blackboards=boards, workflow=workflow,
                                 scope="tenant_a", incident_id="case-1",
                                 objective="Investigate status", as_of="2024-02-01T00:00:00Z",
                                 seed_ids=[evidence_id])
    assert bridge.context()["seed_evidence"][0]["_evidence_id"] == evidence_id
    state = bridge.tool("get_state_at", {"as_of": "2025-01-01T00:00:00Z",
                                         "scopes": ["tenant_b"]})
    assert future_id not in state["evidence_ids"]
    assert bridge.tool("verify_evidence", {"observation_id": evidence_id})["source_integrity"]
    with pytest.raises(ValueError, match="not retrieved"):
        bridge.submit_report({"assessment": "Attempted future citation",
                              "evidence_ids": [future_id]})
    report = bridge.submit_report({
        "assessment": "Source status requires review", "severity": "HIGH",
        "evidence_ids": [evidence_id], "open_questions": ["Is this recurrent?"],
        "hypotheses": [{"hypothesis_id": "H1", "statement": "Possible process issue",
                        "supporting_evidence_ids": [evidence_id],
                        "contradicting_evidence_ids": [], "confidence": 0.25,
                        "contradicting_evidence_status":"not_searched",
                        "contradicting_evidence_absence_reason":"Test investigation has not searched for counterevidence.",
                        "unknowns": ["Mechanism unknown"]}],
        "tasks": [{"owner": "QA", "action": "Review source status", "priority": "high",
                   "evidence_ids": [evidence_id], "reason": "Human review"}],
        "evidence_requests": [], "decision_branches": [],
    })
    assert report["workflow"]["triage"]["level"] == "L1"
    assert report["causal_hypotheses"][0]["hypothesis_id"] == "H1"
    assert boards.load("case-1").evidence_ids == [evidence_id]
    with pytest.raises(ValueError, match="already submitted"):
        bridge.submit_report({"evidence_ids": [evidence_id]})
    with pytest.raises(ValueError, match="unavailable"):
        ManufacturingBridge(store=store, blackboards=boards, workflow=workflow,
                            scope="tenant_a", incident_id="case-2", objective="Investigate",
                            as_of="2024-02-01T00:00:00Z", seed_ids=[future_id])


def test_manufacturing_api_defaults_to_prime_harness(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from benchmark.application.api import create_app
    from benchmark.application.bootstrap import build_demo_services
    from src.prime_runtime import PrimeManufacturingHarness
    import src.state as state

    store, _boards, _workflow, evidence_id, _future_id = setup_case(tmp_path)
    original = state.BlackboardStore
    monkeypatch.setattr(state, "BlackboardStore",
                        lambda _path: original(tmp_path / "api-boards"))
    monkeypatch.setenv("BIODEMO_MANUFACTURING_STORE", str(store.root))
    monkeypatch.setenv("BIODEMO_MANUFACTURING_SCOPE", "tenant_a")
    invoked = []

    class StubPrime:
        def run(self, **kwargs):
            invoked.append(kwargs)
            return {"assessment": "Prime route selected", "provider_id": "prime-agent"}

    monkeypatch.setattr(PrimeManufacturingHarness, "from_env",
                        classmethod(lambda cls, **_kwargs: StubPrime()))
    client = TestClient(create_app(build_demo_services(tmp_path / "app-evidence")))
    response = client.post("/api/manufacturing-os/rollouts",
                           headers={"X-Tenant-Id": "tenant_a"},
                           json={"incident_id": "prime-api", "problem": "Investigate",
                                 "new_evidence_ids": [evidence_id],
                                 "as_of": "2024-02-01T00:00:00Z"})
    assert response.status_code == 200, response.text
    assert response.json()["provider_id"] == "prime-agent"
    assert invoked[0]["new_evidence_ids"] == [evidence_id]


def test_manufacturing_rollout_requires_configured_store(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from benchmark.application.api import create_app
    from benchmark.application.bootstrap import build_demo_services

    monkeypatch.delenv("BIODEMO_MANUFACTURING_STORE", raising=False)
    monkeypatch.delenv("BIODEMO_MANUFACTURING_SCOPE", raising=False)
    client = TestClient(create_app(build_demo_services(tmp_path / "evidence")))
    response = client.post("/api/manufacturing-os/rollouts", json={
        "incident_id": "no-store", "problem": "Investigate",
        "as_of": "2024-02-01T00:00:00Z",
    })
    assert response.status_code == 503


def test_prime_harness_rejects_missing_report_without_fallback(tmp_path):
    store, boards, workflow, evidence_id, _future_id = setup_case(tmp_path)
    fake = tmp_path / "incomplete_prime.py"
    fake.write_text('print("{\\"type\\":\\"session\\",\\"id\\":\\"unused\\"}")\n')
    harness = PrimeManufacturingHarness(
        command=[sys.executable, str(fake)], store=store, blackboards=boards,
        workflow=workflow, scope="tenant_a", runtime_root=tmp_path / "prime")
    with pytest.raises(RuntimeError, match="without submitting"):
        harness.run(incident_id="incomplete", problem="Investigate",
                    new_evidence_ids=[evidence_id], as_of="2024-02-01T00:00:00Z")
    assert boards.load("incomplete") is None
    assert not (tmp_path / "prime/sessions/incomplete.json").exists()


def test_sdk_transport_uses_session_api_protocol_and_resumes(tmp_path, monkeypatch):
    store, boards, workflow, evidence_id, _ = setup_case(tmp_path)
    fake = tmp_path / "fake_sdk_host.py"
    fake.write_text('''
import json, os, sys
from pathlib import Path
sys.path.insert(0, os.environ["SKILL_SRC"])
from manufacturing_os import context, submit_report
request = json.load(sys.stdin)
assert request["skill_paths"] and request["prompt"]
assert not request["session_file"] or Path(request["session_file"]).is_file()
session_file = Path(request["session_dir"]) / "sdk-session.jsonl"
session_file.write_text('{"type":"session","id":"sdk-session"}\\n')
identifier = context()["seed_evidence"][0]["_evidence_id"]
submit_report({"assessment":"SDK host submitted cited evidence", "severity":"MEDIUM",
               "evidence_ids":[identifier], "hypotheses":[], "open_questions":[],
               "evidence_requests":[], "tasks":[], "decision_branches":[]})
print(json.dumps({"type":"session", "id":"sdk-session", "file":str(session_file)}))
print(json.dumps({"type":"message_end", "message":{"role":"assistant",
                "usage":{"input":11,"output":7,"cacheRead":2,"cost":{"total":0.01}}}}))
''')
    monkeypatch.setenv("SKILL_SRC", str(Path(__file__).resolve().parents[1] /
                                       "prime_skills/manufacturing_os/src"))
    harness = PrimeManufacturingHarness(
        command=[sys.executable, str(fake)], store=store, blackboards=boards,
        workflow=workflow, scope="tenant_a", runtime_root=tmp_path / "prime")
    first = harness.run(incident_id="sdk-case", problem="Investigate",
                        new_evidence_ids=[evidence_id], as_of="2024-02-01T00:00:00Z")
    second = harness.run(incident_id="sdk-case", problem="Update",
                         new_evidence_ids=[evidence_id], as_of="2024-02-01T00:00:00Z")
    assert first["rollout_metrics"]["prime_transport"] == "sdk"
    assert second["rollout_metrics"]["prime_session_id"] == "sdk-session"
    assert second["rollout_metrics"]["input_tokens"] == 11
    assert len(boards.load("sdk-case").rollout_history) == 2


def test_prime_environment_selects_sdk_host_by_default(tmp_path, monkeypatch):
    store = ManufacturingStore(tmp_path / "store")
    boards = BlackboardStore(tmp_path / "boards")
    workflow = ManufacturingInvestigationWorkflow(tmp_path / "workflow", store,
                                                   scope="tenant_a", blackboards=boards)
    bundle = tmp_path / "prime-bundle"
    package = bundle / "packages/coding-agent/dist/index.js"
    skill = bundle / "packages/coding-agent/skills/agent-message/SKILL.md"
    package.parent.mkdir(parents=True)
    skill.parent.mkdir(parents=True)
    package.write_text("")
    skill.write_text("---\nname: agent-message\ndescription: test\n---\n")
    monkeypatch.setenv("PRIME_AGENT_BUNDLE_ROOT", str(bundle))
    monkeypatch.setattr("src.prime_runtime.harness.shutil.which", lambda _name: "/usr/bin/node")
    monkeypatch.delenv("BIODEMO_PRIME_SDK_COMMAND", raising=False)
    harness = PrimeManufacturingHarness.from_env(
        store=store, blackboards=boards, workflow=workflow, scope="tenant_a")
    assert Path(harness.command[-1]).name == "sdk_runner.mjs"
