"""The worklist: everything waiting on one person, read from the records that own each item.

Host contracts only. Records are hand-made to exercise the rules; they are not manufacturing data.
"""
import json

import pytest
from fastapi.testclient import TestClient

from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.store import RecordStore
from tests.lifesci.test_engineering_conversation import fake_planner, send

AUTH = {'method': 'password'}


@pytest.fixture
def world():
    p = Platform(RecordStore(), providers={})
    for actor, role, site in (('owner', 'msat', 'S1'), ('colleague', 'msat', 'S1'), ('qa-lead', 'qa', 'S1'), ('qa-rev', 'qa_reviewer', 'S1'),
                              ('operator', 'operator', 'S1'), ('outsider', 'msat', 'S2'), ('wide', 'msat', None)):
        p.identity.assign_role('T', actor, role, site_id=site)
    return p


def who(p, actor):
    return p.identity.context_for('T', actor)


def lists(p, actor, site='S1'):
    return p.worklist.read(who(p, actor), site)


def titles(result, group):
    return [item['title'] for item in result[group]]


def evidence(p, actor='owner', rid='r1', site='S1', content=b'pH=7.1'):
    r = p.evidence.ingest(who(p, actor), source_system='LIMS', source_record_id=rid, content=content, media_type='text/plain',
                          site_id=site, event_time=None)
    return {'kind': 'evidence', 'id': r['evidence_id'], 'revision': r['revision'], 'site_id': site}


def propose(p, target, actor='owner'):
    return p.actions.propose(who(p, actor), target_system='quality-review', operation='close_deviation', target_id=target, payload={},
                             basis=[evidence(p, actor, rid=target)], rationale='Glucose in B matched A after the feed change.',
                             expected_result='The deviation is closed with the comparison attached.', owner_id=actor, site_id='S1')


# --- approvals ------------------------------------------------------------------------------------------------------

def test_a_proposal_reaches_its_approver_and_its_author_sees_where_it_stands(world):
    p = world
    first = propose(p, 'DEV-77')
    item, = lists(p, 'qa-lead')['needs_you']
    assert item['id'] == f"approval:{first['proposal_id']}" and item['title'] == 'Approve or decline: Close deviation · DEV-77'
    assert item['action'] == {'type': 'decide', 'proposal_id': first['proposal_id'], 'revision': 1, 'roles': ['qa'], 'recent_sign_in': True}
    assert item['proposal'] | {'constraints': []} == item['proposal'] and item['proposal']['rests_on'] == '1 source record'
    assert (item['proposal']['approvers'], item['proposal']['proposed_by'], item['by']) == ('QA', 'owner', 'owner')
    mine = lists(p, 'owner')
    assert titles(mine, 'in_progress') == ['Waiting for QA to approve: Close deviation · DEV-77'] and not mine['needs_you']
    for bystander in ('colleague', 'qa-rev', 'operator'):       # not theirs to approve, and not their proposal
        assert lists(p, bystander)['counts'] == {'needs_you': 0, 'in_progress': 0, 'done': 0}
    assert lists(p, 'outsider')['counts']['needs_you'] == 0       # another site's person, asking about this site

    # Decided through the action service, with exactly what the list handed over.
    p.actions.decide(who(p, 'qa-lead'), item['action']['proposal_id'], expected_revision=item['action']['revision'], decision='rejected',
                     role=item['action']['roles'][0], comment='The comparison covers one batch only.', authentication=AUTH)
    assert not lists(p, 'qa-lead')['needs_you']
    declined, = lists(p, 'owner')['done']
    assert declined['title'] == 'Declined: Close deviation · DEV-77' and declined['detail'] == 'QA: The comparison covers one batch only.'

    second = propose(p, 'DEV-78')
    p.actions.decide(who(p, 'qa-lead'), second['proposal_id'], expected_revision=1, decision='approved', role='qa', authentication=AUTH)
    # Nothing here will carry it out, so it is not listed as in progress: the approval is what happened, and the list says so.
    mine = lists(p, 'owner')
    assert not mine['in_progress'] and titles(mine, 'done')[0] == 'Approved: Close deviation · DEV-78'
    assert mine['done'][0]['detail'] == ('QA approved it. The approval is on record. Nothing here carries the action out; where it '
                                         'has to be done in another system, that is still to do.')
    assert not lists(p, 'qa-lead')['needs_you']                  # a role that has decided is not asked again
    with p.store.transaction('owner') as tx:                     # a connection at this site that may do exactly this
        tx.put('T', 'connector', 'c-qr', {'family': 'quality-review', 'site_id': 'S1', 'write_operations': ['close_deviation']},
               expected_revision=None, action='test')
        tx.put('T', 'connector', 'c-other', {'family': 'quality-review', 'site_id': 'S2', 'write_operations': ['close_deviation']},
               expected_revision=None, action='test')
    waiting, = lists(p, 'owner')['in_progress']                  # now something can act on it, so it is waiting on that
    assert waiting['title'] == 'Approved, not yet carried out: Close deviation · DEV-78'
    assert waiting['detail'] == ('Approval is not execution. A connection to quality-review can carry this out; it is complete only '
                                 'with a receipt from quality-review (now: queued).')
    with p.store.transaction('owner') as tx:                     # the same system, but not this operation
        tx.put('T', 'connector', 'c-qr', {'family': 'quality-review', 'site_id': 'S1', 'write_operations': ['place_hold']},
               expected_revision=1, action='test')
    assert not lists(p, 'owner')['in_progress'] and titles(lists(p, 'owner'), 'done')[0] == 'Approved: Close deviation · DEV-78'

    propose(p, 'DEV-79')
    evidence(p, rid='DEV-79', content=b'pH=7.4 (corrected)')      # the source it rests on is corrected
    assert [i['title'] for i in lists(p, 'owner')['needs_you']] == ['The evidence behind your proposal changed: Close deviation · DEV-79']
    assert not lists(p, 'qa-lead')['needs_you']                  # a stale proposal cannot be approved, so it is not offered


