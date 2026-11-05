"""A messy CMO dump uploads in one go and every file is accounted for."""
import csv
import io
import zipfile


def _zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        for name, body in files.items():
            z.writestr(name, body)
    return buffer.getvalue()


def test_document_dump_is_sorted_not_refused(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.manufacturing_data.cmo.api import router
    for name in ['OPENAI_API_KEY', 'CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_AUTH_TOKEN', 'SUPABASE_URL', 'CMO_DATABASE_URL']:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('CMO_INGESTION_ROOT', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CMO_PACKAGES_ROOT', str(tmp_path / 'none'))
    monkeypatch.setenv('CMO_API_TOKEN', 't')
    app = FastAPI(); app.include_router(router(tmp_path)); client = TestClient(app); client.headers['X-CMO-Token'] = 't'
    body = io.StringIO(); csv.writer(body).writerows([['Lot', 'Elapsed time (h)', 'pH'], ['L-1', 0, 7.0], ['L-1', 1, 7.1]])
    lims = body.getvalue().encode()
    inner = _zip({'lims.csv': lims, 'cover-letter.md': b'# October lots'})
    dump = _zip({'lims.csv': lims, 'October/resend.zip': inner, '__MACOSX/._lims.csv': b'', 'README.html': b'<p>hi</p>',
                 'v2/lims.csv': lims.replace(b'7.1', b'7.2')})
    delivery = client.post('/api/cmo-ingestion/deliveries', json={'cmo': 'Acme CDMO', 'name': 'October dump'}).json()
    added = client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/files", params={'filename': 'dump.zip'}, content=dump)
    assert added.status_code == 200, added.text
    item = added.json()
    outcomes = {e['path']: e['outcome'] for e in item['intake']}
    assert outcomes == {'lims.csv': 'added', 'October/resend/lims.csv': 'duplicate', 'October/resend/cover-letter.md': 'set_aside',
                        '__MACOSX/._lims.csv': 'system', 'README.html': 'set_aside', 'v2/lims.csv': 'added'}
    assert [f['path'] for f in item['files']] == ['lims.csv', 'v2/lims.csv']
    assert 'possibly a revision' in next(e['reason'] for e in item['intake'] if e['path'] == 'v2/lims.csv')
    # The same file dropped again later is recognised, not refused.
    again = client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/files", params={'filename': 'lims.csv'}, content=lims).json()
    assert again['intake'][-1]['outcome'] == 'duplicate' and len(again['files']) == 2
    # A file from a dropped folder keeps its folder path; traversal is still refused.
    folder = client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/files", params={'filename': 'Nov/batch notes.txt'}, content=b'n').json()
    assert folder['files'][-1]['path'] == 'Nov/batch notes.txt'
    assert client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/files", params={'filename': '../x.csv'}, content=b'x').status_code == 400
    # Set-aside originals are kept as evidence, outside the folder the checks read.
    assert list((tmp_path / 'runtime').rglob('cover-letter.md')) and not list((tmp_path / 'runtime' / 'deliveries').rglob('*.md'))
    run = client.post('/api/cmo-ingestion/runs', json={'package_id': delivery['id']}).json()
    view = client.get('/api/cmo-ingestion/runs/' + run['id']).json()
    assert {e['outcome'] for e in view['intake']} >= {'added', 'duplicate', 'set_aside', 'system'}


def test_outlook_msg_and_forwarded_email_unpack(monkeypatch):
    import struct
    from email.message import EmailMessage
    import olefile
    from src.manufacturing_data.cmo.intake import expand
    u = lambda s: s.encode('utf-16-le')
    # Stand-in for an Outlook compound file: MAPI string streams, one CSV attachment, one attached Outlook item.
    props = b'\0' * 32 + struct.pack('<HHIQ', 0x0040, 0x0039, 0, (13_400_000_000 * 10_000_000))
    streams = {'__substg1.0_0037001F': u('Deviation DV-58 filter integrity'), '__substg1.0_1000001F': u('Filter failed on lot A-105.'),
               '__substg1.0_0C1A001F': u('Alder QA'), '__properties_version1.0': props,
               '__attach_version1.0_#00000000/__substg1.0_3707001F': u('integrity.csv'),
               '__attach_version1.0_#00000000/__substg1.0_37010102': b'lot,result\nA-105,fail',
               '__attach_version1.0_#00000001/__substg1.0_3707001F': u('original.msg')}

    class Ole:
        def __init__(self, _): pass
        def exists(self, name): return name in streams
        def openstream(self, name): return io.BytesIO(streams[name])
        def listdir(self, streams=True, storages=True): return [k.split('/') for k in globals_streams]
    globals_streams = list(streams)
    monkeypatch.setattr(olefile, 'OleFileIO', Ole)
    got = {p.as_posix(): (o, c) for p, c, o, _ in expand('DV-58.msg', b'ole', {'.csv', '.txt'})}
    assert got['DV-58.msg'][0] == 'set_aside' and got['DV-58/integrity.csv'] == ('added', b'lot,result\nA-105,fail')
    assert got['DV-58/original.msg'][0] == 'unreadable'
    text = got['DV-58/message.txt'][1].decode()
    assert 'Subject: Deviation DV-58' in text and 'Filter failed on lot A-105.' in text and 'Date: 2025' in text

    inner = EmailMessage(); inner['Subject'] = 'OOS titer'; inner.set_content('Batch 17 out of spec.')
    inner.add_attachment(b'a\n1', maintype='text', subtype='csv', filename='titer.csv')
    outer = EmailMessage(); outer['Subject'] = 'Fwd: OOS titer'; outer.set_content('See below.')
    outer.add_attachment(inner)
    paths = {p.as_posix(): o for p, _, o, _ in expand('fwd.eml', outer.as_bytes(), {'.csv', '.txt'})}
    assert paths['fwd/forwarded-1/titer.csv'] == 'added' and paths['fwd/forwarded-1/message.txt'] == 'added', paths
