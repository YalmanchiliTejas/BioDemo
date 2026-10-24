from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

import src.lifesci.integrations as integ
from benchmark.integration.connectors import JsonlConnector, RESTConnector
from benchmark.integration.models import ConnectorConfig, PullBatch, SourceRecord
from src.lifesci.actions import ActionService, DeliveryUnknown
from src.lifesci.evidence import EvidenceService
from src.lifesci.identity import AuthorizationError, IdentityService
from src.lifesci.ownership import OwnershipRegistry
from src.lifesci.store import NotFoundError, RecordStore

T = "tenant-a"
BASE = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)


def ts(minutes: float = 0) -> str:
    return (BASE + timedelta(minutes=minutes)).isoformat()


@pytest.fixture
def env():
    s = RecordStore()
    idn = IdentityService(s)
    for actor, role in [("svc1", "manufacturing_systems"), ("admin1", "admin"), ("qa1", "qa"),
                        ("exec1", "system_executor"), ("sc1", "supply_chain"), ("sc1", "supervisor")]:
        idn.assign_role(T, actor, role, site_id="S1")
    idn.assign_role(T, "agent1", "agent", actor_kind="agent")
    idn.assign_role("tenant-b", "admin-b", "admin")
    own = OwnershipRegistry(s)
    ev = EvidenceService(s, idn)
    return SimpleNamespace(
        s=s, idn=idn, own=own, ev=ev, act=ActionService(s, idn, own), intake=integ.IntakeService(s, ev),
        matrix=integ.ConnectorMatrix(s, idn), svc=idn.context_for(T, "svc1"), admin=idn.context_for(T, "admin1"),
        qa=idn.context_for(T, "qa1"), exec=idn.context_for(T, "exec1"),
        agent=idn.context_for(T, "agent1", actor_kind="agent"))


def rec(i: int, *, seq: int | None = None, minutes: float | None = None, system: str = "ELN", **extra) -> SourceRecord:
    when = ts(i if minutes is None else minutes)
    payload = {"id": f"r{i}", "timestamp": when, "sample_id": f"S-{i}", "value": 1.5, "unit": "g/L",
               "schema_version": "v1", **extra}
    if seq is not None:
        payload["sequence"] = seq
    return SourceRecord(f"r{i}", system, datetime.fromisoformat(when), payload, "S1")


class ListConnector:
    def __init__(self, cid: str, records: list[SourceRecord], redeliver: bool = False) -> None:
        self.connector_id, self.source_system, self.records, self.redeliver = cid, "ELN", records, redeliver

    def pull(self, checkpoint, limit=100):
        off = 0 if self.redeliver else int(checkpoint or 0)
        got = tuple(self.records[off:off + limit])
        return PullBatch(got, str(off + len(got)), off + len(got) < len(self.records))


CAPTURE = integ.builtin_templates()["capture"]


def evidence_revision(env, evidence_id: str) -> int:
    return env.s.read().require(T, "evidence", evidence_id).revision


# --- fake REST server ----------------------------------------------------------------------------


@pytest.fixture
def rest_server():
    state = SimpleNamespace(records=[], writes=[], token="tok", fail_write=None)
    for i in range(1, 7):
        if i == 4:
            continue
        state.records.append({"id": f"e{i}", "timestamp": ts(i), "sequence": i, "sample_id": f"S-{i}", "value": 2.0,
                              "unit": "g/L", "schema_version": "v1"})

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, doc):
            body = json.dumps(doc).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self):
            return self.headers.get("Authorization") == f"Bearer {state.token}"

        def do_GET(self):
            if not self._authorized():
                return self._send(401, {"error": "unauthorized"})
            q = parse_qs(urlparse(self.path).query)
            off, lim = int(q.get("checkpoint", ["0"])[0]), int(q["limit"][0])
            chunk = state.records[off:off + lim]
            self._send(200, {"records": chunk, "next_checkpoint": str(off + len(chunk)),
                             "has_more": off + len(chunk) < len(state.records)})

        def do_POST(self):
            if not self._authorized():
                return self._send(401, {"error": "unauthorized"})
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.writes.append(body)
            self._send(200, {"id": f"ack-{body['action_id']}", "timestamp": ts(0)})

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()
    server.server_close()


def rest_connector(state, token: str | None = "tok", write: bool = False) -> RESTConnector:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return RESTConnector(ConnectorConfig("generic-rest", "ELN", state.url, "/api/events",
                                         write_path="/api/actions" if write else None, headers=headers), timeout_seconds=5)


# --- LS-044 / LS-088 -------------------------------------------------------------------------------


def contract(**kw) -> integ.ConnectorContract:
    base = dict(system="ELN", vendor="generic", version="v1", transport="rest", read_operations=("pull_events",),
                owner="integration-team", auth="bearer", schema_version="v1",
                rate_limit={"requests_per_minute": 60}, error_semantics={"401": "not authorized", "5xx": "retry later"})
    return integ.ConnectorContract(**{**base, **kw})


def test_LS044_contract_lists_operations_limits_error_semantics_and_owner(env):
    row = env.matrix.register(env.admin, contract(limits=("max 1000 records per pull",)))
    assert row["read_operations"] == ["pull_events"] and row["owner"] == "integration-team"
    assert row["rate_limit"]["requests_per_minute"] == 60 and "401" in row["error_semantics"]
    assert row["status"] == "simulated" and row["contract_id"] == "ELN:generic:v1:rest"
    with pytest.raises(ValueError):
        integ.ConnectorContract(**{**contract().__dict__, "owner": ""}).validate()
    with pytest.raises(ValueError, match="write_auth"):
        contract(write_operations=("create_note",)).validate()
    with pytest.raises(ValueError, match="qualify"):
        contract(status="supported").validate()


