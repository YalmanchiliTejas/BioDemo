"""Measured-data boundaries and evaluator behavior, never agent-performance tests."""
from copy import deepcopy
from pathlib import Path
import csv
import json

import pytest

from benchmarks.tech_transfer.prepare import prepare, validate, workbook_rows, DATA
from benchmarks.tech_transfer.score import score_case


@pytest.fixture(scope='module')
def frozen(tmp_path_factory):
    root = tmp_path_factory.mktemp('measured-transfer') / 'study'
    prepare(root)
    return root


def test_stages_only_donor_and_no_full_sources(frozen):
    manifest = validate(frozen)
    assert len(manifest['case_ids']) == 5
    assert manifest['new_model_requests'] == 0
    assert manifest['isolation_enforced'] is False
    with (frozen / 'agent-input/TC-1-to-250L/donor-gas.csv').open() as f:
        donor = list(csv.DictReader(f))
    with (frozen / 'evaluator-only/receiving-gas.csv').open() as f:
        receiver = list(csv.DictReader(f))
    assert len(donor) == 4389 and len(receiver) == 3294
    assert {r['source_sheet'] for r in donor} == {'1 L culture'}
    assert {r['source_sheet'] for r in receiver} == {'250 L culture'}
    for path in (frozen / 'agent-input').rglob('*'):
        assert path.suffix not in ('.xlsx', '.xml', '.pdf', '.docx')
    # Prediction covariates are released only in phase2; measured answers are not.
    phase1 = json.loads((frozen / 'agent-input/SC-2-to-20L/evidence.json').read_text())
    assert 'receiver_water_kla' in str(phase1['prediction_requests'])
    assert '40.5' not in json.dumps(phase1)
    query = json.loads((frozen / 'phase2-input/SC-2-to-20L/characterization-query.json').read_text())
    assert query['agitation_rpm'] == 285
    assert 'kla_h_inv' not in query and 'aerated_power_density_kw_m3' not in query


def test_every_receiver_target_matches_a_real_workbook_cell(frozen):
    rows = workbook_rows(DATA / 'Paasikallio2017_CO2_data.xlsx')['250 L culture']
    refs = json.loads((frozen / 'evaluator-only/references.json').read_text())
    target = next(r for r in refs if r['case_id'] == 'TC-1-to-250L')
    for p in target['predictions']:
        observed = next(r for r in rows if r['time_h'] == p['time_h'])
        assert p['value'] == observed['carbon_dioxide']
        assert p['evidence'] == f"250 L culture!E{observed['source_row']}"
        assert p['unit'] == 'source_recorded_unit_unspecified'


def test_refuses_overwrite_and_detects_changed_input(frozen, tmp_path):
    with pytest.raises(ValueError, match='overwrite'):
        prepare(frozen)
    import shutil
    copy = tmp_path / 'changed'
    shutil.copytree(frozen, copy)
    (copy / 'agent-input/TC-1-to-250L/donor-gas.csv').write_text('replaced')
    with pytest.raises(ValueError, match='Frozen file changed'):
        validate(copy)


def reference(frozen):
    return json.loads((frozen / 'evaluator-only/references.json').read_text())[0]


def test_missing_forecasts_and_timing_never_become_success(frozen):
    ref = reference(frozen)
    result = score_case(ref, {'case_id': ref['case_id']})
    assert result['fact_accuracy'] == 0
    assert result['prediction_metrics']['water_kla']['coverage'] == 0
    assert result['prediction_metrics']['water_kla']['mae'] is None
    assert result['risk_scores']['recall'] is None
    assert result['observed_human_minutes'] is None
    assert result['time_saved_minutes'] is None


def test_units_nonfinite_and_duplicate_guards(frozen):
    ref = reference(frozen)
    prediction = {'id': 'receiver_water_kla', 'value': 40.5, 'unit': 'h^-1'}
    for value in (float('nan'), float('inf'), True):
        with pytest.raises(ValueError, match='finite'):
            score_case(ref, {'case_id': ref['case_id'], 'predictions': [dict(prediction, value=value)]})
    with pytest.raises(ValueError, match='unit'):
        score_case(ref, {'case_id': ref['case_id'], 'predictions': [dict(prediction, unit='mg/L')]})
    with pytest.raises(ValueError, match='Duplicate'):
        score_case(ref, {'case_id': ref['case_id'], 'predictions': [prediction, prediction]})
    with pytest.raises(ValueError, match='Unknown prediction'):
        score_case(ref, {'case_id': ref['case_id'], 'predictions': [dict(prediction, id='made_up')]})


def test_risk_precision_requires_complete_review_and_penalizes_duplicates(frozen):
    ref = reference(frozen)
    submission = {'case_id': ref['case_id'], 'risks': [{'id': i} for i in ('r1', 'r2', 'r3')]}
    key = ref['risks'][0]['id']
    review = {'case_id': ref['case_id'], 'reviewer': 'test fixture, not scientific reviewer', 'risks': [
        {'submission_id': 'r1', 'label': 'reference', 'reference_id': key, 'rationale': 'fixture'},
        {'submission_id': 'r2', 'label': 'reference', 'reference_id': key, 'rationale': 'duplicate fixture'},
        {'submission_id': 'r3', 'label': 'unsupported', 'rationale': 'unsupported fixture'}]}
    result = score_case(ref, submission, review)
    assert result['risk_scores']['precision'] == pytest.approx(1/3)
    assert result['risk_scores']['recall'] == pytest.approx(1/5)
    review['risks'].pop()
    with pytest.raises(ValueError, match='every submitted risk'):
        score_case(ref, submission, review)


def test_facts_require_units_and_citations(frozen):
    ref = reference(frozen)
    expected = ref['facts'][0]
    submission = {'case_id': ref['case_id'], 'facts': [dict(id=expected['id'], value=expected['value'], unit=expected['unit'])]}
    assert score_case(ref, submission)['fact_accuracy'] == 0
    submission['facts'][0]['citations'] = ['S1.equipment[1].working_volume_l']
    result = score_case(ref, submission)
    assert result['fact_accuracy'] == pytest.approx(1/len(ref['facts']))
    assert result['citation_support'] == 'not_automatically_adjudicated'


def test_baseline_uses_only_staged_covariates_and_no_extrapolation(frozen):
    from benchmarks.tech_transfer.baselines import predict, interpolate
    directory = frozen / 'agent-input/SC-2-to-20L'
    public = json.loads((directory / 'evidence.json').read_text())
    query = json.loads((frozen / 'phase2-input/SC-2-to-20L/characterization-query.json').read_text())
    prediction = predict(public, directory, query)
    assert prediction['model_requests'] == 0
    # Earlier published receiver measurement is40.5; source-only correlation
    # must not be silently fitted to it when generating this comparator.
    assert prediction['predictions'][0]['value'] == pytest.approx(35.53, abs=.01)
    assert interpolate([{'time_h': 0, 'carbon_dioxide': 1}, {'time_h': 2, 'carbon_dioxide': 5}], 1) == 3
    with pytest.raises(ValueError, match='extrapolate'):
        interpolate([{'time_h': 0, 'carbon_dioxide': 1}], 1)
