"""Perturbation, authored cases, judge calibration, correction harvest and judge wiring. No inference."""
import csv
import json
from pathlib import Path

import pytest

from benchmarks.agent_pilot import calibrate, harvest, runner
from benchmarks.agent_pilot.authored import load_dir
from benchmarks.agent_pilot.graders import grade_episode
from benchmarks.agent_pilot.perturb import TOKEN, perturb_suite
from benchmarks.agent_pilot.scenarios import build_suite
from tests.lifesci.test_conversation_instruction_provenance import platform, send

EXAMPLES = Path(__file__).resolve().parents[1] / 'benchmarks/agent_pilot/cases/examples'


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def test_rename_removes_every_old_identifier_except_the_grader_ban_list():
    for case in perturb_suite(build_suite('heldout', 3), ['rename_ids']):
        banned = set(case['truth']['banned_tokens'])
        visible = {k: v for k, v in case.items() if k != 'truth'}
        assert not banned & {t for s in _strings(visible) for t in TOKEN.findall(s)}, case['id']
        assert case['truth']['private_sentinels'][0].endswith(case['id'])


def test_remove_evidence_empties_required_sources_and_forbids_old_facts():
    base = {c['id']: c for c in build_suite('heldout', 3)}
    variants = perturb_suite(base.values(), ['remove_evidence'])
    assert variants and all(v['family'] not in ('memory', 'background') for v in variants)
    for v in variants:
        original = base[v['perturbation']['of']]
        required = [s for s in v['sources'] if s['id'] in v['truth']['required_read_ids']]
        assert all('no rows' in s['content'] for s in required)
        assert set(original['truth']['required_facts']) <= set(v['truth']['forbidden_claims'])
        assert not v['truth']['expected_proposals']


def test_distractor_decoy_may_be_named_but_not_used_as_the_answer():
    for v in perturb_suite(build_suite('heldout', 3), ['add_distractor']):
        decoy = v['sources'][-1]['content']
        assert not v['truth'].get('banned_tokens')  # naming the decoy to reject it is correct
        rule = v['truth']['forbidden_claims'][-1]
        assert 'presented as facts about' in rule and TOKEN.findall(rule.split(' are ')[0])[0] in decoy


def test_banned_token_and_runtime_grounding_checks():
    case = {'id': 'x', 'family': 'discovery', 'truth': {'required_read_ids': [], 'banned_tokens': ['D-11'],
            'expected_proposals': False, 'private_sentinels': []}}
    turn = {'status': 'completed', 'reply': 'D-11 shares R-77.', 'grounding': {'status': 'ungrounded', 'unsupported_numbers': [3.0]}}
    result = grade_episode(case, {'turns': [turn]}, None)
    assert result['checks']['banned_tokens']['passed'] is False
    assert result['checks']['runtime_grounding']['passed'] is False
    turn.update(reply='D-110 is unrelated.', grounding={'status': 'grounded'})
    result = grade_episode(case, {'turns': [turn]}, None)
    assert result['checks']['banned_tokens']['passed'] and result['checks']['runtime_grounding']['passed']


def test_authored_cases_refuse_to_grade_until_reviewed(tmp_path):
    with pytest.raises(ValueError, match='not reviewed'):
        load_dir(EXAMPLES)
    raw = json.loads((EXAMPLES / 'example-answerable-coa.json').read_text())
    (tmp_path / 'a.json').write_text(json.dumps({**raw, 'review_status': 'reviewed', 'reviewer': 'QA lead'}))
    [case] = load_dir(tmp_path)
    assert case['truth']['required_read_ids'] == [case['sources'][0]['id']]
    assert case['authored']['reviewer'] == 'QA lead'
    (tmp_path / 'a.json').write_text(json.dumps({**raw, 'review_status': 'reviewed', 'reviewer': 'x', 'surprise': 1}))
    with pytest.raises(ValueError, match='unknown keys'):
        load_dir(tmp_path)


def test_calibration_reports_judge_false_passes(tmp_path):
    for name, judge_pass in [('e1', True), ('e2', True), ('e3', False)]:
        d = tmp_path / 'results' / name
        d.mkdir(parents=True)
        (d / 'reference.json').write_text(json.dumps({'id': name, 'prompt': 'q', 'truth': {}}))
        (d / 'observation.json').write_text(json.dumps({'turns': [{'reply': 'r'}], 'source_revisions': []}))
        (d / 'result.json').write_text(json.dumps({'checks': {'semantic_judge': {'passed': judge_pass}}}))
    sheet = tmp_path / 'labels.csv'
    assert calibrate.export(tmp_path / 'results', sheet) == 3
    rows = list(csv.DictReader(sheet.open()))
    assert 'judge' not in ''.join(rows[0].keys())  # blind
    human = {'e1': 'PASS', 'e2': 'FAIL', 'e3': 'FAIL'}
    for r in rows:
        r['human_verdict'] = human[r['episode_id']]
    with sheet.open('w', newline='') as f:
        w = csv.DictWriter(f, calibrate.COLUMNS); w.writeheader(); w.writerows(rows)
    report = calibrate.score(tmp_path / 'results', sheet)
    assert report['confusion']['human_fail_judge_pass'] == 1
    assert report['judge_false_pass_rate'] == 0.5 and report['agreement'] == pytest.approx(2 / 3)


def test_harvest_turns_a_correction_into_an_unreviewed_candidate(tmp_path):
    db = tmp_path / 'store.sqlite'
    p, ctx, _ = platform(db, [{'reply': 'The supplied synthetic value is 9 mg/L.'}], initialize=True)
    first = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Synthetic assay\nSYN-1,9 mg/L')
    p.missions.record_correction(ctx, first['mission_id'], text='SYN-1 is 7 mg/L.', source_ref=None,
                                 claim_ref=None, rejects_hypothesis='A process cause is established.')
    [case] = list(harvest.candidates(p.store, ctx.tenant_id))
    assert case['review_status'] == 'unreviewed' and case['truth']['required_facts'] == []
    assert case['prompt'].startswith('Synthetic assay')
    assert case['notes']['user_correction'] == 'SYN-1 is 7 mg/L.'
    assert case['truth']['forbidden_claims'] == ['A process cause is established.']
    out = tmp_path / 'cases'
    out.mkdir()
    (out / 'c.json').write_text(json.dumps(case))
    with pytest.raises(ValueError):
        load_dir(out, allow_unreviewed=True)  # still unusable: a reviewer must write required_facts


def test_harvest_refuses_unignored_repo_output():
    with pytest.raises(SystemExit):
        harvest._safe_output(harvest.ROOT / 'backend' / 'benchmarks' / 'harvested-here')


def test_cross_family_judge_uses_its_own_prices_and_usage_shape():
    budget = runner.CampaignBudget(5, 10)
    judge = runner.judge_provider('anthropic', 'claude-sonnet-5-5', {'ANTHROPIC_API_KEY': 'k' * 20}, budget, 'ep', float('inf'))
    assert judge.purpose == 'judge' and judge.rates == (2.0, 10.0) and not judge.exact_model
    assert runner._usage({'input_tokens': 100, 'cache_read_input_tokens': 50, 'output_tokens': 7}) == \
        {'prompt_tokens': 150, 'completion_tokens': 7}
    with pytest.raises(ValueError, match='no registered price'):
        runner.judge_provider('openai', 'unknown-model', {}, budget, 'ep', float('inf'))