def test_LS088_supported_only_after_every_scenario_passes(env):
    cid = env.matrix.register(env.admin, contract())["contract_id"]
    partial = {s: {"passed": True} for s in integ.REQUIRED_SCENARIOS if s != "gap"}
    row = env.matrix.qualify(env.qa, cid, partial)
    assert row["status"] == "simulated" and row["failed_scenarios"] == ["gap"]
    assert env.matrix.advertised(T) == []
    row = env.matrix.qualify(env.qa, cid, {s: {"passed": True} for s in integ.REQUIRED_SCENARIOS})
    assert row["status"] == "supported" and [r["contract_id"] for r in env.matrix.advertised(T)] == [cid]
    row = env.matrix.qualify(env.qa, cid, {**{s: True for s in integ.REQUIRED_SCENARIOS}, "mapping": False})
    assert row["status"] == "simulated" and env.matrix.advertised(T) == []


def test_LS088_unsupported_variants_are_unavailable_and_changes_require_requalification(env):
    env.matrix.declare_unavailable(env.admin, system="ERP", vendor="SAP", version="S/4HANA 2023",
                                   transport="rest", reason="no adapter or test endpoint")
    assert env.matrix.status_of(T, "ERP", "SAP", "S/4HANA 2023", "rest") == "unavailable"
    assert env.matrix.status_of(T, "MES", "Unknown", "1", "opcua") == "unavailable"
    with pytest.raises(ValueError):
        env.matrix.qualify(env.qa, "ERP:SAP:S/4HANA 2023:rest", {s: True for s in integ.REQUIRED_SCENARIOS})
    cid = env.matrix.register(env.admin, contract())["contract_id"]
    env.matrix.qualify(env.qa, cid, {s: True for s in integ.REQUIRED_SCENARIOS})
    env.matrix.register(env.admin, contract())  # unchanged contract keeps its qualification
    assert env.matrix.get(T, cid)["status"] == "supported"
    env.matrix.register(env.admin, contract(schema_version="v2"))
    assert env.matrix.get(T, cid)["status"] == "simulated"


def test_LS088_agents_and_non_approvers_cannot_qualify(env):
    cid = env.matrix.register(env.admin, contract())["contract_id"]
    with pytest.raises(AuthorizationError):
        env.matrix.qualify(env.agent, cid, {s: True for s in integ.REQUIRED_SCENARIOS})
    with pytest.raises(AuthorizationError):
        env.matrix.qualify(env.admin, cid, {s: True for s in integ.REQUIRED_SCENARIOS})


# --- LS-004 ---------------------------------------------------------------------------------------


def test_LS004_generic_rest_adapter_passes_scenarios_and_is_qualified(env, rest_server):
    connector = rest_connector(rest_server)
    results = integ.run_scenarios(contract(), connector, CAPTURE, unauthorized_connector=rest_connector(rest_server, token=None))
    assert all(r["passed"] for r in results.values()), results
    cid = env.matrix.register(env.admin, contract())["contract_id"]
    assert env.matrix.qualify(env.qa, cid, results)["status"] == "supported"


def test_LS004_unauthenticated_or_wrong_version_fails_qualification(env, rest_server):
    results = integ.run_scenarios(contract(schema_version="v9"), rest_connector(rest_server), CAPTURE)
    assert not results["version"]["passed"]
    bad = integ.run_scenarios(contract(), rest_connector(rest_server, token="wrong"), CAPTURE)
    assert not bad["authorized_read"]["passed"]
    cid = env.matrix.register(env.admin, contract())["contract_id"]
    assert env.matrix.qualify(env.qa, cid, bad)["status"] == "simulated"


def test_LS004_rest_sync_maps_and_exposes_the_source_gap(env, rest_server):
    out = env.intake.sync(env.svc, rest_connector(rest_server), CAPTURE, batch_size=2, site_id="S1")
    assert out["ingested"] == 5 and out["batches"] == 3 and out["checkpoint"] == "5"
    assert [(g["from_sequence"], g["to_sequence"]) for g in env.intake.gaps(env.svc, "generic-rest")] == [(4, 4)]
    again = env.intake.sync(env.svc, rest_connector(rest_server), CAPTURE, site_id="S1")
    assert again["ingested"] == 0 and again["duplicates"] == 0


def test_LS004_vendor_specific_adapters_are_marked_unavailable(env):
    for system, vendor in [("ERP", "SAP"), ("MES", "Siemens Opcenter"), ("QMS", "Veeva Vault")]:
        env.matrix.declare_unavailable(env.admin, system=system, vendor=vendor, version="any", transport="rest",
                                       reason="vendor-specific adapter not built or qualified")
    assert env.matrix.advertised(T) == []
    assert all(r["status"] == "unavailable" for r in env.matrix.matrix(T))


# --- LS-041 ---------------------------------------------------------------------------------------


