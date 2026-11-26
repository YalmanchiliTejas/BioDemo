"""Small hand-checked fixture exercises reporting, not a performance claim."""
import csv
import importlib.util
import json

import pytest

from benchmarks.lyo_study.report import generate as report
from benchmarks.lyo_study.report import _group, _records


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def fixture(tmp_path):
    dataset, models, agents, output = [tmp_path/name for name in ('dataset', 'models', 'agents', 'report')]
    save(dataset/'protocol.json', {'version': 'fixture', 'issue': 'https://github.com/YalmanchiliTejas/BioDemo/issues/1'})
    model_rows, agent_rows = [], []
    for task in ('forecast', 'pretransfer'):
        for case in ('safe', 'overload'):
            save(dataset/'public'/case/(task+'.json'), {'case_id': case, 'task': task, 'config': {'load_vials': 1000}})
            outcomes = {'keep': {'completion_time_h': 10., 'first_capacity_h': 2. if case == 'overload' else None,
                                 'first_critical_h': None},
                        'cool': {'completion_time_h': 20., 'first_capacity_h': None, 'first_critical_h': None}}
            save(dataset/'evaluator'/case/(task+'.json'), {'family': 'fixture', 'outcomes': outcomes})
            for arm in ('B', 'C'):
                submission = {'completion_time_h': 12. if arm == 'B' else 10., 'thermal_warning': False,
                              'capacity_warning': case == 'overload', 'action_id': 'keep' if arm == 'B' else 'cool'}
                if case == 'overload' and arm == 'C':
                    submission.update(completion_time_h=None, thermal_warning=None)
                model_rows.append({'case_id': case, 'task': task, 'arm': arm, 'submission': submission,
                                   'score': {'completion_absolute_error_h': 999}, 'wall_seconds': .1})
            for arm in ('A', 'B', 'C'):
                if arm == 'B' and case == 'overload':
                    continue  # scheduled but never attempted
                submission = {'completion_time_h': 11., 'thermal_warning': None, 'capacity_warning': None,
                              'action_id': 'characterize'}
                if arm == 'A' and case == 'safe':
                    submission = None  # attempted execution failed
                agent_rows.append({'case_id': case, 'task': task, 'arm': arm, 'submission': submission,
                                   'status': 'failed' if submission is None else 'completed', 'wall_seconds': 1.,
                                   'error': 'Model call budget exhausted' if submission is None else None,
                                   'provider_cost_usd': None})
    save(models/'results.json', model_rows)
    save(agents/'results.json', {'protocol': {'case_ids': ['safe', 'overload'], 'tasks': ['forecast', 'pretransfer'],
                                           'model_calls': 4, 'wall_seconds': 120, 'tool_calls': 8},
                               'records': agent_rows, 'status': 'interrupted'})
    return dataset, models, agents, output


def group(summary, source, arm, task='forecast'):
    return next(row for row in summary['groups'] if (row['source'], row['arm'], row['task']) == (source, arm, task))


def test_report_recomputes_scores_with_explicit_coverage_censoring_and_failure_counts(fixture):
    summary = report(*fixture)
    b = group(summary, 'model', 'B')
    assert (b['planned'], b['attempted'], b['completed']) == (2, 2, 2)
    assert b['completion_eligible'] == 1
    assert b['completion_predictions'] == 1
    assert b['completion_mae_h'] == 2.  # ignore stale saved score 999
    assert b['thermal']['censored'] == 1
    assert b['capacity']['TP'] == 1
    assert b['unsafe_selections'] == 1
    assert b['feasible_selections'] == 1
    assert b['mean_throughput_vials_h'] == 50.  # unsafe selection earns zero
    assert b['hindsight_capacity_invalid_completion'] == 1
    c = group(summary, 'model', 'C')
    assert c['completion_mae_h'] == 0.
    assert c['mean_feasible_selection_regret_vials_h'] == 25.
    a = group(summary, 'agent', 'A')
    assert (a['attempted'], a['completed'], a['characterize']) == (2, 1, 1)
    assert a['thermal']['execution_failed'] == 1
    assert a['model_call_budget_exhaustions'] == 1
    assert a['mean_throughput_vials_h'] == 0.
    assert a['mean_feasible_selection_regret_vials_h'] is None
    ai_b = group(summary, 'agent', 'B')
    assert (ai_b['planned'], ai_b['attempted']) == (2, 1)
    assert ai_b['thermal']['not_attempted'] == 1
    assert summary['cost']['status'] == 'unknown'