def test_a_proposal_drafted_by_the_assistant_in_the_background_says_so(world):
    from src.lifesci.roles import agent_context_for
    p = world
    p.identity.assign_role('T', 'lead', 'qa', site_id='S1')
    agent = agent_context_for(who(p, 'lead'), p.identity)
    drafted = p.actions.propose(agent, target_system='quality-review', operation='close_deviation', target_id='DEV-80', payload={},
                                basis=[evidence(p, 'owner', rid='DEV-80')], rationale='r', expected_result='e', owner_id='lead', site_id='S1')
    item = next(i for i in lists(p, 'lead')['needs_you'] if i['id'] == f"approval:{drafted['proposal_id']}")
    assert item['by'] == 'assistant' and item['proposal']['proposed_by'] == 'the assistant'


# --- requests -------------------------------------------------------------------------------------------------------

def test_a_request_is_listed_for_the_person_asked_then_its_reply_for_the_person_who_asked(world):
    p = world
    with p.store.transaction('t') as tx:
        tx.put('T', 'organization_member', 'colleague', {'email': 'carla@example.test'}, expected_revision=None, action='c')
    sent = p.assistant_routines.create_work_request(who(p, 'owner'), {
        'site_id': 'S1', 'owner_id': 'colleague', 'title': 'Missing lactate for batch C', 'description': 'Please send the lactate results for C.',
        'record_refs': [evidence(p)]})
    asked, = lists(p, 'colleague')['needs_you']
    assert asked['title'] == 'owner asks: Missing lactate for batch C' and asked['detail'] == 'Please send the lactate results for C.'
    assert asked['action'] == {'type': 'reply', 'request_id': sent['id'], 'revision': sent['revision']}
    assert titles(lists(p, 'owner'), 'in_progress') == ['Waiting for carla@example.test to reply: Missing lactate for batch C']
    assert lists(p, 'qa-lead')['counts'] == {'needs_you': 0, 'in_progress': 0, 'done': 0}   # a request is private to the two people

    p.assistant_routines.answer_work_request(who(p, 'colleague'), asked['action']['request_id'],
                                             {'expected_revision': asked['action']['revision'], 'reply': 'Not sampled on that run.'})
    assert not lists(p, 'colleague')['needs_you']
    mine = lists(p, 'owner')
    assert not mine['in_progress'] and [(i['title'], i['detail']) for i in mine['done']] == [
        ('carla@example.test replied: Missing lactate for batch C', 'Not sampled on that run.')]


