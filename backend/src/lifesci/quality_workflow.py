"""Case-linked local quality preparation, review and pending external handoff.

This service deliberately has no manufacturing writer or official QMS approval.
All store mutations and retry receipts commit in the existing transaction boundary.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import html
import json

from .ids import content_hash, iso, new_id, parse_iso, utc_now
from .quality_evidence import QualityEvidence, refs_in, typed_identifiers, quality_lineage
from .store import ConflictError


class QualityWorkflowService:
    def __init__(self, platform):
        self.p = platform
        self.evidence = QualityEvidence(platform)

    def _current(self, ctx):
        if ctx.actor_kind == 'agent' and ctx.delegated_from:
            return self.p.identity.context_for(ctx.tenant_id, ctx.delegated_from)
        current = self.p.identity.context_for(ctx.tenant_id, ctx.actor_id, actor_kind=ctx.actor_kind)
        return replace(current, authentication=ctx.authentication)

    def _person(self, ctx):
        if ctx.actor_kind != 'person':
            raise PermissionError('quality decisions require a human actor')

    def _assigned(self, tenant, actor_id, site, *, qa=False):
        person = self.p.identity.context_for(tenant, actor_id)
        assignments = self.p.store.read().find(tenant, 'role_assignment', 'actor_id', actor_id)
        if person.actor_kind != 'person' or not person.roles or any(
                r.state.get('actor_kind') != 'person' for r in assignments if not r.state.get('revoked_at')):
            raise ValueError('assignment requires a validated person with current site access')
        self.p.identity.require(person, 'read', 'case', site_id=site)
        if qa and not any(role in ('qa', 'qa_reviewer') and scope in (None, site)
                          for role, scope in person.role_scopes or ()):
            raise ValueError('reviewer must hold a current QA role')
        if qa:
            self.p.identity.require(person, 'approve', 'case', site_id=site)
        return person

    def _load(self, ctx, case_id):
        current = self._current(ctx)
        case = self.p.cases.get(current, case_id)
        workflow = case.get('workflow')
        if not workflow:
            raise ValueError('case is not a managed quality workspace')
        self.evidence.authorize(current, refs_in(workflow))
        return current, case

    def _fingerprint(self, w):
        return content_hash({key: w.get(key) for key in ('sources', 'hypotheses', 'assessment', 'impact', 'requests', 'actions', 'science')})

    def _completeness(self, ctx, case):
        w = case['workflow']
        missing = []
        owner = self.p.identity.context_for(ctx.tenant_id, case['owner_id'])
        if not all(self.p.identity.check(owner, action, 'case', case['case_id'], site_id=case['site_id']) for action in ('read', 'propose', 'approve')):
            missing.append('owner_authority')
        assessment = w['assessment']
        if w.get('triage', {}).get('choice') not in ('local_deviation_preparation', 'reference_external'):
            missing.append('triage')
        if not w['sources']:
            missing.append('sources')
        if w['preparation']['status'] != 'completed':
            missing.append('preparation')
        if not assessment.get('technical_summary'):
            missing.append('technical_summary')
        if assessment.get('root_cause_status') not in ('unresolved', 'supported_hypothesis'):
            missing.append('root_cause_status')
        if assessment.get('root_cause_status') == 'unresolved' and not assessment.get('limitations'):
            missing.append('unresolved_cause_limitations')
        if w['impact'].get('status') != 'assessed' or not w['impact'].get('summary'):
            missing.append('impact_assessment')
        if case.get('category') == 'oos' and not assessment.get('initial_lab_assessment'):
            missing.append('initial_lab_assessment')
        for r in w['requests']:
            valid = True
            try:
                self._validate_followup(ctx, case, r, request=True, current=False)
            except (ValueError, PermissionError, KeyError):
                valid = False
            if r.get('required', True) and (r.get('status') != 'resolved' or not valid):
                missing.append('evidence_request:' + r['id'])
        for action in w['actions']:
            valid = True
            try:
                self._validate_followup(ctx, case, action, current=False)
            except (ValueError, PermissionError, KeyError):
                valid = False
            if action.get('required_immediate') and (action.get('status') != 'completed' or not valid):
                missing.append('immediate_action:' + action['id'])
        if w.get('collection', {}).get('truncated'):
            missing.append('collection_truncated')
        if w.get('triage', {}).get('choice') == 'no_formal_deviation':
            missing = [item for item in missing if item not in ('triage', 'technical_summary', 'root_cause_status', 'unresolved_cause_limitations', 'impact_assessment', 'initial_lab_assessment')]
        drift = []
        for ref in refs_in({k: w[k] for k in ('sources', 'hypotheses', 'assessment', 'impact', 'requests', 'actions', 'science')}):
            rec = self.p.store.read().get(ctx.tenant_id, ref['kind'], ref['id'])
            if not rec or rec.revision != ref['revision'] or rec.state.get('status') in ('stale', 'quarantined', 'superseded'):
                drift.append({**ref, 'current_revision': rec.revision if rec else None})
        # Newly arrived matching evidence also invalidates a submitted basis, without altering it.
        if w['preparation']['status'] == 'completed':
            latest = self.evidence.collect(ctx, case)
            saved = {(r['kind'], r['id'], r['revision']) for r in w['sources']}
            drift.extend({**r, 'reason': 'new_matching_source'} for r in latest['sources']
                         if (r['kind'], r['id'], r['revision']) not in saved)
        submissions = [r for r in w['reviews'] if r['decision'] == 'submitted']
        submission_drift = bool(submissions and w['state'] in ('technical_review', 'qa_review', 'handoff_pending', 'handed_off')
                                and submissions[-1]['fingerprint'] != self._fingerprint(w))
        return {'complete': not missing and not drift and not submission_drift, 'missing': missing, 'source_drift': drift,
                'submission_drift': submission_drift,
                'gaps': w.get('collection', {}).get('gaps', [])}

    def assignees(self, ctx, site_id):
        current = self._current(ctx)
        self.p.identity.require(current, 'read', 'case', site_id=site_id)
        actors = {r.state['actor_id'] for r in self.p.store.read().list(ctx.tenant_id, 'role_assignment')
                  if not r.state.get('revoked_at') and r.state.get('actor_kind') == 'person'
                  and r.state.get('site_id') in (None, site_id)}
        items = []
        for actor_id in sorted(actors):
            person = self.p.identity.context_for(ctx.tenant_id, actor_id)
            roles = sorted(role for role, site in person.role_scopes or () if site in (None, site_id))
            items.append({'actor_id': actor_id, 'label': actor_id, 'roles': roles,
                'eligible_owner': all(self.p.identity.check(person, action, 'case', site_id=site_id) for action in ('read', 'propose', 'approve')),
                'eligible_qa_reviewer': bool(set(roles).intersection({'qa', 'qa_reviewer'})
                    and self.p.identity.check(person, 'approve', 'case', site_id=site_id))})
        return {'site_id': site_id, 'items': items}

    def _allowed(self, ctx, case):
        w, state = case['workflow'], case['workflow']['state']
        out = []
        if self.p.identity.check(ctx, 'propose', 'case', case['case_id'], site_id=case['site_id']):
            out.append('prepare')
            if state not in ('technical_review', 'qa_review', 'handoff_pending', 'handed_off'):
                out += ['assessment', 'hypotheses', 'evidence_requests', 'actions', 'scientific_analysis']
            if ctx.actor_kind == 'person' and state not in ('technical_review', 'qa_review', 'handoff_pending', 'handed_off'):
                out += ['assign', 'request_evidence', 'no_formal_deviation', 'reference_external', 'submit_technical']
            if (ctx.actor_kind == 'person' and state == 'technical_review' and ctx.actor_id == case['owner_id']
                    and self.p.identity.check(ctx, 'approve', 'case', case['case_id'], site_id=case['site_id'])):
                out.append('submit_qa')
        if (ctx.actor_kind == 'person' and ctx.actor_id == case['qa_reviewer_id']
                and ctx.roles.intersection({'qa', 'qa_reviewer'})
                and self.p.identity.check(ctx, 'approve', 'case', case['case_id'], site_id=case['site_id'])):
            if state in ('technical_review', 'qa_review', 'handoff_pending', 'handed_off'):
                out.append('return')
            if state == 'qa_review':
                out.append('approve_local')
        if self.p.identity.check(ctx, 'export', 'case', case['case_id'], site_id=case['site_id']):
            out.append('export')
        if state == 'assessed_no_formal_deviation' and 'submit_technical' in out:
            out.remove('submit_technical')
        return out

    def get(self, ctx, case_id):
        current, case = self._load(ctx, case_id)
        w = case['workflow']
        sources = self.evidence.views(current, w['sources'])
        for source in sources:
            source['url'] = source['url'].replace('{case_id}', case_id)
        return {'case': {k: v for k, v in case.items() if k != 'workflow'}, 'revision': case['revision'],
                'workflow': deepcopy(w), 'timeline': w['timeline'], 'sources': sources,
                **{key: w[key] for key in ('hypotheses', 'impact', 'requests', 'actions', 'reviews', 'activity', 'assessment', 'science')},
                'completeness': self._completeness(current, case), 'allowed_actions': self._allowed(current, case),
                'local_only': True, 'external_status': w.get('external_status', 'pending_external_approval')}

    def list(self, ctx, limit=100):
        items = []
        for rec in self.p.store.read().list(ctx.tenant_id, 'case'):
            if not rec.state.get('workflow'):
                continue
            try:
                w = self.get(ctx, rec.id)
            except PermissionError:
                continue
            items.append(w)
            if len(items) >= min(limit, 200):
                break
        return {'items': items}

    def _intent(self, ctx, case_id, operation, key, payload, run):
        if not key or not 1 <= len(key) <= 128:
            raise ValueError('idempotency_key is required (1-128 characters)')
        rid = content_hash([ctx.actor_id, case_id, operation, key])
        with self.p.store.transaction(ctx.actor_id) as tx:
            old = tx.get(ctx.tenant_id, 'quality_intent', rid)
            digest = content_hash(payload)
            if old:
                if old.state['request_hash'] != digest:
                    raise ConflictError('idempotency key reused with different request')
                return self.get(ctx, case_id)
            run(tx)
            tx.put(ctx.tenant_id, 'quality_intent', rid, {'case_id': case_id, 'request_hash': digest},
                   expected_revision=None, action='quality_intent')
            return self.get(ctx, case_id)

    def adoption_context(self, ctx, case_id):
        """Authorized context for adopting the same legacy case, without repinning sources."""
        current = self._current(ctx)
        case = self.p.cases.get(current, case_id)
        if case.get('workflow'):
            raise ConflictError('case already has a quality workflow')
        refs = [ref for key in ('discovery_refs','source_refs','evidence_refs','procedure_refs') for ref in case.get(key) or []]
        refs.extend(ref for event in case.get('timeline') or [] for ref in event.get('evidence_refs') or [])
        signals, associations = [], {}
        for record in self.p.store.read().list(ctx.tenant_id, 'deviation_signal'):
            if record.state.get('case_id') != case_id:
                continue
            signal = self.p.signals.get(current, record.id)
            if signal['site_id'] != case['site_id']:
                raise PermissionError('linked signal outside case site')
            signals.append(signal)
            refs.append({'kind':'deviation_signal','id':record.id,'revision':record.revision,'site_id':case['site_id']})
            refs.extend(quality_lineage('deviation_signal', signal))
            associations.update(signal.get('associations') or {})
            if (signal.get('subject') or {}).get('kind') == 'batch':
                associations.setdefault('batch_id', signal['subject']['id'])
        associations.update(case.get('associations') or {})
        pinned = self.evidence.authorize(current, refs, current=False)
        if any(ref['site_id'] != case['site_id'] for ref in pinned):
            raise PermissionError('legacy source outside case site')
        category = case.get('category') or ('oos' if any(s['kind']=='lab_oos' for s in signals) else 'process_excursion')
        owner = self.p.identity.context_for(ctx.tenant_id, case['owner_id'])
        assignment_issues = []
        if not all(self.p.identity.check(owner, action, 'case', case_id, site_id=case['site_id']) for action in ('read', 'propose', 'approve')):
            assignment_issues.append(f"Existing owner {case['owner_id']} lacks current technical-review approval permission; select an eligible investigation owner")
        return {'assignment_issues': assignment_issues, 'case':{**case,'title':case.get('title') or (signals[0]['rule'] if signals else case_id),
            'category':category,'associations':associations}, 'signals':signals, 'discovery_refs':pinned, 'local_only':True}

    def create(self, ctx, *, case_id=None, site_id, title, owner_id, qa_reviewer_id,
               associations=None, discovery_refs=None, category='process_excursion', priority='normal',
               initial_risk='', deadline=None, external_reference=None, expected_case_revision=None, idempotency_key):
        self._person(ctx)
        current = self._current(ctx)
        case_id = case_id or 'quality-' + content_hash([ctx.tenant_id, ctx.actor_id, idempotency_key])[:24]
        payload = {k: v for k, v in locals().copy().items() if k not in ('self', 'ctx', 'current', 'refs')}
        if expected_case_revision is None:
            payload.pop('expected_case_revision', None)  # Preserve pre-extension retry receipts.
        def run(tx):
            self.p.identity.require(current, 'propose', 'case', case_id, site_id=site_id)
            owner = self._assigned(ctx.tenant_id, owner_id, site_id)
            if not all(self.p.identity.check(owner, action, 'case', case_id, site_id=site_id) for action in ('propose', 'approve')):
                raise ValueError('investigation owner requires current case proposal and technical-review approval permission')
            self._assigned(ctx.tenant_id, qa_reviewer_id, site_id, qa=True)
            if not title.strip():
                raise ValueError('title is required')
            existing = tx.get(ctx.tenant_id, 'case', case_id)
            if existing and existing.state.get('workflow'):
                raise ConflictError('case already has a quality workflow')
            if existing:
                self.p.cases.get(current, case_id, tx)
                if expected_case_revision is not None and existing.revision != expected_case_revision:
                    raise ConflictError('legacy case revision changed before adoption')
                if existing.state['site_id'] != site_id:
                    raise ValueError('case site cannot change')
                base = existing.state
            else:
                if expected_case_revision is not None:
                    raise ConflictError('legacy case revision no longer exists')
                base = {'case_id': case_id, 'site_id': site_id, 'status': 'open', 'timeline': [],
                        'procedure_refs': [], 'opened_at': iso(utc_now()), 'opened_by': ctx.actor_id}
            # Existing original revisions remain inspectable; completeness separately flags drift.
            refs = self.evidence.authorize(current, discovery_refs or [], current=not bool(existing))
            if any(ref['site_id'] != site_id for ref in refs):
                raise PermissionError('quality source outside case site')
            w = {'state': 'awaiting_triage', 'local_only': True, 'discovery_refs': refs, 'sources': refs,
                 'assessment': {}, 'hypotheses': [], 'impact': {'status': 'draft', 'candidates': [], 'unknowns': []},
                 'requests': [], 'actions': [], 'reviews': [], 'activity': [], 'timeline': [], 'science': {},
                 'preparation': {'status': 'not_started'}, 'effectiveness_concerns': [],
                 'mission_id': 'quality-mission-' + content_hash([ctx.tenant_id, case_id])[:24],
                 'external_reference': external_reference, 'external_status': 'pending_external_approval'}
            self._save(tx, ctx, {**base, 'title': title, 'category': category, 'priority': priority,
                'owner_id': owner_id, 'qa_reviewer_id': qa_reviewer_id, 'associations': associations or {},
                'initial_risk': initial_risk, 'deadline': deadline, 'workflow': w},
                existing.revision if existing else None, 'create')
        return self._intent(ctx, case_id, 'create', idempotency_key, payload, run)

    def _save(self, tx, ctx, case, revision, operation, reason=''):
        case = deepcopy(case)
        case.pop('revision', None)
        case['workflow']['activity'].append({'id': new_id('qact'), 'operation': operation,
            'actor_id': ctx.actor_id, 'actor_kind': ctx.actor_kind, 'at': iso(utc_now()), 'reason': reason})
        tx.put(ctx.tenant_id, 'case', case['case_id'], case, expected_revision=revision,
               action='quality_' + operation, reason=reason or None, event_type='quality.workspace.updated',
               event_payload={'case_id': case['case_id'], 'site_id': case['site_id'], 'operation': operation})

    def _mutate(self, ctx, case_id, operation, expected_revision, idempotency_key, payload, change, *, action='propose'):
        current, case = self._load(ctx, case_id)
        self.p.identity.require(current, action, 'case', case_id, site_id=case['site_id'])
        if ctx.actor_kind != 'person' and (operation not in ('prepare', 'record_science')
                or ctx.delegated_from != case['owner_id']):
            raise PermissionError('workflow edits require a human; owner delegates may prepare evidence and advisory science')
        def run(tx):
            rec = tx.require(ctx.tenant_id, 'case', case_id)
            if rec.revision != expected_revision:
                raise ConflictError(f'case at revision {rec.revision}; expected {expected_revision}')
            changed = deepcopy({**rec.state, 'revision': rec.revision})
            if operation not in ('prepare', 'transition') and changed['workflow']['state'] in (
                    'technical_review', 'qa_review', 'handoff_pending', 'handed_off'):
                raise ValueError('return the submitted workspace before editing its content')
            change(current, changed)
            self.evidence.authorize(current, refs_in(changed['workflow']))
            self._save(tx, ctx, changed, rec.revision, operation, payload.get('reason', ''))
        return self._intent(ctx, case_id, operation, idempotency_key,
                            {'expected_revision': expected_revision, **payload}, run)

    def _mission(self, ctx, case):
        w = case['workflow']
        owner = self._assigned(ctx.tenant_id, case['owner_id'], case['site_id'])
        self.p.missions.start_or_resume(owner, objective=f"Prepare quality workspace {case['case_id']}",
            owner_id=case['owner_id'], scope={'site_ids': [case['site_id']], 'quality_case_id': case['case_id']},
            mission_id=w['mission_id'], constraints=['Local read and draft only; no operational actions'],
            subscriptions=[{'type': prefix, 'site_id': case['site_id'], 'require_site': True,
                'authorized_owner_id': case['owner_id'], 'subjects': sorted(typed_identifiers(case) | {r['id'] for r in w['discovery_refs']})}
                for prefix in ('evidence.', 'signal.', 'lab.', 'exec.', 'work_order.')])
        return w['mission_id']

    def prepare(self, ctx, case_id, *, expected_revision, idempotency_key, queued=False):
        def change(current, case):
            w = case['workflow']
            mid = self._mission(current, case)
            if queued:
                w['preparation'] = {'status': 'queued', 'queued_at': iso(utc_now())}
                owner = self._assigned(ctx.tenant_id, case['owner_id'], case['site_id'])
                self.p.missions.add_obligation(owner, mid, description='Prepare local quality evidence',
                    due_at=iso(utc_now()), task_kind='quality_workspace_prepare', case_id=case_id)
                self.p.missions.scheduler.schedule_wakeup(ctx.tenant_id, mid, 'quality:prepare')
                return
            self._assemble(current, case)
        return self._mutate(ctx, case_id, 'prepare', expected_revision, idempotency_key, {'queued': queued}, change)

    def _assemble(self, ctx, case):
        w = case['workflow']
        started = iso(utc_now())
        collected = self.evidence.collect(ctx, case)
        before = {(r['kind'], r['id'], r['revision']) for r in w['sources']}
        added = [r for r in collected['sources'] if (r['kind'], r['id'], r['revision']) not in before]
        # Reviewed content is retained. New drafts require a deliberate resubmission.
        if w['science'] and before != {(r['kind'],r['id'],r['revision']) for r in collected['sources']}:
            if w['state'] in ('technical_review','qa_review','handoff_pending','handed_off'):
                w['scientific_refresh'] = {'status':'pending_review_return','reason':'Pinned case evidence changed'}
            else:
                w['science']['status'] = 'stale_requires_rerun'
                w['science']['stale_reason'] = 'Pinned case evidence changed; previous calculations remain historical and require an explicit rerun'
        w['sources'] = collected['sources']
        w['timeline'] = collected['timeline']
        w['impact']['candidates'] = collected['candidates']
        w['collection'] = {'gaps': collected['gaps'], 'truncated': collected['truncated']}
        if added and w['actions']:
            for action in w['actions']:
                if action.get('status') != 'completed':
                    continue
                completion = parse_iso(action.get('completed_at'))
                relevant, uncertain = [], False
                for ref in added:
                    record = self.p.store.read().revision(ctx.tenant_id, ref['kind'], ref['id'], ref['revision'])
                    mapped = (record.state.get('metadata') or {}).get('mapped') or {}
                    # A related record is not by itself recurrence. Require an explicit
                    # adverse source status or a detected adverse signal tied to this source.
                    adverse = str(mapped.get('status') or record.state.get('limit_evaluation') or '').lower() in {
                        'oos', 'out_of_limits', 'out_of_specification', 'out_of_trend', 'failed',
                        'overdue', 'missing', 'alarm', 'mismatch', 'positive'}
                    detected = any(s.state.get('kind') != 'evaluation_issue' and any(
                        r.get('kind') == ref['kind'] and r.get('id') == ref['id'] and r.get('revision') == ref['revision']
                        for r in quality_lineage('deviation_signal', s.state))
                        for s in self.p.store.read().list(ctx.tenant_id, 'deviation_signal'))
                    if not (adverse or detected):
                        continue
                    event_time = parse_iso(record.state.get('event_time') or mapped.get('event_time'))
                    if event_time is None or completion is None:
                        uncertain = True
                        relevant.append(ref)
                    elif event_time >= completion:
                        relevant.append(ref)
                if not relevant:
                    continue
                key = content_hash([action['id'], relevant])
                if not any(c['id'] == key for c in w['effectiveness_concerns']):
                    w['effectiveness_concerns'].append({'id': key, 'action_id': action['id'],
                        'evidence_refs': relevant, 'status': 'requires_human_assessment',
                        'timing_status': 'uncertain' if uncertain else 'after_action_completion',
                        'action_completed_at': action.get('completed_at'),
                        'description': 'Related adverse evidence requires recurrence/effectiveness assessment; no conclusion is established'})
        w['preparation'] = {'status': 'completed', 'started_at': started, 'completed_at': iso(utc_now()),
                            'source_count': len(w['sources'])}
        if w['state'] not in ('technical_review', 'qa_review', 'handoff_pending', 'handed_off', 'assessed_no_formal_deviation'):
            w['state'] = 'in_progress' if w['sources'] else 'waiting_for_evidence'

    def run_mission(self, ctx, act):
        mission = self.p.missions.get(ctx, act.mission_id)
        case_id = mission['scope'].get('quality_case_id')
        if not case_id:
            return None
        current, case = self._load(ctx, case_id)
        w = case['workflow']
        if w['preparation']['status'] != 'queued' and not act.pending_event_ids:
            return self.p.case_science.run_mission(ctx,act) or {'status': 'idle'}
        with self.p.store.transaction(ctx.actor_id) as tx:
            tx.check_lease(ctx.tenant_id, 'mission', act.mission_id, act.worker_id, act.token)
            rec = tx.require(ctx.tenant_id, 'case', case_id)
            changed = deepcopy(rec.state)
            obligations = [o for o in mission['obligations'] if o['status'] == 'open'
                           and o.get('task_kind') == 'quality_workspace_prepare']
            try:
                self._assemble(current, changed)
                # Do not produce duplicate activity on equivalent/duplicate delivery.
                if content_hash(changed['workflow']['sources']) == content_hash(w['sources']) and w['preparation']['status'] == 'completed':
                    return {'status': 'unchanged'}
                self._save(tx, ctx, changed, rec.revision, 'background_preparation')
                for obligation in obligations:
                    self.p.missions.complete_obligation(ctx, act.mission_id, obligation['obligation_id'],
                        artifact_ref={'kind': 'case', 'id': case_id})
            except (ValueError, PermissionError, KeyError) as exc:
                changed['workflow']['preparation'] = {'status': 'failed', 'recoverable': True,
                    'error': str(exc), 'failed_at': iso(utc_now())}
                self._save(tx, ctx, changed, rec.revision, 'preparation_failed')
                for obligation in obligations:
                    self.p.missions.block_obligation(ctx, act.mission_id, obligation['obligation_id'],
                        ['Quality preparation failed; inspect workspace and retry'])
                return {'status': 'failed', 'case_id': case_id,
                        'blocked_obligations': [o['obligation_id'] for o in obligations]}
        return self.p.case_science.run_mission(ctx,act) or {'status': 'completed', 'case_id': case_id}

    def assessment(self, ctx, case_id, *, assessment, expected_revision, idempotency_key):
        def change(current, case):
            if case['workflow']['state'] in ('technical_review', 'qa_review', 'handoff_pending', 'handed_off'):
                raise ValueError('return the submitted workspace before editing assessment')
            value = deepcopy(assessment)
            lab = value.get('initial_lab_assessment')
            if lab and (lab.get('conclusion') not in ('expanded_investigation', 'laboratory_error_supported', 'inconclusive')
                        or not lab.get('rationale') or not lab.get('evidence_refs')):
                raise ValueError('initial lab assessment requires explicit conclusion, rationale and evidence_refs')
            if lab:
                lab.update(recorded_by=ctx.actor_id, recorded_at=iso(utc_now()), original_oos_preserved=True)
            if value.get('root_cause_status') not in (None, 'unresolved', 'supported_hypothesis'):
                raise ValueError('root cause remains unresolved or a supported hypothesis')
            impact = value.pop('impact', None)
            case['workflow']['assessment'].update(value)
            if impact:
                case['workflow']['impact'].update(impact)
        return self._mutate(ctx, case_id, 'assessment', expected_revision, idempotency_key, {'assessment': assessment}, change)

    def record_science(self, ctx, case_id, *, science, expected_revision, idempotency_key):
        """Attach source-backed scientific service outputs; never executes or confirms a model."""
        def change(current, case):
            refs = refs_in(science)
            if not refs:
                raise ValueError('scientific output requires pinned source references')
            self.evidence.authorize(current, refs, current=True)
            basis = {(r['kind'], r['id'], r['revision']) for r in case['workflow']['sources']}
            def leaves(ref, seen=frozenset()):
                key = (ref['kind'], ref['id'], ref['revision'])
                if key in seen:
                    raise ValueError('cyclic scientific basis')
                rec = self.p.store.read().revision(ctx.tenant_id, ref['kind'], ref['id'], ref['revision'])
                if rec.state.get('inputs'):
                    return set().union(*(leaves(r, seen | {key}) for r in rec.state['inputs']))
                return {key}
            if not set().union(*(leaves(ref) for ref in refs)) <= basis:
                raise ValueError('scientific inputs are outside the pinned case basis; refresh the draft explicitly')
            case['workflow']['science'].update(deepcopy(science))
            case['workflow']['science']['advisory'] = True
        return self._mutate(ctx, case_id, 'record_science', expected_revision, idempotency_key,
                            {'science': science}, change)

    def hypotheses(self, ctx, case_id, *, hypothesis, expected_revision, idempotency_key):
        def change(current, case):
            if not hypothesis.get('text') or hypothesis.get('status', 'hypothesis') not in ('hypothesis', 'unresolved', 'rejected'):
                raise ValueError('hypothesis requires text and an unconfirmed status')
            if hypothesis.get('counterevidence_status') not in ('not_searched', 'searched_none', 'searched_found'):
                raise ValueError('hypothesis requires counterevidence_status')
            item = {'id': new_id('qhyp'), 'status': 'hypothesis', 'support_refs': [], 'counterevidence_refs': [],
                    'assumptions': [], 'unknowns': [], **deepcopy(hypothesis), 'recorded_by': ctx.actor_id}
            case['workflow']['hypotheses'].append(item)
        return self._mutate(ctx, case_id, 'hypotheses', expected_revision, idempotency_key, {'hypothesis': hypothesis}, change)

    def evidence_request(self, ctx, case_id, *, request, expected_revision, idempotency_key):
        def change(current, case):
            if 'history' in request:
                raise ValueError('request history is server owned')
            items = case['workflow']['requests']
            if request.get('id'):
                item = next((r for r in items if r['id'] == request['id']), None)
                if not item:
                    raise ValueError('unknown evidence request')
                item.update(deepcopy(request))
            else:
                if not request.get('description') or not request.get('owner_id'):
                    raise ValueError('evidence request requires description and owner_id')
                item = {'status': 'open', 'required': True, **deepcopy(request), 'id': new_id('qreq')}
                items.append(item)
            self._validate_followup(current, case, item, request=True)
        return self._mutate(ctx, case_id, 'evidence_request', expected_revision, idempotency_key, {'request': request}, change)

    def action(self, ctx, case_id, *, action, expected_revision, idempotency_key):
        def change(current, case):
            if 'history' in action:
                raise ValueError('action history is server owned')
            items = case['workflow']['actions']
            if action.get('id'):
                item = next((a for a in items if a['id'] == action['id']), None)
                if not item:
                    raise ValueError('unknown action')
                item.update(deepcopy(action))
            else:
                if action.get('kind') not in ('immediate_correction', 'corrective_action', 'capa'):
                    raise ValueError('action kind must distinguish immediate_correction, corrective_action or capa')
                if not all(action.get(k) for k in ('description', 'owner_id', 'due_at')):
                    raise ValueError('action requires description, owner_id and due_at')
                item = {'status': 'planned', 'completion_refs': [],
                    'required_immediate': False, 'change_control_reference': None, 'effectiveness_status': 'not_assessed',
                    **deepcopy(action), 'id': new_id('qaction'), 'history': []}
                items.append(item)
            if item.get('status') == 'completed':
                item['completed_at'] = item.get('completed_at') or iso(utc_now())
            self._validate_followup(current, case, item)
            item['history'].append({'at': iso(utc_now()), 'by': ctx.actor_id, 'change': deepcopy(action)})
        return self._mutate(ctx, case_id, 'action', expected_revision, idempotency_key, {'action': action}, change)

    def _validate_followup(self, ctx, case, item, *, request=False, current=True):
        """Validate the resulting record, including values retained from an earlier revision."""
        if not isinstance(item.get('description'), str) or not item['description'].strip():
            raise ValueError('follow-up description is required')
        self._assigned(ctx.tenant_id, item.get('owner_id'), case['site_id'])
        statuses = ('open', 'resolved', 'cancelled') if request else ('planned', 'in_progress', 'completed', 'cancelled')
        if item.get('status') not in statuses:
            raise ValueError('invalid follow-up status')
        required_field = 'required' if request else 'required_immediate'
        if not isinstance(item.get(required_field, True if request else False), bool):
            raise ValueError('required flag must be boolean')
        if not request:
            if item.get('kind') not in ('immediate_correction', 'corrective_action', 'capa'):
                raise ValueError('invalid action kind')
            if not item.get('due_at') or parse_iso(item['due_at']) is None:
                raise ValueError('action due_at is required')
            if item['status'] == 'completed':
                try:
                    completion = parse_iso(item.get('completed_at'))
                except (TypeError, ValueError):
                    raise ValueError('action completion time must be a valid ISO timestamp') from None
                if completion is None:
                    raise ValueError('completed action requires a completion time')
        field = 'evidence_refs' if request else 'completion_refs'
        refs = item.get(field, [])
        if not isinstance(refs, list):
            raise ValueError(field + ' must be a list of pinned references')
        for ref in refs:
            if (not isinstance(ref, dict) or not isinstance(ref.get('kind'), str) or not ref['kind'].strip()
                    or not isinstance(ref.get('id'), str) or not ref['id'].strip()
                    or type(ref.get('revision')) is not int or ref['revision'] < 1):
                raise ValueError(field + ' requires kind, id and positive integer revision')
        if item['status'] == ('resolved' if request else 'completed') and not refs:
            raise ValueError('resolved/completed follow-up requires ' + field)
        if refs:
            self.evidence.authorize(ctx, refs, current=current)

    def transition(self, ctx, case_id, *, transition, reason, expected_revision, idempotency_key, external_reference=None):
        self._person(ctx)
        if not reason.strip():
            raise ValueError('transition reason is required')
        review = transition in ('approve_local', 'return')
        def change(current, case):
            w, state = case['workflow'], case['workflow']['state']
            if transition not in self._allowed(current, case):
                raise PermissionError('transition is not allowed for current actor and state')
            if review:
                self._assigned(ctx.tenant_id, current.actor_id, case['site_id'], qa=True)
            if transition == 'assign':
                w['state'] = 'investigation_assigned'
                w['external_status'] = 'pending_external_approval'
                w['triage'] = {'choice': 'local_deviation_preparation', 'reason': reason, 'actor_id': ctx.actor_id}
            elif transition == 'request_evidence':
                w['state'] = 'waiting_for_evidence'
                w['external_status'] = 'pending_external_approval'
                w['triage'] = {'choice': 'more_evidence', 'reason': reason, 'actor_id': ctx.actor_id}
            elif transition in ('no_formal_deviation', 'reference_external'):
                if transition == 'reference_external' and not external_reference:
                    raise ValueError('external_reference is required')
                w['triage'] = {'choice': transition, 'reason': reason, 'actor_id': ctx.actor_id}
                if transition == 'no_formal_deviation':
                    w['state'] = 'assessed_no_formal_deviation'
                    w['external_status'] = 'not_requested'
                else:
                    w['external_status'] = 'pending_external_approval'
                if external_reference:
                    w['external_reference'] = external_reference
            elif transition == 'submit_technical':
                if state in ('qa_review', 'handoff_pending', 'handed_off'):
                    raise ValueError('return before resubmitting reviewed content')
                self.evidence.authorize(current, refs_in({k: w[k] for k in ('sources', 'assessment', 'hypotheses', 'impact', 'requests', 'actions', 'science')}), current=True)
                w['reviews'].append({'id': new_id('qreview'), 'decision': 'submitted', 'submitted_by': ctx.actor_id,
                    'submitted_at': iso(utc_now()), 'fingerprint': self._fingerprint(w),
                    'snapshot': deepcopy({k: w[k] for k in ('sources', 'assessment', 'hypotheses', 'impact', 'requests', 'actions', 'science')}),
                    'completeness': self._completeness(current, case), 'reason': reason})
                w['state'] = 'technical_review'
            elif transition == 'submit_qa':
                submission = next(r for r in reversed(w['reviews']) if r['decision'] == 'submitted')
                w['reviews'].append({'id': new_id('qdecision'), 'decision': 'technical_review_completed',
                    'actor_id': ctx.actor_id, 'at': iso(utc_now()), 'reason': reason,
                    'submission_id': submission['id'], 'fingerprint': submission['fingerprint'], 'local_only': True})
                w['state'] = 'qa_review'
            elif transition == 'return':
                w['reviews'].append({'id': new_id('qdecision'), 'decision': 'return', 'actor_id': ctx.actor_id,
                    'at': iso(utc_now()), 'reason': reason, 'submission_id': next(r['id'] for r in reversed(w['reviews']) if r['decision'] == 'submitted')})
                w['state'] = 'returned'
                if w.pop('scientific_refresh',None):
                    w['science']['status'] = 'stale_requires_rerun'
                    if w['science'].get('auto_refresh'):
                        owner=self._assigned(ctx.tenant_id,case['owner_id'],case['site_id'])
                        mission_id=self._mission(owner,case)
                        self.p.missions.add_obligation(owner,mission_id,
                            description='Refresh returned scientific draft '+case_id, due_at=iso(utc_now()),
                            task_kind='quality_scientific_analysis',case_id=case_id)
            elif transition == 'approve_local':
                completeness = self._completeness(current, case)
                if not completeness['complete']:
                    raise ValueError('incomplete or stale quality basis: ' + ', '.join(completeness['missing']) + (' source drift' if completeness['source_drift'] else ''))
                submission = next(r for r in reversed(w['reviews']) if r['decision'] == 'submitted')
                if submission['fingerprint'] != self._fingerprint(w):
                    raise ConflictError('submitted content changed; submit a new review')
                w['reviews'].append({'id': new_id('qdecision'), 'decision': 'approve_local', 'actor_id': ctx.actor_id,
                    'at': iso(utc_now()), 'reason': reason, 'submission_id': submission['id'],
                    'fingerprint': submission['fingerprint'], 'local_only': True})
                w['state'] = 'handoff_pending'
            else:
                raise ValueError('unknown transition')
        return self._mutate(ctx, case_id, 'transition', expected_revision, idempotency_key,
            {'transition': transition, 'reason': reason, 'external_reference': external_reference}, change,
            action='approve' if review else 'propose')

    def source(self, ctx, case_id, kind, source_id, *, revision):
        current, case = self._load(ctx, case_id)
        manifest = refs_in(case['workflow'])
        ref = next((r for r in manifest if r['kind'] == kind and r['id'] == source_id and r['revision'] == revision), None)
        if not ref:
            raise ValueError('source revision is not part of this workspace')
        self.evidence.authorize(current, [ref])
        state = self.p.store.read().revision(ctx.tenant_id, kind, source_id, revision).state
        result = {'ref': ref, 'state': state, 'local_only': True}
        if kind == 'evidence':
            raw = self.p.evidence.original(current, source_id, revision)
            import base64
            if state.get('media_type', '').startswith(('text/', 'application/json')):
                result['content_text'] = raw.decode('utf-8', errors='replace')
                result['original_base64'] = base64.b64encode(raw).decode('ascii')
            else:
                result['content_base64'] = base64.b64encode(raw).decode('ascii')
        return result

    def export(self, ctx, case_id, format='json'):
        if format not in ('json', 'html'):
            raise ValueError('export format must be json or html')
        current, case = self._load(ctx, case_id)
        self.p.identity.require(current, 'export', 'case', case_id, site_id=case['site_id'])
        refs = refs_in(case['workflow'])
        self.evidence.authorize(current, refs, action='export')
        no_deviation = case['workflow'].get('triage', {}).get('choice') == 'no_formal_deviation'
        external_status = 'not_requested' if no_deviation else 'pending_external_approval'
        label = ('No formal deviation requested; local human assessment and follow-up only' if no_deviation
                 else 'Local preparation and review only; pending external approval')
        package = {'workspace': self.get(current, case_id), 'source_manifest': refs,
            'source_records': [self.source(current, case_id, r['kind'], r['id'], revision=r['revision']) for r in refs],
            'local_only': True, 'external_status': external_status, 'external_receipt': None,
            'label': label}
        with self.p.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, 'quality_export', new_id('qexport'), {
                'case_id': case_id, 'case_revision': case['revision'], 'site_id': case['site_id'],
                'format': format, 'source_manifest': refs, 'package_hash': content_hash(package),
                'exported_by': ctx.actor_id, 'exported_at': iso(utc_now()),
                'external_status': external_status, 'external_receipt': None},
                expected_revision=None, action='export_local_quality_package')
        if format == 'html':
            return '<!doctype html><html><body><h1>' + html.escape(label) + '</h1><pre>' + html.escape(json.dumps(package, indent=2)) + '</pre></body></html>'
        if format != 'json':
            raise ValueError('export format must be json or html')
        return package
