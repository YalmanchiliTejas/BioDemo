"""Protect the publication boundary using recorded, sanitized app receipts."""
import hashlib
import json
from pathlib import Path

import pytest

from frontend.scripts.export_live_app_study import summarize
from scripts.collect_live_app_demo import redact

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / 'frontend/public/case-study-results/live-app'
CAPTURES = [PUBLIC / 'pensim-attempt.json', PUBLIC / 'freeze-drying-final.json']


def test_actual_failed_requests_remain_in_denominator():
    data = summarize(CAPTURES)
    assert data['counts']['attempts'] == 4
    assert data['counts']['completed'] == 1
    assert data['counts']['blocked_or_unavailable'] == 3
    assert data['provider_billed_cost_usd'] is None


def test_completed_solver_does_not_become_a_feasible_process_claim():
    data = summarize(CAPTURES)
    result = data['results'][0]
    assert result['numerical_status'] == 'completed'
    assert result['minimum_capacity_margin_kg_h'] < 0
    assert any(v['constraint'] == 'vapor_capacity' for v in result['violations'])
    assert result['holdout']['points'] == 0
    assert any(c['status'] == 'not_applicable' and 'holdout' in c['id'] for c in data['checks'])


def test_capture_tampering_blocks_export(tmp_path):
    data = json.loads(CAPTURES[0].read_text())
    data['thread']['turns'][0]['status'] = 'completed'
    path = tmp_path / 'changed.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='changed'):
        summarize([path])


def test_pending_attempts_cannot_be_published_as_completed(tmp_path):
    data = json.loads(CAPTURES[0].read_text())
    data['thread']['turns'][0]['status'] = 'running'
    data['capture_sha256'] = hashlib.sha256(json.dumps({k: v for k, v in data.items() if k != 'capture_sha256'}, sort_keys=True).encode()).hexdigest()
    path = tmp_path / 'running.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='terminal'):
        summarize([path])


def test_nested_account_and_authentication_fields_are_removed():
    value = {'thread': {'owner_id': 'private-owner', 'reply': 'Synthetic result',
                        'metadata': [{'email': 'private@example.test', 'authorization': 'secret', 'value': 3}]},
             'access_token': 'secret', 'password': 'secret'}
    assert redact(value) == {'thread': {'reply': 'Synthetic result', 'metadata': [{'value': 3}]}}
