"""CMO files are tenant-scoped on disk and in storage; another tenant can neither list nor read them."""
from __future__ import annotations

import contextvars
import io
import shutil
import time
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.manufacturing_data.cmo.persistence import current_tenant

API = '/api/cmo-ingestion'
CSV = b'batch_id,elapsed_h,pH [pH]\nB,0,7\nB,1,7.1\n'


class Storage:
    backend = 'supabase'

    def __init__(self): self.objects = {}
    def put(self, key, path): self.objects.setdefault(key, path.read_bytes())
    def delete(self, key): self.objects.pop(key, None)

    def get(self, key, destination):
        if key not in self.objects: raise FileNotFoundError(key)
        destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(self.objects[key])


@pytest.fixture
def env(tmp_path, monkeypatch):
    from src.manufacturing_data.cmo.api import router
    for name in ['OPENAI_API_KEY', 'CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_AUTH_TOKEN', 'SUPABASE_URL', 'CMO_DATABASE_URL',
                 'LIFESCI_DATABASE_URL', 'AWS_LAMBDA_FUNCTION_NAME', 'CMO_ALLOW_UNAUTHENTICATED_TENANT_HEADER']:
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / 'runtime'
    monkeypatch.setenv('CMO_INGESTION_ROOT', str(root)); monkeypatch.setenv('CMO_API_TOKEN', 't')
    monkeypatch.setenv('CMO_PACKAGES_ROOT', str(tmp_path / 'none')); monkeypatch.setenv('CMO_DEMO_ROOT', str(tmp_path / 'none'))
    storage = Storage()
    monkeypatch.setattr('src.manufacturing_data.cmo.pipeline.evidence_store', lambda: storage)
    app = FastAPI(); app.include_router(router(tmp_path))
    as_ = lambda tenant: TestClient(app, headers={'X-CMO-Token': 't', 'X-Tenant-Id': tenant})
    return as_('tenant-a'), as_('tenant-b'), root, storage, app


def delivery(client):
    item = client.post(f'{API}/deliveries', json={'cmo': 'Acme', 'name': 'Lots'}).json()
    client.post(f"{API}/deliveries/{item['id']}/files", params={'filename': 'lot.csv'}, content=CSV)
    return item


def finished(client, package_id):
    ident = client.post(f'{API}/runs', json={'package_id': package_id, 'configuration': 'preview'}).json()['id']
    for _ in range(300):
        run = client.get(f'{API}/runs/{ident}').json()
        if run['status'] not in {'queued', 'running'}: break
        time.sleep(.02)
    assert run['status'] == 'complete', run.get('error')
    return run


def test_upload_is_invisible_to_another_tenant_and_cannot_be_run(env):
    a, b, root, *_ = env
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as z: z.writestr('lot.csv', CSV)
    upload = a.post(f'{API}/upload', content=archive.getvalue()).json()
    assert (root / 'uploads' / 'tenant-a' / upload['id'] / 'raw.zip').is_file()
    ids = lambda c: {p['id'] for p in c.get(f'{API}/catalog').json()['packages']}
    assert upload['id'] in ids(a) and upload['id'] not in ids(b)
    assert b.post(f'{API}/runs', json={'package_id': upload['id']}).status_code == 404


def test_another_tenant_cannot_fetch_runs_sources_cells_pages_or_links(env):
    a, b, *_ = env
    run = finished(a, delivery(a)['id'])
    m = run['measurements'][0]
    for path in ['', f"/sources/{m['source_id']}", f"/cells/{m['id']}", f"/pages/{m['source_id']}/1", '/links']:
        assert a.get(f"{API}/runs/{run['id']}{path}").status_code != 404 or path.startswith('/pages')
        assert b.get(f"{API}/runs/{run['id']}{path}").status_code == 404, path
    assert run['package_id'] not in {p['id'] for p in b.get(f'{API}/catalog').json()['packages']}


def test_folders_and_storage_keys_carry_the_tenant(env):
    a, _, root, storage, _ = env
    item = delivery(a)
    run = finished(a, item['id'])
    sha = run['documents'][0]['sha256']
    assert (root / 'deliveries' / 'tenant-a' / item['id'] / 'lot.csv').is_file()
    assert (root / 'stores' / 'tenant-a' / run['id']).is_dir()
    assert f"deliveries/tenant-a/{item['id']}/lot.csv" in storage.objects
    assert f'originals/tenant-a/{sha[:2]}/{sha}.csv' in storage.objects
    assert all(k.split('/')[1] == 'tenant-a' for k in storage.objects), sorted(storage.objects)


def test_unbound_tenant_raises_and_unsafe_or_unauthenticated_tenants_are_refused(env, monkeypatch):
    with pytest.raises(RuntimeError, match='No CMO tenant'):
        contextvars.Context().run(current_tenant)
    *_, app = env
    bad = TestClient(app, headers={'X-CMO-Token': 't', 'X-Tenant-Id': '../tenant-a'})
    assert bad.get(f'{API}/catalog').status_code == 400
    monkeypatch.delenv('CMO_API_TOKEN')  # standalone without a token: the header alone is not identity
    assert TestClient(app, headers={'X-Tenant-Id': 'tenant-a'}).get(f'{API}/catalog').status_code == 401


def test_pre_tenant_delivery_stays_readable_by_its_owner_only(env):
    a, b, root, storage, _ = env
    item = delivery(a)
    # Re-shape it the way deliveries were stored before keys and folders carried the tenant.
    shutil.rmtree(root / 'deliveries' / 'tenant-a' / item['id'])
    storage.objects[f"deliveries/{item['id']}/lot.csv"] = storage.objects.pop(f"deliveries/tenant-a/{item['id']}/lot.csv")
    assert finished(a, item['id'])['summary']['measurements'] == 2
    assert b.post(f'{API}/runs', json={'package_id': item['id']}).status_code == 404
