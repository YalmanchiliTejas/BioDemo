"""Similar closed cases: ranked by shared identifiers then wording, advisory only."""
import pytest

from src.lifesci.container import Platform
from src.lifesci.store import RecordStore


def put(p, kind, rid, state):
    with p.store.transaction('fixture') as tx:
        tx.put('T', kind, rid, state, expected_revision=None, action='fixture')


def case(p, ctx, case_id, text, *, site='NF1', closed=True):
    p.cases.open(ctx, case_id, 'owner', 'qa', site)
    p.cases.add_timeline_event(ctx, case_id, '2024-01-01T00:00:00+00:00', text)
    if closed:
        with p.store.transaction('fixture') as tx:
            rec = tx.require('T', 'case', case_id)
            tx.put('T', 'case', case_id, {**rec.state, 'status': 'closed'}, expected_revision=rec.revision, action='fixture')


@pytest.fixture
def plant():
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role('T', 'owner', 'msat')
    ctx = p.identity.context_for('T', 'owner')
    case(p, ctx, 'DEV-1', 'Foaming on BR-03 during batch B-001')
    put(p, 'claim', 'CL-1', {'case_id': 'DEV-1', 'claim_class': 'hypothesis', 'text': 'Antifoam pump AF-2 failed',
                             'status': 'current', 'site_id': 'NF1', 'evidence_refs': []})
    put(p, 'proposal', 'PR-1', {'target_id': 'DEV-1', 'operation': 'create_work_order', 'status': 'approved',
                                'execution_status': 'confirmed', 'effectiveness': 'effective', 'site_id': 'NF1'})
    case(p, ctx, 'DEV-2', 'Low pH excursion on BR-07 during batch B-050')
    case(p, ctx, 'DEV-3', 'Foaming on BR03 during batch B-077', closed=False)
    case(p, ctx, 'DEV-4', 'Foaming on BR-03 during batch B-001', site='NF2')
    case(p, ctx, 'DEV-9', 'Foaming again on BR-03', closed=False)
    thread = p.engineering_conversations.create(ctx, {'site_id': 'NF1'})
    return p, ctx, thread


def test_closed_case_sharing_equipment_ranks_first_with_its_card(plant):
    p, ctx, thread = plant
    result = p.engineering_conversations.workspace.similar_cases(ctx, thread, case_id='DEV-9')
    top = result['records'][0]
    assert top['id'] == 'DEV-1'
    assert top['similarity']['shared_identifiers'] == ['BR03']
    assert top['label'] == 'similar, not established as applicable'
    assert top['card']['recorded_causes'] == ['Antifoam pump AF-2 failed']
    assert top['card']['outcomes'][0]['effectiveness'] == 'effective'
    assert 'case review' in top['card']['cause_status']
    assert result['closed_cases_searched'] == 2  # DEV-1, DEV-2; DEV-4 is another site
    assert result['open_cases_not_searched'] == 1  # DEV-3; DEV-9 is the query itself
    assert 'Among 2 closed cases searched' in result['coverage']
    assert 'approval' in result['reuse']


def test_open_cases_only_on_request(plant):
    p, ctx, thread = plant
    result = p.engineering_conversations.workspace.similar_cases(ctx, thread, case_id='DEV-9', include_open=True)
    assert 'DEV-3' in {r['id'] for r in result['records']}


def test_description_alone_finds_precedent(plant):
    p, ctx, thread = plant
    result = p.engineering_conversations.workspace.similar_cases(ctx, thread, text='foaming on BR-03')
    assert result['records'][0]['id'] == 'DEV-1'
    with pytest.raises(ValueError):
        p.engineering_conversations.workspace.similar_cases(ctx, thread, text='  ')


@pytest.fixture
def closable(plant):
    p, ctx, thread = plant
    p.identity.assign_role('T', 'qa-lead', 'qa')
    p.identity.assign_role('T', 'bot', 'agent', actor_kind='agent')  # agents may only hold the agent role
    return p, ctx, thread


def close_args(p, case_id, **extra):
    return {'root_cause': 'Antifoam pump AF-2 seal failure', 'actions_taken': 'Replaced seal; added PM check',
            'outcome': 'No foaming in next 5 batches', 'expected_revision': p.cases.get(p.identity.context_for('T', 'qa-lead'), case_id)['revision'],
            **extra}


def test_only_people_with_close_permission_close_a_case(closable):
    p, owner, thread = closable
    from src.lifesci.identity import AuthorizationError
    with pytest.raises(AuthorizationError):  # msat may propose and approve, but not close
        p.cases.close(owner, 'DEV-9', **close_args(p, 'DEV-9'))
    with pytest.raises(AuthorizationError):  # agents never close
        p.cases.close(p.identity.context_for('T', 'bot', actor_kind='agent'), 'DEV-9', **close_args(p, 'DEV-9'))
    closed = p.cases.close(p.identity.context_for('T', 'qa-lead'), 'DEV-9', **close_args(p, 'DEV-9'))
    assert closed['status'] == 'closed' and closed['closure']['closed_by'] == 'qa-lead'


def test_close_requires_fields_current_revision_and_open_case(closable):
    p, _, _ = closable
    qa = p.identity.context_for('T', 'qa-lead')
    from src.lifesci.store import ConflictError
    with pytest.raises(ValueError, match='root_cause'):
        p.cases.close(qa, 'DEV-9', **close_args(p, 'DEV-9', root_cause='  '))
    with pytest.raises(ConflictError):
        p.cases.close(qa, 'DEV-9', **close_args(p, 'DEV-9', expected_revision=1))
    p.cases.close(qa, 'DEV-9', **close_args(p, 'DEV-9', root_cause='not established'))
    with pytest.raises(ValueError, match='already closed'):
        p.cases.close(qa, 'DEV-9', **close_args(p, 'DEV-9'))


def test_closing_makes_the_case_a_precedent_with_its_closure_on_the_card(closable):
    p, ctx, thread = closable
    before = p.engineering_conversations.workspace.similar_cases(ctx, thread, text='foaming on BR-03')
    assert 'DEV-3' not in {r['id'] for r in before['records']}
    p.cases.close(p.identity.context_for('T', 'qa-lead'), 'DEV-3', **close_args(p, 'DEV-3'))
    after = p.engineering_conversations.workspace.similar_cases(ctx, thread, text='foaming on BR-03')
    card = next(r for r in after['records'] if r['id'] == 'DEV-3')['card']
    assert card['closure']['root_cause'] == 'Antifoam pump AF-2 seal failure'
    assert card['cause_status'] == 'as recorded at closure'
    assert after['closed_cases_searched'] == before['closed_cases_searched'] + 1