def test_people_who_can_be_asked_are_colleagues_at_the_site_by_the_name_they_are_known_by(world):
    p = world
    with p.store.transaction('t') as tx:
        tx.put('T', 'organization_member', 'colleague', {'email': 'carla@example.test'}, expected_revision=None, action='c')
    p.identity.assign_role('T', 'left', 'msat', site_id='S1')
    p.identity.revoke_role('T', 'left', 'msat', site_id='S1')
    people = p.worklist.people(who(p, 'owner'), 'S1')
    assert {'id': 'colleague', 'label': 'carla@example.test'} in people and {'id': 'wide', 'label': 'wide'} in people
    assert not {'owner', 'outsider', 'left'} & {person['id'] for person in people}      # not yourself, another site, or someone who left


# --- the assistant --------------------------------------------------------------------------------------------------

@pytest.fixture
def seeded(monkeypatch):
    monkeypatch.setenv('ASSISTANT_LOOP', 'tools')
    p = Platform(RecordStore(), providers={})
    seed(p)
    return p, p.identity.context_for(TENANT, 'priya')


def test_a_question_from_the_assistant_waits_in_the_list_and_its_answer_moves_it_to_done(seeded):
    p, priya = seeded
    fake = fake_planner(p, [])
    model = p.gateway.registry.profiles['anthropic-opus'].model
    fake.scripts[model] = [{'content': 'One thing first.', 'tool_calls': [{'name': 'ask_user', 'arguments': {'question': 'Which batch do you mean?'}}]}]
    thread = p.engineering_conversations.create(priya, {})
    send(p, priya, thread, 'Forecast the batch')
    asked, = [i for i in p.worklist.read(priya, 'NF1')['needs_you'] if i['kind'] == 'question']
    assert asked['title'] == 'The assistant asks: Which batch do you mean?' and asked['by'] == 'assistant'
    assert asked['href'] == f"/home/?conversation={thread['id']}" and asked['action']['questions'] == ['Which batch do you mean?']
    assert json.dumps(asked).find('_loop') < 0 and '_transcript' not in json.dumps(asked)    # never the working transcript
    quinn = p.identity.context_for(TENANT, 'quinn')
    assert not [i for i in p.worklist.read(quinn, 'NF1')['needs_you'] if i['kind'] == 'question']   # a conversation is private

    # The list hands over what answering needs: the conversation and its current revision.
    fake.scripts[model] = ['B-200 is forecast to finish within its limits.']
    send(p, priya, {'id': asked['action']['conversation_id'], 'revision': asked['action']['revision']}, 'B-200')
    after = p.worklist.read(priya, 'NF1')
    assert not [i for i in after['needs_you'] if i['kind'] == 'question']
    assert 'The assistant answered: Forecast the batch' in titles(after, 'done')


def test_running_and_stopped_assistant_work_is_listed_as_such(seeded):
    p, priya = seeded
    thread = p.engineering_conversations.create(priya, {})
    queued = p.engineering_conversations.enqueue(priya, thread['id'], {'text': 'Compare the last two lots', 'expected_revision': thread['revision']})
    assert 'The assistant is working on: Compare the last two lots' in titles(p.worklist.read(priya, 'NF1'), 'in_progress')
    p.engineering_conversations._update_turn(priya, queued['turn_ids'][-1], status='agent_unavailable')
    stopped = p.worklist.read(priya, 'NF1')
    assert 'The assistant could not finish: Compare the last two lots' in titles(stopped, 'needs_you')
    assert not [t for t in titles(stopped, 'in_progress') if 'Compare the last two lots' in t]


