"""Multi-agent investigations: the platform side (docs/architecture/multi-agent-investigations.md).

The platform is the system of record (runs, events, permissions, report). Execution happens on a
separate executor (``cloud_backend``), reached service-to-service with short-lived RS256 tokens this
module mints. Browsers never talk to the executor. When the executor is not configured, starting an
investigation is refused with a clear message; nothing is simulated.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from .identity import AccessContext, AuthorizationError, Decision
from .ids import iso, new_id, utc_now
from .store import ConflictError

KIND, EVENT, REPORT, PROPOSAL = 'investigation_run', 'investigation_event', 'investigation_report', 'investigation_proposal'
ACTIVE = ('queued', 'submitted', 'running', 'finalizing')
TERMINAL = ('awaiting_review', 'blocked', 'failed', 'cancelled')
DEFAULT_BUDGET = {'max_tool_calls': 30, 'minutes': 10, 'max_tokens': None}  # pre-revenue defaults; raise per request
MAX_ACTIVE_PER_TENANT = 1
SNAPSHOT_LIMIT = 64 * 1024 * 1024
SYNC_INTERVAL_S = 2.0
REPORT_GRACE_S = 300
NOT_CONFIGURED = 'Investigation execution is not configured'
NOT_ENTITLED = 'Multi-agent investigations are available on the paid plan'
EVENT_KINDS = ('phase', 'agent_started', 'agent_activity', 'agent_finished', 'allocation', 'subreport_saved', 'budget', 'error')


class ExecutorUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutorConfig:
    url: str
    audience: str
    issuer: str
    tenant: str
    key_pem: str
    key_id: str
    project: str | None = None  # default: one executor project per platform tenant

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> 'ExecutorConfig | None':
        env = os.environ if env is None else env
        url, key = env.get('INVESTIGATION_EXECUTOR_URL', '').strip(), env.get('INVESTIGATION_SIGNING_KEY', '').strip()
        if url and not key and env.get('INVESTIGATION_SIGNING_KEY_SECRET_ARN'):
            try:
                import boto3  # deployed: the PEM lives in Secrets Manager, not the 4 KB Lambda environment
                key = boto3.client('secretsmanager').get_secret_value(SecretId=env['INVESTIGATION_SIGNING_KEY_SECRET_ARN'])['SecretString']
            except Exception as exc:  # an optional feature must not stop the API from starting
                import sys
                print(f'investigations disabled: signing key unavailable ({type(exc).__name__})', file=sys.stderr)
                return None
        if not url or not key:
            return None
        return cls(url=url.rstrip('/'), audience=env.get('INVESTIGATION_EXECUTOR_AUDIENCE') or url,
                   issuer=env.get('INVESTIGATION_ISSUER', ''), key_pem=key.replace('\\n', '\n'),
                   key_id=env.get('INVESTIGATION_SIGNING_KEY_ID') or 'investigation-1',
                   tenant=env.get('INVESTIGATION_EXECUTOR_TENANT') or env.get('DEPLOYMENT_TENANT', ''),
                   project=env.get('INVESTIGATION_EXECUTOR_PROJECT') or None)

    def project_for(self, tenant_id: str) -> str:
        project = self.project or re.sub(r'[^a-zA-Z0-9_-]', '-', tenant_id)[:80]
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', project):
            raise ValueError('cannot derive an executor project for this tenant')
        return project


class Issuer:
    """Signs the executor's service tokens and publishes the matching public key (JWKS)."""

    def __init__(self, config: ExecutorConfig):
        from cryptography.hazmat.primitives import serialization
        self.config = config
        self.key = serialization.load_pem_private_key(config.key_pem.encode(), password=None)

    def token(self, project: str, ttl_seconds: int = 300) -> str:
        import jwt
        now = int(time.time())
        claims = {'iss': self.config.issuer, 'aud': self.config.audience, 'sub': 'platform-service', 'iat': now,
                  'exp': now + ttl_seconds, 'tenant_id': self.config.tenant, 'projects': {project: 'operator'}}
        return jwt.encode(claims, self.key, algorithm='RS256', headers={'kid': self.config.key_id})

    def jwks(self) -> dict[str, Any]:
        from jwt.algorithms import RSAAlgorithm
        jwk = json.loads(RSAAlgorithm.to_jwk(self.key.public_key()))
        return {'keys': [{**jwk, 'kid': self.config.key_id, 'use': 'sig', 'alg': 'RS256'}]}


