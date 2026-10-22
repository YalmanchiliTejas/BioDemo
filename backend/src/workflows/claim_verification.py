"""Claim-local automated checks. Source support semantics still require review.

No runtime report can promote its own causal hypothesis to verified causation.
Independent reviews belong to the hash-bound evaluation layer.
"""
import math
import re

CLASSES = {'observed', 'derived', 'association', 'hypothesis', 'verified_cause'}
NUMBER = re.compile(r'(?<![\w./:-])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?(?![\w/:-]|\.\d)')


def displayed_metric_values(claim, metrics):
    """Only explicitly declared rounding of referenced computed values."""
    precision = claim.get('display_decimals')
    if precision is None:
        return []
    if type(precision) is not int or not 0 <= precision <= 12:
        raise ValueError('claim display_decimals must be an integer from 0 to 12')
    return [round(metrics[i]['value'], precision) for i in claim.get('metric_ids', [])
            if i in metrics and type(metrics[i].get('value')) in (int, float)
            and math.isfinite(metrics[i]['value'])]


def check_claims(report, rows, metrics=()):
    by_id = {r['id']: r for r in rows}
    by_metric = {m['metric_id']: m for m in metrics}
    claims = report.get('claims')
    if claims is None:
        return {'status': 'evaluation_unavailable', 'claims': [],
                'issues': [{'code': 'claim_ledger_missing'}], 'semantic_support': 'not_evaluated'}
    if not isinstance(claims, list):
        raise ValueError('claims must be a list')
    issues, receipts, seen = [], [], set()
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError('claims must be objects')
        cid = claim.get('claim_id')
        if not cid or cid in seen:
            raise ValueError('claim_id must be nonempty and unique')
        seen.add(cid)
        classification = claim.get('classification')
        problems = []
        if classification not in CLASSES:
            problems.append('classification_missing_or_invalid')
        if classification == 'verified_cause' or claim.get('root_cause_confirmed'):
            problems.append('unsupported_verified_cause')
        for field in ('statement', 'uncertainty', 'missing_information', 'temporal_basis'):
            value=claim.get(field)
            valid=isinstance(value,str) and bool(value.strip())
            if field in {'uncertainty','missing_information'} and isinstance(value,list):
                valid=bool(value) and all(isinstance(v,str) and bool(v.strip()) for v in value)
            if not valid:
                problems.append(field + '_missing')
        links = claim.get('evidence_ids', [])
        counter = claim.get('contradicting_evidence_ids', [])
        metric_ids = claim.get('metric_ids', [])
        if not isinstance(links, list) or not links or not set(links) <= by_id.keys():
            problems.append('supporting_source_unavailable')
            links = []
        if not isinstance(counter, list) or not set(counter) <= by_id.keys():
            problems.append('contradicting_source_unavailable')
            counter = []
        if not counter and not str(claim.get('counterevidence_search', '')).strip():
            problems.append('counterevidence_search_missing')
        if not isinstance(metric_ids, list) or not set(metric_ids) <= by_metric.keys():
            problems.append('metric_unavailable')
            metric_ids = []
        if classification == 'derived' and not metric_ids:
            problems.append('derived_calculation_missing')
        if claim.get('confidence') is not None:
            problems.append('uncalibrated_probability')
        # Numbers must come from this claim's evidence/metrics, never some other
        # sentence's unrelated citation. This is a necessary, not sufficient test.
        allowed = []
        for identifier in links + counter:
            for field in ('value_number', 'time_value'):
                value = by_id[identifier].get(field)
                if type(value) in (int, float) and math.isfinite(value):
                    allowed.extend([value, *(round(value, d) for d in range(-6, 7))])
        for identifier in metric_ids:
            allowed.extend(by_metric[identifier].get(k) for k in ('value', 'display_value','claimed_value'))
        allowed.extend(displayed_metric_values(claim, by_metric))
        unlinked = [m.group() for m in NUMBER.finditer(str(claim.get('statement', '')))
                    if not any(type(v) in (int, float) and math.isclose(float(m.group()), v, rel_tol=1e-6, abs_tol=0)
                               for v in allowed)]
        if unlinked:
            problems.append('claim_numeric_literals_unlinked')
        if classification == 'observed' and re.search(r'\b(caused|proves?|confirmed cause|therefore)\b', str(claim.get('statement')), re.I):
            problems.append('causal_language_in_observation')
        receipts.append({**claim, 'sources': [{'evidence_id': i, 'location': by_id[i].get('source_ref'),
                         'unit': by_id[i].get('unit'), 'time_value': by_id[i].get('time_value'),
                         'time_basis': by_id[i].get('time_basis')} for i in links + counter],
                         'unlinked_numeric_literals': unlinked, 'issues': problems,
                         'semantic_support': 'independent_review_pending'})
        issues.extend({'code': code, 'claim_id': cid} for code in problems)
    if not claims:
        issues.append({'code': 'claim_ledger_empty'})
    return {'status': 'automated_checks_failed' if issues else 'technical_checks_passed',
            'claims': receipts, 'issues': issues, 'semantic_support': 'independent_review_pending',
            'limitation': 'Location/value checks cannot establish that prose is entailed by a source or prove causation.'}
