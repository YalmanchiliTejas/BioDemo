"""Conversations can be renamed and archived by their owner; archiving hides, never deletes."""
import pytest

from src.lifesci.container import Platform
from src.lifesci.store import RecordStore


@pytest.fixture
def p():
    platform = Platform(RecordStore(), providers={})
    platform.identity.assign_role('T', 'ana', 'msat', site_id='NF1')
    platform.identity.assign_role('T', 'ben', 'msat', site_id='NF1')
    platform.identity.assign_role('T', 'bot', 'agent', site_id='NF1', actor_kind='agent')
    return platform


def ctx(p, who, kind='person'):
    return p.identity.context_for('T', who, actor_kind=kind)


def test_owner_renames_and_title_survives_first_message(p):
    svc, ana = p.engineering_conversations, ctx(p, 'ana')
    thread = svc.create(ana, {'site_id': 'NF1'})
    renamed = svc.update(ana, thread['id'], {'title': '  BR-03 foaming  '})
    assert renamed['title'] == 'BR-03 foaming'
    svc.enqueue(ana, thread['id'], {'text': 'What happened on BR-03?', 'expected_revision': renamed['revision']})
    assert [c['title'] for c in svc.list_for(ana)] == ['BR-03 foaming']


def test_archive_hides_without_deleting_and_can_be_restored(p):
    svc, ana = p.engineering_conversations, ctx(p, 'ana')
    keep, old = svc.create(ana, {'site_id': 'NF1'}), svc.create(ana, {'site_id': 'NF1'})
    svc.update(ana, old['id'], {'archived': True})
    assert [c['id'] for c in svc.list_for(ana)] == [keep['id']]
    assert [c['id'] for c in svc.list_for(ana, archived=True)] == [old['id']]
    assert svc.get(ana, old['id'])['id'] == old['id']  # still readable: nothing deleted
    svc.update(ana, old['id'], {'archived': False})
    assert {c['id'] for c in svc.list_for(ana)} == {keep['id'], old['id']}


def test_only_the_owner_person_can_manage_a_conversation(p):
    svc = p.engineering_conversations
    thread = svc.create(ctx(p, 'ana'), {'site_id': 'NF1'})
    with pytest.raises(PermissionError):
        svc.update(ctx(p, 'ben'), thread['id'], {'title': 'mine now'})
    with pytest.raises(PermissionError):
        svc.update(ctx(p, 'bot', 'agent'), thread['id'], {'archived': True})
    with pytest.raises(ValueError):
        svc.update(ctx(p, 'ana'), thread['id'], {'title': ''})
    with pytest.raises(ValueError):
        svc.update(ctx(p, 'ana'), thread['id'], {'title': '   '})