def test_report_artifacts_are_separated_by_task_and_describe_synthetic_limits(fixture):
    # A sensitivity protocol changes context and budgets without changing truths.
    path = fixture[2]/'results.json'
    document = json.loads(path.read_text())
    document['protocol'].update(model_calls=8, wall_seconds=240,
                                scope='Post-hoc-motivated, prospectively frozen sensitivity analysis',
                                completion_policy='final turn submit only')
    save(path, document)
    for path in (fixture[0]/'evaluator').glob('*/*.json'):
        value = json.loads(path.read_text())
        value['outcomes']['keep']['first_capacity_h'] = None
        save(path, value)
    summary = report(*fixture)
    output = fixture[-1]
    assert len(summary['groups']) == 10
    assert (output/'summary.json').exists()
    rows = list(csv.DictReader((output/'per-case.csv').open()))
    assert len(rows) == 20
    assert {row['task'] for row in rows} == {'forecast', 'pretransfer'}
    text = (output/'report.md').read_text()
    assert 'shared constitutive' in text
    assert 'censored' in text
    assert 'Unknown' in text
    assert (output/'linkedin-draft.md').exists()
    brief = output/'case-study-brief.pdf'
    assert brief.exists()
    assert brief.read_bytes().startswith(b'%PDF-')
    if importlib.util.find_spec('pypdf'):
        from pypdf import PdfReader
        pages = PdfReader(brief).pages
        assert len(pages) == 4
        assert all('SYNTHETIC' in page.extract_text() for page in pages)
        assert 'Model B' in pages[1].extract_text()
        assert 'AI A' in pages[2].extract_text()
        assert '8 model calls' in pages[2].extract_text()
        assert '240 seconds' in pages[2].extract_text()
        assert 'sensitivity cannot be estimated' in ' '.join(pages[3].extract_text().split())
    assert 'four-model-call' not in (output/'linkedin-draft.md').read_text()
    assert 'not an independent' in text
    for task in ('forecast', 'pretransfer'):
        assert (output/f'{task}-comparison.png').stat().st_size > 1000
        assert (output/f'{task}-comparison.svg').stat().st_size > 1000
    pairs = [p for p in summary['paired_comparisons'] if p['task'] == 'forecast'
             and p['left'] == 'model:B' and p['right'] == 'model:C']
    assert pairs[0]['completion_mae_difference_h']['paired_cases'] == 1
    assert pairs[0]['completion_mae_difference_h']['mean_difference'] == -2.
    with pytest.raises(FileExistsError):
        report(*fixture)


def test_duplicate_results_rejected_instead_of_counted_twice(fixture):
    path = fixture[1]/'results.json'
    rows = json.loads(path.read_text())
    save(path, rows+[rows[0]])
    with pytest.raises(ValueError, match='duplicate'):
        report(*fixture)


def test_proxy_cost_ledger_keeps_unknown_reservations_separate_from_settled_estimates(fixture):
    ledger = fixture[2].parent/'campaign/modal-admission.jsonl'
    ledger.parent.mkdir()
    ledger.write_text('\n'.join(json.dumps(row) for row in [
        {'event': 'settled', 'ordinal': 1, 'conservative_cost_usd': .04, 'total_reserved_usd': .04},
        {'event': 'reserved', 'ordinal': 2, 'total_reserved_usd': .14},
        {'event': 'abandoned', 'ordinal': 2},
    ]))
    cost = report(*fixture)['cost']
    assert cost['status'] == 'proxy_estimate_with_unsettled_reservations'
    assert cost['settled_conservative_estimate_usd'] == .04
    assert cost['total_reserved_usd'] == .14
    assert cost['unsettled_reserved_usd'] == pytest.approx(.10)
    assert 'campaign' in cost['basis']


def test_warning_truth_support_includes_failed_and_unattempted_cases(fixture):
    dataset, models, agents, _output = fixture
    rows = _records(dataset, json.loads((models/'results.json').read_text()),
                    json.loads((agents/'results.json').read_text()))
    model = _group(rows, 'model', 'B', 'forecast')
    assert model['capacity']['truth_positive'] == 1
    assert model['capacity']['truth_negative'] == 1
    assert model['thermal']['truth_positive'] == 0
    assert model['thermal']['truth_negative'] == 1
    assert model['thermal']['truth_unknown_or_censored'] == 1
    # Outcomes do not disappear when an arm fails or never attempts the case.
    for arm in ('A', 'B'):
        agent = _group(rows, 'agent', arm, 'forecast')
        assert agent['capacity']['truth_positive'] == 1
        assert agent['capacity']['truth_negative'] == 1


def test_protocol_subset_limits_deterministic_controls_and_agent_comparisons(fixture):
    dataset, models, agents, _output = fixture
    document = json.loads((agents/'results.json').read_text())
    document['protocol'].update(case_ids=['safe'], tasks=['forecast'])
    document['records'] = [r for r in document['records'] if r['case_id'] == 'safe' and r['task'] == 'forecast']
    rows = _records(dataset, json.loads((models/'results.json').read_text()), document)
    assert len(rows) == 5
    assert {r['case_id'] for r in rows} == {'safe'}
    assert {r['task'] for r in rows} == {'forecast'}
    for source, arms in [('model', ('B', 'C')), ('agent', ('A', 'B', 'C'))]:
        for arm in arms:
            assert _group(rows, source, arm, 'forecast')['planned'] == 1