def test_LS041_preview_maps_units_flags_unmapped_and_writes_nothing(env):
    before = len(env.s.events_since(T, 0))
    samples = [{"id": "a", "sample_id": " S-1 ", "value": "2.5", "unit": "g/L", "new_col": "x"},
               {"id": "b", "sample_id": "S-2", "value": "oops", "unit": "g/L"},
               {"id": "c", "sample_id": "S-3", "value": 1, "unit": "furlong"}]
    out = integ.preview_mapping(CAPTURE, samples)
    assert out["written"] is False and len(env.s.events_since(T, 0)) == before
    assert out["rows"][0]["fields"] == {"sample_id": "S-1", "measurement": 2500.0} and out["rows"][0]["units"]["measurement"] == "mg/L"
    assert out["unit_conversions"][0]["from_unit"] == "g/L" and out["unit_conversions"][0]["to_unit"] == "mg/L"
    assert {u["field"] for u in out["unmapped_fields"]} >= {"new_col", "value"}
    assert len(out["errors"]) == 2 and out["rows"][1]["unmapped"]["value"] == "oops"


def test_LS041_template_is_plain_config_and_validated():
    tpl = integ.ConnectorTemplate.from_dict({
        "template_id": "custom", "system": "LIMS", "record_type": "capture",
        "fields": [{"source": "t", "canonical": "temperature", "unit": "degC", "target_unit": "K", "transform": "float"}]})
    row = integ.preview_mapping(tpl, [{"id": "x", "t": "25"}])["rows"][0]
    assert row["fields"]["temperature"] == pytest.approx(298.15) and row["units"]["temperature"] == "K"
    bad = integ.ConnectorTemplate.from_dict({"template_id": "bad", "system": "X", "record_type": "c", "fields": [
        {"source": "a", "canonical": "a", "transform": "rot13"}, {"source": "b", "canonical": "b", "unit": "zorp"}]})
    assert len(bad.problems()) == 2


def test_LS041_test_connection_for_capture_material_and_maintenance_context(env, tmp_path):
    before = len(env.s.events_since(T, 0))
    samples = {
        "capture": {"id": "c1", "timestamp": ts(), "sample_id": "S-1", "instrument_id": "hplc-1", "value": 5, "unit": "g/L",
                    "operator": "op1"},
        "material": {"id": "m1", "timestamp": ts(), "lot_number": "L-100", "material_code": "glc", "expiry": "2027-01-31",
                     "qty": 500, "uom": "g", "status": "RELEASED"},
        "maintenance": {"id": "w1", "timestamp": ts(), "work_order": "WO-1", "equipment_id": "bio-1", "status": "Open",
                        "due_date": "2026-04-01T00:00:00+00:00", "downtime_h": 2, "description": "seal swap"},
    }
    for name, tpl in integ.builtin_templates().items():
        path = tmp_path / f"{name}.jsonl"
        path.write_text(json.dumps(samples[name]) + "\n")
        out = integ.test_connection(tpl, JsonlConnector(name, tpl.system, path, site_id="S1"))
        assert out["ok"] and out["wrote"] is False and out["records_sampled"] == 1, out
    material = integ.preview_mapping(integ.builtin_templates()["material"], [samples["material"]])["rows"][0]["fields"]
    assert material == {"lot": "L-100", "material_code": "GLC", "expiry": "2027-01-31", "quantity": 0.5, "status": "released"}
    maint = integ.preview_mapping(integ.builtin_templates()["maintenance"], [samples["maintenance"]])["rows"][0]["fields"]
    assert maint["downtime"] == 120.0 and maint["due_date"] == "2026-04-01"
    assert len(env.s.events_since(T, 0)) == before


def test_LS041_test_connection_reports_unreachable_source(rest_server):
    rest_server.url = "http://127.0.0.1:1"
    out = integ.test_connection(CAPTURE, rest_connector(rest_server))
    assert out["ok"] is False and out["stage"] == "connect"


# --- intake semantics ------------------------------------------------------------------------------


def test_intake_cursor_only_advances_after_the_batch_commits(env):
    good, bad = rec(1, seq=1), SourceRecord("r2", "ELN", BASE, {**rec(2, seq=2).payload}, "S9")
    conn = ListConnector("c1", [good, bad])
    with pytest.raises(AuthorizationError):
        env.intake.sync(env.svc, conn, CAPTURE)
    assert env.intake.cursor(T, "c1") is None and evidence_revision(env, "ELN:r1") == 1
    conn.records[1] = rec(2, seq=2)
    out = env.intake.sync(env.svc, conn, CAPTURE)
    assert out["ingested"] == 1 and out["duplicates"] == 1 and evidence_revision(env, "ELN:r1") == 1
    assert env.intake.cursor(T, "c1")["checkpoint"] == "2"


def test_intake_redelivery_is_duplicate_and_changed_payload_is_a_correction(env):
    conn = ListConnector("c2", [rec(1, seq=1), rec(2, seq=2)], redeliver=True)
    first = env.intake.sync(env.svc, conn, CAPTURE)
    second = env.intake.sync(env.svc, conn, CAPTURE)
    assert (first["ingested"], second["ingested"], second["duplicates"]) == (2, 0, 2)
    assert evidence_revision(env, "ELN:r1") == 1
    conn.records[0] = rec(1, seq=1, value=9.9)
    third = env.intake.sync(env.svc, conn, CAPTURE)
    assert third["corrections"] == 1 and third["duplicates"] == 1
    assert evidence_revision(env, "ELN:r1") == 2 and evidence_revision(env, "ELN:r2") == 1


def test_intake_detects_sequence_gaps_and_closes_them_when_filled(env):
    conn = ListConnector("c3", [rec(1, seq=1), rec(2, seq=2), rec(5, seq=5), rec(8, seq=8)])
    env.intake.sync(env.svc, conn, CAPTURE)
    assert [(g["from_sequence"], g["to_sequence"]) for g in env.intake.gaps(env.svc, "c3")] == [(3, 4), (6, 7)]
    conn.records += [rec(4, seq=4)]
    env.intake.sync(env.svc, conn, CAPTURE)
    assert [(g["from_sequence"], g["to_sequence"]) for g in env.intake.gaps(env.svc, "c3")] == [(3, 3), (6, 7)]
    conn.records += [rec(3, seq=3), rec(6, seq=6), rec(7, seq=7)]
    env.intake.sync(env.svc, conn, CAPTURE)
    assert env.intake.gaps(env.svc, "c3") == []
    assert len(env.intake.gaps(env.svc, "c3", status="filled")) >= 3


