"""Case reads as the HTTP layer makes them: no caller-bound tenant around the service call."""
from src.manufacturing_data.cmo.cases import CaseService
from src.manufacturing_data.cmo.persistence import tenant_scope

from test_pharma_cases import DATA, execute, reviewed


def test_snapshot_and_handoff_read_accepted_originals_without_a_caller_scope(tmp_path):
    service = CaseService(tmp_path / 'runtime')
    with tenant_scope('tenant-a'):
        project = service.create_project('tenant-a', 'Fermentation')
        record = service.create_case(project['id'], 'tenant-a', 'Compare batches', 'Describe product observations.')
        item = service.import_bytes(record['id'], 'tenant-a', 'fermentation.csv', DATA)
        execute(service, item['job_id'])
        reviewed(service, item['job_id'])
    snapshot = service.snapshot(record['id'], 'tenant-a')
    assert snapshot['measurements'] and not any('unverified' in gap for gap in snapshot['gaps'])
    assert 'SHA-256' in service.export(record['id'], 'tenant-a')
