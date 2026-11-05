"""Multi-agent investigations, platform side: start, sync, stop, report, service tokens and the chat proposal.
A fake executor stands in for cloud_backend; no network is used."""
import io
import json
import zipfile
from datetime import timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.lifesci import investigations as inv
from src.lifesci.container import Platform
from src.lifesci.identity import AuthorizationError
from src.lifesci.store import ConflictError, RecordStore


def pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()


KEY = pem()
CONFIG = inv.ExecutorConfig(url='https://exec.example', audience='exec-aud', issuer='https://api.example',
                            tenant='exec-tenant', key_pem=KEY, key_id='k1')


class FakeExecutor:
    def __init__(self):
        self.uploads, self.jobs, self.cancelled, self.events_by_job = {}, {}, [], {}
        self.down = False
        self.results = {}

    def _guard(self):
        if self.down:
            raise inv.ExecutorUnavailable('execution service unreachable: ConnectError')

    def upload(self, project, sha256, data):
        self._guard(); self.uploads[sha256] = data
        return {'sha256': sha256, 'version_id': 'v1'}

    def submit(self, project, key, job):
        self._guard()
        ident = 'job-' + key
        self.jobs[ident] = {'id': ident, 'project': project, 'state': 'queued', 'attempt': 0, 'request': job, 'error_code': None}
        return self.jobs[ident]

    def job(self, project, job_id):
        self._guard(); return self.jobs[job_id]

    def events(self, project, job_id, after):
        self._guard()
        events = [e for e in self.events_by_job.get(job_id, []) if e['seq'] > after]
        return {'events': events, 'next': events[-1]['seq'] if events else after}

    def cancel(self, project, job_id):
        self._guard(); self.cancelled.append(job_id); self.jobs[job_id]['state'] = 'cancelled'
        return self.jobs[job_id]

    def result(self, project, job_id):
        self._guard(); return self.results[job_id]


def ev(seq, kind, agent=None, parent=None, **payload):
    return {'seq': seq, 'attempt': 1, 'at': f'2026-11-05T10:00:{seq:02d}+00:00', 'kind': kind,
            'agent_id': agent, 'parent_id': parent, 'payload': payload}


@pytest.fixture
def p():
    platform = Platform(RecordStore(), providers={})
    for actor, role, site in [('ana', 'msat', 'NF1'), ('ben', 'msat', 'NF1'), ('far', 'msat', 'NF2')]:
        platform.identity.assign_role('T', actor, role, site_id=site)
    platform.identity.assign_role('T', 'bot', 'agent', site_id='NF1', actor_kind='agent')
    platform.investigations = inv.InvestigationService(platform, config=CONFIG, executor=FakeExecutor())
    ana = ctx(platform, 'ana')
    platform.evidence.ingest(ana, source_system='lims', source_record_id='B-001', content=b'batch,do\nB-001,24\n',
                             media_type='text/csv', site_id='NF1', event_time=None)
    platform.evidence.ingest(ctx(platform, 'far'), source_system='lims', source_record_id='NF2-B9', content=b'x',
                             media_type='text/csv', site_id='NF2', event_time=None)
    return platform


def ctx(p, who, kind='person'):
    return p.identity.context_for('T', who, actor_kind=kind)


def start(p, who='ana', **extra):
    return p.investigations.start(ctx(p, who), {'objective': 'Why did DEV-31 foam?', 'site_id': 'NF1',
                                                'record_refs': [{'kind': 'evidence', 'id': 'lims:B-001'}], **extra})


def job_of(p, run):
    return p.investigations.executor.jobs[p.store.read().require('T', inv.KIND, run['run_id']).state['executor']['job_id']]


def test_start_builds_pinned_snapshot_and_submits_with_defaults(p):
    run = start(p)
    assert run['status'] == 'submitted'
    job = job_of(p, run)
    snapshot = p.store.read().require('T', inv.KIND, run['run_id']).state['evidence_snapshot']
    assert job['request']['sha256'] == snapshot['sha256'] and job['request']['max_tool_calls'] == 60
    assert job['request']['timeout_seconds'] == 1200 and job['id'] == 'job-' + run['run_id']
    archive = zipfile.ZipFile(io.BytesIO(p.investigations.executor.uploads[snapshot['sha256']]))
    assert archive.namelist() == ['evidence/lims:B-001.csv']
    assert [i['id'] for i in snapshot['items']] == ['lims:B-001']


def test_identical_evidence_gives_identical_snapshot_bytes(p):
    a, _ = p.investigations.snapshot(ctx(p, 'ana'), site_id='NF1', record_refs=[{'kind': 'evidence', 'id': 'lims:B-001'}])
    b, _ = p.investigations.snapshot(ctx(p, 'ana'), site_id='NF1', record_refs=[{'kind': 'evidence', 'id': 'lims:B-001'}])
    assert a == b


