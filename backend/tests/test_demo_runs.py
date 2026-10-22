import json
import threading
import time

import pytest

from benchmark.application.demo_runs import DemoRuns


def wait_for_terminal(manager, identifier, tenant="demo"):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = manager.get(identifier, tenant)
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(.01)
    raise AssertionError("job did not finish")


def source_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("BIODEMO_PRIME_SDK_COMMAND", "test-sdk")
    package = tmp_path / "benchmarks/cho/raw/workbooks"
    package.mkdir(parents=True)
    (package / "source.xlsx").write_bytes(b"fixture")
    return tmp_path


def test_click_launches_background_job_and_deduplicates_running_case(tmp_path, monkeypatch):
    root = source_repo(tmp_path, monkeypatch)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def runner(**arguments):
        calls.append(arguments)
        arguments["progress"]("Agent investigating evidence")
        entered.set()
        assert release.wait(5)
        arguments["output"].mkdir(parents=True)
        (arguments["output"] / "agent_report.json").write_text(json.dumps({
            "assessment": "Review the evidence.", "evidence_ids": ["e1"],
            "report_status":"complete_for_available_evidence",
            "causal_hypotheses": [], "open_questions": ["Validate this finding."],
        }))
        return {"with_agent": {"investigation_seconds": 2}}

    manager = DemoRuns(root, runner=runner)
    assert not calls
    first = manager.start("cho", "demo", as_of=None)
    assert entered.wait(5)
    assert manager.get(first["id"], "demo")["phase"] == "Agent investigating evidence"
    assert manager.start("cho", "demo", as_of=None)["id"] == first["id"]
    with pytest.raises(KeyError):
        manager.get(first["id"], "another-tenant")
    release.set()
    job = wait_for_terminal(manager, first["id"])
    assert len(calls) == 1
    assert job["status"] == "completed"
    assert job["result"]["evidence_count"] == 1
    assert job["result"]["assessment"] == "Review the evidence."
    assert DemoRuns(root).get(first["id"], "demo")["result"] == job["result"]


def test_failures_are_visible_and_do_not_substitute_a_fake_report(tmp_path, monkeypatch):
    root = source_repo(tmp_path, monkeypatch)

    def fail(**_):
        raise RuntimeError("provider unavailable")

    manager = DemoRuns(root, runner=fail)
    first = manager.start("cho", "demo", as_of=None)
    job = wait_for_terminal(manager, first["id"])
    assert job["status"] == "failed"
    assert job["error"] == "provider unavailable"
    assert job["result"] is None
    retry = manager.start("cho", "demo", as_of=None)
    assert retry["id"] != first["id"]
    assert wait_for_terminal(manager, retry["id"])["status"] == "failed"


def test_fresenius_stages_only_the_selected_cutoff(tmp_path, monkeypatch):
    import benchmarks.fresenius.build_multimodal_package as builder

    source_repo(tmp_path, monkeypatch)
    calls = []

    def stage(output, *, as_of, map_output):
        calls.append(as_of)
        output.mkdir(parents=True)
        (output / "records.csv").write_text("visible,records")
        assert map_output.parent == output.parent  # hidden map stays outside input

    monkeypatch.setattr(builder, "build_package", stage)

    def runner(**arguments):
        assert arguments["as_of"] == "2025-01-04T12:25:00Z"
        assert arguments["package"].name == "source"
        raise RuntimeError("stop after verifying input")

    manager = DemoRuns(tmp_path, runner=runner)
    job = manager.start("fresenius", "demo", as_of="2025-01-04T12:25:00Z")
    assert wait_for_terminal(manager, job["id"])["status"] == "failed"
    assert calls == ["2025-01-04T12:25:00Z"]


def test_stale_running_jobs_become_interrupted_after_restart(tmp_path, monkeypatch):
    source_repo(tmp_path, monkeypatch)
    manager = DemoRuns(tmp_path)
    identifier = "a" * 32
    manager._save({"id": identifier, "status": "running", "tenant": "demo"})
    assert manager.get(identifier, "demo")["status"] == "failed"
    assert "restarted" in manager.get(identifier, "demo")["error"]
    with pytest.raises(KeyError):
        manager.get("../another-file", "demo")


def test_api_start_requires_an_explicit_post_and_valid_milestone(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from benchmark.application.api import create_app
    from benchmark.application.bootstrap import build_demo_services

    monkeypatch.delenv("BIODEMO_MANUFACTURING_STORE", raising=False)
    app = create_app(build_demo_services(tmp_path / "evidence"))
    calls = []
    def start(case_id, tenant, *, as_of):
        calls.append((case_id, tenant, as_of))
        return {"id": "a" * 32, "status": "queued"}
    monkeypatch.setattr(app.state.demo_runs, "start", start)
    client = TestClient(app)
    assert client.get("/api/demo").status_code == 200
    assert client.get("/").status_code == 200
    assert calls == []
    response = client.post("/api/demo/fresenius/runs", json={"milestone": 1})
    assert response.status_code == 202
    assert calls[0][2] == "2025-01-04T12:25:00Z"
    assert client.post("/api/demo/fresenius/runs", json={"milestone": 20}).status_code == 409
    assert client.post("/api/demo/no-case/runs", json={}).status_code == 404
    assert client.post("/api/demo/cho/runs", json={"milestone": -1}).status_code == 422


def test_partial_report_is_visible_without_completed_label(tmp_path, monkeypatch):
    root=source_repo(tmp_path,monkeypatch)
    def runner(**args):
        args['output'].mkdir(parents=True)
        (args['output']/'agent_report.json').write_text(json.dumps({'assessment':'One source examined.',
            'report_status':'incomplete','investigation_review':{'screened_unit_count':4,'reviewed_unit_count':1}}))
        return {'with_agent':{'investigation_seconds':2}}
    manager=DemoRuns(root,runner=runner)
    job=wait_for_terminal(manager,manager.start('cho','demo',as_of=None)['id'])
    assert job['status']=='incomplete'
    assert job['result']['investigation_review']['reviewed_unit_count']==1
    assert 'Partial' in job['phase']
