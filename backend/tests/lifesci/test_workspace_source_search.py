"""Discover source text without exposing unauthorized originals in search output."""
import json

from src.lifesci.container import Platform
from src.lifesci.store import RecordStore


def test_evidence_search_finds_original_text_and_keeps_scope():
    p = Platform(RecordStore(), providers={})
    for actor, site in [('owner', 'NF1'), ('outsider', 'NF2')]:
        p.identity.assign_role('T', actor, 'msat', site_id=site)
    owner = p.identity.context_for('T', 'owner')
    outsider = p.identity.context_for('T', 'outsider')
    source = p.evidence.ingest(owner, source_system='MES', source_record_id='opaque-123',
        content=b'SOP CLEAN-8 revision 3 applies from July 1. Source details require inspection.',
        media_type='text/plain', site_id='NF1', event_time=None)
    p.evidence.ingest(outsider, source_system='MES', source_record_id='opaque-private',
        content=b'SOP CLEAN-8 PRIVATE-CONTROL-MUST-NOT-LEAK', media_type='text/plain', site_id='NF2', event_time=None)
    thread = p.engineering_conversations.create(owner, {'site_id': 'NF1'})
    result = p.engineering_conversations.workspace.search(owner, thread, kinds=['evidence'], query='clean-8')
    assert [r['id'] for r in result['records']] == [source['evidence_id']]
    assert result['matching_count'] == 1
    assert 'PRIVATE-CONTROL' not in json.dumps(result)
    assert 'Source details require inspection' not in json.dumps(result)
    original = p.engineering_conversations.workspace.read(owner, thread, kind='evidence',
        record_id=source['evidence_id'], revision=source['revision'])
    assert 'revision 3' in original['record']['data']['original']


def test_missing_original_does_not_hide_other_matches():
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role('T', 'owner', 'msat', site_id='NF1')
    ctx = p.identity.context_for('T', 'owner')
    p.evidence.ingest(ctx, source_system='MES', source_record_id='good', content=b'CLEAN-8 good',
        media_type='text/plain', site_id='NF1', event_time=None)
    with p.store.transaction('fixture') as tx:
        tx.put('T', 'evidence', 'MES:missing', {'site_id': 'NF1', 'media_type': 'text/plain',
            'digest': 'unavailable', 'size': 100, 'source_record_id': 'opaque'},
            expected_revision=None, action='fixture')
    thread = p.engineering_conversations.create(ctx, {'site_id': 'NF1'})
    result = p.engineering_conversations.workspace.search(ctx, thread, kinds=['evidence'], query='CLEAN-8')
    assert [r['id'] for r in result['records']] == ['MES:good']
    assert result['content_search_gaps'] == [{'id': 'MES:missing', 'reason': 'original_unavailable'}]
    assert result['matching_count_is_lower_bound'] is True


def test_oversized_source_is_reported_as_unsearched():
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role('T', 'owner', 'msat', site_id='NF1')
    ctx = p.identity.context_for('T', 'owner')
    p.evidence.ingest(ctx, source_system='MES', source_record_id='large',
        content=b'x' * (3 * 1024 * 1024) + b'CLEAN-8', media_type='text/plain', site_id='NF1', event_time=None)
    thread = p.engineering_conversations.create(ctx, {'site_id': 'NF1'})
    result = p.engineering_conversations.workspace.search(ctx, thread, kinds=['evidence'], query='CLEAN-8')
    assert result['records'] == []
    assert result['content_search_gaps'] == [{'id': 'MES:large', 'reason': 'text_search_byte_limit'}]
    assert result['truncated'] is True


def test_text_match_is_pinned_to_discovered_revision(monkeypatch):
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role('T', 'owner', 'msat', site_id='NF1')
    ctx = p.identity.context_for('T', 'owner')
    p.evidence.ingest(ctx, source_system='MES', source_record_id='racing', content=b'CLEAN-8 previous',
        media_type='text/plain', site_id='NF1', event_time=None)
    original = p.evidence.original

    def updated_before_read(actor, evidence_id, revision=None):
        p.evidence.ingest(ctx, source_system='MES', source_record_id='racing', content=b'changed content',
            media_type='text/plain', site_id='NF1', event_time=None)
        return original(actor, evidence_id, revision=revision)

    monkeypatch.setattr(p.evidence, 'original', updated_before_read)
    thread = p.engineering_conversations.create(ctx, {'site_id': 'NF1'})
    result = p.engineering_conversations.workspace.search(ctx, thread, kinds=['evidence'], query='CLEAN-8')
    assert [(r['id'], r['revision']) for r in result['records']] == [('MES:racing', 1)]