def test_only_people_with_permission_start_and_evidence_is_rechecked(p):
    with pytest.raises(AuthorizationError):
        p.investigations.start(ctx(p, 'bot', 'agent'), {'objective': 'x' * 10, 'site_id': 'NF1'})
    with pytest.raises((PermissionError, AuthorizationError)):  # another site's evidence is not readable
        p.investigations.start(ctx(p, 'ana'), {'objective': 'Check NF2', 'site_id': 'NF1',
                                               'record_refs': [{'kind': 'evidence', 'id': 'lims:NF2-B9'}]})
    with pytest.raises(ValueError):
        p.investigations.start(ctx(p, 'ana'), {'objective': 'Nothing to read', 'site_id': 'NF1'})


def test_concurrency_cap_and_not_configured(p):
    start(p); start(p)
    with pytest.raises(ConflictError, match='already running'):
        start(p)
    p.investigations = inv.InvestigationService(p, config=None, executor=None)
    p.investigations.config = None
    with pytest.raises(ConflictError, match=inv.NOT_CONFIGURED):
        start(p)


def test_sync_folds_agents_copies_events_once_and_maps_status(p):
    run = start(p)
    job = job_of(p, run)
    job['state'] = 'running'
    p.investigations.executor.events_by_job[job['id']] = [
        ev(1, 'phase', phase='investigating'),
        ev(2, 'agent_started', 'c1', None, depth=1, status='running', question='Is DO linked to foaming?'),
        ev(3, 'agent_activity', 'c1', None, status='running', tool='query_data', tool_use_count=4, token_count=900),
        ev(4, 'subreport_saved', 'c1', None, subreport_id='do', assessment='DO fell below 30% before foaming', fact_count=3,
           claim_count=1, open_question_count=0, evidence_ids=['b1:x']),
        ev(5, 'budget', tool_calls_used=9, tool_calls_limit=60, elapsed_seconds=120, tokens=5000)]
    view = p.investigations.get(ctx(p, 'ana'), run['run_id'])
    assert view['status'] == 'running'
    child = next(a for a in view['agents'] if a['agent_id'] == 'c1')
    assert child['parent_id'] == 'lead' and child['current_tool'] == 'query_data' and child['tool_calls'] == 4
    assert child['subreports'][0]['subreport_id'] == 'do' and child['attribution'] == 'exact'
    assert view['budget']['tool_calls_used'] == 9 and view['budget']['cost_status'] == 'unknown'
    # A second sync, including a redelivered event, adds nothing.
    p.investigations.executor.events_by_job[job['id']].append(ev(5, 'budget', tool_calls_used=9))
    p.investigations.sync(ctx(p, 'ana'), run['run_id'], force=True)
    assert len(p.investigations.events(ctx(p, 'ana'), run['run_id'])['events']) == 5


def test_unattributed_subreport_is_marked_approximate(p):
    folded = inv.fold([ev(1, 'agent_activity', 'c1', None, status='running', tool='search_evidence'),
                       ev(2, 'subreport_saved', None, None, subreport_id='s', assessment='a')], run_status='running',
                      limits={'max_tool_calls': 60, 'timeout_seconds': 1200})
    c1 = next(a for a in folded['agents'] if a['agent_id'] == 'c1')
    assert c1['subreports'][0]['subreport_id'] == 's' and c1['attribution'] == 'approximate'


def test_unreachable_executor_keeps_status_and_says_so(p):
    run = start(p)
    p.investigations.executor.down = True
    view = p.investigations.get(ctx(p, 'ana'), run['run_id'])
    assert view['status'] == 'submitted' and view['sync']['reachable'] is False


def test_deadline_without_report_blocks(p):
    run = start(p)
    with p.store.transaction('t') as tx:
        rec = tx.require('T', inv.KIND, run['run_id'])
        tx.put('T', inv.KIND, run['run_id'], {**rec.state, 'deadline': inv.iso(inv._now() - timedelta(minutes=10))},
               expected_revision=rec.revision, action='fixture')
    assert p.investigations.get(ctx(p, 'ana'), run['run_id'])['status'] == 'blocked'


def test_stop_cancels_and_later_events_are_ignored(p):
    run = start(p)
    job = job_of(p, run)
    with pytest.raises(PermissionError):
        p.investigations.stop(ctx(p, 'ben'), run['run_id'])
    stopped = p.investigations.stop(ctx(p, 'ana'), run['run_id'])
    assert stopped['status'] == 'cancelled' and p.investigations.executor.cancelled == [job['id']]
    p.investigations.executor.events_by_job[job['id']] = [ev(1, 'phase', phase='investigating')]
    job['state'] = 'succeeded'
    assert p.investigations.get(ctx(p, 'ana'), run['run_id'])['status'] == 'cancelled'
    assert p.investigations.events(ctx(p, 'ana'), run['run_id'])['events'] == []


