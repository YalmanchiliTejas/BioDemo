from __future__ import annotations

import csv
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest

from src.manufacturing_data import ManufacturingStore, ManufacturingTools, ingest_package
from src.state import BlackboardStore
from src.workflows import ManufacturingInvestigationWorkflow
from src.manufacturing_data.models import Observation, SourceRef

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def workspace(tmp_path):
    source=tmp_path/"package"
    source.mkdir()
    store=ManufacturingStore(tmp_path/"store")
    return source,store

def test_ingest_provenance_incremental_and_entity_link(workspace):
    source,store=workspace
    (source/"measurements.csv").write_text("batch_id,available_at,Temperature (degC)\nB001,2024-01-02T00:00:00Z,37\n")
    first=ingest_package(source,store)
    assert first["observations"]==3 and first["errors"]==[]
    assert ingest_package(source,store)["unchanged"]==1
    tools=ManufacturingTools(store)
    context=tools.get_process_context(entity_id="B001")
    assert len(context["records"])==3
    first=tools.get_state_at(as_of="2025-01-01T00:00:00Z",limit=1)["records"]
    second=tools.get_state_at(as_of="2025-01-01T00:00:00Z",limit=1,offset=1)["records"]
    assert first and second and first[0]["id"]!=second[0]["id"]
    temp=next(o for o in context["records"] if o["name"]=="Temperature (degC)")
    assert tools.verify_evidence(observation_id=temp["id"])["value_matches"]
    assert tools.extract_region(source_id=temp["source_id"],row=2,column="Temperature (degC)")["data"]=={"Temperature (degC)":"37"}
    assert len(list(store.measurements.glob("*.parquet")))==1
    with store.connect() as con:
        assert con.execute("SELECT count(*) FROM observations").fetchone()[0]==0

def test_historical_and_scope_filters(workspace):
    source,store=workspace
    with (source/"history.csv").open("w",newline="") as handle:
        writer=csv.writer(handle)
        writer.writerow(["batch_id","available_at","result","field_available_at"])
        writer.writerow(["B001","2024-01-02T00:00:00Z",8,
                         json.dumps({"result":"2024-02-02T00:00:00Z"})])
    ingest_package(source,store,access_scope="tenant_a")
    assert ManufacturingTools(store,scopes=("tenant_b",)).inspect_data()["sources"]==[]
    early=ManufacturingTools(store,as_of="2024-01-15T00:00:00Z",scopes=("tenant_a",))
    assert not any(o["name"]=="result" for o in early.get_state_at(as_of="2024-01-15T00:00:00Z")["records"])
    with pytest.raises(PermissionError): early.inspect_data(scopes=["tenant_b"])
    with pytest.raises(PermissionError): early.get_state_at(as_of="2024-03-01T00:00:00Z")
    assert ManufacturingTools(store,as_of="1900-01-01T00:00:00Z",scopes=("tenant_a",)).inspect_data()["sources"]==[]

def test_unit_conversion_and_safe_query(workspace):
    source,store=workspace
    (source/"data.csv").write_text("batch_id,Temp (degC)\nB1,37\n")
    ingest_package(source,store)
    tools=ManufacturingTools(store)
    obs=next(o for o in tools.get_process_context(entity_id="B1")["records"] if o["name"]=="Temp (degC)")
    converted=tools.normalize_measurements(observation_ids=[obs["id"]],target_unit="kelvin")
    assert converted["measurements"][0]["value"]==pytest.approx(310.15)
    assert tools.query_data(sql="SELECT avg(value_number) FROM observations")["rows"]==[[37.0]]
    with pytest.raises(ValueError): tools.query_data(sql="SELECT * FROM read_parquet('/tmp/x.parquet')")

def test_query_unions_parquet_shards_with_different_null_types(workspace):
    source,store=workspace
    (source/"a.csv").write_text("batch_id,value\nB1,1\n")
    (source/"b.csv").write_text("batch_id,occurred_at,value\nB2,2024-01-01T00:00:00Z,2\n")
    ingest_package(source,store)
    result=ManufacturingTools(store).query_data(sql="SELECT sum(value_number) FROM observations")
    assert result["rows"]==[[3.0]]

