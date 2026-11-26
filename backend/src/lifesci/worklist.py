"""Everything waiting on one person, in one read.

Decisions are raised all over the product: an action proposed for approval, a request from a colleague, a question
the assistant asked, a signal, a quality review, a delivery with values to check. Each lives with the service that
owns it and, until now, was visible only on the page that raised it, so a proposal could wait for an approver who
had no way to see it. This module reads them together for one person at one site, in three groups: what needs
them, what is in progress for them, and what was recently finished.

It owns nothing and decides nothing. Every item is read from its own record under the reader's current access, and
every decision is still made through the owning service. Reads are filtered and trimmed in the database
(``Transaction.select``), so the list costs a few small queries, not a download of each record kind.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Iterator

from .ids import content_hash, iso, utc_now
from .memory import principal
from .workspace_tasks import ROLE_WORDS

log = logging.getLogger(__name__)

DONE_DAYS = 7   # how long finished work stays listed
SHOWN = 30      # per group
# What the list reads, and what it does not yet read. Both are returned, so that an item missing from the list is
# never taken to mean that nothing is waiting.
PREPARED = 'worklist_prepared_check'   # a delivery checked against approved requirements before anyone asked
COVERS = {'approvals': 'actions proposed for approval', 'requests': 'requests between colleagues',
          'prepared': 'checks of new deliveries against approved requirements',
          'assistant': 'assistant questions and answers', 'signals': 'open signals', 'quality': 'quality events',
          'deliveries': 'delivery checks'}
NOT_COVERED = ('routine and rule drafts', 'investigations waiting to start', 'record reviews for connected sources')
# Needs-you order: what blocks other people or carries risk first.
RANK = {'signal': 0, 'approval': 1, 'question': 2, 'request': 3, 'missing_evidence': 4, 'quality': 5, 'delivery': 6, 'assistant': 7, 'proposal': 8}
SEVERITY_WORDS = {'warning': 'Early warning', 'action': 'Out of specification', 'critical': 'Critical'}
QUALITY_WAITS = {  # workflow state -> (who it waits on, what they do)
    'awaiting_triage': ('owner_id', 'decide how to handle it'),
    'technical_review': ('owner_id', 'confirm the technical review to send it to QA'),
    'returned': ('owner_id', 'QA returned it; read the reason and revise'),
    'qa_review': ('qa_reviewer_id', 'approve the local preparation or return it'),
}
Item = tuple[str, dict[str, Any]]  # (group, item)


def _words(operation: str) -> str:
    return ' '.join('CAPA' if w == 'capa' else w for w in str(operation).split('_')).capitalize().replace('capa', 'CAPA')


def _people(roles) -> str:
    names = [ROLE_WORDS.get(r, str(r).replace('_', ' ')) for r in roles or ()]
    return ' and '.join(names) or 'an approver'


def _count(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else many or one + 's'}"


def _clip(text, limit=300) -> str:
    text = ' '.join(str(text or '').split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def _item(kind: str, record_id: str, title: str, *, detail: str = '', by: str = 'system', at: str | None = None,
          href: str | None = None, action: dict[str, Any] | None = None, **facts: Any) -> dict[str, Any]:
    return {'id': f'{kind}:{record_id}', 'kind': kind, 'title': _clip(title, 240), 'detail': _clip(detail, 600), 'by': by,
            'at': at, 'href': href, 'action': action, **facts}


class WorklistService:
    def __init__(self, platform) -> None:
        self.p = platform
        self.deliveries = None  # set where delivery verification is installed: tenant -> per-run review counts

    # --- the list --------------------------------------------------------------------------------------------
    def read(self, ctx, site_id: str) -> dict[str, Any]:
        """What needs this person, what is in progress for them and what was finished in the last week, at one site."""
        me = principal(ctx)
        since = iso(utc_now() - timedelta(days=DONE_DAYS))
        names = Names(self.p.store, ctx.tenant_id, me)
        groups: dict[str, list[dict[str, Any]]] = {'needs_you': [], 'in_progress': [], 'done': []}
        unavailable = []
        for source, read in (('approvals', self._proposals), ('requests', self._requests), ('prepared', self._prepared),
                             ('assistant', self._assistant), ('signals', self._signals), ('quality', self._quality),
                             ('deliveries', self._deliveries)):
            try:
                found = list(read(ctx, me, site_id, since, names))
            except PermissionError:
                continue  # outside this person's access: nothing of theirs can be waiting there
            except Exception:  # noqa: BLE001 - one failing source is named in the result, never dropped silently
                log.exception('worklist source %s failed', source)
                unavailable.append({'source': source, 'covers': COVERS[source]})
                continue
            for group, item in found:
                groups[group].append(item)
        groups['needs_you'].sort(key=lambda i: i['at'] or '', reverse=True)
        groups['needs_you'].sort(key=lambda i: RANK.get(i['kind'], 9))  # stable: newest first within a kind
        for group in ('in_progress', 'done'):
            groups[group].sort(key=lambda i: i['at'] or '', reverse=True)
        counts = {group: len(items) for group, items in groups.items()}
        return {'site_id': site_id, 'as_of': iso(utc_now()), 'done_since': since, **{g: items[:SHOWN] for g, items in groups.items()},
                'counts': counts, 'covers': list(COVERS.values()), 'not_covered': list(NOT_COVERED), 'unavailable': unavailable}

    # --- actions proposed for approval -----------------------------------------------------------------------
    def _proposals(self, ctx, me, site_id, since, names) -> Iterator[Item]:
        tx, check = self.p.store.read(), self.p.identity.check
        fields = ('operation', 'target_id', 'target_system', 'rationale', 'expected_result', 'risk', 'required_roles',
                  'requested_by', 'requested_by_kind', 'revised_by', 'constraints', 'basis', 'content_hash', 'status',
                  'execution_status', 'follow_up_measure', 'created_at', 'origin')
        writers = None  # (system, operation) pairs a connection at this site may carry out; read only if needed
        for p in tx.select(ctx.tenant_id, 'proposal', fields, limit=200,
                           where={'site_id': site_id, 'status': ['proposed', 'approved', 'rejected', 'stale']}):
            if not check(ctx, 'read', 'proposal', p['id'], site_id=site_id):
                continue
            what = f"{_words(p['operation'])} · {p['target_id']}"
            mine = p['requested_by'] in (me, f'agent:{me}')
            origin = p.get('origin') or {}
            background = p.get('requested_by_kind') == 'agent'
            by = 'assistant' if background or origin.get('drafted_by') == 'assistant' else p['requested_by']
            author = ('the assistant' if background else f"the assistant, asked by {names(p['requested_by'])}" if by == 'assistant'
                      else names(by))
            if p.get('revised_by'):
                author += '; revised by ' + ', '.join(names(r) for r in p['revised_by'])
            common = {'at': p['updated_at'], 'by': by}
            if p['status'] == 'proposed':
                roles = self._can_decide(ctx, tx, p, site_id)
                if roles:
                    basis = p.get('basis') or []
                    described = origin.get('result') or {}
                    # The account is of one saved result. It is shown only while the proposal still rests on that result.
                    says = origin.get('result_says') if any(
                        ref.get('kind') == 'workspace_task_result' and ref.get('id') == described.get('id')
                        and ref.get('revision') == described.get('revision') for ref in basis) else None
                    yield 'needs_you', _item(
                        'approval', p['id'], f'Approve or decline: {what}', **common,
                        detail=p['rationale'],
                        action={'type': 'decide', 'proposal_id': p['id'], 'revision': p['revision'], 'roles': roles,
                                'recent_sign_in': p['risk'] in ('high', 'critical')},
                        proposal={'action': _words(p['operation']), 'target': p['target_id'], 'system': p.get('target_system'),
                                  'rationale': p['rationale'], 'expected_result': p['expected_result'],
                                  'follow_up_measure': p.get('follow_up_measure'), 'constraints': p.get('constraints') or [],
                                  'risk': p['risk'], 'approvers': _people(p['required_roles']),
                                  'proposed_by': author, 'rests_on': self._basis_words(basis),
                                  'result_says': says})
                elif mine:
                    yield 'in_progress', _item('proposal', p['id'], f"Waiting for {_people(p['required_roles'])} to approve: {what}",
                                               detail=p['rationale'], **common)
            elif not mine:
                continue
            elif p['status'] == 'approved':
                system, state = p.get('target_system') or 'the owning system', p.get('execution_status') or 'not_started'
                if state in ('not_started', 'queued') and writers is None:
                    writers = {(c.get('family'), op)
                               for c in tx.select(ctx.tenant_id, 'connector', ('family', 'write_operations'), where={'site_id': site_id})
                               for op in c.get('write_operations') or []}
                if state == 'delivered':
                    if p['updated_at'] >= since:
                        yield 'done', _item('proposal', p['id'], f'Carried out: {what}', **common, detail=f'Confirmed by {system}.')
                elif state not in ('not_started', 'queued') or (p.get('target_system'), p['operation']) in writers:
                    # A connection here can carry it out, or has already tried: it is waiting on that system.
                    yield 'in_progress', _item(
                        'proposal', p['id'], f'Approved, not yet carried out: {what}', **common,
                        detail=f'Approval is not execution. A connection to {system} can carry this out; it is complete only '
                               f"with a receipt from {system} (now: {state.replace('_', ' ')}).")
                elif p['updated_at'] >= since:
                    # Nothing here will act on it, so it is not "in progress": the approval is what happened. Many targets
                    # are review gates inside this product, and no deployed connection may write to an outside system.
                    yield 'done', _item(
                        'proposal', p['id'], f'Approved: {what}', **common,
                        detail=f"{_people(p['required_roles'])} approved it. The approval is on record. Nothing here carries the "
                               'action out; where it has to be done in another system, that is still to do.')
            elif p['status'] == 'rejected' and p['updated_at'] >= since:
                yield 'done', _item('proposal', p['id'], f'Declined: {what}', **common, detail=self._decline_reason(tx, ctx, p))
            elif p['status'] == 'stale':
                yield 'needs_you', _item('proposal', p['id'], f'The evidence behind your proposal changed: {what}', **common,
                                         detail='It can no longer be approved as written. Run the work again and propose it again if it still applies.')

    def _can_decide(self, ctx, tx, p, site_id) -> list[str]:
        """The roles this person may decide with now: the same rule the action service enforces at decision time."""
        if ctx.actor_kind != 'person' or ctx.actor_id == p['requested_by'] or ctx.actor_id in (p.get('revised_by') or []):
            return []
        held = [r for r in p['required_roles'] if r in ctx.roles]
        if not held or not self.p.identity.check(ctx, 'approve', 'proposal', p['id'], site_id=site_id):
            return []
        decided = {a.state['role'] for a in tx.find(ctx.tenant_id, 'approval', 'proposal_id', p['id'])
                   if a.state['content_hash'] == p['content_hash']}
        return [r for r in held if r not in decided]

    @staticmethod
    def _basis_words(basis) -> str:
        kinds: dict[str, int] = {}
        for ref in basis:
            kind = str(ref.get('kind') or 'record')
            kinds[kind] = kinds.get(kind, 0) + 1
        words = {'workspace_task_result': 'saved result', 'evidence': 'source record', 'specification': 'approved specification'}
        return ', '.join(_count(n, words.get(kind, kind.replace('_', ' '))) for kind, n in kinds.items()) or 'no cited records'

    @staticmethod
    def _decline_reason(tx, ctx, p) -> str:
        for a in tx.find(ctx.tenant_id, 'approval', 'proposal_id', p['id']):
            if a.state['decision'] == 'rejected' and a.state['content_hash'] == p['content_hash']:
                return f"{ROLE_WORDS.get(a.state['role'], a.state['role'])}: {a.state.get('comment') or 'no reason given'}"
        return ''

    # --- requests between colleagues -------------------------------------------------------------------------
    def _requests(self, ctx, me, site_id, since, names) -> Iterator[Item]:
        self.p.assistant_routines._current_owner(ctx, site_id)  # the same access a single request requires
        tx = self.p.store.read()
        fields = ('title', 'description', 'severity', 'owner_id', 'requested_by', 'status', 'reply', 'answered_at', 'created_at')
        for r in tx.select(ctx.tenant_id, 'assistant_work_request', fields, where={'site_id': site_id, 'owner_id': me}, limit=100):
            if (r.get('status') or 'open') == 'open':
                asks = 'A note to yourself' if r['requested_by'] == me else f"{names(r['requested_by'])} asks"
                yield 'needs_you', _item('request', r['id'], f"{asks}: {r['title']}", detail=r['description'],
                                         by=r['requested_by'], at=r['created_at'],
                                         action={'type': 'reply', 'request_id': r['id'], 'revision': r['revision']})
        for r in tx.select(ctx.tenant_id, 'assistant_work_request', fields, where={'site_id': site_id, 'requested_by': me}, limit=100):
            if r['owner_id'] == me:
                continue  # a note to oneself is listed once, above
            if (r.get('status') or 'open') == 'open':
                yield 'in_progress', _item('request', r['id'], f"Waiting for {names(r['owner_id'])} to reply: {r['title']}",
                                           detail=r['description'], by=me, at=r['created_at'])
            elif (r.get('answered_at') or '') >= since:
                yield 'done', _item('request', r['id'], f"{names(r['owner_id'])} replied: {r['title']}", detail=r.get('reply') or '',
                                    by=r['owner_id'], at=r['answered_at'])

    # --- deliveries checked before anyone asked --------------------------------------------------------------
    def prepare_delivery(self, ctx, evidence_id: str, site_id: str) -> dict[str, Any] | None:
        """Check a newly published delivery against the site's approved requirements, once per delivery revision and
        person, without being asked. A host calculation: no model is called and nothing is sent. What it finds is kept
        as that person's saved gap check, with the request it drafted, and offered in their list for them to send."""
        me, tx = principal(ctx), self.p.store.read()
        delivery = tx.require(ctx.tenant_id, 'evidence', evidence_id)
        meta = delivery.state.get('metadata') or {}
        if meta.get('classification') != 'verified_cmo_dataset':
            return None  # values still in review are not checked on anyone's behalf
        key = 'prepchk_' + content_hash([me, evidence_id, delivery.revision])[:28]
        existing = tx.get(ctx.tenant_id, PREPARED, key)
        if existing is not None:
            return existing.state
        task = {'site_id': site_id, 'operation': 'check_gaps', 'dataset_ids': [evidence_id]}
        if self.p.workspace_tasks.compute(ctx, task)['data'].get('expectation_basis') != 'approved_specifications':
            return None  # nothing is approved for this site, so there is nothing to check against
        result = self.p.workspace_tasks.execute(ctx, task)  # saved, so that a request can cite it
        data, draft = result['data'], result['data'].get('draft_request')
        missing = [' '.join(str(x) for x in (gap.get('parameter') or gap.get('document_kind'), f"for {gap['batch']}" if gap.get('batch') else '') if x)
                   for gap in data.get('gaps') or []]
        state = {'id': key, 'owner_id': me, 'site_id': site_id, 'delivery_id': evidence_id, 'delivery_revision': delivery.revision,
                 'delivery_name': meta.get('delivery_name') or meta.get('cmo') or 'Delivery', 'partner': meta.get('cmo'),
                 'result_id': result['id'], 'requirements_checked': data.get('requirements_checked') or 0,
                 'gap_count': data.get('gap_count') or 0, 'missing': missing[:6],
                 'draft': {'title': draft['title'], 'description': '\n'.join([draft['description'], *(f'- {q}' for q in draft.get('questions') or [])])[:2000]} if draft else None,
                 'prepared_at': iso(utc_now())}
        with self.p.store.transaction(ctx.actor_id) as wtx:
            if wtx.get(ctx.tenant_id, PREPARED, key) is None:
                wtx.put(ctx.tenant_id, PREPARED, key, state, expected_revision=None, action='prepare_delivery_check')
        return state

    def _prepared(self, ctx, me, site_id, since, names) -> Iterator[Item]:
        self.p.assistant_routines._current_owner(ctx, site_id)
        tx = self.p.store.read()
        fields = ('delivery_id', 'delivery_revision', 'delivery_name', 'partner', 'result_id', 'requirements_checked', 'gap_count',
                  'missing', 'draft', 'prepared_at')
        rows = tx.select(ctx.tenant_id, PREPARED, fields, where={'owner_id': me, 'site_id': site_id}, limit=10)
        if not rows:
            return
        current = {d['id']: d['revision'] for d in tx.select(ctx.tenant_id, 'evidence', ids=[r['delivery_id'] for r in rows])}
        sent = [r.get('request_key') or '' for r in tx.select(ctx.tenant_id, 'assistant_work_request', ('request_key',),
                                                               where={'site_id': site_id, 'requested_by': me}, limit=200)]
        for r in rows:
            if current.get(r['delivery_id']) != r['delivery_revision']:
                continue  # the delivery changed after this check; it no longer describes what is there
            name = f"{r['delivery_name']} from {r['partner']}" if r.get('partner') and r['partner'] != r['delivery_name'] else r['delivery_name']
            checked = _count(r['requirements_checked'], 'approved requirement')
            href = f"/workbench/?datasets={r['delivery_id']}"
            if r['gap_count'] and r.get('draft') and not any(k.startswith(f"result:{r['result_id']}:") for k in sent):
                shown = ', '.join(r.get('missing') or [])
                more = r['gap_count'] - len(r.get('missing') or [])
                yield 'needs_you', _item(
                    'missing_evidence', r['id'], f"{name}: {_count(r['gap_count'], 'required item')} not in this delivery", at=r['prepared_at'], href=href,
                    detail=f"Checked against {checked} when it was published. Missing: {shown}{f' and {more} more' if more > 0 else ''}. "
                           'A request is drafted; choose who to ask.',
                    action={'type': 'send_request', 'result_id': r['result_id'], **r['draft']})
            elif not r['gap_count'] and r['prepared_at'] >= since:
                yield 'done', _item('missing_evidence', r['id'], f'Checked {name} against {checked}: nothing missing', at=r['prepared_at'], href=href,
                                    detail='Checked when it was published. This covers the delivery only, not other systems.')

    # --- the assistant: questions it asked, work it is doing, answers it finished ------------------------------
    def _assistant(self, ctx, me, site_id, since, names) -> Iterator[Item]:
        if not self.p.identity.check(ctx, 'propose', 'physical_analysis_plan', site_id=site_id):
            return
        tx = self.p.store.read()
        threads = {c['id']: c for c in tx.select(ctx.tenant_id, 'engineering_conversation', ('title', 'turn_ids', 'archived'),
                                                 where={'owner_id': ctx.actor_id, 'site_id': site_id}, limit=12)
                   if c.get('turn_ids') and not c.get('archived')}
        latest = {c['turn_ids'][-1]: c for c in threads.values()}
        # Only the latest turn of each recent conversation, and only its status and questions: never its transcript.
        for turn in tx.select(ctx.tenant_id, 'engineering_chat_turn', ('status', 'questions', 'created_at'), ids=list(latest)):
            thread = latest[turn['id']]
            href, title = f"/home/?conversation={thread['id']}", thread.get('title') or 'Conversation'
            if turn['status'] == 'needs_information':
                questions = [q for q in turn.get('questions') or [] if isinstance(q, str) and q.strip()][:4]
                yield 'needs_you', _item('question', turn['id'], f"The assistant asks: {questions[0] if questions else 'for more information'}",
                                         detail=f'It needs this to continue “{_clip(title, 120)}”.', by='assistant', at=turn['updated_at'], href=href,
                                         action={'type': 'answer', 'conversation_id': thread['id'], 'revision': thread['revision'],
                                                 'questions': questions})
            elif turn['status'] in ('queued', 'running'):
                yield 'in_progress', _item('assistant', turn['id'], f'The assistant is working on: {title}', by='assistant',
                                           at=turn.get('created_at') or turn['updated_at'], href=href)
            elif turn['status'] in ('blocked', 'agent_unavailable'):
                yield 'needs_you', _item('assistant', turn['id'], f'The assistant could not finish: {title}', by='assistant',
                                         detail='Open the conversation to see why, then try again or change the request.',
                                         at=turn['updated_at'], href=href)
            elif turn['status'] == 'completed' and turn['updated_at'] >= since:
                yield 'done', _item('assistant', turn['id'], f'The assistant answered: {title}', by='assistant', at=turn['updated_at'], href=href)

    # --- signals ---------------------------------------------------------------------------------------------
    def _signals(self, ctx, me, site_id, since, names) -> Iterator[Item]:
        if ctx.actor_kind != 'person':
            return
        fields = ('site_id', 'severity', 'rule', 'status', 'subject', 'occurrences', 'last_at', 'triage', 'kind',
                  'evidence_refs', 'observations')  # the last two only decide access; they are not returned
        for s in self.p.store.read().select(ctx.tenant_id, 'deviation_signal', fields, where={'site_id': site_id, 'status': 'open'}, limit=50):
            state = {**s, 'signal_id': s['id']}
            # A signal needs a person who may decide it and can read every source it rests on.
            if not self.p.identity.check(ctx, 'propose', 'deviation_signal', s['id'], site_id=site_id) or not self.p.signals._readable(ctx, state):
                continue
            subject = s.get('subject') or {}
            about = ' '.join(str(subject.get(k) or '') for k in ('kind', 'id')).strip()
            triage = (s.get('triage') or {}).get('status')
            detail = ' · '.join(x for x in (
                about, SEVERITY_WORDS.get(s['severity'], s['severity']),
                f"seen {_count(int(s.get('occurrences') or 1), 'time')}",
                'the assistant’s triage is ready' if triage == 'ready' else 'the assistant is triaging it' if triage == 'running' else '') if x)
            yield 'needs_you', _item('signal', s['id'], s.get('rule') or 'A signal needs a decision', detail=detail + '. A signal is for review, not a confirmed deviation.',
                                     at=s.get('last_at') or s['updated_at'], href=f"/signals/?id={s['id']}", severity=s['severity'],
                                     action={'type': 'acknowledge', 'signal_id': s['id']})

    # --- quality events --------------------------------------------------------------------------------------
    def _quality(self, ctx, me, site_id, since, names) -> Iterator[Item]:
        fields = ('title', 'owner_id', 'qa_reviewer_id', 'workflow.state', 'workflow.requests')
        for c in self.p.store.read().select(ctx.tenant_id, 'case', fields, where={'site_id': site_id}, limit=200):
            state = c.get('workflow.state')
            if not state or not self.p.identity.check(ctx, 'read', 'case', c['id'], site_id=site_id):
                continue
            href, title = f"/quality/?case={c['id']}", c.get('title') or c['id']
            waits_on, doing = QUALITY_WAITS.get(state, (None, ''))
            if waits_on and c.get(waits_on) == me:
                yield 'needs_you', _item('quality', c['id'], f'{title}: {doing}', at=c['updated_at'], href=href,
                                         detail=f"Quality event {c['id']}.")
            elif state == 'qa_review' and c.get('owner_id') == me:
                yield 'in_progress', _item('quality', c['id'], f"With {names(c.get('qa_reviewer_id'))} for QA review: {title}", at=c['updated_at'], href=href)
            for request in c.get('workflow.requests') or []:
                if request.get('owner_id') == me and request.get('status') == 'open':
                    yield 'needs_you', _item('quality', f"{c['id']}:{request.get('id')}", f"Evidence requested for {title}", href=href,
                                             detail=request.get('description') or '', at=c['updated_at'])

    # --- delivery checks -------------------------------------------------------------------------------------
    def _deliveries(self, ctx, me, site_id, since, names) -> Iterator[Item]:
        # Delivery records are organization-wide: a site-restricted account cannot open them, so none are listed.
        if self.deliveries is None or not ctx.roles or ctx.site_ids or not self.p.identity.check(ctx, 'read', 'cmo_delivery'):
            return
        sample_marker = ' · demo '   # sample deliveries a person opened while exploring are not their own work
        for r in self.deliveries(ctx.tenant_id):
            if sample_marker in r['cmo'] and not ctx.tenant_id.startswith('demo_'):
                continue
            partner = r['cmo'].split(sample_marker)[0]
            name = f"{r['delivery_name']} from {partner}" if r.get('delivery_name') else f'Delivery from {partner}'
            href = f"/cmo/?run={r['id']}"
            waiting = [_count(r['needs_review'], 'value') if r['needs_review'] else '', _count(r['open_issues'], 'issue') if r['open_issues'] else '',
                       _count(r['unconfirmed_layouts'], 'file layout') if r['unconfirmed_layouts'] else '']
            waiting = [w for w in waiting if w]
            if r['status'] in ('queued', 'running'):
                yield 'in_progress', _item('delivery', r['id'], f'Checking {name}', at=r['started_at'], href=href,
                                           detail='Every value is being read and matched to its source.')
            elif r['status'] == 'complete' and waiting:
                yield 'needs_you', _item('delivery', r['id'], f"{name}: {' and '.join(waiting)} to check", at=r.get('completed_at') or r['started_at'],
                                         href=href, detail='Nothing from this delivery is treated as verified until these are decided.')
            elif r['status'] in ('failed', 'interrupted') and (r['started_at'] or '') >= since:
                yield 'needs_you', _item('delivery', r['id'], f'The check of {name} did not finish', at=r['started_at'], href=href,
                                         detail='No partial results were accepted. Open it to start the check again.')
            elif r['status'] == 'complete' and (r.get('completed_at') or '') >= since:
                yield 'done', _item('delivery', r['id'], f'Checked {name}', at=r['completed_at'], href=href,
                                    detail='No value, issue or file layout is waiting for a decision.')

    # --- who can be asked ------------------------------------------------------------------------------------
    def people(self, ctx, site_id: str) -> list[dict[str, str]]:
        """Colleagues who can receive a request at this site, by the name they are known by here."""
        self.p.assistant_routines._current_owner(ctx, site_id)
        tx, me = self.p.store.read(), principal(ctx)
        actors = {r['actor_id'] for r in tx.select(ctx.tenant_id, 'role_assignment', ('actor_id', 'actor_kind', 'site_id', 'revoked_at'), limit=2000)
                  if r.get('actor_id') and not r.get('revoked_at') and (r.get('actor_kind') or 'person') == 'person' and r.get('site_id') in (None, site_id)}
        names = Names(self.p.store, ctx.tenant_id, me)
        out = []
        for actor in sorted(actors - {me})[:200]:
            person = self.p.identity.context_for(ctx.tenant_id, actor)
            if self.p.identity.check(person, 'read', 'assistant_work_request', site_id=site_id):
                out.append({'id': actor, 'label': names(actor)})
        return sorted(out, key=lambda person: person['label'].lower())


class Names:
    """A person as their colleagues know them: their email here, else their sign-in name. Looked up once each."""

    def __init__(self, store, tenant_id: str, me: str) -> None:
        self.store, self.tenant_id, self.known = store, tenant_id, {me: 'you'}

    def __call__(self, actor: str | None) -> str:
        if not actor:
            return 'someone'
        if actor.startswith('agent:'):
            return 'the assistant'
        if actor not in self.known:
            rows = self.store.read().select(self.tenant_id, 'organization_member', ('email',), ids=[actor])
            self.known[actor] = (rows[0].get('email') if rows else None) or actor
        return self.known[actor]


def install_worklist_api(p, app, ctx_dep) -> None:
    from fastapi import Depends

    @app.get('/v1/worklist')
    def worklist(site_id: str, ctx=Depends(ctx_dep)):
        """What needs this person, what is in progress for them and what was recently finished, across the product."""
        return p.worklist.read(ctx, site_id)

    @app.get('/v1/worklist/people')
    def people(site_id: str, ctx=Depends(ctx_dep)):
        """Colleagues who can be asked for something at this site."""
        return {'people': p.worklist.people(ctx, site_id)}
