"""Chat assistant: records linked by shared identifiers, and word-ranked search."""
import pytest
from pydantic import ValidationError

from src.lifesci.container import Platform
from src.lifesci.process_engineering.conversation_schemas import WorkspaceSearch
from src.lifesci.store import RecordStore


def put(p, kind, rid, state):
    with p.store.transaction('fixture') as tx:
        tx.put('T', kind, rid, state, expected_revision=None, action='fixture')


@pytest.fixture
def plant():
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role('T', 'owner', 'msat', site_id='NF1')
    ctx = p.identity.context_for('T', 'owner')
    put(p, 'batch', 'B-001', {'batch_id': 'B-001', 'equipment_id': 'BR-03', 'status': 'complete', 'site_id': 'NF1'})
    put(p, 'batch', 'B-002', {'batch_id': 'B-002', 'equipment_id': 'BR03', 'status': 'complete', 'site_id': 'NF1'})
    put(p, 'sample', 'S-1', {'sample_id': 'S-1', 'batch_id': 'b_001', 'status': 'tested', 'site_id': 'NF1'})
    put(p, 'batch', 'B-900', {'batch_id': 'B-900', 'equipment_id': 'BR-99', 'status': 'complete', 'site_id': 'NF1'})
    put(p, 'sample', 'S-X', {'sample_id': 'S-X', 'batch_id': 'B-001', 'status': 'tested', 'site_id': 'NF2'})
    p.cases.open(ctx, 'DEV-9', 'owner', 'qa', 'NF1')
    p.cases.add_timeline_event(ctx, 'DEV-9', '2024-03-01T00:00:00+00:00', 'Foaming in B-001 on the bioreactor')
    thread = p.engineering_conversations.create(ctx, {'site_id': 'NF1'})
    return p, ctx, thread


def by_id(result):
    return {r['id']: r for r in result['records']}


def test_links_follow_shared_identifiers_across_spellings_with_status(plant):
    p, ctx, thread = plant
    result = p.engineering_conversations.workspace.links(ctx, thread, kind='batch', record_id='B-001')
    found = by_id(result)
    assert {'S-1', 'B-002', 'DEV-9'} <= set(found)
    assert 'B-900' not in found
    sample = found['S-1']['shared_identifiers'][0]
    assert sample['canonical'] == 'B001' and sample['status'] == 'extracted'
    assert found['B-002']['shared_identifiers'][0]['canonical'] == 'BR03'
    case_link = found['DEV-9']['shared_identifiers'][0]
    assert case_link['status'] == 'candidate'  # mentioned in free text, not an ID field
    assert result['records_searched'] >= 4
    assert 'does not establish that none exist' in result['coverage']


def test_links_never_include_another_site(plant):
    p, ctx, thread = plant
    result = p.engineering_conversations.workspace.links(ctx, thread, kind='batch', record_id='B-001')
    assert 'S-X' not in by_id(result)


def test_multi_word_query_finds_records_without_the_literal_phrase(plant):
    p, ctx, thread = plant
    p.evidence.ingest(ctx, source_system='MES', source_record_id='note-1',
                      content=b'Foaming observed after the antifoam pump failure on BR-03.',
                      media_type='text/plain', site_id='NF1', event_time=None)
    p.evidence.ingest(ctx, source_system='MES', source_record_id='note-2', content=b'Routine cleaning completed.',
                      media_type='text/plain', site_id='NF1', event_time=None)
    tools = p.engineering_conversations.workspace
    words = tools.search(ctx, thread, kinds=['evidence'], query='pump foaming failure')
    assert [r['id'] for r in words['records']] == ['MES:note-1']
    assert words['records'][0]['match'] == 'words'
    literal = tools.search(ctx, thread, kinds=['evidence'], query='Routine cleaning')
    assert [r['id'] for r in literal['records']] == ['MES:note-2'] and literal['records'][0]['match'] == 'exact'
    # Single words keep the old literal-substring behaviour.
    assert tools.search(ctx, thread, kinds=['evidence'], query='pumps')['records'] == []


def test_search_modes_validate_their_inputs():
    with pytest.raises(ValidationError):
        WorkspaceSearch(mode='links')
    with pytest.raises(ValidationError):
        WorkspaceSearch(mode='similar_cases')
    assert WorkspaceSearch(mode='links', record_kind='batch', record_id='B-001').mode == 'links'
    assert WorkspaceSearch().mode == 'search'
