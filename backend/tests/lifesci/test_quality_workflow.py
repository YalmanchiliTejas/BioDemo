import pytest
from fastapi.testclient import TestClient

from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.evidence import EvidenceRef
from src.lifesci.identity import AuthorizationError
from src.lifesci.store import RecordStore, ConflictError


@pytest.fixture
def env(monkeypatch):
    import os
    for name in os.environ:
        if 'DATABASE' in name or name.endswith('DB_URL'):
            monkeypatch.setenv(name, '')
    p = Platform(RecordStore(), providers={})
    for actor, role in [('owner', 'msat'), ('qa', 'qa_reviewer'), ('other', 'engineering')]:
        p.identity.assign_role('T', actor, role, site_id='S1')
    return p, p.identity.context_for('T', 'owner'), p.identity.context_for('T', 'qa')


def source(p, ctx, rid='r1', content=b'original', event_time='2026-01-01T00:00:00+00:00', **mapped):
    r = p.evidence.ingest(ctx, source_system='LIMS', source_record_id=rid, content=content,
        media_type='text/plain', site_id='S1', event_time=event_time,
        metadata={'mapped': {'batch_id': 'B1', **mapped}})
    return {'kind': 'evidence', 'id': r['evidence_id'], 'revision': r['revision'], 'site_id': 'S1'}


def create(p, ctx, refs=(), **extra):
    return p.quality_workflow.create(ctx, case_id='C1', site_id='S1', title='Synthetic excursion',
        owner_id='owner', qa_reviewer_id='qa', associations={'batch_id': 'B1'},
        discovery_refs=list(refs), idempotency_key='create-1', **extra)


def mutate(p, ctx, operation, **data):
    w = p.quality_workflow.get(ctx, 'C1')
    return getattr(p.quality_workflow, operation)(ctx, 'C1', expected_revision=w['revision'],
        idempotency_key=f'{operation}-{w["revision"]}', **data)


def assessed(p, ctx):
    if not p.quality_workflow.get(ctx, 'C1')['workflow'].get('triage'):
        mutate(p, ctx, 'transition', transition='assign', reason='Prepare local deviation')
    return mutate(p, ctx, 'assessment', assessment={'technical_summary': 'Cause not established',
        'root_cause_status': 'unresolved', 'limitations': ['Limited observation period'],
        'impact': {'summary': 'B1 reviewed; distribution unknown', 'status': 'assessed',
                   'disposition': 'pending external QA'}})


def test_source_download_preserves_non_utf8_bytes_and_pinned_revision(env):
    import base64
    p, owner, _ = env
    original = b'batch,label\r\nB1,caf\xe9\r\n'
    ref = source(p, owner, content=original)
    create(p, owner, [ref])
    source(p, owner, content=b'new revision')
    result = p.quality_workflow.source(owner, 'C1', 'evidence', ref['id'], revision=1)
    assert base64.b64decode(result['original_base64']) == original
    assert '\ufffd' in result['content_text']  # preview is explicitly distinct from original bytes


def test_authorized_legacy_adoption_context_keeps_oos_site_people_identifiers_and_original_revisions(env):
    p, _, _ = env
    for actor, role in [('owner','msat'),('qa','qa_reviewer')]:
        p.identity.assign_role('T',actor,role,site_id='S2')
    owner = p.identity.context_for('T','owner')
    original = p.evidence.ingest(owner, source_system='synthetic-lims', source_record_id='legacy-oos',
        content=b'original OOS', media_type='text/plain', site_id='S2', event_time=None)
    ref = {'kind':'evidence','id':original['evidence_id'],'revision':1,'site_id':'S2'}
    signal = p.signals.raise_signal('T',kind='lab_oos',severity='action',site_id='S2',subject={'kind':'batch','id':'0002'},
        rule='Synthetic OOS',rule_key='adoption',evidence_refs=[ref],
        associations={'batch_id':'0002','equipment_id':'EQ2','product_id':'P2','supplier_id':'SUP2'})
    p.signals.open_case(owner,signal['signal_id'],owner_id='owner',qa_reviewer_id='qa',case_id='LEGACY-S2')
    with p.store.transaction('fixture') as tx:
        case = tx.require('T','case','LEGACY-S2')
        tx.put('T','case','LEGACY-S2',{**case.state,'title':'Recorded laboratory event','associations':{'lot_id':'0007'},
            'priority':'high','initial_risk':'Pending lab review','deadline':'2026-12-01T12:00:00+00:00'},expected_revision=case.revision,action='fixture')
    p.evidence.ingest(owner,source_system='synthetic-lims',source_record_id='legacy-oos',content=b'newer source',media_type='text/plain',site_id='S2',event_time=None)
    client = TestClient(create_app(p))
    response = client.get('/v1/quality/workspaces/LEGACY-S2/adoption-context',headers={'X-Tenant-Id':'T','X-Actor-Id':'owner'})
    assert response.status_code == 200
    context = response.json()
    assert context['case']['site_id']=='S2' and context['case']['category']=='oos'
    assert context['case']['owner_id']=='owner' and context['case']['qa_reviewer_id']=='qa'
    assert context['case']['title']=='Recorded laboratory event' and context['case']['priority']=='high'
    assert context['case']['associations']=={'batch_id':'0002','equipment_id':'EQ2','product_id':'P2','supplier_id':'SUP2','lot_id':'0007'}
    assert ref in context['discovery_refs']
    assert context['signals'][0]['signal_id']==signal['signal_id']
    p.identity.grant('T',grantee_id='limited',resource_kind='case',resource_id='LEGACY-S2',actions=['read','propose'],site_id='S2')
    assert client.get('/v1/quality/workspaces/LEGACY-S2/adoption-context',headers={'X-Tenant-Id':'T','X-Actor-Id':'limited'}).status_code==403
    # A word in a title is not a laboratory classification.
    p.cases.open(owner,'TITLE-OOS','owner','qa','S2')
    with p.store.transaction('fixture') as tx:
        case=tx.require('T','case','TITLE-OOS')
        tx.put('T','case','TITLE-OOS',{**case.state,'title':'Question mentioning OOS'},expected_revision=case.revision,action='fixture')
    assert client.get('/v1/quality/workspaces/TITLE-OOS/adoption-context',headers={'X-Tenant-Id':'T','X-Actor-Id':'owner'}).json()['case']['category']=='process_excursion'


