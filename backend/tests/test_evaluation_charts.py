import json

from benchmark.case_comparison import ComparisonService
from benchmark.case_comparison.demo import build_demo
from benchmarks.common.engineering_work import GATES, PHASES, template


def test_recorded_signal_coverage_is_distinct_from_valid_citations():
    evaluation = ComparisonService().section('fresenius', 'evaluation')
    recall, precision = evaluation['charts']
    recall_values = {r['label']: r['value'] for r in recall['series'][1]['values']}
    precision_values = {r['label']: r['value'] for r in precision['series'][1]['values']}
    assert recall_values['FRE-04'] == 0.5
    assert precision_values['FRE-04'] == 1
    assert recall_values['FRE-05'] is None  # no critical signals: undefined, not 100%
    assert all(r['value'] is None for r in recall['series'][0]['values'])
    assert all(p['minutes'] is None for side in evaluation['effort'] for p in side['phases'])


def test_legacy_effort_is_not_relabelled_as_v2_measurement(tmp_path):
    ledger = template('cho')
    for run in ledger['runs']:
        run.update(package_sha256='a' * 64, task_spec_sha256='b' * 64,
                   output_ref='output.json', effort_complete=True)
        run['human_effort'] = {phase: {'person_minutes': 12, 'manual_steps': 2} for phase in PHASES}
        run['review'] = {'reviewer': 'reviewer', 'evidence_ref': 'review.json', 'gates': {g: True for g in GATES}}
    target = tmp_path / 'results/cho/engineering_work.json'
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(ledger))
    result = ComparisonService(tmp_path).section('cho', 'evaluation')
    assert result['outcomes'][1]['rate'] is None
    assert result['effort'][1]['hours'] is None
    assert len(result['effort'][1]['phases']) == 7
    assert all(p['minutes'] is None for p in result['effort'][1]['phases'])
    assert result['version'] == 'manufacturing-evaluation-v2'


def test_incident_excerpts_exclude_future_records_and_include_counter_evidence():
    demo = build_demo(ComparisonService().case('fresenius'))
    for stage in demo['stages']:
        for item in stage['source_records']:
            record = item['record']
            assert record.get('timestamp', record.get('opened_at')) <= stage['time']
    first_ids = {x['record'].get('id') for x in demo['stages'][0]['source_records']}
    assert 'LAB-0255' not in first_ids
    second_ids = {x['record'].get('id') for x in demo['stages'][1]['source_records']}
    assert {'LAB-0225', 'LAB-0255', 'LAB-0226', 'LAB-0227'} <= second_ids
    assert any(x['collection'] == 'complaints' for x in demo['stages'][-1]['source_records'])


def test_cho_source_excerpts_and_reference_results_are_not_os_scores():
    service = ComparisonService()
    demo = build_demo(service.case('cho'))
    assert demo['source_previews'][0]['preview'][0] == ['Time (h)', 'Dissolved CO2 (%-sat)', 'Status']
    assert demo['observation']['classification'] == 'observed'
    evaluation = service.section('cho', 'evaluation')
    assert evaluation['charts'][1]['series'][0]['values'][0]['value'] > 0.99
    assert evaluation['charts'][1]['series'][1]['values'][0]['value'] is None