class Executor(Protocol):
    def upload(self, project: str, sha256: str, data: bytes) -> dict[str, Any]: ...
    def submit(self, project: str, idempotency_key: str, job: dict[str, Any]) -> dict[str, Any]: ...
    def job(self, project: str, job_id: str) -> dict[str, Any]: ...
    def events(self, project: str, job_id: str, after: int) -> dict[str, Any]: ...
    def cancel(self, project: str, job_id: str) -> dict[str, Any]: ...
    def result(self, project: str, job_id: str) -> dict[str, Any]: ...


class HttpExecutor:
    """The cloud_backend job API (see cloud_backend/api.py and design §12.2)."""

    def __init__(self, config: ExecutorConfig, issuer: Issuer, timeout: float = 20.0):
        import httpx
        self.config, self.issuer = config, issuer
        self.http = httpx.Client(base_url=config.url, timeout=timeout)

    def _call(self, method: str, project: str, path: str, **kwargs) -> Any:
        import httpx
        headers = {'Authorization': 'Bearer ' + self.issuer.token(project), **kwargs.pop('headers', {})}
        try:
            response = self.http.request(method, f'/v1/projects/{project}{path}', headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ExecutorUnavailable(f'execution service unreachable: {type(exc).__name__}') from exc
        if response.status_code >= 500 or response.status_code in (401, 403, 429):
            raise ExecutorUnavailable(f'execution service returned HTTP {response.status_code}')
        if response.status_code >= 400:
            raise ValueError(f'execution service rejected the request: HTTP {response.status_code}')
        return response.json()

    def upload(self, project, sha256, data):
        return self._call('PUT', project, f'/inputs/{sha256}', content=data,
                          headers={'Content-Type': 'application/zip'})

    def submit(self, project, idempotency_key, job):
        return self._call('POST', project, '/jobs', json=job, headers={'Idempotency-Key': idempotency_key})

    def job(self, project, job_id):
        return self._call('GET', project, f'/jobs/{job_id}')

    def events(self, project, job_id, after):
        return self._call('GET', project, f'/jobs/{job_id}/events', params={'after': after})

    def cancel(self, project, job_id):
        return self._call('POST', project, f'/jobs/{job_id}/cancel')

    def result(self, project, job_id):
        return self._call('GET', project, f'/jobs/{job_id}/result')


def _now() -> datetime:
    return utc_now()


def _parse(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None
    except ValueError:
        return None


_AGENT_STATUS = {'running': 'running', 'active': 'running', 'working': 'running', 'started': 'running',
                 'queued': 'waiting', 'pending': 'waiting', 'idle': 'waiting', 'waiting': 'waiting',
                 'completed': 'done', 'complete': 'done', 'done': 'done', 'finished': 'done', 'succeeded': 'done',
                 'failed': 'failed', 'error': 'failed', 'aborted': 'failed', 'cancelled': 'failed'}


def fold(events: list[dict[str, Any]], *, run_status: str, limits: dict[str, Any]) -> dict[str, Any]:
    """Agent tree, budget and phase from the event log. Pure: the same events always give the same view."""
    lead = {'agent_id': 'lead', 'parent_id': None, 'role': 'lead', 'question': None,
            'status': 'waiting', 'current_tool': None, 'tool_calls': 0, 'tokens': 0,
            'started_at': None, 'last_activity_at': None, 'subreports': [], 'attribution': 'exact'}
    agents: dict[str, dict[str, Any]] = {'lead': lead}
    budget = {'tool_calls_used': 0, 'tool_calls_limit': limits.get('max_tool_calls'), 'elapsed_seconds': 0,
              'deadline_seconds': limits.get('timeout_seconds'), 'tokens': 0, 'token_limit': limits.get('max_tokens'),
              'cost_status': 'unknown'}
    phase, last_child = None, None

    def agent(event):
        ident = event.get('agent_id') or 'lead'
        if ident not in agents:
            agents[ident] = {**lead, 'agent_id': ident, 'parent_id': event.get('parent_id') or 'lead', 'role': 'investigator',
                             'subreports': []}
        return agents[ident]

    for e in sorted(events, key=lambda e: e['seq']):
        kind, payload, at = e['kind'], e.get('payload') or {}, e.get('at')
        if kind == 'phase':
            phase = payload.get('phase')
            lead['status'] = 'done' if phase == 'submitted' else 'running'
            lead['started_at'] = lead['started_at'] or at
            lead['last_activity_at'] = at
            continue
        if kind == 'budget':
            budget.update({k: payload[k] for k in ('tool_calls_used', 'elapsed_seconds', 'tokens') if k in payload})
            if payload.get('tool_calls_limit'):
                budget['tool_calls_limit'] = payload['tool_calls_limit']
            continue
        if kind == 'error':
            continue
        if kind == 'subreport_saved':
            target = agents.get(e.get('agent_id') or '') if e.get('agent_id') else None
            exact = target is not None
            target = target or (agents[last_child] if last_child else lead)
            target['subreports'].append({k: payload.get(k) for k in ('subreport_id', 'assessment', 'fact_count', 'claim_count',
                                                                       'open_question_count', 'evidence_ids')})
            if not exact:
                target['attribution'] = 'approximate'
            continue
        if kind == 'allocation':
            continue
        a = agent(e)
        if a['role'] == 'investigator':
            last_child = a['agent_id']
        a['started_at'] = a['started_at'] or at
        a['last_activity_at'] = at
        if kind == 'agent_started':
            a['question'] = payload.get('question') or a['question']
            a['status'] = 'running'
        elif kind == 'agent_finished':
            a['status'] = _AGENT_STATUS.get(str(payload.get('status', 'done')).lower(), 'done')
            a['current_tool'] = None
        else:
            a['status'] = _AGENT_STATUS.get(str(payload.get('status', 'running')).lower(), 'running')
            a['current_tool'] = payload.get('tool') if a['status'] == 'running' else None
            a['tool_calls'] = max(a['tool_calls'], int(payload.get('tool_use_count') or 0))
            a['tokens'] = max(a['tokens'], int(payload.get('token_count') or 0))
    if run_status in TERMINAL:
        for a in agents.values():
            if a['status'] in ('running', 'waiting'):
                a['status'] = 'done' if run_status == 'awaiting_review' else 'failed'
            a['current_tool'] = None
    elif run_status in ('running', 'finalizing') and lead['status'] == 'waiting':
        lead['status'] = 'running'
    return {'agents': list(agents.values()), 'budget': budget, 'phase': phase}


class InvestigationService:
    def __init__(self, platform, *, config: ExecutorConfig | None = None, executor: Executor | None = None):
        self.p = platform
        self.config = config if config is not None else ExecutorConfig.from_env()
        self.issuer = Issuer(self.config) if self.config else None
        self.executor = executor or (HttpExecutor(self.config, self.issuer) if self.config else None)
        if self.executor is None:
            # Laptop demo / development: run the RLM harness in-process (INVESTIGATION_EXECUTOR=local).
            from .local_executor import local_executor_from_env
            self.executor = local_executor_from_env()

    @property
    def configured(self) -> bool:
        return self.executor is not None

    @staticmethod
    def entitled(tenant_id: str) -> bool:
        """Multi-agent investigations are a paid feature, switched on per organization by the operator
        (INVESTIGATIONS_ENABLED_TENANTS: comma-separated tenant ids, or * for a demo machine)."""
        allowed = {t.strip() for t in os.environ.get('INVESTIGATIONS_ENABLED_TENANTS', '').split(',') if t.strip()}
        return '*' in allowed or tenant_id in allowed

    # --- permissions ---------------------------------------------------------------
    @staticmethod
    def _person(ctx: AccessContext, what: str) -> None:
        if ctx.actor_kind != 'person' or ctx.delegated_from:
            raise AuthorizationError(Decision(False, f'{what} requires the person; {ctx.actor_kind} credentials cannot'))

    def _readable(self, ctx: AccessContext, state: dict[str, Any]) -> bool:
        if state['tenant_id'] != ctx.tenant_id:
            return False
        if state['owner_id'] == (ctx.delegated_from or ctx.actor_id):
            return True
        return bool(state.get('case_id')) and bool(self.p.identity.check(ctx, 'read', 'case', state['case_id'], site_id=state['site_id']))

    def _run(self, ctx: AccessContext, run_id: str):
        rec = self.p.store.read().require(ctx.tenant_id, KIND, run_id)
        if not self._readable(ctx, rec.state):
            raise PermissionError('this investigation belongs to someone else')
        return rec

    # --- evidence snapshot ---------------------------------------------------------
    def snapshot(self, ctx: AccessContext, *, site_id: str, dataset_ids=(), case_ids=(), record_refs=(),
                 extra_files: dict[str, bytes] | None = None) -> tuple[bytes, dict[str, Any]]:
        """Authorized evidence as one deterministic ZIP. Permission is checked now, item by item."""
        from .cmo_datasets import require_dataset
        files: dict[str, bytes] = {}
        items: list[dict[str, Any]] = []

        def add(path, content, **meta):
            files[path] = content
            items.append({**meta, 'path': path, 'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)})

        for evidence_id in dict.fromkeys(dataset_ids):
            rec = require_dataset(self.p, ctx, evidence_id, site_id)
            data = json.loads(self.p.evidence.original(ctx, evidence_id, rec.revision))
            out = io.StringIO()
            out.write('measurement_id,batch_id,elapsed_h,parameter,value,unit,source_path\n')
            import csv
            writer = csv.writer(out)
            for m in data.get('measurements', []):
                writer.writerow([m.get('id'), m.get('batch'), m.get('time'), m.get('parameter'), m.get('value'), m.get('unit'),
                                 (m.get('source') or {}).get('path')])
            add(f'datasets/{evidence_id}.csv', out.getvalue().encode(), kind='evidence', id=evidence_id, revision=rec.revision)
        for case_id in dict.fromkeys(case_ids):
            case = self.p.cases.get(ctx, case_id)
            if case['site_id'] != site_id:
                raise PermissionError('case belongs to another site')
            add(f'cases/{case_id}.json', json.dumps(case, sort_keys=True, default=str).encode(), kind='case', id=case_id,
                revision=case['revision'])
        for ref in record_refs:
            kind, ident = str(ref.get('kind', '')), str(ref.get('id', ''))
            if not re.fullmatch(r'[a-z_]{1,64}', kind) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', ident):
                raise ValueError('invalid record reference')
            if kind == 'evidence':
                rec = self.p.store.read().require(ctx.tenant_id, 'evidence', ident)
                self.p.identity.require(ctx, 'read', 'evidence', ident, site_id=rec.state.get('site_id'))
                media = str(rec.state.get('media_type') or '')
                suffix = {'application/json': '.json', 'text/csv': '.csv', 'application/pdf': '.pdf'}.get(media, '.txt')
                add(f'evidence/{ident}{suffix}', self.p.evidence.original(ctx, ident, rec.revision), kind=kind, id=ident,
                    revision=rec.revision)
            else:
                rec = self.p.store.read().require(ctx.tenant_id, kind, ident)
                self.p.identity.require(ctx, 'read', kind, ident, site_id=rec.state.get('site_id'))
                if rec.state.get('site_id') not in (None, site_id):
                    raise PermissionError('record belongs to another site')
                add(f'records/{kind}-{ident}.json', json.dumps(rec.state, sort_keys=True, default=str).encode(),
                    kind=kind, id=ident, revision=rec.revision)
        for name, content in sorted((extra_files or {}).items()):
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,120}', name):
                raise ValueError('invalid snapshot file name')
            add(f'context/{name}', content, kind='context', id=name, revision=None)
        if not files:
            raise ValueError('an investigation needs at least one evidence item it can read')
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(files):
                info = zipfile.ZipInfo(path, date_time=(2020, 1, 1, 0, 0, 0))  # deterministic bytes for identical evidence
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, files[path])
        data = buffer.getvalue()
        if len(data) > SNAPSHOT_LIMIT:
            raise ValueError('evidence snapshot exceeds the 64 MiB execution limit; select fewer items')
        return data, {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'items': items, 'taken_at': iso(_now())}

    # --- start / stop --------------------------------------------------------------
    def start(self, ctx: AccessContext, request: dict[str, Any], *, extra_files: dict[str, bytes] | None = None) -> dict[str, Any]:
        self._person(ctx, 'starting an investigation')
        if not self.entitled(ctx.tenant_id):
            raise ConflictError(NOT_ENTITLED)
        if not self.configured:
            raise ConflictError(NOT_CONFIGURED)
        site_id = request.get('site_id') or 'NF1'
        proposal = None
        if request.get('proposal_id'):
            proposal = self.p.store.read().require(ctx.tenant_id, PROPOSAL, request['proposal_id'])
            if proposal.state['owner_id'] != ctx.actor_id:
                raise PermissionError('this proposed investigation belongs to someone else')
            if proposal.state.get('run_id'):
                return self.get(ctx, proposal.state['run_id'])
            if request.get('conversation_id') and request['conversation_id'] != proposal.state['conversation_id']:
                raise PermissionError('proposal belongs to another conversation')
            site_id = proposal.state['site_id']
        objective = (request.get('objective') or (proposal.state['objective'] if proposal else '')).strip()
        if not 3 <= len(objective) <= 8000:
            raise ValueError('an investigation needs an objective of 3-8000 characters')
        case_id = request.get('case_id') or (proposal.state.get('case_id') if proposal else None)
        if case_id:
            case = self.p.cases.get(ctx, case_id)
            site_id = case['site_id']
            self.p.identity.require(ctx, 'propose', 'case', case_id, site_id=site_id)
        else:
            self.p.identity.require(ctx, 'propose', 'mission', site_id=site_id)
        budget_in = {**DEFAULT_BUDGET, **{k: v for k, v in (request.get('budget') or {}).items() if v is not None}}
        tool_calls = int(budget_in['max_tool_calls'])
        minutes = int(budget_in['minutes'])
        if not (1 <= tool_calls <= 200 and 1 <= minutes <= 60):
            raise ValueError('budget must be 1-200 tool calls and 1-60 minutes')
        limits = {'max_tool_calls': tool_calls, 'timeout_seconds': max(60, minutes * 60),
                  'max_tokens': int(budget_in['max_tokens']) if budget_in.get('max_tokens') else None}
        active = [r for r in self.p.store.read().list(ctx.tenant_id, KIND) if r.state['status'] in ACTIVE]
        if len(active) >= MAX_ACTIVE_PER_TENANT:
            raise ConflictError(f'{MAX_ACTIVE_PER_TENANT} investigations are already running; wait for one to finish or stop it')
        if proposal and not (request.get('dataset_ids') or request.get('record_refs')):
            request = {**request, 'dataset_ids': proposal.state.get('dataset_ids', [])}
        data, snapshot = self.snapshot(ctx, site_id=site_id, dataset_ids=request.get('dataset_ids') or [],
                                       case_ids=[case_id] if case_id else [], record_refs=request.get('record_refs') or [],
                                       extra_files=extra_files)
        run_id = new_id('invrun')
        project = self.config.project_for(ctx.tenant_id) if self.config else 'investigation'
        now = _now()
        state = {'run_id': run_id, 'tenant_id': ctx.tenant_id, 'site_id': site_id, 'owner_id': ctx.actor_id,
                 'case_id': case_id, 'conversation_id': request.get('conversation_id') or (proposal.state['conversation_id'] if proposal else None),
                 'turn_id': proposal.state.get('turn_id') if proposal else None, 'proposal_id': request.get('proposal_id'),
                 'mission_id': proposal.state.get('mission_id') if proposal else None,
                 'objective': objective, 'as_of': iso(now), 'evidence_snapshot': snapshot, 'budget': limits,
                 'deadline': iso(now + timedelta(seconds=limits['timeout_seconds'])), 'status': 'queued', 'issues': [],
                 'executor': {'project': project, 'job_id': None, 'version_id': None}, 'events_cursor': 0,
                 'agents': [], 'budget_used': {}, 'phase': None,
                 'sync': {'updated_at': None, 'reachable': True, 'last_error': None}, 'report_ref': None,
                 'created_at': iso(now)}
        with self.p.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, KIND, run_id, state, expected_revision=None, action='start_investigation',
                   event_type='investigation.started', event_payload={'run_id': run_id, 'site_id': site_id})
            if proposal:
                current = tx.require(ctx.tenant_id, PROPOSAL, proposal.id)
                tx.put(ctx.tenant_id, PROPOSAL, proposal.id, {**current.state, 'run_id': run_id}, expected_revision=current.revision,
                       action='start_proposed_investigation')
        try:
            uploaded = self.executor.upload(project, snapshot['sha256'], data)
            job = {'sha256': snapshot['sha256'], 'version_id': uploaded['version_id'], 'objective': objective,
                   'as_of': state['as_of'], 'timeout_seconds': limits['timeout_seconds'], 'max_tool_calls': limits['max_tool_calls']}
            if limits['max_tokens']:
                job['max_tokens'] = limits['max_tokens']
            submitted = self.executor.submit(project, run_id, job)
        except (ExecutorUnavailable, ValueError, KeyError) as exc:
            return self._update(ctx, run_id, status='failed', issues=[f'Could not start: {exc}'],
                                sync={'updated_at': iso(_now()), 'reachable': not isinstance(exc, ExecutorUnavailable), 'last_error': str(exc)})
        return self._update(ctx, run_id, status='submitted',
                            executor={'project': project, 'job_id': submitted['id'], 'version_id': uploaded['version_id']})

    def stop(self, ctx: AccessContext, run_id: str) -> dict[str, Any]:
        self._person(ctx, 'stopping an investigation')
        rec = self._run(ctx, run_id)
        if rec.state['owner_id'] != ctx.actor_id:
            raise PermissionError('only the person who started this investigation can stop it')
        if rec.state['status'] in TERMINAL:
            return self.view(rec.state)
        self._update(ctx, run_id, status='cancelled', issues=[*rec.state['issues'], f'Stopped by {ctx.actor_id}'])
        job_id = rec.state['executor']['job_id']
        if job_id:
            try:
                self.executor.cancel(rec.state['executor']['project'], job_id)
            except (ExecutorUnavailable, ValueError) as exc:
                # The run stays cancelled here; the executor's fencing rejects any later result.
                self._update(ctx, run_id, sync={**rec.state['sync'], 'last_error': f'cancel not confirmed: {exc}'})
        return self.get(ctx, run_id, sync=False)

    # --- sync from the executor ----------------------------------------------------
    def sync(self, ctx: AccessContext, run_id: str, *, force: bool = False) -> dict[str, Any]:
        rec = self._run(ctx, run_id)
        s = rec.state
        if s['status'] in TERMINAL or not s['executor']['job_id'] or not self.configured:
            return s
        last = _parse(s['sync']['updated_at'])
        if not force and last and (_now() - last).total_seconds() < SYNC_INTERVAL_S:
            return s
        project, job_id = s['executor']['project'], s['executor']['job_id']
        changes: dict[str, Any] = {}
        try:
            job = self.executor.job(project, job_id)
            cursor, fresh = s['events_cursor'], []
            for _ in range(5):
                page = self.executor.events(project, job_id, cursor)
                batch = [e for e in page.get('events', []) if int(e['seq']) > cursor and e.get('kind') in EVENT_KINDS]
                fresh.extend(batch)
                nxt = int(page.get('next') or cursor)
                if not batch or nxt <= cursor:
                    break
                cursor = nxt
            if fresh:
                cursor = max(cursor, max(int(e['seq']) for e in fresh))
            changes['sync'] = {'updated_at': iso(_now()), 'reachable': True, 'last_error': None}
        except ExecutorUnavailable as exc:
            changes['sync'] = {'updated_at': iso(_now()), 'reachable': False, 'last_error': str(exc),
                               'unreachable_since': s['sync'].get('unreachable_since') or iso(_now())}
            job, fresh, cursor = None, [], s['events_cursor']
        self._record_events(ctx, run_id, fresh)
        status, issues = s['status'], list(s['issues'])
        if job:
            state = job.get('state')
            if state == 'queued':
                status = 'submitted'
            elif state == 'running':
                status = 'running'
            elif state == 'succeeded':
                status, report, problem = self._fetch_report(ctx, s, project, job_id)
                if problem:
                    issues.append(problem)
                if report is not None:
                    changes['report_ref'] = {'kind': REPORT, 'id': run_id}
            elif state == 'cancelled':
                status = 'cancelled'
            elif state == 'failed':
                status = 'failed'
                issues.append(f"Execution failed ({job.get('error_code') or 'no error code'}); saved progress remains visible.")
        deadline = _parse(s['deadline'])
        if status in ACTIVE and deadline and _now() > deadline + timedelta(seconds=REPORT_GRACE_S):
            status = 'blocked'
            issues.append('No validated report arrived within the time limit; saved subreports remain visible.')
        events = self._events(ctx, run_id)
        folded = fold(events, run_status=status, limits=s['budget'])
        changes.update(status=status, issues=list(dict.fromkeys(issues)), events_cursor=cursor,
                       agents=folded['agents'], budget_used=folded['budget'], phase=folded['phase'])
        if status in ACTIVE and folded['phase'] == 'finalizing':
            changes['status'] = 'finalizing'
        try:
            return self._update(ctx, run_id, expected=rec.revision, **changes)
        except ConflictError:
            return self.p.store.read().require(ctx.tenant_id, KIND, run_id).state  # a concurrent sync won; use its view

    def _fetch_report(self, ctx, s, project, job_id):
        try:
            result = self.executor.result(project, job_id)
        except ExecutorUnavailable:
            return 'finalizing', None, None
        except ValueError as exc:
            return 'blocked', None, f'Report could not be read: {exc}'
        ok = (isinstance(result, dict) and result.get('run_id') == job_id
              and result.get('input_sha256') == s['evidence_snapshot']['sha256']
              and result.get('review_status') == 'requires_human_review' and isinstance(result.get('report'), dict))
        if not ok:
            return 'blocked', None, 'The returned report failed validation (run, evidence fingerprint or review status did not match); it was not accepted.'
        with self.p.store.transaction(ctx.actor_id) as tx:
            if tx.get(ctx.tenant_id, REPORT, s['run_id']) is None:
                tx.put(ctx.tenant_id, REPORT, s['run_id'],
                       {'run_id': s['run_id'], 'site_id': s['site_id'], 'case_id': s.get('case_id'), 'owner_id': s['owner_id'],
                        'executor_job_id': job_id, 'input_sha256': result['input_sha256'], 'as_of': result.get('as_of'),
                        'review_status': 'requires_human_review', 'report': result['report'], 'received_at': iso(_now())},
                       expected_revision=None, action='receive_investigation_report',
                       event_type='investigation.report_received', event_payload={'run_id': s['run_id']})
        # ponytail: report is stored for review here; wiring into the QA review package is the next seam (quality.PackageService).
        return 'awaiting_review', result['report'], None

    def _record_events(self, ctx, run_id, events):
        if not events:
            return
        with self.p.store.transaction(ctx.actor_id) as tx:
            if tx.require(ctx.tenant_id, KIND, run_id).state['status'] == 'cancelled':
                return  # events after Stop are ignored
            for e in events:
                ident = f"{run_id}:{int(e['seq']):08d}"
                if tx.get(ctx.tenant_id, EVENT, ident) is not None:
                    continue  # duplicate delivery
                tx.put(ctx.tenant_id, EVENT, ident,
                       {'run_id': run_id, 'seq': int(e['seq']), 'attempt': e.get('attempt'), 'at': e.get('at'), 'kind': e['kind'],
                        'agent_id': e.get('agent_id'), 'parent_id': e.get('parent_id'), 'payload': e.get('payload') or {}},
                       expected_revision=None, action='record_investigation_event')

    def _events(self, ctx, run_id, after: int = 0) -> list[dict[str, Any]]:
        rows = self.p.store.read().list(ctx.tenant_id, EVENT, lambda s: s.get('run_id') == run_id and s.get('seq', 0) > after)
        return sorted((r.state for r in rows), key=lambda e: e['seq'])

    def _update(self, ctx, run_id, *, expected: int | None = None, **changes) -> dict[str, Any]:
        with self.p.store.transaction(ctx.actor_id) as tx:
            current = tx.require(ctx.tenant_id, KIND, run_id)
            if expected is not None and current.revision != expected:
                raise ConflictError('investigation changed during sync')
            if current.state['status'] == 'cancelled' and changes.get('status') not in (None, 'cancelled'):
                changes.pop('status')  # Stop is final
            state = {**current.state, **changes}
            terminal_now = state['status'] in TERMINAL and current.state['status'] not in TERMINAL
            tx.put(ctx.tenant_id, KIND, run_id, state, expected_revision=current.revision,
                   action='update_investigation', event_type='investigation.' + state['status'] if terminal_now else None,
                   event_payload={'run_id': run_id} if terminal_now else None)
        return state

    # --- reads ---------------------------------------------------------------------
    @staticmethod
    def view(state: dict[str, Any]) -> dict[str, Any]:
        updated = _parse(state['sync'].get('updated_at'))
        return {k: state.get(k) for k in ('run_id', 'site_id', 'owner_id', 'case_id', 'conversation_id', 'proposal_id', 'objective',
                                          'as_of', 'status', 'issues', 'phase', 'deadline', 'created_at')} | {
            'evidence_snapshot': {k: state['evidence_snapshot'][k] for k in ('sha256', 'bytes', 'taken_at')}
                                 | {'items': [{k: i.get(k) for k in ('kind', 'id', 'revision', 'path')} for i in state['evidence_snapshot']['items']]},
            'agents': state.get('agents') or fold([], run_status=state['status'], limits=state['budget'])['agents'],
            'budget': state.get('budget_used') or fold([], run_status=state['status'], limits=state['budget'])['budget'],
            'sync': {**state['sync'], 'lag_seconds': round((_now() - updated).total_seconds(), 1) if updated else None},
            'report_available': bool(state.get('report_ref'))}

    def get(self, ctx: AccessContext, run_id: str, *, sync: bool = True) -> dict[str, Any]:
        return self.view(self.sync(ctx, run_id) if sync else self._run(ctx, run_id).state)

    def events(self, ctx: AccessContext, run_id: str, after: int = 0) -> dict[str, Any]:
        self._run(ctx, run_id)
        events = self._events(ctx, run_id, after)[:500]
        return {'events': events, 'next': events[-1]['seq'] if events else after}

    def list(self, ctx: AccessContext, *, case_id: str | None = None, conversation_id: str | None = None) -> list[dict[str, Any]]:
        rows = [r.state for r in self.p.store.read().list(ctx.tenant_id, KIND)
                if (not case_id or r.state.get('case_id') == case_id)
                and (not conversation_id or r.state.get('conversation_id') == conversation_id)]
        return [self.view(s) for s in sorted(rows, key=lambda s: s['created_at'], reverse=True) if self._readable(ctx, s)][:50]

    def report(self, ctx: AccessContext, run_id: str) -> dict[str, Any]:
        run = self._run(ctx, run_id)
        if run.state['status'] != 'awaiting_review' or not run.state.get('report_ref'):
            raise ConflictError('the report is not available yet')
        return self.p.store.read().require(ctx.tenant_id, REPORT, run_id).state

    def send_for_review(self, ctx: AccessContext, run_id: str) -> dict[str, Any]:
        """Put the report's hypotheses and open questions on the case as labelled claims, then build the QA package.
        Nothing becomes a finding: causes stay hypotheses until QA review approves them."""
        self._person(ctx, 'sending an investigation for QA review')
        rec = self._run(ctx, run_id)
        state = rec.state
        if state['status'] != 'awaiting_review':
            raise ConflictError('only a finished investigation with a validated report can be sent for review')
        if not state.get('case_id'):
            raise ValueError('link this investigation to a case before sending it for QA review')
        if state.get('review_package_id'):
            return {'run_id': run_id, 'package_id': state['review_package_id'], 'claims': state.get('review_claim_ids', [])}
        from .quality import SEARCH_STATUSES, ClaimService
        report = self.report(ctx, run_id)['report']
        note = (f"From investigation {run_id} (evidence snapshot {state['evidence_snapshot']['sha256'][:12]}); "
                'citations are in that snapshot and have not been re-checked against platform originals.')
        claims = ClaimService(self.p.store, self.p.identity, self.p.evidence)
        ids = []
        for h in (report.get('hypotheses') or [])[:12]:
            text = str((h or {}).get('statement') or (h or {}).get('text') or '').strip() if isinstance(h, dict) else str(h).strip()
            if not text:
                continue
            searched = h.get('contradicting_evidence_status') if isinstance(h, dict) else None
            ids.append(claims.record_claim(ctx, state['case_id'], text[:2000], 'hypothesis', [], [], unknowns=[note],
                counterevidence_status=searched if searched in SEARCH_STATUSES else 'not_searched')['id'])
        for q in (report.get('open_questions') or [])[:12]:
            text = str(q.get('question') if isinstance(q, dict) else q).strip()
            if text:
                ids.append(claims.record_claim(ctx, state['case_id'], text[:2000], 'unknown', [], [], unknowns=[text[:500]])['id'])
        with self.p.store.transaction(ctx.actor_id):
            package = self.p.packages.build_package(ctx, state['case_id'])
        package_id = package['id']
        self._update(ctx, run_id, review_package_id=package_id, review_claim_ids=ids)
        return {'run_id': run_id, 'package_id': package_id, 'claims': ids}

    def sync_active(self, ctx_for_owner) -> int:
        """For a scheduler: sync every active run. ``ctx_for_owner(tenant, owner)`` builds each owner's context."""
        count = 0
        for tenant in getattr(self.p.runtime, 'tenants', lambda: [])():
            for rec in self.p.store.read().list(tenant, KIND, lambda s: s.get('status') in ACTIVE):
                try:
                    self.sync(ctx_for_owner(tenant, rec.state['owner_id']), rec.id, force=True)
                    count += 1
                except (PermissionError, ConflictError, ValueError):
                    continue
        return count

    # --- chat proposal -------------------------------------------------------------
    def propose(self, ctx: AccessContext, *, thread: dict[str, Any], turn: dict[str, Any], objective: str,
                case_id: str | None, rationale: str, tx=None) -> dict[str, Any]:
        """The assistant may only propose; a person presses Start (see ``start``)."""
        self.p.identity.require(ctx, 'propose', 'mission', site_id=thread['site_id'])
        pid = new_id('invprop')
        state = {'id': pid, 'owner_id': thread['owner_id'], 'site_id': thread['site_id'], 'conversation_id': thread['id'],
                 'turn_id': turn['id'], 'mission_id': thread.get('mission_id'), 'objective': objective, 'case_id': case_id,
                 'rationale': rationale, 'dataset_ids': list(thread.get('dataset_ids') or []),
                 'budget': {'max_tool_calls': DEFAULT_BUDGET['max_tool_calls'], 'minutes': DEFAULT_BUDGET['minutes']},
                 'executor_configured': self.configured, 'entitled': self.entitled(ctx.tenant_id), 'run_id': None, 'proposed_by': ctx.actor_id,
                 'proposed_by_kind': ctx.actor_kind, 'created_at': iso(_now())}
        if tx is not None:
            tx.put(ctx.tenant_id, PROPOSAL, pid, state, expected_revision=None, action='propose_investigation')
        else:
            with self.p.store.transaction(ctx.actor_id) as t:
                t.put(ctx.tenant_id, PROPOSAL, pid, state, expected_revision=None, action='propose_investigation')
        return state

    def proposal_view(self, ctx: AccessContext, proposal_id: str) -> dict[str, Any]:
        rec = self.p.store.read().require(ctx.tenant_id, PROPOSAL, proposal_id)
        out = {**rec.state, 'revision': rec.revision, 'executor_configured': self.configured, 'entitled': self.entitled(ctx.tenant_id)}
        if rec.state.get('run_id'):
            try:
                out['run'] = self.get(ctx, rec.state['run_id'], sync=False)
            except PermissionError:
                out['run'] = None
        return out
