"""Entity links across files: typed entities, cited cells, aliases, as-of, scope and review."""
from __future__ import annotations

import pytest
from openpyxl import Workbook

from src.manufacturing_data import ManufacturingStore, ManufacturingTools, ingest_package
from src.manufacturing_data.knowledge import canonical, review


def write(folder, name, text):
    folder.mkdir(exist_ok=True)
    (folder/name).write_text(text)


@pytest.fixture
def plant(tmp_path):
    """Batch record, lot record and a deviation that spells the batch ID differently."""
    package = tmp_path/'plant'
    write(package, 'batches.csv', 'batch_id,equipment_id,material_lot_id,available_at,temp\n'
                                  'B-001,BR-03,L-77,2024-01-02T00:00:00Z,37\n')
    write(package, 'lots.csv', 'material_lot_id,material_id,available_at\nL-77,GLC-01,2024-01-01T00:00:00Z\n')
    write(package, 'deviations.csv', 'deviation_id,batch_id,available_at,description\n'
                                     'DEV-9,B001,2024-03-01T00:00:00Z,foaming\n')
    store = ManufacturingStore(tmp_path/'store')
    assert ingest_package(package, store)['errors'] == []
    return store


def ids(graph):
    return set(graph['entities'])


def test_canonical_ignores_case_and_separators_but_not_leading_zeros():
    assert canonical('B-001') == canonical('b_001') == canonical('B 001') == canonical('B.001') == 'B001'
    assert canonical('B-01') != canonical('B-001')


def test_lot_material_and_deviation_are_typed_not_folded_into_batch(plant):
    with plant.connect() as con:
        kinds = {r['id']: r['kind'] for r in con.execute('SELECT id,kind FROM entities')}
    assert kinds['B-001'] == 'batch'
    assert kinds['L-77'] == 'lot'
    assert kinds['GLC-01'] == 'material'
    assert kinds['BR-03'] == 'equipment'
    assert kinds['DEV-9'] == 'deviation'


def test_deviation_reaches_equipment_and_lot_through_alias_in_two_hops(plant):
    graph = ManufacturingTools(plant).entity_graph(entity_id='DEV-9', hops=2)
    assert {'B001', 'B-001', 'BR-03', 'L-77'} <= ids(graph)
    assert 'GLC-01' not in ids(graph)  # three hops away
    alias = next(l for l in graph['links'] if l['predicate'] == 'same_identifier')
    assert {alias['a'], alias['b']} == {'B001', 'B-001'} and alias['status'] == 'extracted'
    assert graph['sources_searched'] == 3


def test_every_extracted_row_link_cites_a_verifiable_cell_holding_one_endpoint(plant):
    tools = ManufacturingTools(plant)
    graph = tools.entity_graph(entity_id='B-001', hops=2)
    row_links = [l for l in graph['links'] if l['predicate'] == 'same_record']
    assert row_links and all(l['status'] == 'extracted' for l in row_links)
    for link in row_links:
        cited = [e['evidence_id'] for e in link['evidence'] if e['evidence_id']]
        assert cited, link
        for evidence_id in cited:
            assert tools.verify_evidence(observation_id=evidence_id)['value_matches']
            cell = plant.get_many([evidence_id])[0]
            assert cell['value_text'] in {link['a'], link['b']}
    assert set(graph['evidence_ids']) == {e['evidence_id'] for l in row_links for e in l['evidence']}


def test_as_of_hides_later_links_and_aliases(plant):
    early = ManufacturingTools(plant, as_of='2024-02-01T00:00:00Z').entity_graph(entity_id='B-001', hops=2)
    assert 'DEV-9' not in ids(early) and 'B001' not in ids(early)
    assert early['aliases'] == []
    assert {'BR-03', 'L-77'} <= ids(early)
    later = ManufacturingTools(plant, as_of='2024-04-01T00:00:00Z').entity_graph(entity_id='B-001', hops=2)
    assert {'DEV-9', 'B001'} <= ids(later)