def test_legacy_adoption_pins_supplied_old_source_and_rejects_changed_case_context(env):
    p, owner, _ = env
    ref = source(p,owner)
    legacy = p.cases.open(owner,'LEG','owner','qa','S1')
    source(p,owner,content=b'corrected source')
    args = dict(case_id='LEG',site_id='S1',title='Legacy adoption',owner_id='owner',qa_reviewer_id='qa',discovery_refs=[ref])
    with pytest.raises(ConflictError,match='case revision'):
        p.quality_workflow.create(owner,**args,expected_case_revision=legacy['revision']+1,idempotency_key='stale-context')
    w = p.quality_workflow.create(owner,**args,expected_case_revision=legacy['revision'],idempotency_key='adopt-context')
    assert w['sources'][0]['ref']==ref
    assert p.quality_workflow.source(owner,'LEG','evidence',ref['id'],revision=1)['content_text']=='original'
    assert w['completeness']['source_drift']


def test_optional_legacy_revision_guard_preserves_existing_create_retry_receipts(env):
    from src.lifesci.ids import content_hash
    p, owner, _ = env
    ref=source(p,owner)
    original=create(p,owner,[ref])
    # A receipt written by the pre-extension signature has no optional guard field.
    payload={'case_id':'C1','site_id':'S1','title':'Synthetic excursion','owner_id':'owner','qa_reviewer_id':'qa',
        'associations':{'batch_id':'B1'},'discovery_refs':[ref],'category':'process_excursion','priority':'normal',
        'initial_risk':'','deadline':None,'external_reference':None,'idempotency_key':'create-1'}
    receipt_id=content_hash(['owner','C1','create','create-1'])
    with p.store.transaction('fixture') as tx:
        receipt=tx.require('T','quality_intent',receipt_id)
        tx.put('T','quality_intent',receipt_id,{**receipt.state,'request_hash':content_hash(payload)},
            expected_revision=receipt.revision,action='pre_extension_receipt')
    assert create(p,owner,[ref])['revision']==original['revision']


def test_assistant_projection_identifies_managed_case_without_workflow_payload(env):
    p, owner, _ = env
    w = create(p, owner)
    thread = p.engineering_conversations.create(owner, {'site_id':'S1'})
    result = p.engineering_conversations.workspace.read(owner, thread, kind='case', record_id='C1', revision=w['revision'])
    assert result['record']['data']['managed_quality'] is True
    assert 'workflow' not in result['record']['data']
    truncated = p.engineering_conversations.workspace.read(owner, thread, kind='case', record_id='C1', revision=w['revision'], max_chars=32)
    assert truncated['record']['data']['truncated'] is True
    assert truncated['record']['data']['managed_quality'] is True
    p.cases.open(owner, 'LEGACY', 'owner', 'qa', 'S1')
    result = p.engineering_conversations.workspace.read(owner, thread, kind='case', record_id='LEGACY', revision=1)
    assert result['record']['data']['managed_quality'] is False


def test_A_persistent_local_review_handoff_and_legacy_bypass(env):
    p, owner, qa = env
    ref = source(p, owner)
    w = create(p, owner, [ref])
    assert w['workflow']['state'] == 'awaiting_triage'
    with pytest.raises(ValueError, match='managed'):
        p.cases.close(qa, 'C1', root_cause='unknown', actions_taken='none', outcome='pending', expected_revision=w['revision'])
    mutate(p, owner, 'transition', transition='assign', reason='Prepare local deviation')
    mutate(p, owner, 'prepare')
    assessed(p, owner)
    mutate(p, owner, 'transition', transition='submit_technical', reason='Ready')
    mutate(p, owner, 'transition', transition='submit_qa', reason='Technical review complete')
    w = mutate(p, qa, 'transition', transition='approve_local', reason='Local preparation reviewed')
    assert w['workflow']['state'] == 'handoff_pending'
    assert w['reviews'][-1]['decision'] == 'approve_local'
    package = p.quality_workflow.export(qa, 'C1')
    assert package['external_status'] == 'pending_external_approval'
    assert package['source_manifest'][0]['revision'] == 1
    assert p.quality_workflow.source(qa, 'C1', 'evidence', ref['id'], revision=1)['content_text'] == 'original'
    assert not p.store.read().list('T', 'action_intent')


