"""Deterministic, source-derived answers for the saved synthetic assay demo.

This deliberately narrow route performs no inference and creates no formal
deviation, approval or action. It never reads an earlier assistant's answer.
"""
import csv
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import io
import math
import re

from ..evidence import EvidenceRef

KIND = 'assistant_demo_deviations'
METHOD = 'synthetic-assay-comparison:v1'
FILES = re.compile(r'(?:^|\n)([A-Za-z0-9_. -]{1,100}\.csv)\r?\n')
NEXT_STEPS = [
    'Confirm the applicable specification, units and actual test timestamps against the source records.',
    'Review each flagged assay and its original laboratory record; check method, calibration and any permitted confirmation testing.',
    'Prepare deviation investigation drafts for the flagged results in the owning quality system, subject to reviewer authorization.',
    'Collect batch, equipment and process evidence to investigate cause. No root cause is established by these assay values alone.',
]


def _number(value):
    try:
        number = Decimal(str(value).strip().replace(',', '.'))
        return number if number.is_finite() and math.isfinite(float(number)) else None
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _time(value):
    try:
        result = datetime.fromisoformat(value)
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def _tables(text):
    matches = list(FILES.finditer(text))
    if len(matches) > 8:
        raise ValueError('Too many source tables for the bounded assay demo')
    result = []
    for i, match in enumerate(matches):
        raw = text[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)].strip()
        reader = csv.reader(io.StringIO(raw), strict=True)
        headers = next(reader, [])
        if len(set(headers)) != len(headers) or len(headers) > 64:
            raise ValueError('Ambiguous CSV headers; source review required')
        rows, previous = [], reader.line_num
        for values in reader:
            line, previous = previous + 1, reader.line_num
            if not any(v.strip() for v in values):
                continue
            if len(values) != len(headers) or len(rows) >= 1000:
                raise ValueError('Malformed or oversized CSV; source review required')
            rows.append({'line': line, 'values': dict(zip(headers, values))})
        result.append({'name': match[1], 'headers': headers, 'rows': rows})
    return result


def calculate(text):
    """Recalculate from original CSV rows, including inclusive bounds and effective dates."""
    tables = _tables(text)
    assays = [t for t in tables if {'result_id', 'Result (mg/L)'} <= set(t['headers'])]
    specs = [t for t in tables if {'revision', 'Lower (mg/L)', 'Upper (mg/L)'} <= set(t['headers'])]
    if len(assays) != 1 or len(specs) != 1:
        raise ValueError('A unique assay table and specification table are required')
    assay, spec = assays[0], specs[0]
    if not assay['rows']:
        raise ValueError('The assay table contains no source rows')
    rows, issues = [], []
    counts = Counter(r['values'].get('result_id', '').strip() for r in assay['rows'])
    for item in assay['rows']:
        value = item['values']
        observed = _number(value.get('Result (mg/L)'))
        available = _time(value.get('available_at'))
        eligible = []
        for candidate in spec['rows']:
            fields = candidate['values']
            effective = _time(fields.get('effective_at'))
            if available and effective and effective <= available:
                eligible.append((effective, candidate))
            elif not available and fields.get('revision') == 'current':
                eligible.append((datetime.min.replace(tzinfo=timezone.utc), candidate))
        latest = max((t for t, _ in eligible), default=None)
        selected = [s for t, s in eligible if t == latest]
        bounds = selected[0] if len(selected) == 1 else None
        lower = _number(bounds['values'].get('Lower (mg/L)')) if bounds else None
        upper = _number(bounds['values'].get('Upper (mg/L)')) if bounds else None
        ident = value.get('result_id', '').strip()
        duplicate = not ident or counts[ident] > 1
        invalid_time = bool(value.get('available_at')) and available is None
        valid = not duplicate and not invalid_time and observed is not None and lower is not None and upper is not None and lower <= upper
        status = 'below_limit' if valid and observed < lower else 'above_limit' if valid and observed > upper else 'within_limits' if valid else 'needs_source_review'
        if not valid:
            issues.append(f'{ident or "Unnamed result"}: missing, duplicate or ambiguous source values/specification; no conclusion calculated.')
        rows.append({'result_id': ident, 'batch_id': value.get('batch_id'),
            'value': float(observed) if observed is not None else None, 'unit': 'mg/L',
            'lower': float(lower) if lower is not None else None, 'upper': float(upper) if upper is not None else None,
            'status': status, 'source': {'file': assay['name'], 'row': item['line']},
            'specification': {'file': spec['name'], 'row': bounds['line'] if bounds else None,
                'revision': bounds['values']['revision'] if bounds else None},
            'available_at': value.get('available_at'),
            'time_basis': 'availability_time_proxy' if available else 'current_label_only'})
    return {'rows': rows, 'issues': list(dict.fromkeys(issues)),
        'flagged_count': sum(r['status'] in ('below_limit', 'above_limit') for r in rows),
        'review_count': sum(r['status'] == 'needs_source_review' for r in rows),
        'assay_count': len(rows), 'bounds_inclusive': True,
        'timing_note': 'Latest means latest saved review, not latest manufacturing occurrence. Specification selection uses available_at as a test-time proxy when present; confirm actual test time. Missing time uses the source current label only.'}


