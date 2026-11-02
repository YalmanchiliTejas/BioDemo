"""Strict descriptive scoring; narrative risks require explicit human review."""
import math


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def score_case(reference, submission, review=None):
    """No LLM-as-judge, implicit zero error, or fabricated human timing.

    Missing predictions remain coverage failures. Facts require source citations;
    source support of those citations is separately reviewed, not inferred here.
    """
    if submission.get('case_id') != reference['case_id']:
        raise ValueError('Submission case does not match evaluator reference')
    facts = submission.get('facts', [])
    predictions = submission.get('predictions', [])
    risks = submission.get('risks', [])
    for label, rows in [('fact', facts), ('prediction', predictions), ('risk', risks)]:
        if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get('id'), str) for r in rows):
            raise ValueError(f'Malformed {label} rows')
        if len({r['id'] for r in rows}) != len(rows):
            raise ValueError(f'Duplicate {label} IDs')
    known = {r['id']: r for r in reference['facts']}
    if any(r['id'] not in known for r in facts):
        raise ValueError('Unknown fact ID; additional findings belong in narrative')
    fact_results = []
    supplied = {r['id']: r for r in facts}
    for key, target in known.items():
        row = supplied.get(key, {})
        value = row.get('value')
        expected = target['value']
        equal = (finite(value) and abs(value - expected) <= target.get('tolerance', 0)) if finite(expected) else type(value) is type(expected) and value == expected
        fact_results.append({'id': key, 'correct': bool(equal and row.get('unit') == target['unit'] and row.get('citations')),
                             'submitted': key in supplied})
    targets = {r['id']: r for r in reference['predictions']}
    if any(r['id'] not in targets for r in predictions):
        raise ValueError('Unknown prediction ID')
    prediction_results = []
    for row in predictions:
        target = targets[row['id']]
        if not finite(row.get('value')) or row.get('unit') != target['unit']:
            raise ValueError('Prediction must be finite and use the declared unit')
        error = row['value'] - target['value']
        prediction_results.append({'id': row['id'], 'metric': target['metric'], 'unit': target['unit'],
                                   'predicted': row['value'], 'observed': target['value'], 'error': error,
                                   'absolute_error': abs(error),
                                   'relative_error': error / target['value'] if target['value'] else None})
    # Never pool kLa, raw gas readings, and empirical protein endpoints.
    metrics = {}
    for metric in sorted({r['metric'] for r in reference['predictions']}):
        rows = [r for r in prediction_results if r['metric'] == metric]
        total = sum(r['metric'] == metric for r in reference['predictions'])
        metrics[metric] = {'unit': next(r['unit'] for r in reference['predictions'] if r['metric'] == metric),
                           'expected': total, 'submitted': len(rows), 'coverage': len(rows) / total,
                           'mae': sum(r['absolute_error'] for r in rows) / len(rows) if rows else None,
                           'rmse': math.sqrt(sum(r['error'] ** 2 for r in rows) / len(rows)) if rows else None,
                           'complete': len(rows) == total}
    risk_scores = {'status': 'awaiting_human_review', 'precision': None, 'recall': None}
    if review is not None:
        if review.get('case_id') != reference['case_id'] or not review.get('reviewer'):
            raise ValueError('Named reviewer and matching case required')
        judgments = review.get('risks', [])
        if len({r['submission_id'] for r in judgments}) != len(judgments) or {r['submission_id'] for r in judgments} != {r['id'] for r in risks}:
            raise ValueError('Review must adjudicate every submitted risk exactly once')
        reference_ids = {r['id'] for r in reference['risks']}
        found = set()
        false_positive = duplicate = out_of_scope = 0
        for row in judgments:
            if not row.get('rationale'):
                raise ValueError('Review rationale required')
            if row['label'] == 'reference':
                key = row.get('reference_id')
                if key not in reference_ids:
                    raise ValueError('Unknown reference risk')
                if key in found:
                    duplicate += 1
                else:
                    found.add(key)
            elif row['label'] == 'unsupported':
                false_positive += 1
            elif row['label'] == 'valid_out_of_scope':
                out_of_scope += 1
            else:
                raise ValueError('Unknown review label')
        denominator = len(found) + false_positive + duplicate
        risk_scores = {'status': 'human_reviewed', 'reviewer': review['reviewer'],
                       'true_positive': len(found), 'false_positive': false_positive, 'duplicate': duplicate,
                       'valid_out_of_scope': out_of_scope,
                       'precision': len(found) / denominator if denominator else None,
                       'recall': len(found) / len(reference_ids) if reference_ids else None,
                       'reference_risks': len(reference_ids)}
    timing = submission.get('timing', {})
    for key in ('preparation_minutes', 'configuration_minutes', 'review_minutes', 'correction_minutes', 'elapsed_seconds', 'provider_cost_usd'):
        value = timing.get(key)
        if value is not None and (not finite(value) or value < 0):
            raise ValueError('Timing/cost must be nonnegative measurements or null')
    human = [timing.get(k) for k in ('preparation_minutes', 'configuration_minutes', 'review_minutes', 'correction_minutes')]
    return {'case_id': reference['case_id'], 'classification': 'descriptive_retrospective_task_score',
            'fact_accuracy': sum(r['correct'] for r in fact_results) / len(known) if known else None,
            'fact_results': fact_results, 'citation_support': 'not_automatically_adjudicated',
            'prediction_metrics': metrics, 'prediction_results': prediction_results, 'risk_scores': risk_scores,
            'observed_human_minutes': sum(human) if all(v is not None for v in human) else None,
            'timing': timing, 'time_saved_minutes': None,
            'manufacturing_efficacy_established': False}