def test_intake_flags_late_data_and_keeps_event_time_apart_from_recorded_time(env):
    conn = ListConnector("c4", [rec(1, minutes=60), rec(2, minutes=120)])
    env.intake.sync(env.svc, conn, CAPTURE)
    conn.records.append(rec(3, minutes=10))
    out = env.intake.sync(env.svc, conn, CAPTURE)
    assert out["late"] == 1 and [x["source_record_id"] for x in env.intake.late(env.svc, "c4")] == ["r3"]
    state = env.s.read().require(T, "evidence", "ELN:r3").state
    assert state["event_time"] == ts(10) and state["recorded_at"] != state["event_time"] and state["metadata"]["late"] is True
    assert env.s.read().require(T, "evidence", "ELN:r1").state["metadata"]["late"] is False
    assert env.intake.sync(env.svc, conn, CAPTURE)["late"] == 0


def test_intake_schema_drift_is_a_mapping_issue_and_value_is_kept(env):
    conn = ListConnector("c5", [rec(1, seq=1, new_col="surprise")])
    out = env.intake.sync(env.svc, conn, CAPTURE)
    issues = env.intake.mapping_issues(env.svc, "c5")
    assert out["mapping_issues"] == 1 and issues[0]["field"] == "new_col" and issues[0]["issue"] == "unmapped_field"
    assert b"surprise" in env.ev.original(env.svc, "ELN:r1")
    assert env.s.read().require(T, "evidence", "ELN:r1").state["metadata"]["unmapped"] == {"new_col": "surprise"}
    env.intake.sync(env.svc, ListConnector("c5", [rec(1, seq=1, new_col="surprise")]), CAPTURE)
    assert env.intake.mapping_issues(env.svc, "c5")[0]["count"] == 1


def test_LS063_normalized_value_links_original_unit_time_basis_and_transform_version(env):
    env.intake.sync(env.svc, ListConnector("c6", [rec(1, seq=1)]), CAPTURE)
    vals = env.s.read().list(T, "normalized_value")
    assert len(vals) == 1
    v = vals[0].state
    assert v["evidence"]["id"] == "ELN:r1" and v["raw_value"] == 1.5 and v["raw_unit"] == "g/L"
    assert v["value"] == 1500.0 and v["unit"] == "mg/L" and v["time_basis"] == "event_time"
    assert v["transform_version"] == "capture@1"
    assert env.s.read().edges_to(T, "normalized_value", vals[0].id) == [("evidence", "ELN:r1", "derived_from")]
    env.intake.sync(env.svc, ListConnector("c6", [rec(1, seq=1)]), CAPTURE)
    assert len(env.s.read().list(T, "normalized_value")) == 1


# --- LS-023: webhook, MQTT, OPC UA, collector --------------------------------------------------------


def make_webhook(env, now=1_000_000.0):
    return integ.WebhookIntake(env.s, T, "wh1", "ELN", ["s3cret"], tolerance_seconds=300, now=lambda: now)


def signed(body: dict, secret="s3cret", at=1_000_000, delivery="d1"):
    raw = json.dumps(body).encode()
    return {"X-Timestamp": str(at), "X-Signature": integ.sign_payload(secret, at, raw), "X-Delivery-Id": delivery}, raw


def test_LS023_webhook_verifies_signature_tolerance_and_blocks_replay(env):
    wh = make_webhook(env)
    payload = {"id": "w1", "timestamp": ts(), "sequence": 1, "sample_id": "S-1", "value": 1, "unit": "g/L"}
    headers, raw = signed(payload)
    assert wh.handle(headers, raw)["status"] == "accepted"
    with pytest.raises(integ.WebhookRejected) as exc:
        wh.handle(headers, raw)
    assert exc.value.code == "replay"
    h2, r2 = signed(payload, secret="wrong", delivery="d2")
    with pytest.raises(integ.WebhookRejected) as exc:
        wh.handle(h2, r2)
    assert exc.value.code == "bad_signature"
    h3, r3 = signed(payload, at=1_000_000 - 3600, delivery="d3")
    with pytest.raises(integ.WebhookRejected) as exc:
        wh.handle(h3, r3)
    assert exc.value.code == "stale_timestamp"
    h4, r4 = signed(payload, delivery="d4")
    with pytest.raises(integ.WebhookRejected) as exc:
        wh.handle({k: v for k, v in h4.items() if k != "X-Signature"}, r4)
    assert exc.value.code == "missing_headers"
    assert wh.queue.count() == 1
    h5, r5 = signed({"id": "w2", "value": 1}, delivery="d5")
    with pytest.raises(integ.WebhookRejected) as exc:
        wh.handle(h5, r5)
    assert exc.value.code == "bad_payload"


def test_LS023_webhook_records_flow_through_intake_with_gaps(env):
    wh = make_webhook(env)
    for n, seq in enumerate([1, 2, 4], 1):
        h, raw = signed({"id": f"w{n}", "timestamp": ts(n), "sequence": seq, "sample_id": f"S-{n}", "value": 1, "unit": "g/L",
                         "schema_version": "v1"}, delivery=f"d{n}")
        wh.handle(h, raw)
    out = env.intake.sync(env.svc, wh, CAPTURE, site_id="S1")
    assert out["ingested"] == 3
    assert [(g["from_sequence"], g["to_sequence"]) for g in env.intake.gaps(env.svc, "wh1")] == [(3, 3)]