def test_B_oos_requires_explicit_lab_assessment_preserves_original(env):
    p, owner, _ = env
    ref = source(p, owner, record_type='result', status='OOS')
    create(p, owner, [ref], category='oos')
    mutate(p, owner, 'prepare')
    assert 'initial_lab_assessment' in p.quality_workflow.get(owner, 'C1')['completeness']['missing']
    mutate(p, owner, 'assessment', assessment={'initial_lab_assessment': {'conclusion': 'expanded_investigation',
           'rationale': 'No assignable laboratory error', 'evidence_refs': [ref]}})
    assert p.quality_workflow.get(owner, 'C1')['sources'][0]['state']['metadata']['mapped']['status'] == 'OOS'


def test_D_E_incomplete_return_immutable_snapshots_and_source_drift(env):
    p, owner, qa = env
    ref = source(p, owner)
    create(p, owner, [ref])
    mutate(p, owner, 'prepare')
    mutate(p, owner, 'evidence_request', request={'description': 'Calibration certificate', 'owner_id': 'owner', 'required': True})
    mutate(p, owner, 'transition', transition='submit_technical', reason='Inspect incomplete draft')
    mutate(p, owner, 'transition', transition='submit_qa', reason='QA inspection needed')
    first = p.quality_workflow.get(qa, 'C1')['reviews'][0]
    with pytest.raises(ValueError, match='incomplete'):
        mutate(p, qa, 'transition', transition='approve_local', reason='Approve')
    mutate(p, qa, 'transition', transition='return', reason='Obtain calibration')
    mutate(p, owner, 'prepare')
    assessed(p, owner)
    assert p.quality_workflow.get(qa, 'C1')['reviews'][0] == first
    source(p, owner, content=b'corrected')
    assert p.quality_workflow.get(owner, 'C1')['completeness']['source_drift']


def test_authorization_revision_idempotency_and_stored_source_permissions(env):
    p, owner, qa = env
    ref = source(p, owner)
    w = create(p, owner, [ref])
    assert create(p, owner, [ref])['revision'] == w['revision']
    with pytest.raises(ConflictError):
        p.quality_workflow.prepare(owner, 'C1', expected_revision=0, idempotency_key='stale')
    with pytest.raises((PermissionError, AuthorizationError)):
        mutate(p, qa, 'assessment', assessment={'technical_summary': 'changed'})
    with pytest.raises((PermissionError, AuthorizationError)):
        mutate(p, p.identity.context_for('T', 'other'), 'transition', transition='approve_local', reason='no')
    # Case-only grant never exposes a stored source or prior review.
    p.identity.grant('T', grantee_id='limited', resource_kind='case', resource_id='C1', actions=['read', 'export'], site_id='S1')
    limited = p.identity.context_for('T', 'limited')
    for fn in [lambda: p.quality_workflow.get(limited, 'C1'), lambda: p.quality_workflow.export(limited, 'C1')]:
        with pytest.raises((PermissionError, AuthorizationError)):
            fn()
    with pytest.raises((PermissionError, AuthorizationError)):
        p.cases.get(limited, 'C1')
    client = TestClient(create_app(p, resolver=lambda _: limited))
    assert client.get('/v1/records/case/C1').status_code == 403
    assert client.get('/v1/records/case').json()['items'] == []


def test_F_mission_preparation_resume_recurrence_and_idle_noop(env):
    p, owner, _ = env
    source(p, owner)
    create(p, owner)
    w = mutate(p, owner, 'prepare', queued=True)
    assert w['workflow']['preparation']['status'] == 'queued'
    p.runtime.tick()
    w = p.quality_workflow.get(owner, 'C1')
    assert w['sources'] and w['workflow']['preparation']['status'] == 'completed'
    w = mutate(p, owner, 'action', action={'description': 'Recalibrate', 'kind': 'capa', 'owner_id': 'owner', 'due_at': '2026-12-01T00:00:00+00:00'})
    action_id = w['actions'][0]['id']
    ref = w['sources'][0]['ref']
    mutate(p, owner, 'action', action={'id': action_id, 'status': 'completed', 'completion_refs': [ref],
           'completed_at': '2026-01-02T00:00:00+00:00'})
    source(p, owner, 'r2', content=b'recurrence', event_time='2026-01-03T00:00:00+00:00', status='OOS')
    p.runtime.tick()
    w = p.quality_workflow.get(owner, 'C1')
    assert w['workflow']['effectiveness_concerns']
    rev = w['revision']
    p.runtime.tick()
    assert p.quality_workflow.get(owner, 'C1')['revision'] == rev