def test_valid_report_is_stored_for_review_and_invalid_one_is_refused(p):
    good, bad = start(p), start(p)
    for run, sha in ((good, None), (bad, '0' * 64)):
        job = job_of(p, run)
        job['state'] = 'succeeded'
        snapshot = p.store.read().require('T', inv.KIND, run['run_id']).state['evidence_snapshot']['sha256']
        p.investigations.executor.results[job['id']] = {'run_id': job['id'], 'input_sha256': sha or snapshot,
                                                       'review_status': 'requires_human_review', 'report': {'summary': 'x'}}
    assert p.investigations.get(ctx(p, 'ana'), good['run_id'])['status'] == 'awaiting_review'
    report = p.investigations.report(ctx(p, 'ana'), good['run_id'])
    assert report['review_status'] == 'requires_human_review' and report['report'] == {'summary': 'x'}
    refused = p.investigations.get(ctx(p, 'ana'), bad['run_id'])
    assert refused['status'] == 'blocked' and any('failed validation' in i for i in refused['issues'])
    with pytest.raises(ConflictError):
        p.investigations.report(ctx(p, 'ana'), bad['run_id'])


def test_runs_are_private_to_their_owner_without_case_access(p):
    run = start(p)
    with pytest.raises(PermissionError):
        p.investigations.get(ctx(p, 'ben'), run['run_id'])
    assert p.investigations.list(ctx(p, 'ben')) == []


def test_service_token_verifies_with_published_jwks(p):
    issuer = p.investigations.issuer
    token = issuer.token('proj-1')
    key = jwt.PyJWK(issuer.jwks()['keys'][0]).key
    claims = jwt.decode(token, key, algorithms=['RS256'], audience='exec-aud', issuer='https://api.example')
    assert claims['sub'] == 'platform-service' and claims['tenant_id'] == 'exec-tenant'
    assert claims['projects'] == {'proj-1': 'operator'} and claims['exp'] - claims['iat'] == 300
    assert jwt.get_unverified_header(token)['kid'] == 'k1'
    assert 'd' not in issuer.jwks()['keys'][0]  # public key only


def test_config_from_env_and_project_derivation():
    assert inv.ExecutorConfig.from_env({}) is None
    cfg = inv.ExecutorConfig.from_env({'INVESTIGATION_EXECUTOR_URL': 'https://x/', 'INVESTIGATION_SIGNING_KEY': KEY,
                                       'DEPLOYMENT_TENANT': 'sievance'})
    assert cfg.url == 'https://x' and cfg.tenant == 'sievance' and cfg.project_for('org 7') == 'org-7'


def test_routes_jwks_404_and_start_409_when_not_configured():
    from fastapi.testclient import TestClient
    from src.lifesci.api import create_app
    platform = Platform(RecordStore(), providers={})
    platform.investigations = inv.InvestigationService(platform, config=None, executor=None)
    platform.investigations.config = None
    platform.identity.assign_role('T', 'ana', 'msat', site_id='NF1')
    client = TestClient(create_app(platform))
    assert client.get('/.well-known/investigation-jwks.json').status_code == 404
    response = client.post('/v1/investigation-runs', json={'objective': 'Why?', 'site_id': 'NF1'},
                           headers={'X-Tenant-Id': 'T', 'X-Actor-Id': 'ana'})
    assert response.status_code == 409 and inv.NOT_CONFIGURED in response.text


def test_chat_proposal_is_only_a_proposal_and_start_consumes_it(p):
    ana = ctx(p, 'ana')
    thread = p.engineering_conversations.create(ana, {'site_id': 'NF1'})
    turn = {'id': 'turn-1'}
    proposal = p.investigations.propose(ana, thread={**thread, 'dataset_ids': []}, turn=turn, objective='Why did DEV-31 foam?',
                                        case_id=None, rationale='multi-source causal question')
    assert proposal['run_id'] is None and proposal['executor_configured'] is True
    with pytest.raises(PermissionError):
        p.investigations.start(ctx(p, 'ben'), {'proposal_id': proposal['id'], 'site_id': 'NF1'})
    run = p.investigations.start(ana, {'proposal_id': proposal['id'], 'site_id': 'NF1',
                                       'record_refs': [{'kind': 'evidence', 'id': 'lims:B-001'}]})
    assert run['proposal_id'] == proposal['id'] and run['conversation_id'] == thread['id']
    assert p.investigations.proposal_view(ana, proposal['id'])['run']['run_id'] == run['run_id']
    # Starting the same proposal again returns the same run instead of a second one.
    assert p.investigations.start(ana, {'proposal_id': proposal['id'], 'site_id': 'NF1'})['run_id'] == run['run_id']


