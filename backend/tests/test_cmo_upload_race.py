"""Parallel uploads to one delivery that finish on different servers (Lambda) must all be kept.

Regression: each request read the delivery, appended its file and saved; when another file was committed in
between, the save was refused ("Files cannot be removed from or reordered") and the upload returned 400.
"""
from src.manufacturing_data.cmo import persistence


def test_upload_committed_underneath_another_is_retried_and_both_are_kept(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.manufacturing_data.cmo.api import router
    for name in ['OPENAI_API_KEY', 'CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_AUTH_TOKEN', 'SUPABASE_URL', 'CMO_DATABASE_URL']:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('CMO_INGESTION_ROOT', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CMO_PACKAGES_ROOT', str(tmp_path / 'none'))
    monkeypatch.setenv('CMO_API_TOKEN', 't')
    app = FastAPI(); app.include_router(router(tmp_path)); client = TestClient(app); client.headers['X-CMO-Token'] = 't'
    delivery = client.post('/api/cmo-ingestion/deliveries', json={'cmo': 'Northfield', 'name': 'September'}).json()

    original = persistence.Repository.save_delivery
    state = {'raced': False}

    def save_with_a_concurrent_commit(self, item):
        # The first time the CSV is saved, another server commits the PDF to the same delivery first.
        if not state['raced'] and any(f['path'] == 'lims.csv' for f in item.get('files', [])):
            state['raced'] = True
            current = next(d for d in self.deliveries() if d['id'] == item['id'])
            original(self, {**current, 'files': [*current['files'], {'path': 'coa.pdf', 'size': 3, 'sha256': '0' * 64}],
                            'intake': [*current.get('intake', []), {'source': 'coa.pdf', 'path': 'coa.pdf', 'outcome': 'added',
                                                                    'reason': 'new file', 'size': 3, 'sha256': '0' * 64}]})
        return original(self, item)

    monkeypatch.setattr(persistence.Repository, 'save_delivery', save_with_a_concurrent_commit)
    response = client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/files", params={'filename': 'lims.csv'},
                           content=b'Batch,Time (h),pH\nB-1,0,7.0\n')
    assert state['raced']
    assert response.status_code == 200, response.text
    assert [f['path'] for f in response.json()['files']] == ['coa.pdf', 'lims.csv']
