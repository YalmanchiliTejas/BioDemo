"""Standing rules and corrections outlive a single conversation; only people with authority activate rules."""
import pytest

from src.lifesci.container import Platform
from src.lifesci.ids import iso, utc_now
from src.lifesci.store import RecordStore


@pytest.fixture
def p():
    platform = Platform(RecordStore(), providers={})
    platform.identity.assign_role('T', 'ana', 'msat', site_id='NF1')
    platform.identity.assign_role('T', 'ben', 'msat', site_id='NF1')
    platform.identity.assign_role('T', 'op', 'operator', site_id='NF1')
    platform.identity.assign_role('T', 'qa1', 'qa', site_id='NF1')
    platform.identity.assign_role('T', 'qa-global', 'qa')
    platform.identity.assign_role('T', 'bot', 'agent', site_id='NF1', actor_kind='agent')
    return platform


def ctx(p, who, kind='person'):
    return p.identity.context_for('T', who, actor_kind=kind)


def test_user_rule_is_private_and_only_its_user_activates_it(p):
    rule = p.rules.propose(ctx(p, 'ana'), scope='user', text='Report temperatures in degC.')
    assert rule['status'] == 'proposed'
    with pytest.raises(PermissionError):
        p.rules.activate(ctx(p, 'ben'), rule['rule_id'], 'not mine')
    with pytest.raises(ValueError):
        p.rules.activate(ctx(p, 'ana'), rule['rule_id'], '  ')
    p.rules.activate(ctx(p, 'ana'), rule['rule_id'], 'my preference')
    assert [r['text'] for r in p.rules.applicable(ctx(p, 'ana'), site_id='NF1')] == ['Report temperatures in degC.']
    assert p.rules.applicable(ctx(p, 'ben'), site_id='NF1') == []
    with pytest.raises(PermissionError):
        p.rules.propose(ctx(p, 'ana'), scope='user', text='x', owner_id='ben')


def test_agent_may_propose_but_only_an_approver_activates_a_site_rule(p):
    rule = p.rules.propose(ctx(p, 'bot', 'agent'), scope='site', site_id='NF1',
                           text='Flag dissolved oxygen below 30% for review.')
    with pytest.raises(PermissionError):
        p.rules.activate(ctx(p, 'bot', 'agent'), rule['rule_id'], 'agent cannot')
    with pytest.raises(PermissionError):
        p.rules.activate(ctx(p, 'op'), rule['rule_id'], 'operator lacks approve')
    p.rules.activate(ctx(p, 'qa1'), rule['rule_id'], 'agreed at site QA meeting')
    assert p.rules.applicable(ctx(p, 'ana'), site_id='NF1')[0]['rule_id'] == rule['rule_id']
    assert p.rules.applicable(ctx(p, 'ana'), site_id='NF2') == []
    p.rules.retire(ctx(p, 'qa1'), rule['rule_id'], 'superseded by SOP-12')
    assert p.rules.applicable(ctx(p, 'ana'), site_id='NF1') == []
    history = [h['event'] for h in p.rules.visible(ctx(p, 'qa1'), site_id='NF1')[0]['history']]
    assert history == ['proposed', 'active', 'retired']


def test_org_rule_needs_tenant_wide_authority(p):
    rule = p.rules.propose(ctx(p, 'ana'), scope='org', text='Never present simulated data as measured.')
    with pytest.raises(PermissionError):
        p.rules.activate(ctx(p, 'qa1'), rule['rule_id'], 'site-scoped QA')
    p.rules.activate(ctx(p, 'qa-global'), rule['rule_id'], 'corporate quality policy')
    assert p.rules.applicable(ctx(p, 'ben'), site_id='NF1')[0]['scope'] == 'org'