def test_recurrence_uses_event_clock_and_exposes_missing_clock(env):
    p, owner, _ = env
    ref = source(p, owner)
    create(p, owner, [ref])
    mutate(p, owner, 'prepare')
    w = mutate(p, owner, 'action', action={'description': 'Repair', 'kind': 'corrective_action',
        'owner_id': 'owner', 'due_at': '2026-01-02T00:00:00+00:00'})
    mutate(p, owner, 'action', action={'id': w['actions'][0]['id'], 'status': 'completed',
        'completion_refs': [ref], 'completed_at': '2026-01-02T00:00:00+00:00'})
    source(p, owner, 'late', event_time='2026-01-01T12:00:00+00:00')
    p.runtime.tick()
    assert not p.quality_workflow.get(owner, 'C1')['workflow']['effectiveness_concerns']
    source(p, owner, 'unknown-clock', event_time=None, status='OOS')
    p.runtime.tick()
    concerns = p.quality_workflow.get(owner, 'C1')['workflow']['effectiveness_concerns']
    assert concerns[-1]['timing_status'] == 'uncertain'
    assert concerns[-1]['status'] == 'requires_human_assessment'


def test_review_source_arrival_requires_resubmission_after_refresh(env):
    p, owner, qa = env
    create(p, owner, [source(p, owner)])
    mutate(p, owner, 'prepare')
    assessed(p, owner)
    mutate(p, owner, 'transition', transition='submit_technical', reason='Inspect')
    mutate(p, owner, 'transition', transition='submit_qa', reason='Review')
    snapshot = p.quality_workflow.get(qa, 'C1')['reviews'][0]
    source(p, owner, 'new')
    p.runtime.tick()
    w = p.quality_workflow.get(qa, 'C1')
    assert w['reviews'][0] == snapshot
    assert w['completeness']['submission_drift']
    with pytest.raises(ValueError, match='incomplete'):
        mutate(p, qa, 'transition', transition='approve_local', reason='Cannot approve stale')
    mutate(p, qa, 'transition', transition='return', reason='Review new evidence')
    mutate(p, owner, 'transition', transition='submit_technical', reason='New source reviewed')
    mutate(p, owner, 'transition', transition='submit_qa', reason='Ready again')
    assert mutate(p, qa, 'transition', transition='approve_local', reason='Current basis')['workflow']['state'] == 'handoff_pending'


def test_assignee_directory_is_site_scoped_and_has_current_qa_roles(env):
    p, owner, _ = env
    p.identity.assign_role('T', 'elsewhere', 'qa', site_id='S2')
    directory = p.quality_workflow.assignees(owner, 'S1')
    assert {r['actor_id'] for r in directory['items']} == {'owner', 'qa', 'other'}
    assert next(r for r in directory['items'] if r['actor_id'] == 'qa')['eligible_qa_reviewer']
    assert all(set(r) <= {'actor_id', 'label', 'roles', 'eligible_owner', 'eligible_qa_reviewer'} for r in directory['items'])
    p.identity.assign_role('T', 'split', 'qa', site_id='S2')
    p.identity.assign_role('T', 'split', 'msat', site_id='S1')
    with pytest.raises(ValueError, match='QA'):
        p.quality_workflow.create(owner, case_id='split-case', site_id='S1', title='Synthetic',
            owner_id='owner', qa_reviewer_id='split', idempotency_key='split-case')


def test_identifier_types_and_leading_zero_are_preserved(env):
    p, owner, _ = env
    source(p, owner, 'wrong-type', batch_id='different', equipment_id='001')
    source(p, owner, 'wrong-zero', batch_id='1')
    ref = source(p, owner, 'correct', batch_id='001')
    p.quality_workflow.create(owner, case_id='C1', site_id='S1', title='Synthetic', owner_id='owner',
        qa_reviewer_id='qa', associations={'batch_id': '001'}, idempotency_key='typed')
    w = mutate(p, owner, 'prepare')
    assert [r['ref']['id'] for r in w['sources']] == [ref['id']]


def test_science_hook_pins_current_inputs_and_locked_review_blocks_edits(env):
    p, owner, _ = env
    ref = source(p, owner)
    create(p, owner, [ref])
    w = mutate(p, owner, 'record_science', science={'model_runs': [{'id': 'local-run', 'source_refs': [ref]}], 'unknowns': ['Parameters absent']})
    assert w['science']['model_runs'][0]['source_refs'] == [ref]
    mutate(p, owner, 'transition', transition='submit_technical', reason='Inspect')
    with pytest.raises(ValueError, match='return'):
        mutate(p, owner, 'hypotheses', hypothesis={'text': 'New possibility', 'counterevidence_status': 'not_searched'})
    with pytest.raises(PermissionError):
        mutate(p, owner, 'transition', transition='assign', reason='Bypass return')