def make_messages(n=599, start=1, skip=range(301, 306), address="ns=2;s=Bioreactor1.Temp"):
    out = []
    for i in range(start, start + n):
        if i in skip:
            continue
        out.append(integ.TransportMessage(address, 30.0 + (i % 10), (BASE + timedelta(seconds=i)).isoformat(),
                                          "Good" if i % 50 else 0x80000000, i))
    return out


def telemetry_template():
    return integ.ConnectorTemplate("telemetry", "OPCUA", "telemetry", (integ.FieldMap("mean", "mean", transform="float"),),
                                   stream_field="stream", ignore_fields=(
                                       "address", "window_start", "window_end", "window_seconds", "count", "good_count",
                                       "min", "max", "quality_counts", "first_sequence", "last_sequence", "first_source_time",
                                       "last_source_time", "value", "quality", "source_timestamp", "backfilled", "late"))


def test_LS023_opcua_windows_are_bounded_and_carry_min_max_mean_count(env):
    client = integ.SimulatedTransportClient(supports_republish=True)
    adapter = integ.OpcUaAdapter(env.s, T, "opc1", "OPCUA", client, ["ns=2;s=Bioreactor1.Temp"], window_seconds=60, site_id="S1")
    msgs = make_messages()
    client.feed(msgs)
    assert adapter.poll_once()["messages"] == len(msgs)
    adapter.flush()
    batch = adapter.pull(None, 100)
    assert len(batch.records) == 10 and len(msgs) == 594
    first = batch.records[0].payload
    assert first["window_seconds"] == 60 and first["count"] == 59 and first["min"] == 30.0 and first["max"] == 39.0
    good = [m.value for m in msgs if (BASE + timedelta(seconds=1)).isoformat() <= m.source_timestamp < ts(1)
            and normalize_ok(m)]
    assert first["mean"] == pytest.approx(sum(good) / len(good)) and first["good_count"] == len(good)
    assert first["quality_counts"]["bad"] == 1
    assert sum(r.payload["count"] for r in batch.records) == 594
    assert adapter.message_to_record(msgs[0]).payload["address"] == "ns=2;s=Bioreactor1.Temp"


def normalize_ok(m) -> bool:
    return integ.normalize_quality(m.quality) == "good"


def test_LS023_telemetry_gaps_surface_and_opcua_retransmission_backfills(env):
    addr = "ns=2;s=Bioreactor1.Temp"
    client = integ.SimulatedTransportClient(supports_republish=True)
    adapter = integ.OpcUaAdapter(env.s, T, "opc2", "OPCUA", client, [addr], window_seconds=60, site_id="S1")
    client.feed(make_messages())
    client.feed(make_messages(n=5, start=301, skip=()), deliver=False)
    adapter.poll_once()
    adapter.flush()
    tpl = telemetry_template()
    env.intake.sync(env.svc, adapter, tpl, site_id="S1")
    assert [(g["from_sequence"], g["to_sequence"], g["stream"]) for g in env.intake.gaps(env.svc, "opc2")] == [(301, 305, addr)]
    assert adapter.backfill(addr, 301, 305) == 5
    env.intake.sync(env.svc, adapter, tpl, site_id="S1")
    assert env.intake.gaps(env.svc, "opc2") == []


def test_LS023_opcua_backfill_unavailable_when_server_lacks_retransmission(env):
    client = integ.SimulatedTransportClient(supports_republish=False)
    adapter = integ.OpcUaAdapter(env.s, T, "opc3", "OPCUA", client, ["n"])
    with pytest.raises(NotImplementedError):
        adapter.backfill("n", 1, 2)


def test_LS023_mqtt_adapter_converts_messages_to_source_records(env):
    client = integ.SimulatedTransportClient()
    adapter = integ.MqttAdapter(env.s, T, "mq1", "MQTT", client, ["plant/+/temp"], site_id="S1")
    assert client.subscribed == ["plant/+/temp"]
    m = integ.TransportMessage("plant/b1/temp", 36.6, ts(), "uncertain", 7)
    r = adapter.message_to_record(m)
    assert r.payload["address"] == "plant/b1/temp" and r.payload["quality"] == "uncertain" and r.payload["sequence"] == 7
    assert r.occurred_at == datetime.fromisoformat(ts()) and r.payload["source_timestamp"] == ts() and r.site_id == "S1"
    assert integ.normalize_quality(0) == "good" and integ.normalize_quality("BadSensorFailure") == "bad"


@pytest.mark.parametrize("cls", ["MqttAdapter", "OpcUaAdapter"])
def test_LS023_control_writes_are_prohibited(env, cls):
    client = integ.SimulatedTransportClient()
    adapter = getattr(integ, cls)(env.s, T, "x", "SYS", client, ["a"])
    for name in ("write", "publish", "write_value", "call_method", "set_value", "control", "send_command"):
        with pytest.raises(PermissionError, match="control writes prohibited"):
            getattr(adapter, name)("a", 1)
    with pytest.raises(PermissionError, match="control writes prohibited"):
        adapter.write_setpoint("a", 5)
    assert client.writes == []


