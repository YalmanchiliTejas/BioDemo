"""Every record type the product stores is searchable by the assistant or excluded on purpose, with a reason.

Live miss (2026-11-10): specifications (the DO limits) were added for deviation signals but never made searchable,
so QA answers called the limits missing. This test turns that silent gap into a failure that forces a decision.
ponytail: checks the types that seeding plus one representative assistant turn create; extend the turn when a
feature adds record types elsewhere.
"""
from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.process_engineering.workspace import ASSISTANT_EXCLUDED, KINDS
from src.lifesci.store import RecordStore
from tests.lifesci.test_engineering_conversation import fake_planner, send


def call(name, **arguments):
    return {'name': name, 'arguments': arguments}


def test_every_stored_record_type_is_searchable_or_excluded_with_a_reason(monkeypatch):
    monkeypatch.setenv('ASSISTANT_LOOP', 'tools')
    p = Platform(RecordStore(), providers={})
    seed(p)
    for persona in ('process_engineer', 'msat', 'qa', 'executive'):
        p.demo.provision('anon-' + persona, persona, True)
    ctx = p.identity.context_for(TENANT, 'priya')
    sending = next(r.id for r in p.store.read().list(TENANT, 'physical_analysis_context')
                   if r.state.get('label') == 'SYNTHETIC · chemical.parallel_batch')
    latest = lambda kind: sorted(p.store.read().list(TENANT, kind), key=lambda r: r.id)[-1].id
    fake = fake_planner(p, [])
    fake.scripts[p.gateway.registry.profiles['anthropic-opus'].model] = [
        {'tool_calls': [call('workspace_search', query='BR-07'),
                        call('model_library_read', kind='physical_analysis_context', record_id=sending)]},
        {'tool_calls': [call('model_library_prepare', mode='model_library', context_id=sending, model_id='chemical.parallel_batch',
                             objective='Simulate the reactor example', operation='simulate', max_solver_calls=4)]},
        lambda m: {'tool_calls': [call('model_library_execute', plan_id=latest('physical_analysis_plan'))]},
        lambda m: {'tool_calls': [call('remember', text='The 10 L reactor example completes within its temperature limit.',
                                       kind='lesson', basis='observed',
                                       sources=[{'kind': 'physical_analysis_result', 'id': latest('physical_analysis_result')}])]},
        'Done.']
    send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Simulate the reactor example and note what you learn.')
    stored = {row[0] for row in p.store._db.execute('SELECT DISTINCT kind FROM aggregates').fetchall()}
    undecided = sorted(stored - set(KINDS) - set(ASSISTANT_EXCLUDED))
    assert not undecided, (f'New record types {undecided}: add each to workspace.KINDS (with FIELDS) so the assistant can '
                           'search it, or to workspace.ASSISTANT_EXCLUDED with the reason it must not.')
    assert not set(KINDS) & set(ASSISTANT_EXCLUDED), 'a record type cannot be both searchable and excluded'
    assert all(reason.strip() for reason in ASSISTANT_EXCLUDED.values())