def test_delegated_science_is_advisory_and_constrained_to_case_basis(env):
    from src.lifesci.roles import agent_context_for
    p, owner, _ = env
    ref = source(p, owner)
    create(p, owner, [ref])
    agent = agent_context_for(owner, p.identity)
    w = mutate(p, agent, 'record_science', science={'source_refs': [ref], 'result': 'Parameter missing'})
    assert w['science']['advisory']
    outside = source(p, owner, 'unattached', batch_id='B2')
    with pytest.raises(ValueError, match='basis'):
        mutate(p, agent, 'record_science', science={'source_refs': [outside]})


def test_runtime_failure_is_visible_recoverable_and_duplicate_delivery_does_not_write(env, monkeypatch):
    p, owner, _ = env
    create(p, owner, [source(p, owner)])
    mutate(p, owner, 'prepare', queued=True)
    original = p.quality_workflow.evidence.collect
    def fail(*args, **kwargs):
        raise ValueError('synthetic source unavailable')
    monkeypatch.setattr(p.quality_workflow.evidence, 'collect', fail)
    p.runtime.tick()
    w = p.quality_workflow.get(owner, 'C1')
    assert w['workflow']['preparation']['status'] == 'failed'
    assert w['workflow']['preparation']['recoverable']
    monkeypatch.setattr(p.quality_workflow.evidence, 'collect', original)
    mutate(p, owner, 'prepare', queued=True)
    p.runtime.tick()
    assert p.quality_workflow.get(owner, 'C1')['workflow']['preparation']['status'] == 'completed'


def test_queued_preparation_recovers_without_ephemeral_scheduler_wakeup(env):
    p, owner, _ = env
    create(p, owner, [source(p, owner)])
    mutate(p, owner, 'prepare', queued=True)
    # A replacement process retains records but loses the in-process wakeup list.
    p.missions.scheduler.wakeups.clear()
    p.missions.scheduler.timers.clear()
    p.runtime.tick()
    assert p.quality_workflow.get(owner, 'C1')['workflow']['preparation']['status'] == 'completed'


def test_persisted_workspace_mission_recovers_in_new_platform(env, tmp_path):
    p, _, _ = env
    path = str(tmp_path / 'synthetic-quality.sqlite')
    first = Platform(RecordStore(path), providers={})
    for actor, role in [('owner', 'msat'), ('qa', 'qa_reviewer')]:
        first.identity.assign_role('T', actor, role, site_id='S1')
    owner = first.identity.context_for('T', 'owner')
    create(first, owner, [source(first, owner)])
    mutate(first, owner, 'prepare', queued=True)
    replacement = Platform(RecordStore(path), providers={})
    replacement.runtime.track('T')
    replacement.runtime.tick()
    assert replacement.quality_workflow.get(owner, 'C1')['workflow']['preparation']['status'] == 'completed'


def test_material_immediate_action_blocks_local_approval_future_capa_does_not(env):
    p, owner, qa = env
    ref = source(p, owner)
    create(p, owner, [ref])
    mutate(p, owner, 'prepare')
    assessed(p, owner)
    w = mutate(p, owner, 'action', action={'description': 'Check affected equipment', 'kind': 'immediate_correction',
        'owner_id': 'owner', 'due_at': '2026-12-01T00:00:00+00:00', 'required_immediate': True})
    action_id = w['actions'][0]['id']
    mutate(p, owner, 'action', action={'description': 'Long-term prevention', 'kind': 'capa',
        'owner_id': 'owner', 'due_at': '2026-12-01T00:00:00+00:00'})
    assert 'immediate_action:' + action_id in p.quality_workflow.get(qa, 'C1')['completeness']['missing']
    mutate(p, owner, 'action', action={'id': action_id, 'status': 'completed', 'completion_refs': [ref]})
    assert p.quality_workflow.get(qa, 'C1')['completeness']['complete']


def test_pinned_source_endpoint_and_export_do_not_replace_historical_original(env):
    p, owner, qa = env
    ref = source(p, owner, 'folder/r1')
    create(p, owner, [ref])
    source(p, owner, 'folder/r1', content=b'correction')
    client = TestClient(create_app(p, resolver=lambda _: qa))
    response = client.get('/v1/quality/workspaces/C1/evidence/evidence/LIMS:folder/r1?revision=1')
    assert response.status_code == 200
    assert response.json()['content_text'] == 'original'
    assert client.get('/v1/quality/workspaces/C1/export?format=html').status_code == 200


def test_revoked_qa_role_and_delegated_agent_cannot_make_decisions(env):
    from src.lifesci.roles import agent_context_for
    p, owner, qa = env
    create(p, owner, [source(p, owner)])
    agent = agent_context_for(owner, p.identity)
    with pytest.raises(PermissionError, match='human'):
        mutate(p, agent, 'transition', transition='assign', reason='Agent may not triage')
    p.identity.revoke_role('T', 'qa', 'qa_reviewer', site_id='S1')
    with pytest.raises((PermissionError, AuthorizationError)):
        p.quality_workflow.transition(qa, 'C1', transition='approve_local', reason='Old session',
            expected_revision=1, idempotency_key='revoked')


