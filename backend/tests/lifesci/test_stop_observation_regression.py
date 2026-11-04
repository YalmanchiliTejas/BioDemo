"""Offline stop observations; provider responses are scripted, never network calls."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.gateway import FakeProvider
from src.lifesci.gateway.registry import Qualification
from src.lifesci.store import ConflictError, RecordStore


def _queued_search():
    platform = Platform(RecordStore(), providers={})
    seed(platform)
    context = platform.identity.context_for(TENANT, 'priya')
    fake = FakeProvider(name='anthropic')
    platform.gateway.providers['anthropic'] = fake
    platform.gateway.registry.qualify(Qualification('investigation_planning', 'anthropic-opus',
        'offline-stop-regression', True, {'contract': 1.}, {'contract': 1.},
        'Scripted provider; not a model qualification', 'test'))
    model = platform.gateway.registry.profiles['anthropic-opus'].model
    fake.scripts[model] = [json.dumps({'reply': 'Inspecting authorized source records.', 'workflow': [{
        'node_id': 'search', 'task_kind': 'workspace_search', 'title': 'Find source records',
        'depends_on': [], 'payload': {'kinds': ['evidence'], 'query': 'F-2408'}}]})]
    thread = platform.engineering_conversations.create(context, {})
    queued = platform.engineering_conversations.enqueue(context, thread['id'], {
        'text': 'Inspect F-2408 source records', 'expected_revision': thread['revision']})
    return platform, context, fake, queued


def test_stop_acknowledges_while_provider_is_still_in_flight(monkeypatch):
    """A slow model call must not delay owner acknowledgment or publish its plan."""
    platform, context, fake, queued = _queued_search()
    entered, release = Event(), Event()
    complete = fake.complete

    def pending_provider(**kwargs):
        entered.set()
        assert release.wait(10), 'test did not release scripted provider'
        return complete(**kwargs)

    monkeypatch.setattr(fake, 'complete', pending_provider)
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(platform.engineering_conversations.run_turn,
            context, queued['id'], queued['turn_ids'][-1])
        try:
            assert entered.wait(10), 'worker did not reach scripted provider'
            stopped = platform.engineering_conversations.stop(context, queued['id'])
            assert stopped['turns'][-1]['status'] == 'cancelled'
            assert not running.done()
            assert not stopped['turns'][-1]['artifacts']
        finally:
            release.set()
        final = running.result(timeout=10)
    assert final['turns'][-1]['status'] == 'cancelled'
    assert not final['turns'][-1]['artifacts']
    assert not platform.store.read().list(TENANT, 'data_flow_run')


def test_stop_during_workspace_tool_does_not_publish_new_artifacts(monkeypatch):
    """Stopping an active tool must fence outputs that finish after acknowledgment."""
    platform, context, _, queued = _queued_search()
    entered, release = Event(), Event()
    search = platform.engineering_conversations.workspace.search

    def pending_search(*args, **kwargs):
        result = search(*args, **kwargs)
        if kwargs.get('query') == 'F-2408':
            entered.set()
            assert release.wait(10), 'test did not release workspace search'
        return result

    monkeypatch.setattr(platform.engineering_conversations.workspace, 'search', pending_search)
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(platform.engineering_conversations.run_turn,
            context, queued['id'], queued['turn_ids'][-1])
        try:
            assert entered.wait(10), 'worker did not reach workspace tool'
            stopped = platform.engineering_conversations.stop(context, queued['id'])
            assert stopped['turns'][-1]['status'] == 'cancelled'
            assert not stopped['turns'][-1]['artifacts']
        finally:
            release.set()
        final = running.result(timeout=10)
    assert final['turns'][-1]['status'] == 'cancelled'
    assert not final['turns'][-1]['artifacts']
    assert not platform.store.read().list(TENANT, 'assistant_workspace_result')


def test_stop_during_draft_preparation_does_not_leave_a_proposal(monkeypatch):
    """A draft whose basis finishes validating after stop must leave no proposal."""
    platform, context, _, queued = _queued_search()
    service = platform.engineering_conversations
    turn_id = queued['turn_ids'][-1]
    service._update_turn(context, turn_id, status='running')
    evidence = next(record for record in platform.store.read().list(TENANT, 'evidence')
        if record.state.get('source_record_id') == 'F-2408-titer')
    basis = {'kind': 'evidence', 'id': evidence.id, 'revision': evidence.revision, 'site_id': 'NF1'}
    service._operator('workspace_read')(context, {'_turn_id': turn_id,
        'kind': 'evidence', 'record_id': evidence.id, 'revision': evidence.revision})
    before = service.get(context, queued['id'])['turns'][-1]['artifacts']
    entered, release = Event(), Event()
    validate = platform.identity.validate_refs

    def pending_basis(ctx, refs, **kwargs):
        result = validate(ctx, refs, **kwargs)
        if refs == [basis]:
            entered.set()
            assert release.wait(10), 'test did not release draft basis validation'
        return result

    monkeypatch.setattr(platform.identity, 'validate_refs', pending_basis)
    proposal = {'_turn_id': turn_id, 'target_system': 'LIMS', 'operation': 'request_retest',
        'target_id': 'F-2408', 'payload': {'reason': 'Investigate lower titer'}, 'basis': [basis],
        'rationale': 'A repeat measurement can help distinguish an assay error.',
        'expected_result': 'A reviewed assay result with source provenance.',
        'follow_up_measure': 'Review repeat results before further decisions.'}
    with ThreadPoolExecutor(max_workers=1) as executor:
        drafting = executor.submit(service._operator('workspace_propose_action'), context, proposal)
        try:
            assert entered.wait(10), 'worker did not reach draft basis validation'
            stopped = service.stop(context, queued['id'])
            assert stopped['turns'][-1]['status'] == 'cancelled'
        finally:
            release.set()
        with pytest.raises(ConflictError, match='stopped or superseded'):
            drafting.result(timeout=10)
    final = service.get(context, queued['id'])['turns'][-1]
    assert final['status'] == 'cancelled'
    assert final['artifacts'] == before
    assert not platform.store.read().list(TENANT, 'proposal')
    assert not platform.store.read().list(TENANT, 'action_intent')