def test_cross_entity_context_respects_time(workspace):
    source,store=workspace
    (source/"events.csv").write_text("batch_id,equipment_id,available_at,event\nB1,EQ7,2024-03-01T00:00:00Z,cleaned\n")
    ingest_package(source,store)
    early=ManufacturingTools(store,as_of="2024-02-01T00:00:00Z")
    assert early.get_process_context(entity_id="B1")["related_entities"]==[]
    later=ManufacturingTools(store,as_of="2024-04-01T00:00:00Z")
    assert "EQ7" in later.get_process_context(entity_id="B1")["related_entities"]

def test_manufacturing_tools_expose_data_and_deterministic_analysis_operations(workspace):
    source,store=workspace
    (source/"data.csv").write_text("batch_id,result\nB1,7\n")
    ingest_package(source,store)
    tools=ManufacturingTools(store)
    assert {"inspect_data","infer_schema","reconcile_entities","normalize_measurements",
            "query_data","search_evidence","verify_evidence","extract_region",
            "get_process_context","get_state_at","summarize_series","calculate_metrics","align_series"} == set(tools.handlers())
    assert tools.search_evidence(query="B1")["evidence_ids"]

def test_zip_ingestion_rejects_traversal(workspace,tmp_path):
    _,store=workspace
    archive=tmp_path/"evil.zip"
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("../escape.csv","a\n1\n")
    with pytest.raises(ValueError): ingest_package(archive,store)

def test_zip_member_clock_does_not_reveal_document_early(workspace,tmp_path):
    _,store=workspace
    archive=tmp_path/"package.zip"
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("notes.txt","B1 reviewed later")
    assert ingest_package(archive,store)["observations"]>0
    assert ManufacturingTools(store,as_of="1990-01-01T00:00:00Z").get_state_at(
        as_of="1990-01-01T00:00:00Z")["records"]==[]

def test_unsupported_source_is_preserved_without_invented_extraction(workspace):
    source,store=workspace
    (source/"instrument.bin").write_bytes(b"opaque instrument export")
    result=ingest_package(source,store)
    assert result["files_preserved_unsupported"]==1
    item=store.visible_sources()[0]
    assert item["extraction_status"]=="preserved_unsupported"
    assert (store.originals/item["sha256"][:2]/(item["sha256"]+".bin")).read_bytes()==b"opaque instrument export"

def test_sampling_change_reindexes_same_source(workspace):
    source,store=workspace
    (source/"data.csv").write_text("batch_id,result\nB1,1\nB2,2\n")
    assert ingest_package(source,store,max_rows_per_file=1)["observations"]==2
    assert ingest_package(source,store,max_rows_per_file=2)["observations"]==4
    assert len(store.visible(limit=None))==4


def test_auto_backend_routes_each_zip_member_independently(tmp_path, monkeypatch):
    from io import BytesIO
    from pypdf import PdfWriter
    from PIL import Image
    from reportlab.pdfgen import canvas
    from src.manufacturing_data import ingest as ingestion

    text_pdf = BytesIO()
    page = canvas.Canvas(text_pdf)
    page.drawString(72, 720, "Manufacturing batch record with extractable printed text and a long description.")
    page.save()
    scanned_pdf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(scanned_pdf)
    image = BytesIO()
    Image.new("RGB", (100, 40), "white").save(image, format="PNG")
    archive = tmp_path / "mixed.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("data.csv", "batch_id,value\nB1,5\n")
        package.writestr("printed.pdf", text_pdf.getvalue())
        package.writestr("approval_form.pdf", text_pdf.getvalue())
        package.writestr("scanned_form.pdf", scanned_pdf.getvalue())
        package.writestr("handwritten_note.png", image.getvalue())
        package.writestr("notes.txt", "Operator note")

    calls = []
    def fake_document(source_id, rel, path, scope, available, backend):
        calls.append((rel, backend))
        yield Observation(observation_id=store.digest(f"{rel}|{backend}".encode())[:24],
                          source=SourceRef(source_id=source_id, path=rel, page=1, span="line:1"),
                          name="document_text", value_text=rel, available_at=available,
                          access_scope=scope, extraction_method=backend)

    monkeypatch.setattr(ingestion, "_document_observations", fake_document)
    store = ManufacturingStore(tmp_path / "store")
    result = ingest_package(archive, store)
    routes = {item["path"]: item for item in result["routes"]}
    assert result["errors"] == [] and result["files_indexed"] == 6
    assert routes["data.csv"]["selected_backend"] == "structured"
    assert routes["notes.txt"]["selected_backend"] == "text"
    assert routes["printed.pdf"]["selected_backend"] == "docling"
    assert routes["approval_form.pdf"]["selected_backend"] == "chandra"
    assert routes["scanned_form.pdf"]["selected_backend"] == "chandra"
    assert routes["handwritten_note.png"]["selected_backend"] == "chandra"
    assert ("printed.pdf", "docling") in calls
    assert store.visible_sources()[0]["routing"] is not None
    rerun = ingest_package(archive, store)
    assert rerun["unchanged"] == 6