# --- signals, quality events and deliveries ---------------------------------------------------------------------------

def test_an_open_signal_waits_for_someone_who_may_decide_it(world):
    p = world
    p.specifications.create(who(p, 'qa-lead'), site_id='S1', parameter='DO [%]', unit='%', low=30, high=80, critical_low=15, reason='Batch record BR-07')
    p.evidence.ingest(who(p, 'operator'), source_system='HISTORIAN', source_record_id='DO-1', content=json.dumps({'tag': 'DO', 'value': 10}).encode(),
                      media_type='application/json', site_id='S1', event_time=None,
                      metadata={'mapped': {'tag': 'DO', 'value': 10, 'equipment_id': 'BR-07', 'batch_id': 'B-117'}, 'units': {'value': '%'}})
    signal, = p.signals.list(who(p, 'qa-lead'), status='open')
    item, = [i for i in lists(p, 'qa-lead')['needs_you'] if i['kind'] == 'signal']
    assert item['id'] == f"signal:{signal['signal_id']}" and item['title'] == signal['rule'] and item['severity'] == signal['severity']
    assert item['action'] == {'type': 'acknowledge', 'signal_id': signal['signal_id']} and item['href'] == f"/signals/?id={signal['signal_id']}"
    assert 'not a confirmed deviation' in item['detail'] and 'observations' not in item and 'evidence_refs' not in item
    assert not [i for i in lists(p, 'qa-rev')['needs_you'] if i['kind'] == 'signal']        # may read, may not decide
    assert not [i for i in lists(p, 'outsider')['needs_you'] if i['kind'] == 'signal']
    p.signals.acknowledge(who(p, 'qa-lead'), item['action']['signal_id'])
    assert not [i for i in lists(p, 'qa-lead')['needs_you'] if i['kind'] == 'signal']


def test_a_quality_event_waits_on_whoever_holds_its_next_step(world):
    p = world
    owner, reviewer = who(p, 'owner'), who(p, 'qa-rev')
    ref = evidence(p)
    def step(ctx, operation, **data):
        w = p.quality_workflow.get(ctx, 'C1')
        return getattr(p.quality_workflow, operation)(ctx, 'C1', expected_revision=w['revision'], idempotency_key=f"{operation}-{w['revision']}", **data)
    p.quality_workflow.create(owner, case_id='C1', site_id='S1', title='pH excursion in B-117', owner_id='owner', qa_reviewer_id='qa-rev',
                              discovery_refs=[ref], idempotency_key='create-1')
    quality = lambda actor: [(i['title'], i['href']) for i in lists(p, actor)['needs_you'] if i['kind'] == 'quality']
    assert quality('owner') == [('pH excursion in B-117: decide how to handle it', '/quality/?case=C1')] and not quality('qa-rev')
    step(owner, 'evidence_request', request={'description': 'Calibration certificate for the probe', 'owner_id': 'colleague', 'required': True})
    assert quality('colleague') == [('Evidence requested for pH excursion in B-117', '/quality/?case=C1')]
    step(owner, 'transition', transition='submit_technical', reason='Ready for review')
    assert quality('owner')[0][0] == 'pH excursion in B-117: confirm the technical review to send it to QA'
    step(owner, 'transition', transition='submit_qa', reason='Technical review complete')
    assert quality('qa-rev') == [('pH excursion in B-117: approve the local preparation or return it', '/quality/?case=C1')] and not quality('owner')
    assert 'With qa-rev for QA review: pH excursion in B-117' in titles(lists(p, 'owner'), 'in_progress')
    step(reviewer, 'transition', transition='return', reason='Obtain the calibration certificate')
    assert quality('owner')[0][0] == 'pH excursion in B-117: QA returned it; read the reason and revise'


