"""Run-wide reuse of retrieved evidence and compact model-facing bridge responses."""
import importlib.util
import json
from pathlib import Path

import pytest

from src.prime_runtime.agent_view import agent_view
from tests.test_investigation_review import case, complete_report  # noqa: F401  (fixture)

CLIENT = Path(__file__).resolve().parents[1] / 'prime_skills/manufacturing_os/src/manufacturing_os/__init__.py'


def load_client():
    spec = importlib.util.spec_from_file_location('manufacturing_os_reuse_test', CLIENT)
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    return client


@pytest.fixture
def served(case, tmp_path, monkeypatch):
    bridge, _, prepared, rows = case
    bridge.start()
    config = tmp_path / 'bridge-config.json'
    config.write_text(json.dumps({'url': bridge.url, 'token': bridge.token}))
    monkeypatch.setenv('BIODEMO_PRIME_BRIDGE_CONFIG', str(config))
    monkeypatch.setenv('RLM_DEPTH', '0')
    try:
        yield bridge, prepared, rows, load_client()
    finally:
        bridge.close()


def test_identical_requests_from_any_agent_reuse_one_result(case):
    bridge, _, prepared, _ = case
    sid = prepared['source_versions'][0]['source_id']
    sql = f"SELECT id, value_number FROM observations WHERE source_id = '{sid}'"
    first = bridge.tool('query_data', {'sql': sql, 'limit': 5})
    calls = bridge.tool_calls
    again = bridge.tool('query_data', {'limit': 5, 'sql': sql}, caller_depth=1)
    assert again['cache_hit'] and bridge.tool_calls == calls
    assert again['evidence_ids'] == first['evidence_ids']
    assert bridge.tool_history[-1]['budget_admitted'] is False
    bridge.tool('query_data', {'sql': sql, 'limit': 6})
    assert bridge.tool_calls == calls + 1


def test_evidence_lookup_only_returns_records_already_exposed(case):
    bridge, _, prepared, rows = case
    sid = prepared['source_versions'][0]['source_id']
    packet = bridge.tool('evidence_packet', {'requests': [{'source_id': sid, 'limit': 3}]})
    exposed = packet['evidence_ids']
    unseen = 'never-retrieved-id'
    calls = bridge.tool_calls
    lookup = bridge.evidence(exposed + [unseen], caller_depth=1)
    assert lookup['evidence_ids'] == exposed and lookup['not_exposed'] == [unseen]
    assert {r['id'] for r in lookup['records']} == set(exposed)
    assert bridge.tool_calls == calls and lookup['budget_charged'] is False
    with pytest.raises(ValueError, match='500'):
        bridge.evidence(['x'] * 501)


def test_client_reuses_kernel_cache_and_shared_exposure(served):
    bridge, prepared, rows, client = served
    sid = prepared['source_versions'][0]['source_id']
    packet = client.evidence_packet([{'source_id': sid, 'limit': 3}])
    ids = packet['evidence_ids']
    calls = bridge.tool_calls
    local = client.evidence(ids)
    assert local['kernel_cache_hits'] == len(ids) and [r['id'] for r in local['records']] == ids
    # A fresh kernel (another agent) reads the same records from the run-wide set.
    sibling = load_client()
    shared = sibling.evidence(ids + ['never-retrieved-id'])
    assert shared['kernel_cache_hits'] == 0 and [r['id'] for r in shared['records']] == ids
    assert shared['not_exposed'] == ['never-retrieved-id']
    assert bridge.tool_calls == calls


def test_bridge_errors_are_short_and_unchained(served):
    _, _, _, client = served
    with pytest.raises(client.BridgeError) as raised:
        client.call_tool('drop_tables')
    assert 'not an allowed manufacturing data tool' in str(raised.value)
    assert raised.value.__context__ is None and raised.value.__cause__ is None


def test_report_responses_drop_echoes_and_keep_actionable_fields(served):
    bridge, prepared, _, client = served
    report = complete_report(prepared)
    report['coverage'] = report['coverage'][:1]
    full = bridge.validate_report(report, record=False)
    view = client.validate_report(report)
    assert view['report_status'] == full['report_status'] == 'incomplete'
    assert view['issues'] == full['issues'] and view['missing_unit_ids'] == full['missing_unit_ids']
    assert view['coverage'] == {'count': 1, 'by_status': {'investigated': 1}}
    assert set(view['budget']) < set(full['budget'])
    assert len(json.dumps(view)) < len(json.dumps(full, default=str))

    receipt = client.submit_report(complete_report(prepared))
    assert receipt['final_report_submitted'] is True
    assert receipt['report_status'] == bridge.result['report_status'] == 'complete_for_available_evidence'
    assert 'analysis_preparation' not in receipt and 'analysis_preparation' in bridge.result
    assert len(json.dumps(receipt)) < len(json.dumps(bridge.result, default=str)) / 4


def test_failing_checks_and_claims_survive_compaction():
    claims = {'status': 'automated_checks_failed', 'issues': [{'code': 'x', 'claim_id': 'C2'}],
              'claims': [{'claim_id': 'C1', 'statement': 'ok', 'issues': []},
                         {'claim_id': 'C2', 'statement': 'bad', 'issues': ['x']}]}
    result = {'status': 'needs_more_work', 'report_status': 'incomplete', 'final_report_submitted': False,
              'investigation_review': {'screened_unit_count': 1, 'coverage': [{'status': 'deferred'}],
                                       'issues': [{'code': 'coverage_unresolved'}], 'claim_verification': claims},
              'verification': {'status': 'requires_source_review',
                               'evidence_checks': {'a': {'value_matches': True}, 'b': {'value_matches': None}}},
              'next_step': 'Resolve verification flags.'}
    view = agent_view('/report', result)
    assert view['next_step'] == result['next_step']
    assert view['investigation_review']['issues'] == [{'code': 'coverage_unresolved'}]
    assert view['investigation_review']['claim_verification']['failing_claims'] == [{'claim_id': 'C2', 'issues': ['x']}]
    assert view['verification']['failing_evidence_checks'] == {'b': {'value_matches': None}}
    assert view['verification']['evidence_check_count'] == 2