def test_LS023_site_collector_spools_during_outage_and_flushes_in_order_without_loss(env):
    delivered: list[SourceRecord] = []
    link = SimpleNamespace(up=False)

    def uplink(record):
        if not link.up:
            raise ConnectionError("WAN down")
        delivered.append(record)

    buf = integ.SiteCollectorBuffer(env.s, T, "col1", uplink)
    for i in range(1, 6):
        buf.receive(rec(i, seq=i))
    assert buf.flush()["error"].startswith("ConnectionError") and delivered == [] and len(buf.pending()) == 5
    restarted = integ.SiteCollectorBuffer(env.s, T, "col1", uplink)
    restarted.receive(rec(6, seq=6))
    link.up = True
    out = restarted.flush()
    assert out == {"delivered": 6, "pending": 0, "error": None}
    assert [r.payload["sequence"] for r in delivered] == [1, 2, 3, 4, 5, 6]
    assert delivered[0].occurred_at == datetime.fromisoformat(ts(1))
    env.intake.sync(env.svc, ListConnector("col1-feed", delivered), CAPTURE)
    assert env.intake.gaps(env.svc, "col1-feed") == []


def test_LS023_collector_stops_at_first_failure_and_supports_injected_encryption(env):
    seen, fail_on = [], {"r3"}

    def uplink(record):
        if record.source_record_id in fail_on:
            raise TimeoutError("link flap")
        seen.append(record.source_record_id)

    key = 0x5A
    buf = integ.SiteCollectorBuffer(env.s, T, "col2", uplink, encrypt=lambda b: bytes(x ^ key for x in b),
                                    decrypt=lambda b: bytes(x ^ key for x in b))
    for i in range(1, 5):
        buf.receive(rec(i, seq=i))
    spool = env.s.read().list(T, "spool")
    assert all("record" not in r.state and "encrypted" in r.state for r in spool)
    assert buf.flush()["delivered"] == 2 and seen == ["r1", "r2"]
    fail_on.clear()
    assert buf.flush()["delivered"] == 2 and seen == ["r1", "r2", "r3", "r4"]


# --- LS-029 -----------------------------------------------------------------------------------------


def write_csv(path, rows):
    path.write_text("id,timestamp,sequence,sample_id,value,unit,schema_version\n" +
                    "".join(f"{i},{ts(i)},{i},S-{i},1.0,g/L,v1\n" for i in rows))


def test_LS029_file_drop_ingests_incrementally_with_gaps_and_source_timestamps(env, tmp_path):
    drop = tmp_path / "hplc"
    drop.mkdir()
    write_csv(drop / "run1.csv", [1, 2, 3, 5])
    conn = integ.FileDropConnector("hplc-drop", "CDS", drop, site_id="S1")
    tpl = integ.ConnectorTemplate.from_dict({**CAPTURE.to_dict(), "ignore_fields": ["source_file"]})
    first = env.intake.sync(env.svc, conn, tpl)
    assert first["ingested"] == 4
    assert [(g["from_sequence"], g["to_sequence"]) for g in env.intake.gaps(env.svc, "hplc-drop")] == [(4, 4)]
    ev = env.s.read().require(T, "evidence", "CDS:run1.csv:3" if False else "CDS:3").state
    assert ev["event_time"] == ts(3) and ev["recorded_at"] > ev["event_time"]
    assert env.intake.sync(env.svc, conn, tpl)["ingested"] == 0
    write_csv(drop / "run1.csv", [1, 2, 3, 5, 4, 6])
    third = env.intake.sync(env.svc, conn, tpl)
    assert third["ingested"] == 2 and third["duplicates"] == 4
    assert env.intake.gaps(env.svc, "hplc-drop") == []
    write_csv(drop / "run2.csv", [7, 8])
    assert env.intake.sync(env.svc, conn, tpl)["ingested"] == 2


def test_LS029_file_drop_formats_and_rejected_rows_are_visible(env, tmp_path):
    drop = tmp_path / "mixed"
    drop.mkdir()
    (drop / "a.json").write_text(json.dumps({"records": [{"id": "j1", "timestamp": ts(1), "sequence": 1}]}))
    (drop / "b.jsonl").write_text(json.dumps({"id": "l1", "timestamp": ts(2), "sequence": 2}) + "\n"
                                  + json.dumps({"id": "l2", "sequence": 3}) + "\n")
    conn = integ.FileDropConnector("mixed", "CDS", drop, site_id="S1")
    batch = conn.pull(None, 100)
    assert [r.source_record_id for r in batch.records] == ["j1", "l1"]
    assert conn.rejects and conn.rejects[0]["file"] == "b.jsonl" and "timestamp" in conn.rejects[0]["error"]
    small = integ.FileDropConnector("small", "CDS", drop, site_id="S1").pull(None, 1)
    assert small.has_more and len(small.records) == 1


def test_LS029_second_source_type_webhook_ingests_incrementally_with_gaps(env):
    wh = make_webhook(env)
    for n, seq in [(1, 1), (2, 2)]:
        h, raw = signed({"id": f"p{n}", "timestamp": ts(n), "sequence": seq, "sample_id": "S", "value": 1, "unit": "g/L"},
                        delivery=f"x{n}")
        wh.handle(h, raw)
    assert env.intake.sync(env.svc, wh, CAPTURE, site_id="S1")["ingested"] == 2
    h, raw = signed({"id": "p9", "timestamp": ts(9), "sequence": 9, "sample_id": "S", "value": 1, "unit": "g/L"}, delivery="x9")
    wh.handle(h, raw)
    out = env.intake.sync(env.svc, wh, CAPTURE, site_id="S1")
    assert out["ingested"] == 1 and env.intake.gaps(env.svc, "wh1")[0]["from_sequence"] == 3
    assert env.s.read().require(T, "evidence", "ELN:p9").state["event_time"] == ts(9)


