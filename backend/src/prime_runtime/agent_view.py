"""Compact bridge responses for the model context.

Each response the model reads stays in its context for every later turn, so
echoed report sections and fixed policy fields are paid for repeatedly. The
bridge keeps full results (bridge.result, checkpoints and logs); this view
only changes what is returned over HTTP. Actionable fields (issues, missing
IDs, failing checks, next steps) are kept.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

BUDGET_FIELDS = ('shared_tool_calls_remaining', 'specialist_calls_available', 'lead_reserved_calls',
                 'active_tool_limit', 'elapsed_seconds', 'remaining_seconds', 'phase', 'caller_role')
FAILING_CHECK_LIMIT = 25


def compact_budget(budget: Any) -> Any:
    if not isinstance(budget, dict):
        return budget
    view = {k: budget[k] for k in BUDGET_FIELDS if k in budget}
    for key in ('elapsed_seconds', 'remaining_seconds'):
        if isinstance(view.get(key), float):
            view[key] = round(view[key], 1)
    return view


def _status_counts(items: Any) -> Any:
    if not isinstance(items, list):
        return items
    return {'count': len(items), 'by_status': dict(Counter(str(i.get('status')) for i in items if isinstance(i, dict)))}


def compact_claims(claims: Any) -> Any:
    """Keep failing claim receipts only; passing receipts echo the submitted ledger."""
    if not isinstance(claims, dict) or not isinstance(claims.get('claims'), list):
        return claims
    receipts = claims['claims']
    failing = [{k: c.get(k) for k in ('claim_id', 'issues', 'unlinked_numeric_literals') if c.get(k)}
               for c in receipts if isinstance(c, dict) and c.get('issues')]
    return {**{k: v for k, v in claims.items() if k != 'claims'},
            'claim_count': len(receipts), 'failing_claims': failing}


def compact_review(review: Any) -> Any:
    if not isinstance(review, dict):
        return review
    view = dict(review)
    # Coverage and candidate reviews echo the submitted report; gaps are already
    # reported through missing_unit_ids and issues.
    for key in ('coverage', 'candidate_reviews'):
        if key in view:
            view[key] = _status_counts(view[key])
    if 'claim_verification' in view:
        view['claim_verification'] = compact_claims(view['claim_verification'])
    if 'budget' in view:
        view['budget'] = compact_budget(view['budget'])
    return view


def compact_verification(verification: Any) -> Any:
    if not isinstance(verification, dict):
        return verification
    view = dict(verification)
    checks = view.pop('evidence_checks', None)
    if isinstance(checks, dict):
        failing = {i: c for i, c in checks.items() if not (isinstance(c, dict) and c.get('value_matches') is True)}
        view['evidence_check_count'] = len(checks)
        view['failing_evidence_checks'] = dict(list(failing.items())[:FAILING_CHECK_LIMIT])
        view['failing_evidence_check_count'] = len(failing)
    if 'claim_verification' in view:
        view['claim_verification'] = compact_claims(view['claim_verification'])
    return view


def submission_receipt(output: dict[str, Any]) -> dict[str, Any]:
    """The persisted final investigation stays with the host; the model gets a receipt."""
    review = output.get('investigation_review') or {}
    verification = output.get('verification') or {}
    return {
        'status': 'final_report_persisted', 'final_report_submitted': True,
        **{k: output.get(k) for k in ('report_type', 'report_status', 'investigation_status', 'severity',
                                      'source_verification_status', 'scientific_validation_status',
                                      'continue_investigation')},
        'issues': review.get('issues', []),
        'verification_status': verification.get('status'),
        'pending_source_review_count': verification.get('pending_source_review_count'),
        'cited_evidence_count': len(output.get('evidence_ids') or []),
        'pending_evidence_request_count': len(output.get('pending_evidence_requests') or []),
        'note': 'The full persisted investigation is held by the host. Do not resubmit.',
    }


def agent_view(path: str, result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    if path == '/report' and 'workflow' in result:
        return submission_receipt(result)
    view = dict(result)
    if path in ('/validate-report', '/report', '/subreport'):
        view = compact_review(view) if 'screened_unit_count' in view else view
        for key in ('investigation_review', 'review'):
            if key in view:
                view[key] = compact_review(view[key])
        if 'verification' in view:
            view['verification'] = compact_verification(view['verification'])
    if 'budget' in view:
        view['budget'] = compact_budget(view['budget'])
    for key in ('queue', 'checkpoint', 'work_queue'):
        if isinstance(view.get(key), dict) and 'budget' in view[key]:
            view[key] = {**view[key], 'budget': compact_budget(view[key]['budget'])}
    return view
