"""Contract checks for synthetic evaluation inputs; never AI quality claims."""
import json
from collections import Counter

import pytest

from src.lifesci.container import Platform
from src.lifesci.store import RecordStore


def scenarios():
    from benchmarks.agent_pilot import scenarios as module
    return module


def test_suite_has_independent_heldout_cases_and_serializable_oracles():
    suite = scenarios().build_suite()
    assert Counter(c['family'] for c in suite) == {
        'discovery': 3, 'units': 3, 'revisions': 3, 'missing_evidence': 3,
        'scheduling': 3, 'approval': 3, 'memory': 3, 'background': 3,
    }
    assert len({c['id'] for c in suite}) == 24
    assert json.loads(json.dumps(suite)) == suite
    for case in suite:
        assert case['split'] == 'heldout'
        assert case['prompt'] and case['sources']
        assert set(case['truth']) >= {'required_read_ids', 'required_facts', 'forbidden_claims',
            'expected_proposals', 'expected_background', 'private_sentinels'}
        assert (case['truth']['required_read_ids'] or case['family'] == 'memory'
                or case['id'] == 'heldout-approval-3')
    development = scenarios().build_suite('development')
    for heldout, dev in zip(suite, development):
        # Different conditions and answer facts, beyond renamed records.
        assert heldout['condition'] != dev['condition']
        assert heldout['truth']['required_facts'] != dev['truth']['required_facts']
    assert scenarios().build_suite(count_per_family=1) == [suite[i] for i in range(0, 24, 3)]


@pytest.mark.parametrize('split,count', [('bogus', 3), ('heldout', 0), ('heldout', 4)])
def test_invalid_suite_requests_fail_explicitly(split, count):
    with pytest.raises(ValueError):
        scenarios().build_suite(split, count)


@pytest.mark.parametrize('family', ['discovery', 'units', 'revisions', 'missing_evidence',
    'scheduling', 'approval', 'memory', 'background'])
def test_seed_episode_preserves_real_evidence_and_scoped_private_controls(family):
    module = scenarios()
    case = next(c for c in module.build_suite() if c['family'] == family)
    p = Platform(RecordStore(), providers={})
    seeded = module.seed_episode(p, case)
    ctx, thread = seeded['ctx'], seeded['thread']
    assert ctx.actor_id == 'priya' and ctx.site_ids == frozenset({'NF1'})
    assert thread['owner_id'] == 'priya'
    for source in case['sources']:
        assert p.evidence.original(ctx, source['id']).decode() == source['content']
    for record in case['cases']:
        stored = p.cases.get(ctx, record['id'])
        assert stored['timeline'] and stored['site_id'] == 'NF1'
    index = p.engineering_conversations.workspace.search(ctx, thread, kinds=['evidence', 'case'])
    encoded = json.dumps(index)
    for sentinel in case['truth']['private_sentinels']:
        assert sentinel not in encoded
    with pytest.raises(PermissionError):
        p.evidence.original(ctx, f"PILOT:{case['id']}-private-site")
    # The hidden grading oracle must not become a source or conversation context.
    public_states = [r.state for kind in ['evidence', 'case', 'engineering_conversation']
        for r in p.store.read().list(ctx.tenant_id, kind)]
    assert 'required_facts' not in json.dumps(public_states)
    assert not p.store.read().list(ctx.tenant_id, 'proposal')
    assert not p.store.read().list(ctx.tenant_id, 'action_intent')


def test_known_answers_cover_conversion_history_and_background_negative_control():
    suite = scenarios().build_suite()
    units = [c for c in suite if c['family'] == 'units']
    assert units[0]['truth']['normalized_values'] == {'assay_g_L': 2.5, 'passes': False}
    history = [c for c in suite if c['family'] == 'revisions']
    assert history[0]['truth']['applicable_revision'] == '2'
    background = [c for c in suite if c['family'] == 'background']
    assert any(c['truth']['expected_background'] is False for c in background)
    assert any(c['truth']['expected_background'] is True for c in background)
    approvals = [c for c in suite if c['family'] == 'approval']
    assert sum(c['truth']['expected_proposals'] for c in approvals) == 1
    assert all(c['followups'] and c['restart'] for c in suite if c['family'] == 'memory')


def test_memory_needs_no_unrelated_read_and_background_has_precise_responsibility():
    suite = scenarios().build_suite()
    assert all(c['truth']['required_read_ids'] == [] for c in suite if c['family'] == 'memory')
    for case in suite:
        if case['family'] == 'background':
            assert 'WATCH-7' in case['background_objective']
            assert case['subscription_kinds'] == ['case', 'evidence']


def test_heldout_draft_oracle_uses_actual_supervisor_approval_policy():
    module = scenarios()
    case = next(c for c in module.build_suite() if c['family'] == 'approval')
    p = Platform(RecordStore(), providers={})
    seeded = module.seed_episode(p, case)
    draft = p.actions.propose(seeded['ctx'], target_system='LIMS',
        operation=case['truth']['proposed_operation'], target_id='Q-42', payload={},
        basis=[{'kind': 'evidence', 'id': case['sources'][0]['id'], 'revision': 1, 'site_id': 'NF1'}],
        rationale='Synthetic policy consistency check', expected_result='Reviewed retest request',
        owner_id='priya', site_id='NF1')
    assert case['truth']['required_approval_roles'] == draft['required_roles'] == ['supervisor']


def test_heldout_bypass_refusal_needs_no_source_read_and_preserves_development():
    module = scenarios()
    heldout = [c for c in module.build_suite() if c['family'] == 'approval'][2]
    development = [c for c in module.build_suite('development') if c['family'] == 'approval'][2]
    assert heldout['truth']['required_read_ids'] == []
    assert development['truth']['required_read_ids'] == ['PILOT:development-approval-3-authorization-status']
    assert heldout['truth']['expected_proposals'] is False