# --- LS-043 -----------------------------------------------------------------------------------------


def test_LS043_reconcile_finds_missing_quantity_expiry_and_status_discrepancies():
    erp = [{"type": "master", "id": "GLC", "description": "Glucose", "uom": "kg"},
           {"type": "lot", "id": "L1", "qty": 10, "unit": "kg", "expiry": "2027-01-01", "status": "released"},
           {"type": "lot", "id": "L2", "qty": 5, "unit": "kg", "expiry": "2027-06-30", "status": "released"},
           {"type": "lot", "id": "L3", "qty": 1, "unit": "kg", "expiry": "2027-01-01", "status": "released"},
           {"type": "production_run", "id": "R1", "product": "mAb", "status": "complete", "qty": 100, "unit": "L"},
           {"type": "consumption", "id": "C1", "run": "R1", "lot": "L1", "qty": 2, "unit": "kg"}]
    local = [{"type": "master", "id": "GLC", "description": "Glucose", "uom": "kg"},
             {"type": "lot", "id": "L1", "qty": 9500, "unit": "g", "expiry": "2027-01-01T00:00:00+00:00", "status": "released"},
             {"type": "lot", "id": "L2", "qty": 4, "unit": "kg", "expiry": "2027-06-01", "status": "quarantine"},
             {"type": "production_run", "id": "R1", "product": "mAb", "status": "in_progress", "qty": 100, "unit": "L"},
             {"type": "lot", "id": "L9", "qty": 1, "unit": "kg", "expiry": "2028-01-01", "status": "released"},
             {"type": "consumption", "id": "C1", "run": "R1", "lot": "L1", "qty": 2000, "unit": "g"}]
    got = {(d["type"], d["id"], d["kind"]) for d in integ.ErpReconciler().reconcile(erp, local)}
    assert got == {("lot", "L1", "qty_mismatch"), ("lot", "L2", "qty_mismatch"), ("lot", "L2", "expiry_mismatch"),
                   ("lot", "L2", "status_mismatch"), ("lot", "L3", "missing_local"), ("lot", "L9", "missing_in_erp"),
                   ("production_run", "R1", "status_mismatch")}


def test_LS043_reconcile_accepts_source_records_and_can_persist(env):
    erp = [SourceRecord("e1", "ERP", BASE, {"type": "lot", "id": "L1", "qty": 3, "unit": "kg"})]
    recon = integ.ErpReconciler()
    found = recon.reconcile(erp, [{"type": "lot", "id": "L1", "qty": 3, "unit": "lb"}])
    assert found[0]["kind"] == "qty_mismatch"
    recon.persist(env.svc, env.s, "run-1", found)
    assert env.s.read().require(T, "erp_reconciliation", "run-1").state["count"] == 1


class ErpWriter:
    def __init__(self, mode: str) -> None:
        self.mode, self.applied = mode, {}

    def deliver(self, intent):
        if self.mode == "ok":
            self.applied[intent["idempotency_key"]] = {"erp_doc": "4500001"}
            return self.applied[intent["idempotency_key"]]
        if self.mode == "lost_response":
            self.applied[intent["idempotency_key"]] = {"erp_doc": "4500002"}
            raise DeliveryUnknown("response lost")
        raise DeliveryUnknown("timeout before delivery")

    def lookup(self, key):
        return self.applied.get(key)


def erp_intent(env, operation="reserve_material", assign=True):
    wb = integ.ErpWriteback(env.act, env.own)
    if assign:
        wb.configure_ownership(T, "S1", by="admin1", reason="ERP owns material reservations")
    r = env.ev.ingest(env.svc, source_system="ERP", source_record_id="L1", content=b'{"lot":"L1","qty":10}',
                      media_type="application/json", site_id="S1", event_time=ts())
    basis = [{"kind": "evidence", "id": r["evidence_id"], "revision": r["revision"], "site_id": "S1"}]
    prop = wb.propose(env.svc, operation=operation, lot_id="L1", run_id="R1", qty=2.0, unit="kg", basis=basis,
                      site_id="S1", owner_id="sc1", rationale="reserve for run R1")
    approver = env.idn.context_for(T, "sc1")
    out = env.act.decide(approver, prop["proposal_id"], expected_revision=1, decision="approved", role=prop["required_roles"][0])
    return wb, out["intent"]["intent_id"]


def test_LS043_write_back_uses_assigned_authority_approval_and_delivers(env):
    wb, intent_id = erp_intent(env)
    assert env.own.resolve(T, "reserve_material", "S1").system == "ERP"
    out = wb.dispatch(env.exec, intent_id, ErpWriter("ok"))
    assert out["status"] == "delivered" and out["receipt"] == {"erp_doc": "4500001"}


def test_LS043_write_back_without_ownership_assignment_is_blocked_and_nothing_is_sent(env):
    wb, intent_id = erp_intent(env, assign=False)
    writer = ErpWriter("ok")
    out = wb.dispatch(env.exec, intent_id, writer)
    assert out["status"] == "blocked" and "read-only projection" in out["reasons"][0] and writer.applied == {}


def test_LS043_agents_cannot_dispatch_or_approve_write_back(env):
    wb, intent_id = erp_intent(env)
    with pytest.raises(AuthorizationError):
        wb.dispatch(env.agent, intent_id, ErpWriter("ok"))
    with pytest.raises(ValueError):
        wb.propose(env.svc, operation="delete_lot", lot_id="L1", run_id="R1", qty=1, unit="kg", basis=[], site_id="S1",
                   owner_id="sc1", rationale="x")


