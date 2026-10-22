"""Specialist checkpoints survive later saves; imports replace lead placeholders; closing windows."""
import time

import pytest

from src.prime_runtime.bridge import finalization_reserve
from src.prime_runtime.coordination import merge_subreport
from tests.test_investigation_review import case, complete_report  # noqa: F401  (fixture)


def test_later_specialist_save_keeps_earlier_findings(case):
    bridge, _, prepared, _ = case
    full = complete_report(prepared)
    full['subreport_id'] = 'specialist-1'
    bridge.submit_subreport(full, caller_depth=1)
    summary = {'subreport_id': 'specialist-1', 'assessment': 'Short summary for the lead.',
               'open_questions': ['Recipe records unavailable.', 'Controller logs out of scope.']}
    bridge.submit_subreport(summary, caller_depth=1)
    saved = next(s for s in bridge.subreports if s['subreport_id'] == 'specialist-1')
    assert saved['observed_facts'] == full['observed_facts']
    assert len(saved['coverage']) == len(full['coverage'])
    assert saved['assessment'] == 'Short summary for the lead.'
    assert saved['open_questions'] == ['Design intent remains unverified.', 'Recipe records unavailable.', 'Controller logs out of scope.']


def test_merge_replaces_resubmitted_records_and_keeps_saved_assessment():
    saved = {'assessment': 'Saved.', 'hypotheses': [{'hypothesis_id': 'H1', 'statement': 'old'}],
             'tasks': [{'owner': 'QA'}]}
    merged = merge_subreport(saved, {'hypotheses': [{'hypothesis_id': 'H1', 'statement': 'new'},
                                                    {'hypothesis_id': 'H2', 'statement': 'added'}]})
    assert [h['statement'] for h in merged['hypotheses']] == ['new', 'added']
    assert merged['assessment'] == 'Saved.' and merged['tasks'] == [{'owner': 'QA'}]


def test_lead_checkpoints_are_still_replaced(case):
    bridge, _, prepared, _ = case
    report = complete_report(prepared)
    bridge.submit_subreport({**report, 'subreport_id': 'lead-preflight-checkpoint'}, caller_depth=0)
    bridge.submit_subreport({**report, 'subreport_id': 'lead-preflight-checkpoint', 'observed_facts': []}, caller_depth=0)
    saved = next(s for s in bridge.subreports if s['subreport_id'] == 'lead-preflight-checkpoint')
    assert saved['observed_facts'] == []


def test_imported_reviews_replace_lead_placeholders_but_specialists_cannot_silently_disagree(case):
    bridge, _, prepared, _ = case
    report = complete_report(prepared)
    first = report['candidate_reviews'][0]
    bridge.save_progress({'candidate_reviews': [{**first, 'reason': 'pending'}]})
    scoped = {'assessment': 'Candidate reviews.', 'candidate_reviews': report['candidate_reviews'],
              'evidence_ids': report['evidence_ids']}
    bridge.submit_subreport({**scoped, 'subreport_id': 'specialist-1'}, caller_depth=1)
    assembled = bridge.assemble_report(subreport_ids=['specialist-1'])
    review = next(r for r in assembled['report']['candidate_reviews'] if r['candidate_id'] == first['candidate_id'])
    assert review['reason'] == first['reason']
    assert {'section': 'candidate_reviews', 'id': first['candidate_id'], 'subreport_id': 'specialist-1'} in assembled['replaced_draft_entries']
    other = {**scoped, 'subreport_id': 'specialist-2',
             'candidate_reviews': [{**first, 'reason': 'A different specialist conclusion.'}]}
    bridge.submit_subreport(other, caller_depth=1)
    with pytest.raises(ValueError, match="specialist-1 and specialist-2"):
        bridge.assemble_report(subreport_ids=['specialist-1', 'specialist-2'])


def test_synthesis_window_scales_and_specialists_close_first(case):
    bridge, _, prepared, _ = case
    assert finalization_reserve(1800) == 300 and finalization_reserve(900) == 153 and finalization_reserve(300) == 90
    bridge.time_budget_seconds = 1800
    bridge.finalization_reserve_seconds = finalization_reserve(1800)
    bridge.started_monotonic = time.monotonic() - (1800 - 360)
    assert bridge.budget(0)['phase'] == 'investigation'
    assert bridge.budget(1)['phase'] == 'finalization'
    sid = prepared['source_versions'][0]['source_id']
    refused = bridge.tool('evidence_packet', {'requests': [{'source_id': sid, 'limit': 2}]}, caller_depth=1)
    assert refused['status'] == 'finalization_required' and 'submit_subreport' in refused['next_step']
    assert bridge.tool('evidence_packet', {'requests': [{'source_id': sid, 'limit': 2}]})['packets']