def test_api_is_mounted_and_requires_revision_and_intent_key(env):
    p, owner, _ = env
    client = TestClient(create_app(p, resolver=lambda _: owner))
    body = {'case_id': 'C1', 'site_id': 'S1', 'title': 'Synthetic', 'owner_id': 'owner', 'qa_reviewer_id': 'qa'}
    assert client.post('/v1/quality/workspaces', json=body).status_code == 422
    response = client.post('/v1/quality/workspaces', json=body, headers={'Idempotency-Key': 'create-1'})
    assert response.status_code == 200
    assert client.get('/v1/quality/workspaces/C1').json()['case']['title'] == 'Synthetic'
    assert client.post('/v1/quality/workspaces/C1/prepare', json={}).status_code == 422


def test_nested_managed_case_and_derived_inputs_never_bypass_source_permissions(env):
    p, owner, _ = env
    ref = source(p, owner)
    create(p, owner, [ref])
    case_ref = {'kind': 'case', 'id': 'C1', 'revision': 1, 'site_id': 'S1'}
    derived = p.evidence.record_derived(owner, 'draft_artifact', {'site_id': 'S1'},
        inputs=[EvidenceRef(**case_ref)],
        produced_by={'method': 'synthetic'})
    for kind, rid, actions in [('case', 'C1', ['read']), ('case', 'C2', ['read', 'propose']),
                               ('draft_artifact', derived['id'], ['read'])]:
        p.identity.grant('T', grantee_id='limited', resource_kind=kind, resource_id=rid, actions=actions, site_id='S1')
    limited = p.identity.context_for('T', 'limited')
    for nested in [case_ref, {'kind': 'draft_artifact', 'id': derived['id'], 'revision': 1, 'site_id': 'S1'}]:
        with pytest.raises(PermissionError):
            p.quality_workflow.create(limited, case_id='C2', site_id='S1', title='Nested', owner_id='owner',
                qa_reviewer_id='qa', discovery_refs=[nested], idempotency_key='nested-' + nested['kind'])
    grant = p.identity.grant('T', grantee_id='limited', resource_kind='evidence', resource_id=ref['id'], actions=['read'], site_id='S1')
    p.quality_workflow.create(limited, case_id='C2', site_id='S1', title='Nested', owner_id='owner',
        qa_reviewer_id='qa', discovery_refs=[case_ref], idempotency_key='authorized-nested')
    p.identity.revoke_grant('T', grant)
    with pytest.raises(PermissionError):
        p.quality_workflow.get(limited, 'C2')
    # Authorized historical content still resolves after a correction.
    source(p, owner, content=b'correction')
    assert p.quality_workflow.evidence.views(owner, [case_ref])[0]['state']['workflow']['sources'] == [ref]
    with p.store.transaction('synthetic') as tx:
        old = tx.require('T', 'case', 'C1')
        state = old.state
        state['workflow']['sources'] = [case_ref]
        tx.put('T', 'case', 'C1', state, expected_revision=old.revision, action='synthetic_cycle')
    with pytest.raises(PermissionError, match='cycl'):
        p.quality_workflow.evidence.views(owner, [case_ref])


@pytest.mark.parametrize('observation_only', [False, True])
def test_deviation_signal_source_requires_its_known_evidence_lineage(env, observation_only):
    p, owner, _ = env
    ref = source(p, owner)
    signal = p.signals.raise_signal('T', kind='lab_oos', severity='action', rule='Synthetic OOS',
        site_id='S1', subject={'kind': 'batch', 'id': 'B1'}, rule_key='synthetic-oos',
        evidence_refs=[] if observation_only else [ref],
        observations=[{'evidence_ref': ref, 'original_value': 4.0}])
    signal_ref = {'kind': 'deviation_signal', 'id': signal['signal_id'],
        'revision': p.store.read().require('T', 'deviation_signal', signal['signal_id']).revision, 'site_id': 'S1'}
    for kind, rid, actions in [('deviation_signal', signal['signal_id'], ['read']), ('case', 'C2', ['read', 'propose'])]:
        p.identity.grant('T', grantee_id='limited', resource_kind=kind, resource_id=rid, actions=actions, site_id='S1')
    limited = p.identity.context_for('T', 'limited')
    with pytest.raises(PermissionError):
        p.quality_workflow.create(limited, case_id='C2', site_id='S1', title='Signal source', owner_id='owner',
            qa_reviewer_id='qa', discovery_refs=[signal_ref], idempotency_key='signal-source')


