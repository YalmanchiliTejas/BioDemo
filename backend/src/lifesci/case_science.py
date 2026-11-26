"""Case scientific stages: direct controls share the executor's frozen numerical tools."""
from .ids import content_hash
from .evidence import EvidenceRef
from .store import ConflictError
from .quality_evidence import refs_in
from copy import deepcopy
from src.prime_runtime.science import FrozenScience


class CaseScienceService:
    def __init__(self, platform):
        self.p = platform

    def catalog(self, ctx, case_id):
        _, frozen = self._snapshot(ctx, case_id)
        return frozen.catalog()

    def _snapshot(self, ctx, case_id):
        workspace = self.p.quality_workflow.get(ctx, case_id)
        data, _ = self.p.investigations.snapshot(ctx, site_id=workspace['case']['site_id'],
                                               record_refs=workspace['workflow']['sources'])
        return workspace, FrozenScience.from_package(data)

    def analyze(self, ctx, case_id, *, expected_revision, idempotency_key, configuration_ids=None, activation=None):
        # Intent replay happens before solver execution and retains current read authorization.
        workflow = self.p.quality_workflow
        payload = {'expected_revision':expected_revision, 'configuration_ids':configuration_ids}
        current, workspace = workflow._load(ctx, case_id)
        self.p.identity.require(current, 'propose','case',case_id,site_id=workspace['site_id'])
        if not idempotency_key or len(idempotency_key) > 100:
            raise ValueError('idempotency_key is required (1-100 characters)')
        receipt_id = content_hash([ctx.actor_id,case_id,'scientific_analysis',idempotency_key])
        receipt = self.p.store.read().get(ctx.tenant_id,'quality_intent',receipt_id)
        if receipt:
            if receipt.state['request_hash'] != content_hash(payload):
                raise ConflictError('idempotency key reused with different request')
            return workflow.get(ctx,case_id)
        if workspace['revision'] != expected_revision:
            raise ConflictError('case revision changed before scientific analysis')
        if workspace['workflow']['state'] in ('technical_review','qa_review','handoff_pending','handed_off'):
            raise ValueError('return the submitted workspace before scientific analysis')
        if ctx.actor_kind != 'person' and ctx.delegated_from != workspace['owner_id']:
            raise PermissionError('science requires a person or the assigned owner delegate')
        _, frozen = self._snapshot(current, case_id)
        selected = list(frozen.configurations) if configuration_ids is None else configuration_ids
        if len(selected)>16:
            raise ValueError('select at most 16 scientific configurations')
        runs = [frozen.run(ident) for ident in selected]  # Outside a persistence transaction.
        refs = workspace['workflow']['sources']
        if not refs:
            raise ValueError('scientific work requires pinned case evidence')
        basis={(r['kind'],r['id'],r['revision']) for r in refs}
        hypotheses={}
        for original in [*workspace['workflow']['science'].get('hypotheses',[]),*workspace['workflow']['hypotheses']]:
            hypothesis=deepcopy(original)
            stale=[r for r in refs_in(hypothesis) if (r['kind'],r['id'],r['revision']) not in basis]
            if stale:
                # Historical claim/report/review artifacts keep the exact original refs.
                # Do not silently repin a causal argument onto corrected content.
                historical=[f"{r['kind']}:{r['id']}@{r['revision']}" for r in stale]
                hypothesis.update(status='unresolved',support_refs=[],counterevidence_refs=[],counterevidence_status='not_searched')
                hypothesis['unknowns']=[*hypothesis.get('unknowns',[]),
                    'Historical hypothesis requires reassessment after source change: '+', '.join(historical)]
            hypotheses[hypothesis.get('id') or hypothesis.get('text') or content_hash(hypothesis)]=hypothesis
        science = {'source_refs':refs, 'model_runs':runs, 'hypotheses':list(hypotheses.values()),
                   'assessment':{'root_cause_status':'unresolved', 'summary':'Scientific results require human technical assessment'},
                   'unknowns':[*workspace['workflow']['science'].get('report_unknowns',[]),
                               *[f"{r['configuration_id']}: {issue}" for r in runs for issue in r['issues']]],
                   'advisory':True, 'auto_refresh':True, 'configuration_ids':configuration_ids,
                   'status':('ready_for_assessment' if all(r['status']=='completed' for r in runs) else 'waiting_for_inputs') if runs else 'waiting_for_configuration'}
        if not runs:
            science['unknowns'].append('No explicit scientific_models source configuration is attached')
        def commit(tx):
            if activation:
                tx.check_lease(ctx.tenant_id,'mission',activation.mission_id,activation.worker_id,activation.token)
            rec=tx.require(ctx.tenant_id,'case',case_id)
            if rec.revision != expected_revision:
                raise ConflictError('case changed while scientific models were running')
            self.p.identity.validate_refs(current,refs,tx=tx)
            for run in runs:
                ident='case-science-'+content_hash([ctx.tenant_id,case_id,idempotency_key,run['configuration_id']])[:32]
                self.p.identity.require(current,'propose','physical_analysis_result',site_id=workspace['site_id'],tx=tx)
                self.p.evidence.record_derived(current,'physical_analysis_result',{'site_id':workspace['site_id'],
                    'case_id':case_id,'review_state':'draft_requires_review','scientific_result':run},
                    inputs=[EvidenceRef(**ref) for ref in run['source_refs']],
                    produced_by={'method':'frozen_source_model_calculation','actor_id':ctx.actor_id,'actor_kind':ctx.actor_kind},artifact_id=ident)
                record=tx.require(ctx.tenant_id,'physical_analysis_result',ident)
                run['result_ref']={'kind':record.kind,'id':record.id,'revision':record.revision,'site_id':workspace['site_id']}
            workflow.record_science(ctx,case_id,science=science,expected_revision=expected_revision,
                                    idempotency_key='scientific-attachment-'+idempotency_key)
        return workflow._intent(ctx,case_id,'scientific_analysis',idempotency_key,payload,commit)


    def queue(self, ctx, case_id, *, expected_revision, idempotency_key, configuration_ids=None):
        from .ids import iso, utc_now
        workflow=self.p.quality_workflow
        def change(current, case):
            if not case['workflow']['sources']:
                raise ValueError('scientific work requires pinned case evidence')
            case['workflow']['science'].update(status='queued',auto_refresh=True,configuration_ids=configuration_ids,
                source_refs=case['workflow']['sources'],advisory=True)
            mission_id=workflow._mission(current,case)
            self.p.missions.add_obligation(current,mission_id,
                description='Run source-backed scientific analysis for '+case_id,
                due_at=iso(utc_now()),task_kind='quality_scientific_analysis',case_id=case_id)
        return workflow._mutate(ctx,case_id,'record_science',expected_revision,idempotency_key,
                                {'queued_science':True,'configuration_ids':configuration_ids},change)

    def run_mission(self, ctx, act):
        mission=self.p.missions.get(ctx,act.mission_id)
        case_id=mission['scope'].get('quality_case_id')
        if not case_id:
            return None
        workspace=self.p.quality_workflow.get(ctx,case_id)
        science=workspace['science']
        if workspace['workflow']['state'] in ('technical_review','qa_review','handoff_pending','handed_off'):
            return {'status':'waiting_for_human_return','case_id':case_id}
        if science.get('status') not in ('queued','stale_requires_rerun') or not science.get('auto_refresh'):
            return None
        obligations=[o for o in mission['obligations'] if o['status']=='open' and o.get('task_kind')=='quality_scientific_analysis']
        try:
            result=self.analyze(ctx,case_id,expected_revision=workspace['revision'],
                idempotency_key='mission-'+content_hash([act.mission_id,workspace['revision']])[:32],
                configuration_ids=science.get('configuration_ids'),activation=act)
            status=result['science']['status']
            blocked=[]
            with self.p.store.transaction(ctx.actor_id) as tx:
                tx.check_lease(ctx.tenant_id,'mission',act.mission_id,act.worker_id,act.token)
                for o in obligations:
                    if status=='ready_for_assessment':
                        self.p.missions.complete_obligation(ctx,act.mission_id,o['obligation_id'],artifact_ref={'kind':'case','id':case_id})
                    else:
                        self.p.missions.block_obligation(ctx,act.mission_id,o['obligation_id'],result['science']['unknowns'])
                        blocked.append(o['obligation_id'])
            return {'status':status,'case_id':case_id,'blocked_obligations':blocked}
        except (ValueError,PermissionError,ConflictError) as exc:
            # Do not consume a replaced worker's lease. Durable pending intent is retryable.
            with self.p.store.transaction(ctx.actor_id) as tx:
                tx.check_lease(ctx.tenant_id,'mission',act.mission_id,act.worker_id,act.token)
                for o in obligations:
                    self.p.missions.block_obligation(ctx,act.mission_id,o['obligation_id'],[str(exc)])
            return {'status':'blocked','case_id':case_id,'blocked_obligations':[o['obligation_id'] for o in obligations]}