def test_delivery_checks_are_listed_from_counts_for_people_who_can_open_deliveries(world):
    p = world
    recent = p.worklist.read(who(p, 'wide'), 'S1')['as_of']
    rows = [
        {'id': 'r1', 'cmo': 'Acme', 'delivery_name': 'October delivery', 'status': 'complete', 'started_at': recent, 'completed_at': recent,
         'needs_review': 6, 'open_issues': 1, 'unconfirmed_layouts': 0},
        {'id': 'r2', 'cmo': 'Acme', 'delivery_name': None, 'status': 'running', 'started_at': recent, 'completed_at': None,
         'needs_review': 0, 'open_issues': 0, 'unconfirmed_layouts': 0},
        {'id': 'r3', 'cmo': 'Acme', 'delivery_name': 'September delivery', 'status': 'complete', 'started_at': recent, 'completed_at': recent,
         'needs_review': 0, 'open_issues': 0, 'unconfirmed_layouts': 0},
        {'id': 'r4', 'cmo': 'Acme', 'delivery_name': 'August delivery', 'status': 'interrupted', 'started_at': recent, 'completed_at': None,
         'needs_review': 0, 'open_issues': 0, 'unconfirmed_layouts': 0},
        {'id': 'r5', 'cmo': 'Northfield Biologics · demo ab12', 'delivery_name': 'Sample', 'status': 'complete', 'started_at': recent,
         'completed_at': recent, 'needs_review': 9, 'open_issues': 0, 'unconfirmed_layouts': 2},
        {'id': 'r6', 'cmo': 'Acme', 'delivery_name': 'Long ago', 'status': 'complete', 'started_at': '2020-01-01T00:00:00+00:00',
         'completed_at': '2020-01-01T00:10:00+00:00', 'needs_review': 0, 'open_issues': 0, 'unconfirmed_layouts': 0},
    ]
    asked = []
    p.worklist.deliveries = lambda tenant: asked.append(tenant) or rows
    mine = lists(p, 'wide')
    assert [(i['title'], i['href']) for i in mine['needs_you']] == [
        ('October delivery from Acme: 6 values and 1 issue to check', '/cmo/?run=r1'), ('The check of August delivery from Acme did not finish', '/cmo/?run=r4')]
    assert titles(mine, 'in_progress') == ['Checking Delivery from Acme'] and titles(mine, 'done') == ['Checked September delivery from Acme']
    assert asked == ['T']
    # Delivery records are organization-wide, so a site-restricted account is not shown them (it could not open them).
    assert lists(p, 'owner')['counts'] == {'needs_you': 0, 'in_progress': 0, 'done': 0} and asked == ['T']


# --- what the list says about itself --------------------------------------------------------------------------------

def test_a_source_that_cannot_be_read_is_named_and_the_rest_is_still_listed(world, monkeypatch):
    p = world
    propose(p, 'DEV-77')
    def broken(*args):
        raise RuntimeError('database unavailable')
        yield  # pragma: no cover
    monkeypatch.setattr(p.worklist, '_signals', broken)
    result = lists(p, 'qa-lead')
    assert result['unavailable'] == [{'source': 'signals', 'covers': 'open signals'}]
    assert len(result['needs_you']) == 1 and 'open signals' in result['covers'] and result['not_covered']


def test_api_returns_the_list_for_the_signed_in_person_and_lets_the_person_asked_reply(world):
    p = world
    sent = p.assistant_routines.create_work_request(who(p, 'owner'), {
        'site_id': 'S1', 'owner_id': 'colleague', 'title': 'Missing lactate', 'description': 'Please send it.', 'record_refs': [evidence(p)]})
    client = TestClient(create_app(p))
    h = lambda actor: {'X-Tenant-Id': 'T', 'X-Actor-Id': actor}
    body = client.get('/v1/worklist?site_id=S1', headers=h('colleague')).json()
    assert [i['action'] for i in body['needs_you']] == [{'type': 'reply', 'request_id': sent['id'], 'revision': sent['revision']}]
    assert client.post(f"/v1/work-requests/{sent['id']}/answer", headers=h('owner'), json={'expected_revision': sent['revision'], 'reply': 'x'}).status_code == 403
    assert client.post(f"/v1/work-requests/{sent['id']}/answer", headers=h('colleague'), json={'expected_revision': sent['revision'], 'reply': '  '}).status_code == 422
    answered = client.post(f"/v1/work-requests/{sent['id']}/answer", headers=h('colleague'), json={'expected_revision': sent['revision'], 'reply': 'Sent today.'})
    assert answered.status_code == 200 and answered.json()['status'] == 'answered'
    assert client.get('/v1/worklist?site_id=S1', headers=h('owner')).json()['done'][0]['detail'] == 'Sent today.'
    assert {person['id'] for person in client.get('/v1/worklist/people?site_id=S1', headers=h('owner')).json()['people']} >= {'colleague', 'qa-lead'}
    assert client.get('/v1/worklist?site_id=S1').status_code in (401, 403)