def prompt_for(p, who, thread):
    """Build the assistant prompt for a thread with one running turn."""
    tid = f"turn-{thread['id']}"
    with p.store.transaction('fixture') as tx:
        tx.put('T', 'engineering_chat_turn', tid, {'conversation_id': thread['id'], 'site_id': 'NF1', 'user_text': 'hello',
               'artifacts': [], 'status': 'running', 'created_at': iso(utc_now())}, expected_revision=None, action='fixture')
    return p.engineering_conversations._prompt(ctx(p, who), {**thread, 'turn_ids': [tid]}, [])


def test_rules_and_earlier_corrections_reach_a_new_conversation(p):
    ana = ctx(p, 'ana')
    first = p.engineering_conversations.create(ana, {'site_id': 'NF1'})
    p.missions.record_correction(ana, first['mission_id'], text='Valve V-12 failure was ruled out by inspection.',
                                 source_ref=None, claim_ref=None)
    rule = p.rules.propose(ana, scope='user', text='Keep answers under five sentences.')
    p.rules.activate(ana, rule['rule_id'], 'preference')
    second = p.engineering_conversations.create(ana, {'site_id': 'NF1'})
    assert second['mission_id'] != first['mission_id']
    context = prompt_for(p, 'ana', second)['mission_context']
    assert [r['rule_id'] for r in context['standing_rules']] == [rule['rule_id']]
    assert context['corrections_from_earlier_conversations'][0]['text'].startswith('Valve V-12')
    # Another person's conversation gets neither.
    ben_thread = p.engineering_conversations.create(ctx(p, 'ben'), {'site_id': 'NF1'})
    other = prompt_for(p, 'ben', ben_thread)['mission_context']
    assert other['standing_rules'] == [] and other['corrections_from_earlier_conversations'] == []


def test_corrections_are_only_carried_for_their_owner(p):
    with pytest.raises(PermissionError):
        p.missions.owner_corrections(ctx(p, 'ben'), 'ana')


def test_assistant_proposal_stays_proposed_until_a_person_activates(p):
    bot = p.identity.context_for('T', 'bot', actor_kind='agent')
    rule = p.rules.propose(bot, scope='site', site_id='NF1', text='Always report DO in % air saturation.',
                           reason='Proposed by the assistant from: always report DO in % air saturation')
    assert rule['status'] == 'proposed' and rule['proposed_by_kind'] == 'agent'
    assert p.rules.applicable(ctx(p, 'ana'), site_id='NF1') == []  # proposed rules never reach the assistant
    with pytest.raises(PermissionError):
        p.rules.activate(bot, rule['rule_id'], 'self-activation')


def test_rule_proposal_must_quote_the_users_own_message():
    from src.lifesci.process_engineering.conversation import quoted
    said = 'From now on,   ALWAYS flag DO below 30% for review please'
    assert quoted('always flag DO below 30% for review', said)
    assert not quoted('never release batch B-001', said)  # e.g. text injected from a source document
    assert not quoted('  ', said)


def test_answers_record_which_rules_and_earlier_corrections_they_were_given():
    from src.lifesci.process_engineering.conversation import EngineeringConversationService as S
    used = S._context_used({'standing_rules': [{'rule_id': 'rule-1', 'scope': 'user', 'text': 'Use degC.', 'revision': 2}],
                            'corrections': [{'correction_id': 'c1', 'text': 'Pump P-2 was fine.'}],
                            'corrections_from_earlier_conversations': [{'correction_id': 'c0', 'text': 'Valve V-12 ruled out.'},
                                                                       {'correction_id': 'c9', 'status': 'source_unavailable'}]})
    assert used == {'rules': [{'rule_id': 'rule-1', 'scope': 'user', 'text': 'Use degC.'}],
                    'corrections': [{'correction_id': 'c1', 'text': 'Pump P-2 was fine.'}],
                    'earlier_corrections': [{'correction_id': 'c0', 'text': 'Valve V-12 ruled out.'}]}
    assert S._context_used({}) == {'rules': [], 'corrections': [], 'earlier_corrections': []}
