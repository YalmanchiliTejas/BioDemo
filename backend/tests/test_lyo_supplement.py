import json

import pytest

from benchmarks.lyo_study.supplement import report_balance


def write_ledger(path, rows):
    (path/'modal-admission.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))


def test_report_retains_interrupted_reservations_without_finished_events(tmp_path):
    write_ledger(tmp_path, [
        {'event':'reserved','ordinal':1,'reserved_usd':2.25},
        {'event':'settled','ordinal':1,'conservative_cost_usd':.03},
        {'event':'finished','ordinal':1},
        {'event':'reserved','ordinal':2,'reserved_usd':2.25},
    ])
    result=report_balance(tmp_path)
    assert result['original_held_usd']==pytest.approx(2.28)
    assert result['settled_estimate_usd']==.03
    assert result['unknown_reserved_usd']==2.25
    assert result['requests_without_finished_event']==[2]


def test_finished_without_usage_is_not_free(tmp_path):
    write_ledger(tmp_path,[{'event':'reserved','ordinal':1,'reserved_usd':2.25},
                           {'event':'finished','ordinal':1}])
    result=report_balance(tmp_path)
    assert result['original_held_usd']==2.25
    assert result['unknown_request_ordinals']==[1]


def test_settlement_without_reservation_is_rejected(tmp_path):
    write_ledger(tmp_path,[{'event':'settled','ordinal':1,'conservative_cost_usd':.03}])
    with pytest.raises(ValueError,match='reservation'):
        report_balance(tmp_path)
