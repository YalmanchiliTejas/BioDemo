"""Reprocessing reuses parsed files instead of re-parsing (and re-OCRing) the whole delivery."""
from __future__ import annotations

import csv
import shutil

from src.manufacturing_data import ManufacturingStore, ingest_package
from src.manufacturing_data.cmo.pipeline import IngestionService


def delivery(folder):
    folder.mkdir(parents=True)
    with (folder/'bioreactor.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['batch_id', 'elapsed_h', 'temperature [degC]', 'pH [pH]'])
        writer.writerows([['LOCAL-1', 0, 35, 7], ['LOCAL-1', 1, 36, 7.1]])
    (folder/'notes.txt').write_text('Batch LOCAL-1 foaming observed at 1 h.\n')
    return folder


def test_same_namespace_at_a_new_path_skips_unchanged_files(tmp_path):
    first = delivery(tmp_path/'download-1')
    second = tmp_path/'download-2'; shutil.copytree(first, second)
    store = ManufacturingStore(tmp_path/'store')
    one = ingest_package(first, store, source_namespace='delivery-42')
    two = ingest_package(second, store, source_namespace='delivery-42')
    assert one['files_indexed'] == 2
    assert two['unchanged'] == 2 and two['files_indexed'] == 0


def test_changed_bytes_are_reparsed_even_within_a_namespace(tmp_path):
    first = delivery(tmp_path/'d1')
    store = ManufacturingStore(tmp_path/'store')
    ingest_package(first, store, source_namespace='delivery-42')
    (first/'notes.txt').write_text('Batch LOCAL-1 foaming observed at 2 h.\n')
    again = ingest_package(first, store, source_namespace='delivery-42')
    assert again['unchanged'] == 1 and again['files_indexed'] == 1


def test_without_namespace_a_new_path_is_a_new_source(tmp_path):
    # Default behaviour is unchanged: path identifies the package.
    first = delivery(tmp_path/'p1')
    second = tmp_path/'p2'; shutil.copytree(first, second)
    store = ManufacturingStore(tmp_path/'store')
    ingest_package(first, store)
    assert ingest_package(second, store)['files_indexed'] == 2


def test_reprocess_starts_from_superseded_store_and_keeps_old_store_intact(tmp_path):
    service = IngestionService(tmp_path/'svc')
    raw = delivery(tmp_path/'raw')
    old = service.run(raw, 'Acme', package_ref='pkg-1')
    assert old['status'] != 'failed', old.get('error')
    new = service.run(raw, 'Acme', package_ref='pkg-1', supersedes=old['id'])
    assert new['status'] != 'failed', new.get('error')
    assert new['ingestion']['unchanged'] == 2 and new['ingestion']['files_indexed'] == 0
    assert new['store'] != old['store']
    assert ManufacturingStore(old['store']).visible(scopes=('Acme',), limit=None)  # superseded run still readable


def test_reprocess_of_a_different_delivery_parses_fresh(tmp_path):
    service = IngestionService(tmp_path/'svc')
    raw = delivery(tmp_path/'raw')
    old = service.run(raw, 'Acme', package_ref='pkg-1')
    other = service.run(raw, 'Acme', package_ref='pkg-2', supersedes=old['id'])
    assert other['ingestion']['unchanged'] == 0 and other['ingestion']['files_indexed'] == 2


def test_mapping_model_is_skipped_only_when_aliases_cover_every_header():
    from src.manufacturing_data.cmo.pipeline import aliases_cover
    from src.manufacturing_data.cmo.schema import draft_mapping
    known = ['batch_id', 'elapsed_h', 'temperature [degC]', 'pH [pH]']
    assert aliases_cover(draft_mapping(known), known)
    assert not aliases_cover(draft_mapping(known+['Mystery reading']), known+['Mystery reading'])
    assert not aliases_cover(draft_mapping(['temperature [degC]', 'pH [pH]']), ['temperature [degC]', 'pH [pH]'])