def test_auto_backend_records_fallback_without_hiding_failure(tmp_path, monkeypatch):
    from io import BytesIO
    from reportlab.pdfgen import canvas
    from src.manufacturing_data import ingest as ingestion

    pdf = BytesIO()
    page = canvas.Canvas(pdf)
    page.drawString(72, 720, "Printed batch record with enough text to choose a document parser.")
    page.save()
    package = tmp_path / "package"
    package.mkdir()
    (package / "batch.pdf").write_bytes(pdf.getvalue())
    attempts = []
    original_document = ingestion._document_observations
    def fake_document(source_id, rel, path, scope, available, backend):
        attempts.append(backend)
        if backend == "docling":
            raise RuntimeError("Docling runtime unavailable")
        yield from original_document(source_id, rel, path, scope, available, backend)

    monkeypatch.setattr(ingestion, "_document_observations", fake_document)
    store = ManufacturingStore(tmp_path / "store")
    result = ingest_package(package, store)
    route = result["routes"][0]
    assert attempts == ["docling", "pypdf"]
    assert route["selected_backend"] == "pypdf" and route["fallback_used"]
    assert route["attempts"][0]["backend"] == "docling"
    assert store.visible_sources()[0]["routing"]["selected_backend"] == "pypdf"
    assert any(row["source_ref"]["page"] == 1 and "Printed batch record" in row["value_text"]
               for row in store.visible())

def test_cho_real_workbook_links_two_reactors(tmp_path):
    workbook=ROOT/"benchmarks/cho/raw/workbooks/EXP001_batch.xlsx"
    if not workbook.exists(): pytest.skip("authentic CHO workbook is not installed")
    package=tmp_path/"cho"
    package.mkdir()
    shutil.copyfile(workbook,package/workbook.name)
    store=ManufacturingStore(tmp_path/"store")
    result=ingest_package(package,store,max_rows_per_file=3)
    assert result["errors"]==[]
    entities={c["entity_id"] for c in ManufacturingTools(store).reconcile_entities()["candidates"]}
    assert {"EXP001/R01","EXP001/R02"}.issubset(entities)

def test_fresenius_real_package_batch_and_time(tmp_path):
    original=ROOT/"benchmarks/fresenius/raw_package"
    if not original.exists(): pytest.skip("Fresenius synthetic package is not installed")
    package=tmp_path/"fres"
    package.mkdir()
    for rel in ("batch_records/batch_records.csv","laboratory/lims_export.csv"):
        target=package/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(original/rel,target)
    store=ManufacturingStore(tmp_path/"store")
    result=ingest_package(package,store,max_rows_per_file=100)
    assert result["errors"]==[] and result["files_indexed"]==2
    tools=ManufacturingTools(store)
    assert any(c["entity_id"] for c in tools.reconcile_entities()["candidates"])
    assert tools.get_state_at(as_of="1900-01-01T00:00:00Z")["records"]==[]