@pytest.mark.parametrize('operation,payload', [
    ('evidence_request', {'request': {'description': 'Calibration', 'owner_id': 'owner', 'status': 'resolved'}}),
    ('action', {'action': {'description': 'Repair', 'owner_id': 'owner', 'kind': 'immediate_correction',
        'due_at': '2026-12-01T00:00:00+00:00', 'required_immediate': True, 'status': 'completed',
        'completion_refs': [{'id': 'nonexistent'}]}}),
    ('action', {'action': {'description': 'Repair', 'owner_id': 'owner', 'kind': 'invalid',
        'due_at': '2026-12-01T00:00:00+00:00'}}),
    ('action', {'action': {'description': 'Repair', 'owner_id': 'owner', 'kind': 'capa',
        'due_at': '2026-12-01T00:00:00+00:00', 'history': []}}),
])
def test_invalid_complete_record_creation_is_rejected(env, operation, payload):
    p, owner, _ = env
    create(p, owner, [source(p, owner)])
    with pytest.raises((ValueError, PermissionError)):
        mutate(p, owner, operation, **payload)


@pytest.mark.parametrize('operation', ['evidence_request', 'action'])
def test_updates_validate_merged_evidence_assignee_and_server_history(env, operation):
    p, owner, _ = env
    ref = source(p, owner)
    create(p, owner, [ref])
    key = 'request' if operation == 'evidence_request' else 'action'
    field = 'evidence_refs' if key == 'request' else 'completion_refs'
    body = {'description': 'Synthetic followup', 'owner_id': 'owner', 'status': 'resolved' if key == 'request' else 'completed',
        field: [ref]}
    if key == 'action':
        body.update(kind='capa', due_at='2026-12-01T00:00:00+00:00')
    w = mutate(p, owner, operation, **{key: body})
    rid = w['requests' if key == 'request' else 'actions'][0]['id']
    for update in [{field: []}, {'owner_id': 'nonexistent'}, {'history': []}, {'status': 'invented'}]:
        with pytest.raises((ValueError, PermissionError)):
            mutate(p, owner, operation, **{key: {'id': rid, **update}})


def test_skipping_preparation_cannot_approve_uncollected_matching_evidence(env):
    p, owner, qa = env
    create(p, owner, [source(p, owner)])
    source(p, owner, 'uncollected')
    assessed(p, owner)
    mutate(p, owner, 'transition', transition='submit_technical', reason='Inspect without preparation')
    mutate(p, owner, 'transition', transition='submit_qa', reason='QA inspect')
    with pytest.raises(ValueError, match='incomplete'):
        mutate(p, qa, 'transition', transition='approve_local', reason='Must collect context first')


def test_creation_retry_after_source_correction_retains_drift_and_permissions(env):
    p, owner, _ = env
    ref = source(p, owner)
    original = create(p, owner, [ref])
    source(p, owner, content=b'correction')
    retried = create(p, owner, [ref])
    assert retried['revision'] == original['revision']
    assert retried['completeness']['source_drift']
    p.identity.revoke_role('T', 'owner', 'msat', site_id='S1')
    with pytest.raises(PermissionError):
        create(p, owner, [ref])


def test_corrected_current_basis_can_be_approved_while_old_submission_stays_inspectable(env):
    p, owner, qa = env
    ref = source(p, owner)
    create(p, owner, [ref])
    mutate(p, owner, 'prepare')
    assessed(p, owner)
    mutate(p, owner, 'transition', transition='submit_technical', reason='Original basis')
    mutate(p, owner, 'transition', transition='submit_qa', reason='Inspect')
    first = p.quality_workflow.get(qa, 'C1')['reviews'][0]
    source(p, owner, content=b'corrected basis')
    mutate(p, qa, 'transition', transition='return', reason='Review correction')
    mutate(p, owner, 'prepare')
    mutate(p, owner, 'transition', transition='submit_technical', reason='Corrected source assessed')
    mutate(p, owner, 'transition', transition='submit_qa', reason='New basis')
    w = mutate(p, qa, 'transition', transition='approve_local', reason='Current evidence reviewed')
    assert w['workflow']['state'] == 'handoff_pending'
    assert w['reviews'][0] == first
    assert p.quality_workflow.source(qa, 'C1', 'evidence', ref['id'], revision=1)['content_text'] == 'original'


def test_completeness_independently_blocks_legacy_invalid_resolved_records(env):
    p, owner, _ = env
    create(p, owner, [source(p, owner)])
    mutate(p, owner, 'prepare')
    assessed(p, owner)
    with p.store.transaction('synthetic') as tx:
        rec = tx.require('T', 'case', 'C1')
        state = rec.state
        state['workflow']['requests'] = [{'id': 'bad-request', 'description': 'Calibration', 'owner_id': 'owner',
            'required': True, 'status': 'resolved', 'evidence_refs': []}]
        state['workflow']['actions'] = [{'id': 'bad-action', 'description': 'Repair', 'owner_id': 'owner',
            'kind': 'immediate_correction', 'required_immediate': True, 'status': 'completed',
            'due_at': '2026-12-01T00:00:00+00:00', 'completion_refs': [{'id': 'nonexistent'}]}]
        tx.put('T', 'case', 'C1', state, expected_revision=rec.revision, action='synthetic_legacy_invalid')
    completeness = p.quality_workflow.get(owner, 'C1')['completeness']
    assert not completeness['complete']
    assert 'evidence_request:bad-request' in completeness['missing']
    assert 'immediate_action:bad-action' in completeness['missing']


