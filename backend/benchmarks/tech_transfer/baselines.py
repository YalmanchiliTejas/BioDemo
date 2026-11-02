"""Existing model/empirical numerical components, never completed agent trials."""
from bisect import bisect_left
from pathlib import Path
import argparse
import csv
import json
from time import perf_counter

from .prepare import validate, dump, sha


def interpolate(rows, time_h):
    times = [r['time_h'] for r in rows]
    if not times or time_h < times[0] or time_h > times[-1]:
        raise ValueError('Donor interpolation cannot extrapolate')
    index = bisect_left(times, time_h)
    if times[index] == time_h:
        return rows[index]['carbon_dioxide']
    lo, hi = rows[index - 1], rows[index]
    weight = (time_h - lo['time_h']) / (hi['time_h'] - lo['time_h'])
    return lo['carbon_dioxide'] * (1 - weight) + hi['carbon_dioxide'] * weight


def predict(public, case_dir, query=None):
    """Only staged covariates; this function never reads evaluator references."""
    predictions = []
    case_id = public['case_id']
    if case_id.startswith('SC-'):
        from src.lifesci.fermentation.model import transfer_point
        if query is None or query['case_id'] != case_id:
            raise ValueError('Matching phase2 characterization covariates required')
        evidence = public['evidence']
        project = {'equipment': evidence['S1']['equipment'], 'calibration': evidence['S2']['donor_calibration']}
        point = transfer_point(project, query['working_volume_l'], query['agitation_rpm'],
                               query['airflow_l_min'] / query['working_volume_l'], gas_exponent=.5)
        predictions = [{'id': 'receiver_water_kla', 'value': point['predicted_kla_h_inv'], 'unit': 'h^-1'}]
        method = 'existing_source_only_water_kla_correlation; beta0.5 assumption; unvalidated geometry scaling'
    elif case_id.startswith('PC-'):
        value = public['evidence']['P2']['donor'][0]['outcomes']['volumetric_enzyme_production']['value']
        predictions = [{'id': 'receiver_enzyme_empirical', 'value': value, 'unit': 'mg/L'}]
        method = 'constant_donor_endpoint_empirical; no mechanistic_productivity_model'
    elif case_id == 'TC-1-to-250L':
        with (Path(case_dir) / 'donor-gas.csv').open() as stream:
            rows = [{k: float(row[k]) for k in ('time_h', 'carbon_dioxide')} for row in csv.DictReader(stream)]
        predictions = [{'id': r['id'], 'value': interpolate(rows, r['time_h']), 'unit': r['unit']}
                       for r in public['prediction_requests']]
        method = 'donor_elapsed_time_linear_interpolation_empirical; no mechanistic_productivity_model'
    else:
        raise ValueError('Unknown transfer case')
    return {'case_id': case_id, 'arm': 'model_component_only', 'status': 'deterministic_component_executed',
            'method': method, 'predictions': predictions, 'facts': [], 'risks': [],
            'model_requests': 0, 'human_time_minutes': None,
            'comparison_boundary': 'Not a complete conventional workflow or an agent result; no labor-savings claim.'}


def run(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    manifest = validate(root)
    if output.exists() or output.is_relative_to(root):
        raise ValueError('Use a fresh directory outside the frozen study')
    from .score import score_case
    references = {r['case_id']: r for r in json.loads((root / 'evaluator-only/references.json').read_text())}
    records = []
    for case_id in manifest['case_ids']:
        case_dir = root / 'agent-input' / case_id
        public = json.loads((case_dir / 'evidence.json').read_text())
        query_path = root / 'phase2-input' / case_id / 'characterization-query.json'
        query = json.loads(query_path.read_text()) if query_path.exists() else None
        start = perf_counter()
        submission = predict(public, case_dir, query)
        elapsed = perf_counter() - start
        # Prediction commitment precedes loading this case's values into scorer.
        submission['timing'] = {'elapsed_seconds': elapsed, 'provider_cost_usd': 0}
        dump(output / case_id / 'prediction.json', submission)
        scores = score_case(references[case_id], submission)
        dump(output / case_id / 'score.json', scores)
        records.append({'case_id': case_id, 'prediction_sha256': sha(output / case_id / 'prediction.json'),
                        'prediction_metrics': scores['prediction_metrics'], 'numerical_component_elapsed_seconds': elapsed})
    dump(output / 'receipt.json', {'classification': 'deterministic_baseline_smoke_check_not_agent_evaluation',
          'freeze_manifest_sha256': sha(root / 'freeze-manifest.json'), 'model_requests': 0,
          'provider_cost_usd': 0, 'human_effort_measured': False, 'records': records})
    return {'baseline_components': len(records), 'model_requests': 0, 'output': str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.study, args.output), indent=2))


if __name__ == '__main__':
    main()