def test_links_do_not_cross_access_scopes(tmp_path):
    store = ManufacturingStore(tmp_path/'store')
    write(tmp_path/'a', 'batches.csv', 'batch_id,equipment_id\nB-001,BR-03\n')
    write(tmp_path/'b', 'deviations.csv', 'deviation_id,batch_id\nDEV-9,B001\n')
    ingest_package(tmp_path/'a', store, access_scope='tenant-a')
    ingest_package(tmp_path/'b', store, access_scope='tenant-b')
    graph = ManufacturingTools(store, scopes=('tenant-a',)).entity_graph(entity_id='B-001', hops=2, scopes=['tenant-a'])
    assert ids(graph) == {'B-001', 'BR-03'}
    assert graph['aliases'] == []
    with pytest.raises(PermissionError):
        ManufacturingTools(store, scopes=('tenant-a',)).entity_graph(entity_id='B-001', scopes=['tenant-b'])


def test_rejected_link_is_not_followed_and_review_is_not_replayed_before_it_happened(plant):
    tools = ManufacturingTools(plant)
    alias = next(l for l in tools.entity_graph(entity_id='DEV-9', hops=2)['links'] if l['predicate'] == 'same_identifier')
    with pytest.raises(ValueError):
        review(plant, alias['link_id'], 'rejected', actor='', reason='different site numbering')
    with pytest.raises(ValueError):
        review(plant, alias['link_id'], 'approved', actor='qa', reason='x')
    review(plant, alias['link_id'], 'rejected', actor='qa-lead', reason='B001 is site 2 numbering, not B-001')
    after = tools.entity_graph(entity_id='DEV-9', hops=2)
    assert 'B-001' not in ids(after) and 'BR-03' not in ids(after)
    assert any('rejected' in w for w in after['warnings'])
    # A historical replay must not use a review made after its cutoff.
    replay = ManufacturingTools(plant, as_of='2024-04-01T00:00:00Z').entity_graph(entity_id='DEV-9', hops=2)
    assert 'B-001' in ids(replay)


def test_confirmed_review_overrides_status(plant):
    tools = ManufacturingTools(plant)
    link = next(l for l in tools.entity_graph(entity_id='L-77')['links'] if 'GLC-01' in (l['a'], l['b']))
    review(plant, link['link_id'], 'confirmed', actor='qa-lead', reason='matches ERP lot master')
    again = next(l for l in tools.entity_graph(entity_id='L-77')['links'] if l['link_id'] == link['link_id'])
    assert again['status'] == 'confirmed' and again['review']['actor'] == 'qa-lead'


def test_filename_and_sheet_guesses_are_candidates_without_a_cited_cell(tmp_path):
    package = tmp_path/'pkg'; package.mkdir()
    workbook = Workbook(); sheet = workbook.active; sheet.title = 'R01'
    sheet.append(['equipment_id', 'value']); sheet.append(['EQ1', 1.0])
    workbook.save(package/'EXP001.xlsx')
    store = ManufacturingStore(tmp_path/'store')
    ingest_package(package, store)
    tools = ManufacturingTools(store)
    graph = tools.entity_graph(entity_id='EQ1')
    guessed = [l for l in graph['links'] if l['predicate'] == 'source_label']
    assert guessed and all(l['status'] == 'candidate' for l in guessed)
    assert all(e['evidence_id'] is None for l in guessed for e in l['evidence'])
    strict = tools.entity_graph(entity_id='EQ1', include_candidates=False)
    assert strict['links'] == []


def test_unknown_entity_reports_scope_of_search_not_absence(plant):
    graph = ManufacturingTools(plant).entity_graph(entity_id='NOPE-1')
    assert graph['links'] == [] and graph['sources_searched'] == 3
    assert 'not evidence that none exist' in graph['warnings'][0]


def test_entity_graph_is_a_registered_typed_tool(plant):
    handlers = ManufacturingTools(plant).handlers()
    result = handlers['entity_graph'](entity_id='B-001')
    assert result['evidence_ids'] and 'links' in result