def test_workflow_detection_evidence_testing_review_and_outcome(workspace, tmp_path):
    source, store = workspace
    (source / "status.csv").write_text(
        "batch_id,available_at,status\n"
        "B1,2024-01-02T00:00:00Z,action\n"
        "B2,2024-01-03T00:00:00Z,action\n"
        "B3,2024-05-03T00:00:00Z,critical\n"
    )
    ingest_package(source, store, access_scope="tenant_a")
    visible = store.visible(as_of="2024-02-01T00:00:00Z", scopes=("tenant_a",))
    status_ids = [row["id"] for row in visible if row["name"] == "status"]
    future = next(row["id"] for row in store.visible(scopes=("tenant_a",))
                  if row["name"] == "status" and row["entity_id"] == "B3")
    blackboards = BlackboardStore(tmp_path / "workflow-blackboards")
    blackboard = blackboards.load_or_create("case-1")
    blackboard.pending_evidence = [{"request_id": "ER-1", "status": "pending"}]
    blackboard.decision_branches = [{"decision_id": "D1", "pending_dependencies": ["ER-1"]}]
    blackboards.save(blackboard)
    workflow = ManufacturingInvestigationWorkflow(
        tmp_path / "workflow", store, scope="tenant_a", blackboards=blackboards)
    rollout = {"assessment": "Investigation opened", "evidence_ids": status_ids,
               "causal_hypotheses": [{"hypothesis_id": "H1", "statement": "Possible shared cause",
                                       "supporting_evidence_ids": status_ids,
                                       "contradicting_evidence_ids": [], "unknowns": ["Cause unknown"],
                                       "tests_or_observations_that_would_discriminate": ["inspect source"]}],
               "actions_now": [{"task_id": "TASK-1", "owner": "QA", "action": "Review"}],
               "pending_evidence_requests": [{"request_id": "ER-1"}]}
    report = workflow.record_rollout("case-1", "2024-02-01T00:00:00Z", "Investigate", rollout)
    assert report["triage"]["level"] == "L2"
    assert report["hypothesis_tests"][0]["status"] == "observational_support_only"
    assert not report["hypothesis_tests"][0]["root_cause_confirmed"]
    assert all(check["value_matches"] is True for check in report["hypothesis_tests"][0]["evidence_checks"])
    ordinary_id = next(row["id"] for row in visible if row["name"] == "available_at"
                       and row["entity_id"] == "B1")
    discovered = workflow.record_rollout("case-3", "2024-02-01T00:00:00Z", "Review B1",
                                         {"evidence_ids": [ordinary_id],
                                          "related_batches": ["B1"],
                                          "causal_hypotheses": []})
    assert discovered["triage"]["level"] == "L1"
    assert set(discovered["workflow_discovered_evidence_ids"]) == {
        row["id"] for row in visible if row["name"] == "status" and row["entity_id"] == "B1"}
    with pytest.raises(ValueError, match="unavailable"):
        workflow.record_rollout("case-2", "2024-02-01T00:00:00Z", "Investigate",
                                {**rollout, "evidence_ids": status_ids + [future]})
    with pytest.raises(PermissionError):
        workflow.decide_review("case-1", actor_id="operator", roles=("operator",),
                               role="qa", decision="approved")
    qa = workflow.decide_review("case-1", actor_id="qa-1", roles=("qa",),
                                role="qa", decision="approved")
    assert qa["approval"]["status"] == "pending"
    with pytest.raises(PermissionError, match="distinct reviewers"):
        workflow.decide_review("case-1", actor_id="qa-1", roles=("qa", "msat"),
                               role="msat", decision="approved")
    msat = workflow.decide_review("case-1", actor_id="msat-1", roles=("msat",),
                                  role="msat", decision="approved")
    assert msat["approval"]["status"] == "approved"
    updated = workflow.update_task("case-1", "TASK-1", actor_id="qa-1", roles=("qa",),
                                   status="completed")
    assert updated["tasks"][0]["status"] == "completed"
    outcome = workflow.record_outcome("case-1", actor_id="qa-1", roles=("qa",),
                                      finding="Confirmed status records; cause remains open",
                                      evidence_ids=status_ids)
    assert outcome["outcomes"][0]["human_recorded"]
    with pytest.raises(ValueError, match="evidence requests remain pending"):
        workflow.close("case-1", actor_id="qa-1", roles=("qa",))
    fulfilled = workflow.fulfill_evidence_request(
        "case-1", "ER-1", actor_id="qa-1", roles=("qa",), evidence_ids=status_ids,
        note="Records checked")
    assert fulfilled["evidence_requests"][0]["status"] == "fulfilled"
    assert blackboards.load("case-1").pending_evidence[0]["status"] == "fulfilled"
    assert blackboards.load("case-1").decision_branches[0]["pending_dependencies"] == []
    closed = workflow.close("case-1", actor_id="qa-1", roles=("qa",))
    assert closed["status"] == "closed"
    assert len(workflow.history("case-1")) == 7