class DemoAnswers:
    def __init__(self, conversations):
        self.service = conversations
        self.p = conversations.p

    def answer(self, ctx, thread, turn):
        text = turn['user_text'].strip().lower()
        if turn.get('origin') == 'background' or turn.get('display_context'):
            return None
        topic = bool(re.search(r'\b(deviations?|assays?)\b|out[- ]of[- ]spec', text))
        if not topic and len(thread['turn_ids']) > 1:
            previous = self.p.store.read().require(ctx.tenant_id, 'engineering_chat_turn', thread['turn_ids'][-2])
            topic = previous.state.get('response_mode') == 'deterministic_demo' and bool(re.search(r'\b(why|cause|next|explain|summari[sz]e)\b', text))
        if not topic or re.match(r'^(?:please\s+)?(?:open|create|submit|approve|release|reject|execute|close|send)\b', text):
            return None
        # Existing formal cases keep their regular evidence-based agent path unless
        # the person specifically asks to see synthetic/demo samples.
        formal = self.service.workspace.search(ctx, thread, kinds=['case'], limit=1)
        if formal['matching_count'] and not re.search(r'\b(demo|synthetic|sample)\b', text):
            return None
        candidates = []
        for rec in self.p.store.read().list(ctx.tenant_id, 'engineering_chat_turn'):
            original = rec.state.get('user_text', '')
            if rec.id == turn['id'] or not re.match(r'^Synthetic manufacturing evaluation\b', original) or 'Result (mg/L)' not in original:
                continue
            try:
                ref = self.service.workspace._authorize(ctx, thread, rec)
            except (PermissionError, ValueError, KeyError):
                continue
            candidates.append((rec.state.get('created_at', ''), rec.id, rec, ref))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        # An explicit saved-review label selects that example; no LLM resolves it.
        requested = re.search(r'\bdeviations-\d+\b', text)
        if requested:
            candidates = [c for c in candidates if re.search(r'\b' + re.escape(requested[0]) + r'\b', c[2].state['user_text'])]
            if not candidates:
                return None
        _, _, source, ref = candidates[0]
        original = source.state['user_text']
        label = re.search(r'\bdeviations-\d+\b', original)
        label = label[0] if label else 'Saved synthetic assay review'
        try:
            result = calculate(original)
        except (ValueError, csv.Error) as exc:
            result = {'rows': [], 'issues': [str(exc)], 'assay_count': 0,
                'flagged_count': 0, 'review_count': 0, 'source_unusable': True}
        result.update({'site_id': thread['site_id'], 'label': label, 'synthetic': True,
            'source_turn_id': source.id, 'source_conversation_id': source.state['conversation_id'],
            'source_saved_at': source.state.get('created_at'), 'source_refs': [ref],
            'next_steps': NEXT_STEPS, 'root_cause': 'Not established by the supplied assay records.',
            'manufacturing_action': 'Not performed', 'review_state': 'Unreviewed synthetic example',
            'method': METHOD, 'disclosure': 'Deterministic calculation from saved synthetic source CSVs. No LLM was called; this is not an agent accuracy evaluation.'})
        basis = [EvidenceRef(**ref), EvidenceRef(**turn['user_ref'])]
        self.p.identity.validate_refs(ctx, [r.to_dict() for r in basis])
        record = self.p.evidence.record_derived(ctx, KIND, result, inputs=basis,
            produced_by={'method': METHOD, 'actor_id': ctx.actor_id}, artifact_id=turn['id'] + '-assays')
        attached = self.p.store.read().require(ctx.tenant_id, 'engineering_chat_turn', turn['id']).state['artifacts']
        if not any(a['kind'] == KIND and a['id'] == record['id'] for a in attached):
            self.service._remember(ctx, turn, KIND, record, f'{label} · assay findings and next steps')
        if result.get('source_unusable'):
            reply = f'{label} is a saved synthetic example, but its source tables need review before any findings can be calculated. See the source issue below.'
        else:
            gaps = f" {result['review_count']} results need source review before comparison." if result['review_count'] else ''
            reply = f"In the saved synthetic review {label}, {result['flagged_count']} of {result['assay_count']} assay results fall outside the supplied specification.{gaps} See the flagged rows and next review steps below. Cause is not established; no manufacturing action has been performed."
        return {'reply': reply, 'questions': [], 'status': 'completed', 'response_mode': 'deterministic_demo',
            'answer_basis': [r.to_dict() for r in basis], 'system_message': None}