# --- a delivery is checked before anyone asks ------------------------------------------------------------------------

def test_a_published_delivery_is_checked_against_approved_requirements_and_its_drafted_request_waits_to_be_sent(world):
    from tests.lifesci.test_workflow_trial import delivery, glucose
    from src.lifesci.cmo_datasets import _prepare
    p, owner = world, who(world, 'owner')
    first = delivery(p, owner, glucose(), name='September delivery')
    _prepare(p, owner, first, 'S1')
    assert lists(p, 'owner')['counts'] == {'needs_you': 0, 'in_progress': 0, 'done': 0}     # nothing approved yet, so nothing was checked

    p.specifications.create(who(p, 'qa-lead'), site_id='S1', parameter='Glucose', unit='g/L', low=1, high=12, reason='batch record limits')
    clean = delivery(p, owner, glucose(), name='October delivery')
    _prepare(p, owner, clean, 'S1')
    done, = lists(p, 'owner')['done']
    assert done['title'] == 'Checked October delivery from Source lab against 1 approved requirement: nothing missing'
    assert done['href'] == f'/workbench/?datasets={clean}' and not lists(p, 'owner')['needs_you']

    p.specifications.create(who(p, 'qa-lead'), site_id='S1', parameter='Lactate', unit='g/L', high=3, reason='batch record limits')
    lacking = delivery(p, owner, glucose(batches=('C',)), name='November delivery')
    results = lambda: len(p.store.read().list('T', 'workspace_task_result'))
    before = results()
    _prepare(p, owner, lacking, 'S1')
    _prepare(p, owner, lacking, 'S1')                                                         # publishing again does not check again
    assert results() == before + 1
    item, = lists(p, 'owner')['needs_you']
    assert item['kind'] == 'missing_evidence' and item['title'] == 'November delivery from Source lab: 1 required item not in this delivery'
    assert 'Checked against 2 approved requirements when it was published. Missing: Lactate.' in item['detail']
    assert item['action']['type'] == 'send_request' and item['action']['title'] == 'Missing evidence: 1 item' and '- Lactate' in item['action']['description']
    assert not p.store.read().list('T', 'assistant_work_request')                              # drafted, never sent on its own
    assert lists(p, 'colleague')['counts'] == {'needs_you': 0, 'in_progress': 0, 'done': 0}  # the check belongs to the person who published

    # Sending is the person's own act, through the same endpoint the Workbench uses; then it is a request like any other.
    sent = p.workspace_tasks.request_evidence(owner, item['action']['result_id'], {'owner_id': 'colleague', 'title': item['action']['title'],
                                                                                    'description': item['action']['description']})
    after = lists(p, 'owner')
    assert not after['needs_you'] and titles(after, 'in_progress') == ['Waiting for colleague to reply: Missing evidence: 1 item']
    assert [i['action']['request_id'] for i in lists(p, 'colleague')['needs_you']] == [sent['id']]

    # A corrected delivery is a different delivery: the old check is no longer offered as if it described it.
    later = delivery(p, owner, glucose(batches=('D',)), name='December delivery')
    _prepare(p, owner, later, 'S1')
    assert [i['title'] for i in lists(p, 'owner')['needs_you']] == ['December delivery from Source lab: 1 required item not in this delivery']
    delivery(p, owner, glucose(batches=('D',), points=4), name='December delivery')
    assert not lists(p, 'owner')['needs_you']