@pytest.mark.parametrize('existing', [False, True])
def test_invalid_completion_clock_is_rejected_before_save_and_preparation_still_resumes(env, existing):
    p, owner, _ = env
    ref = source(p, owner)
    create(p, owner, [ref])
    mutate(p, owner, 'prepare')
    action = {'description': 'Repair', 'owner_id': 'owner', 'kind': 'corrective_action',
        'due_at': '2026-12-01T00:00:00+00:00'}
    if existing:
        w = mutate(p, owner, 'action', action=action)
        action = {'id': w['actions'][0]['id']}
    revision = p.quality_workflow.get(owner, 'C1')['revision']
    invalid = {**action, 'status': 'completed', 'completion_refs': [ref], 'completed_at': 'not-a-date'}
    with pytest.raises(ValueError, match='completion'):
        mutate(p, owner, 'action', action=invalid)
    assert p.quality_workflow.get(owner, 'C1')['revision'] == revision
    valid = {**invalid, 'completed_at': '2026-01-02T00:00:00+00:00'}
    mutate(p, owner, 'action', action=valid)
    source(p, owner, 'after-completion', event_time='2026-01-03T00:00:00+00:00', status='OOS')
    p.runtime.tick()
    w = p.quality_workflow.get(owner, 'C1')
    assert w['workflow']['preparation']['status'] == 'completed'
    assert w['workflow']['effectiveness_concerns'][-1]['timing_status'] == 'after_action_completion'


def test_native_publishers_and_supplier_only_sources_resume_quality_mission(env):
    from src.lifesci.ownership import Ownership
    p, owner, _ = env
    for role in ['admin', 'operator']:
        p.identity.assign_role('T', 'owner', role, site_id='S1')
    owner = p.identity.context_for('T', 'owner')
    for record_class in ['batch_record', 'lab_record']:
        p.ownership.assign('T', Ownership(record_class, 'S1', 'native', None, (), intended_use='Synthetic test'), by='test', reason='Synthetic')
    p.execution.create_native(owner, 'batch', 'B1', {'batch_id': 'B1', 'status': 'open'}, site_id='S1')
    create(p, owner)
    mutate(p, owner, 'prepare')
    sample = p.lab.register_sample(owner, 'B1', None, 'test', 'native-sample')
    p.runtime.tick()
    assert any(s['ref']['id'] == sample['sample_id'] for s in p.quality_workflow.get(owner, 'C1')['sources'])
    result = p.lab.record_result(owner, sample['sample_id'], 'potency', 4.0, 'mg/mL')
    p.runtime.tick()
    assert any(s['ref']['id'] == result['result_id'] for s in p.quality_workflow.get(owner, 'C1')['sources'])
    p.lab.register_instrument(owner, 'I1', {'batch_id': 'B1'}, site_id='S1')
    p.runtime.tick()
    assert any(s['ref']['id'] == 'I1' for s in p.quality_workflow.get(owner, 'C1')['sources'])
    p.execution.create_native(owner, 'material_lot', 'LOT1', {'batch_id': 'B1'}, site_id='S1')
    p.runtime.tick()
    assert any(s['ref']['id'] == 'LOT1' for s in p.quality_workflow.get(owner, 'C1')['sources'])
    p.quality_workflow.create(owner, case_id='SUP', site_id='S1', title='Supplier concern', owner_id='owner',
        qa_reviewer_id='qa', associations={'supplier_id': 'SUP1'}, idempotency_key='supplier')
    w = p.quality_workflow.get(owner, 'SUP')
    p.quality_workflow.prepare(owner, 'SUP', expected_revision=w['revision'], idempotency_key='supplier-prepare')
    source(p, owner, 'supplier-only', batch_id='unrelated', supplier_id='SUP1')
    p.runtime.tick()
    assert any(s['ref']['id'] == 'LIMS:supplier-only' for s in p.quality_workflow.get(owner, 'SUP')['sources'])


def test_reopened_no_deviation_external_status_matches_workspace_and_export(env):
    p, owner, _ = env
    create(p, owner)
    client = TestClient(create_app(p)); headers={'X-Tenant-Id':'T','X-Actor-Id':'owner'}
    for transition, status in [('no_formal_deviation','not_requested'), ('request_evidence','pending_external_approval'), ('reference_external','pending_external_approval')]:
        w = client.get('/v1/quality/workspaces/C1',headers=headers).json()
        response = client.post('/v1/quality/workspaces/C1/transition',headers={**headers,'Idempotency-Key':transition},json={
            'expected_revision':w['revision'],'transition':transition,'reason':'Synthetic reopening review',
            **({'external_reference':'QMS-SYN-1'} if transition == 'reference_external' else {})})
        assert response.status_code == 200, response.text
        w = response.json()
        package = client.get('/v1/quality/workspaces/C1/export',headers=headers).json()
        assert w['external_status'] == package['external_status'] == status
        assert package['external_receipt'] is None