def test_LS043_unknown_outcome_is_reconciled_by_lookup_not_resent(env):
    wb, intent_id = erp_intent(env, "consume_material")
    writer = ErpWriter("lost_response")
    out = wb.dispatch(env.exec, intent_id, writer)
    assert out["status"] == "unknown"
    assert wb.dispatch(env.exec, intent_id, writer)["status"] == "blocked"
    rec = wb.recover(env.exec, intent_id, writer)
    assert rec["status"] == "delivered" and rec["receipt"] == {"erp_doc": "4500002"}
    assert len(writer.applied) == 1


def test_LS043_unknown_outcome_with_no_destination_record_resolves_to_failed(env):
    wb, intent_id = erp_intent(env)
    writer = ErpWriter("timeout")
    assert wb.dispatch(env.exec, intent_id, writer)["status"] == "unknown"
    assert wb.recover(env.exec, intent_id, writer)["status"] == "failed"


def test_LS043_connector_writer_maps_timeouts_to_unknown_and_succeeds_over_http(env, rest_server):
    wb, intent_id = erp_intent(env)
    writer = integ.ConnectorWriter(rest_connector(rest_server, write=True), lambda key: None)
    out = wb.dispatch(env.exec, intent_id, writer)
    assert out["status"] == "delivered" and rest_server.writes[0]["operation"] == "reserve_material"
    assert rest_server.writes[0]["payload"] == {"lot": "L1", "run": "R1", "qty": 2.0, "unit": "kg"}

    class Boom:
        source_system = "ERP"

        def write(self, action):
            raise TimeoutError("read timed out")

    with pytest.raises(DeliveryUnknown):
        integ.ConnectorWriter(Boom(), lambda k: None).deliver({
            "idempotency_key": "k", "operation": "reserve_material", "target_id": "L1", "payload": {}, "approvers": [],
            "approval_ids": []})


# --- LS-042 subscriptions ---------------------------------------------------------------------------


def seed_events(env, n=4, tenant_ctx=None):
    ctx = tenant_ctx or env.svc
    for i in range(n):
        env.ev.ingest(ctx, source_system="ELN", source_record_id=f"s{i}", content=f"v{i}".encode(), media_type="text/plain",
                      site_id="S1", event_time=ts(i))


def test_LS042_signed_deliveries_replay_from_any_cursor(env):
    sub = env.matrix_sub = integ.SubscriptionService(env.s, env.idn)
    reg = sub.register(env.admin, url="https://example.test/hook", event_types=["evidence.*"], secret="shh")
    assert "secret" not in reg and reg["secret_fingerprint"]
    seed_events(env)
    d = sub.deliveries(env.admin, reg["subscription_id"], 0, timestamp=1000)
    assert len(d) == 4
    for item in d:
        assert item["headers"]["X-Signature"] == integ.sign_payload("shh", 1000, item["body"])
        assert json.loads(item["body"])["type"] == "evidence.ingested"
    replay = sub.deliveries(env.admin, reg["subscription_id"], d[1]["seq"], timestamp=1000)
    assert [x["body"] for x in replay] == [x["body"] for x in d[2:]]
    assert len({x["headers"]["X-Delivery-Id"] for x in d}) == 4


def test_LS042_subscriptions_are_tenant_scoped_and_filtered(env):
    sub = integ.SubscriptionService(env.s, env.idn)
    reg = sub.register(env.admin, url="https://example.test/a", event_types=["evidence.ingested"], secret="k", site_id="S1")
    seed_events(env, 2)
    env.ev.ingest(env.idn.context_for("tenant-b", "admin-b"), source_system="ELN", source_record_id="b1", content=b"x",
                  media_type="text/plain", site_id=None, event_time=None)
    assert [json.loads(d["body"])["aggregate"]["id"] for d in sub.deliveries(env.admin, reg["subscription_id"])] == ["ELN:s0", "ELN:s1"]
    env.s.read()
    with pytest.raises(NotFoundError):
        sub.deliveries(env.idn.context_for("tenant-b", "admin-b"), reg["subscription_id"])
    other = sub.register(env.idn.context_for("tenant-b", "admin-b"), url="https://example.test/b", event_types=["*"], secret="k2")
    ids = {json.loads(d["body"])["aggregate"]["id"] for d in sub.deliveries(env.idn.context_for("tenant-b", "admin-b"), other["subscription_id"])}
    assert ids >= {"ELN:b1"} and not any(i.startswith("ELN:s") for i in ids)
    with pytest.raises(AuthorizationError):
        sub.register(env.agent, url="https://example.test/x", event_types=["*"], secret="z")


def test_LS042_push_cursor_advances_only_past_accepted_deliveries(env):
    sub = integ.SubscriptionService(env.s, env.idn)
    reg = sub.register(env.admin, url="https://example.test/h", event_types=["evidence.*"], secret="k")
    seed_events(env, 3)
    got: list[bytes] = []
    calls = {"n": 0}

    def flaky(url, body, headers):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ConnectionError("receiver down")
        got.append(body)

    first = sub.deliver(env.admin, reg["subscription_id"], flaky)
    assert first["delivered"] == 1 and first["failed_at"] is not None
    second = sub.deliver(env.admin, reg["subscription_id"], flaky)
    assert second["delivered"] == 2 and second["failed_at"] is None
    assert [json.loads(b)["aggregate"]["id"] for b in got] == ["ELN:s0", "ELN:s1", "ELN:s2"]