def test_values_still_in_review_are_not_checked_on_anyones_behalf(world):
    from tests.lifesci.test_workflow_trial import delivery, glucose
    p, owner = world, who(world, 'owner')
    p.specifications.create(who(p, 'qa-lead'), site_id='S1', parameter='Lactate', unit='g/L', high=3, reason='batch record limits')
    pending = delivery(p, owner, glucose(), name='In review', provisional={'pending_values': 2, 'verified_package': False})
    assert p.worklist.prepare_delivery(owner, pending, 'S1') is None and lists(p, 'owner')['counts']['needs_you'] == 0


# --- what an approver is told about where a proposal came from ---------------------------------------------------------

def test_an_approver_sees_what_the_cited_result_says_although_the_result_stays_private(world):
    from tests.lifesci.test_workflow_trial import delivery, glucose
    p, owner = world, who(world, 'owner')
    result = p.workspace_tasks.execute(owner, {'site_id': 'S1', 'operation': 'compare', 'dataset_ids': [delivery(p, owner, glucose())],
                                               'parameter': 'Glucose', 'batches': ['A', 'B']})
    drafted = p.workspace_tasks.propose(owner, result['id'], {'operation': 'close_deviation', 'target_id': 'DEV-90', 'rationale': 'B tracks A.',
                                                               'expected_result': 'Closed.'})
    item = next(i for i in lists(p, 'qa-lead')['needs_you'] if i['id'] == f"approval:{drafted['proposal_id']}")
    says = item['proposal']['result_says']
    assert 'Glucose, B minus A: 3 matching measured times' in says and 'Largest difference -1 g/L at 0 h' in says and '**' not in says
    assert 'They describe a difference; they do not explain it.' in says
    with pytest.raises(PermissionError):                         # the saved result itself is still its author's
        p.workspace_tasks.get(who(p, 'qa-lead'), result['id'])
    # What is approved is unchanged: the account informs the approver and is not part of the approved content.
    from src.lifesci.actions import CONTENT_FIELDS
    assert 'origin' not in CONTENT_FIELDS
    # A colleague revises it to rest on a source record instead. The account described the old basis, so it is no longer shown,
    # and the approver is told who rewrote what they are asked to approve.
    p.actions.revise(who(p, 'colleague'), drafted['proposal_id'], expected_revision=1, changes={'basis': [evidence(p, 'colleague', rid='DEV-90')]},
                     reason='Rests on the source record.')
    revised = next(i for i in lists(p, 'qa-lead')['needs_you'] if i['id'] == f"approval:{drafted['proposal_id']}")
    assert revised['proposal']['result_says'] is None and revised['proposal']['rests_on'] == '1 source record'
    assert revised['proposal']['proposed_by'] == 'owner; revised by colleague' and revised['action']['revision'] == 2
    p.actions.decide(who(p, 'qa-lead'), drafted['proposal_id'], expected_revision=2, decision='approved', role='qa', authentication=AUTH)


def test_a_proposal_the_assistant_drafted_in_a_conversation_says_so_and_names_who_asked(world):
    p = world
    drafted = p.actions.propose(who(p, 'owner'), target_system='LIMS', operation='close_deviation', target_id='DEV-91', payload={},
                                basis=[evidence(p, rid='DEV-91')], rationale='r', expected_result='e', owner_id='owner', site_id='S1',
                                origin={'drafted_by': 'assistant', 'conversation_id': 'c1', 'turn_id': 't1'})
    item = next(i for i in lists(p, 'qa-lead')['needs_you'] if i['id'] == f"approval:{drafted['proposal_id']}")
    assert item['by'] == 'assistant' and item['proposal']['proposed_by'] == 'the assistant, asked by owner'
    # The person who asked for it still cannot approve it, and sees it as waiting on the approver.
    assert titles(lists(p, 'owner'), 'in_progress') == ['Waiting for QA to approve: Close deviation · DEV-91']