def test_chat_operator_requires_the_users_words():
    from src.lifesci.process_engineering.conversation import OPERATIONS, quoted
    from src.lifesci.process_engineering.conversation_schemas import Operator
    assert 'workspace_propose_investigation' in OPERATIONS and 'workspace_propose_investigation' in Operator.__args__
    assert quoted('investigate DEV-31', 'Please investigate DEV-31 for me')
    assert not quoted('investigate DEV-31', 'What is DEV-31?')


def test_fermentation_assessment_unchanged_when_not_configured(p, monkeypatch):
    p.investigations = inv.InvestigationService(p, config=None, executor=None)
    p.investigations.config = None
    called = {}

    def fake_attempt(platform, c, public, directory, blinded, assumptions):
        called['yes'] = True
        return {'execution_status': 'completed'}
    import src.lifesci.fermentation.benchmark as bench
    monkeypatch.setattr(bench, 'attempt', fake_attempt)
    from src.lifesci.fermentation.data import CASE_IDS
    out = p.fermentation.agent_assessment(ctx(p, 'ana'), CASE_IDS[0])
    assert called and out['execution_status'] == 'completed'


def test_fermentation_assessment_keeps_its_calibrated_path_even_when_configured(p, monkeypatch):
    # The executor image lacks the fermentation_transfer tool and calibrated prompt, so no run is started.
    called = {}
    import src.lifesci.fermentation.benchmark as bench
    monkeypatch.setattr(bench, 'attempt', lambda *a, **k: called.setdefault('yes', {'execution_status': 'completed'}))
    from src.lifesci.fermentation.data import CASE_IDS
    out = p.fermentation.agent_assessment(ctx(p, 'ana'), CASE_IDS[0], assumptions={'kla': 100})
    assert called and out['execution_status'] == 'completed'
    assert p.store.read().list('T', inv.KIND) == []



def test_send_for_review_puts_hypotheses_on_the_case_and_builds_the_qa_package(p):
    p.identity.assign_role('T', 'qa-lead', 'qa', site_id='NF1')
    p.cases.open(ctx(p, 'ana'), 'DEV-31', 'ana', 'qa-lead', 'NF1')
    run = start(p, case_id='DEV-31')
    with pytest.raises(ConflictError):  # not finished yet
        p.investigations.send_for_review(ctx(p, 'ana'), run['run_id'])
    job = job_of(p, run)
    job['state'] = 'succeeded'
    sha = p.store.read().require('T', inv.KIND, run['run_id']).state['evidence_snapshot']['sha256']
    p.investigations.executor.results[job['id']] = {'run_id': job['id'], 'input_sha256': sha, 'review_status': 'requires_human_review',
        'report': {'hypotheses': [{'statement': 'Antifoam dosing lagged foaming onset', 'contradicting_evidence_status': 'searched_none'}],
                   'open_questions': ['Was pump AF-2 serviced?']}}
    assert p.investigations.get(ctx(p, 'ana'), run['run_id'])['status'] == 'awaiting_review'
    with pytest.raises(PermissionError):
        p.investigations.send_for_review(ctx(p, 'bot', 'agent'), run['run_id'])
    sent = p.investigations.send_for_review(ctx(p, 'ana'), run['run_id'])
    claims = {c.state['text']: c.state for c in p.store.read().list('T', 'claim', lambda s: s.get('case_id') == 'DEV-31')}
    assert claims['Antifoam dosing lagged foaming onset']['claim_class'] == 'hypothesis'
    assert claims['Was pump AF-2 serviced?']['claim_class'] == 'unknown'
    assert sent['package_id'] and len(sent['claims']) == 2
    assert p.investigations.send_for_review(ctx(p, 'ana'), run['run_id']) == sent  # idempotent


def test_send_for_review_needs_a_case(p):
    run = start(p)
    job = job_of(p, run); job['state'] = 'succeeded'
    sha = p.store.read().require('T', inv.KIND, run['run_id']).state['evidence_snapshot']['sha256']
    p.investigations.executor.results[job['id']] = {'run_id': job['id'], 'input_sha256': sha, 'review_status': 'requires_human_review', 'report': {}}
    p.investigations.get(ctx(p, 'ana'), run['run_id'])
    with pytest.raises(ValueError, match='case'):
        p.investigations.send_for_review(ctx(p, 'ana'), run['run_id'])
