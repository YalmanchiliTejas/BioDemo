"""Prepare a small immutable transfer study without inference or network access.

Original papers/workbooks contain receiving answers. Only allowlisted extracts
and donor CSVs enter agent-input; evaluator material is stored separately.
Filesystem separation here is preparation, not a sandbox for a future worker.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import shutil
import statistics
import tempfile

from openpyxl import load_workbook

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / 'docs/research/tech-transfer-data/paasikallio2017'
FERMENTATION = REPO / 'backend/src/lifesci/fermentation/data'
VERSION = 'measured-transfer-preparation-v1'
CHANNELS = ['time_h', 'nitrogen', 'oxygen', 'argon', 'carbon_dioxide', 'ethanol']
WORKBOOK_SHA = 'af7742d58df66fb46e1ca2e6af32a5adf793714e92e703af9aec3b78a63ed81a'
GAS_GRID_H = tuple(range(0, 169, 6))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=[*CHANNELS, 'source_sheet', 'source_row'])
        writer.writeheader()
        writer.writerows(rows)


def workbook_rows(path):
    if sha(path) != WORKBOOK_SHA:
        raise ValueError('Workbook differs from qualified source')
    book = load_workbook(path, read_only=True, data_only=False)
    result = {}
    try:
        for sheet in ('1 L culture', '250 L culture'):
            rows = []
            for index, cells in enumerate(book[sheet].iter_rows(min_col=1, max_col=6, values_only=True), 1):
                if not isinstance(cells[0], (int, float)) or isinstance(cells[0], bool):
                    continue
                if not all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) for v in cells):
                    raise ValueError(f'Incomplete/nonfinite measurement {sheet}!A{index}:F{index}')
                rows.append(dict(zip(CHANNELS, cells), source_sheet=sheet, source_row=index))
            if not rows or any(a['time_h'] >= b['time_h'] for a, b in zip(rows, rows[1:])):
                raise ValueError('Missing or unordered source observations')
            result[sheet] = rows
    finally:
        book.close()
    expected = {'1 L culture': 4389, '250 L culture': 3294}
    if any(len(result[k]) != n for k, n in expected.items()):
        raise ValueError('Source observation count changed')
    return result


def fact(key, value, unit, evidence, description):
    return {'id': key, 'value': value, 'unit': unit, 'tolerance': 1e-8,
            'evidence': evidence, 'description': description}


def risk(key, description, evidence):
    return {'id': key, 'description': description, 'evidence': evidence}


def packet(case_id, study, evidence, facts, risks, predictions, task):
    public = {'case_id': case_id, 'study': study, 'task': task, 'evidence': evidence,
              'fact_requests': [{'id': r['id'], 'request': r['description'], 'unit': r['unit']} for r in facts],
              'prediction_requests': [{k: v for k, v in r.items() if k in ('id', 'metric', 'unit', 'time_h', 'classification')} for r in predictions],
              'instruction': 'Use only staged evidence. Cite evidence IDs and JSON paths or CSV sheet/row. Distinguish measurements, calculations, assumptions and unknowns. Submit a transfer assessment, supported risks, characterization requests and predictions. A recommendation is not approval or execution. Do not retrieve full papers or future receiver data.'}
    private = {'case_id': case_id, 'study': study, 'facts': facts, 'risks': risks, 'predictions': predictions}
    return public, private


def sulfolobus(receiver, source, target):
    case_id = f'SC-2-to-{receiver}L'
    equipment = [{k: e[k] for k in ('working_volume_l', 'total_volume_l', 'manufacturer', 'model', 'impeller_type', 'blades_per_impeller', 'submerged_impellers', 'impeller_diameter_mm', 'impeller_blade_height_mm')}
                 for e in source['equipment'] if e['working_volume_l'] in (2, receiver)]
    evidence = {'S1': {'source': 'Rastadter2023 Methods2.1 and supplement TableS1; reviewed transcription', 'equipment': equipment},
                'S2': {'source': 'Rastadter2023 Table2 donor ring-sparger rows; reviewed transcription', 'donor_calibration': source['calibration']},
                'S3': {'source': 'Rastadter2023 Methods2.1.1', 'characterization': source['conditions']}}
    facts = [fact('receiver_working_volume', receiver, 'L', 'S1', 'Receiving working volume'),
             fact('receiver_total_volume', equipment[1]['total_volume_l'], 'L', 'S1', 'Receiving total vessel volume'),
             fact('receiver_impeller_diameter', equipment[1]['impeller_diameter_mm'], 'mm', 'S1', 'Receiving impeller diameter'),
             fact('receiver_impeller_count', equipment[1]['submerged_impellers'], 'count', 'S1', 'Receiving submerged impeller count'),
             fact('characterization_temperature', 75, 'degC', 'S3', 'Temperature of the supplied oxygen-transfer characterization'),
             fact('characterization_medium', 'deionized water', 'text', 'S3', 'Medium used for the supplied oxygen-transfer characterization')]
    risks = [risk('water_not_broth', 'Water kLa cannot certify oxygen capacity in consuming process broth.', 'S3'),
             risk('gas_exponent_unidentified', 'Two source ring points at one airflow do not identify gas-flow dependence.', 'S2'),
             risk('geometry_change', 'Impeller geometry/count change; copying rpm does not preserve power per volume.', 'S1'),
             risk('equipment_ratings_missing', 'Published settings do not supply certified motor/torque/pressure limits.', 'S1'),
             risk('oxygen_demand_missing', 'Absolute broth oxygen feasibility additionally requires OUR, Cstar and DO.', 'S2/S3')]
    predictions = [{'id': 'receiver_water_kla', 'metric': 'water_kla', 'unit': 'h^-1', 'value': target['kla_h_inv'],
                    'classification': 'experimental_water_summary_not_broth_or_product', 'evidence': target['source_location']}]
    public, private = packet(case_id, 'rastadter2023', evidence, facts, risks, predictions,
                            'Phase1: assess transfer readiness from donor characterization and equipment. Commit assessment before opening the separate characterization query. Phase2: predict water kLa at the supplied receiver setting; this tests characterization prediction, not selection of a successful operating recipe.')
    # For prediction, rpm/flow are legitimate covariates. They are NOT shown in
    # phase1, and kLa/power/future biology never enter either public phase.
    query = {'case_id': case_id, 'release': 'only_after_phase1_commitment',
             'working_volume_l': receiver, 'agitation_rpm': target['agitation_rpm'],
             'airflow_l_min': target['airflow_l_min'], 'sparger': target['sparger'],
             'context': 'Published receiver characterization setting; not a certified limit or agent-selected plan.'}
    return public, private, query


def pichia(receiver, source, target):
    case_id = f'PC-10-to-{receiver}L'
    equipment = []
    for row in source['equipment']:
        if row['nominal_volume']['value'] in (10, receiver):
            equipment.append({k: deepcopy(row[k]) for k in ('nominal_volume', 'manufacturer', 'model', 'aeration_operating_range', 'agitation_operating_range', 'initial_volume_as_reported', 'seed_volume_added', 'flow_reference_conditions', 'pressure_rating_mpa', 'impeller_diameter_m')})
    # No full manifest, limitations or curated receiver answers are staged.
    conditions = deepcopy(source['conditions'])
    evidence = {'P1': {'source': 'Liu2016 Methods; reviewed equipment transcription', 'equipment': equipment},
                'P2': {'source': 'Liu2016 Table2 donor10L only; reviewed transcription', 'donor': source['calibration']},
                'P3': {'source': 'Liu2016 optimized strategy Methods; reviewed transcription', 'conditions': conditions}}
    facts = [fact('receiver_nominal_volume', receiver, 'L', 'P1', 'Nominal receiving vessel volume'),
             fact('receiver_initial_medium', equipment[1]['initial_volume_as_reported']['value'], 'L', 'P1', 'Reported receiving initial medium charge before separately stated inoculum'),
             fact('nominal_gauge_pressure', conditions['pressure_gauge_MPa_nominal'], 'MPa_gauge', 'P3', 'Nominal operating gauge pressure'),
             fact('methanol_feed_coefficient', conditions['methanol_feed_mL_per_g_DCW_h'], 'mL/(g_DCW*h)', 'P3', 'Reported optimized methanol feed coefficient'),
             fact('receiver_pressure_rating', None, 'MPa_gauge', 'P1', 'Receiving vessel certified pressure rating, or null if not supplied')]
    risks = [risk('pressure_rating_missing', 'Operating pressure is not a certified vessel/filter/relief pressure rating.', 'P1/P3'),
             risk('nominal_not_working', 'Nominal vessel volume differs from medium charge and evolving working volume.', 'P1'),
             risk('kinetics_missing', 'No measured kLa/OUR or kinetics to predict mechanistic productivity from pressure.', 'P1/P2/P3'),
             risk('absolute_pressure', 'Oxygen driving force depends on absolute pressure, not the gauge-pressure ratio.', 'P3'),
             risk('flow_basis', 'Article L/min does not establish actual versus standard/normal gas reference conditions.', 'P1')]
    predictions = [{'id': 'receiver_enzyme_empirical', 'metric': 'enzyme_endpoint_empirical', 'unit': 'mg/L',
                    'value': target['outcomes']['volumetric_enzyme_production']['value'],
                    'classification': 'assay_derived_summary_not_mechanistic_productivity', 'evidence': target['source_location']}]
    return packet(case_id, 'liu2016', evidence, facts, risks, predictions,
                  'Assess transfer readiness and pressure/oxygen assumptions. Supply an optional empirical enzyme endpoint comparator from donor data; explicitly distinguish it from a mechanistic prediction. Do not invent kLa, OUR, utility costs or a safe receiving recipe.')


def trichoderma(rows, context):
    receiver = rows['250 L culture']
    selected = [min(receiver, key=lambda r: abs(r['time_h'] - hour)) for hour in GAS_GRID_H]
    if any(abs(r['time_h'] - hour) > .03 for r, hour in zip(selected, GAS_GRID_H)):
        raise ValueError('Requested observation is not available within declared time tolerance')
    evidence = {'T1': {'source': 'Paasikallio2017 Methods; reviewed source extract', 'context': context},
                'T2': {'source': 'Paasikallio2017_CO2_data.xlsx, 1 L culture', 'file': 'donor-gas.csv',
                       'note': 'Original numeric readings, recorded channel units unspecified. No resampling, normalization or imputation. Preserve source_sheet/source_row.'}}
    facts = [fact('donor_culture_scale', 1, 'L', 'T1', 'Reported donor culture scale'),
             fact('receiver_culture_scale', 250, 'L', 'T1', 'Reported receiving culture scale'),
             fact('receiver_max_working_volume', 350, 'L', 'T1', 'Reported receiving vessel maximum working capacity'),
             fact('temperature', 35, 'degC', 'T1', 'Cultivation temperature'),
             fact('ph', 4, 'pH', 'T1', 'Cultivation pH'),
             fact('gas_unit_confirmed', False, 'boolean', 'T2', 'Whether an explicit gas-channel concentration unit is supplied in the workbook headers')]
    risks = [risk('gas_basis_unconfirmed', 'Gas units, wet/dry basis and calibration must be confirmed before molar balances.', 'T1/T2'),
             risk('feed_confounding', 'Donor/receiver feed initiation differs; scale is not an isolated causal factor.', 'T1'),
             risk('replication', 'One culture per scale; time points are not independent transfer replicates.', 'T2'),
             risk('kinetics_missing', 'Gas traces do not identify product/biomass kinetics or receiving kLa.', 'T1/T2'),
             risk('scale_not_capacity', '250L culture scale is not the350L maximum working capacity.', 'T1')]
    predictions = [{'id': f'co2_{hour}h', 'metric': 'co2_recorded_reading', 'unit': 'source_recorded_unit_unspecified',
                    'time_h': row['time_h'], 'value': row['carbon_dioxide'], 'evidence': f"250 L culture!E{row['source_row']}",
                    'classification': 'gas_channel_observation_not_molar_flux_or_product'}
                   for hour, row in zip(GAS_GRID_H, selected)]
    return packet('TC-1-to-250L', 'paasikallio2017', evidence, facts, risks, predictions,
                  'Reconstruct a transfer assessment using the complete donor gas record and receiver equipment/methods. No receiving gas readings are available. Optionally forecast CO2 recorded readings at requested elapsed times. This is pre-receiver prediction, not adaptation or mechanistic yield validation. Report unsupported predictions as unavailable.')


def prepare(output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Refuse to overwrite an existing study; use a new version directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    inputs = [DATA / 'Paasikallio2017_CO2_data.xlsx', DATA / 'source-manifest.json',
              DATA / 'qualification-notes.md', DATA / 'receiver-context.json',
              FERMENTATION / 'sulfolobus.public.json', FERMENTATION / 'pichia.public.json',
              FERMENTATION / 'validation.evaluator.json', *sorted(Path(__file__).parent.glob('*.py')),
              REPO / 'backend/src/lifesci/fermentation/model.py', REPO / 'backend/src/lifesci/fermentation/schemas.py',
              REPO / 'docs/research/tech-transfer-experiment-protocol-20261101.md']
    for path in inputs:
        if not path.is_file():
            raise ValueError(f'Missing required qualification/protocol input: {path}')
    # Freeze the original publications behind the reviewed context as well.
    qualification_manifest = DATA / 'qualification-source-manifest.json'
    inputs.append(qualification_manifest)
    for row in json.loads(qualification_manifest.read_text())['sources']:
        path = DATA / row['path']
        if sha(path) != row['sha256']:
            raise ValueError('Original qualification article differs from manifest')
        inputs.append(path)
    for case in ('sulfolobus', 'pichia'):
        base = REPO / 'docs/research/fermentation' / case
        source_manifest = base / 'source-manifest.json'
        inputs.append(source_manifest)
        for row in json.loads(source_manifest.read_text())['files']:
            path = REPO / row['path'] if row['path'].startswith('docs/') else base / row['path']
            if sha(path) != row['sha256']:
                raise ValueError(f'Original literature file differs: {path}')
            inputs.append(path)
    source_hashes = {str(p.relative_to(REPO)): sha(p) for p in inputs}
    rows = workbook_rows(inputs[0])
    context = json.loads((DATA / 'receiver-context.json').read_text())
    targets = json.loads((FERMENTATION / 'validation.evaluator.json').read_text())
    sul = json.loads((FERMENTATION / 'sulfolobus.public.json').read_text())
    pic = json.loads((FERMENTATION / 'pichia.public.json').read_text())
    # Stage in a fresh directory and publish only after all validation succeeds.
    with tempfile.TemporaryDirectory(prefix='transfer-prep-', dir=output.parent) as staging:
        root = Path(staging) / 'study'
        root.mkdir()
        references = []
        for receiver, target in zip((20, 200), targets['sulfolobus']):
            if target['working_volume_l'] != receiver:
                raise ValueError('Unexpected receiver ordering')
            public, private, query = sulfolobus(receiver, sul, target)
            dump(root / 'agent-input' / public['case_id'] / 'evidence.json', public)
            dump(root / 'phase2-input' / public['case_id'] / 'characterization-query.json', query)
            references.append(private)
        for receiver, target in zip((100, 1000), targets['pichia']):
            if target['nominal_reactor_volume_l'] != receiver:
                raise ValueError('Unexpected receiver ordering')
            public, private = pichia(receiver, pic, target)
            dump(root / 'agent-input' / public['case_id'] / 'evidence.json', public)
            references.append(private)
        public, private = trichoderma(rows, context)
        dump(root / 'agent-input' / public['case_id'] / 'evidence.json', public)
        write_csv(root / 'agent-input' / public['case_id'] / 'donor-gas.csv', rows['1 L culture'])
        write_csv(root / 'evaluator-only' / 'receiving-gas.csv', rows['250 L culture'])
        references.append(private)
        dump(root / 'evaluator-only' / 'references.json', references)
        qualification = {'status': 'qualified_for_descriptive_workflow_and_declared_measured_targets_only',
            'counts': {k: len(v) for k, v in rows.items()},
            'profiles': {k: {'first_time_h': v[0]['time_h'], 'last_time_h': v[-1]['time_h'],
                            'median_interval_min': 60 * statistics.median(b['time_h'] - a['time_h'] for a, b in zip(v, v[1:])),
                            'channel_ranges': {c: [min(r[c] for r in v), max(r[c] for r in v)] for c in CHANNELS[1:]}} for k, v in rows.items()},
            'imputed_observations': 0, 'gas_unit': 'unspecified_in_workbook',
            'mechanistic_productivity_qualified': False, 'absolute_molar_gas_flux_qualified': False,
            'sulfolobus_endpoint': 'two experimental water-kLa summaries; source-only correlation challenged',
            'independent_studies': 3, 'transfer_cases': 5,
            'statistical_unit': 'study/experimental run; not each time point or receiver summary',
            'human_time_measured': False, 'expert_rubric_review': 'pending; researcher-authored exploratory rubric',
            'existing_model_reuse': 'lifesci.fermentation.model.transfer_point; no new organism kinetics'}
        dump(root / 'evaluator-only' / 'qualification.json', qualification)
        template = {'case_id': 'REPLACE', 'arm': 'agent_alone|model_workflow|agent_plus_model|human_workflow',
            'status': 'not_run', 'facts': [], 'predictions': [], 'risks': [], 'assessment': '',
            'characterization_requests': [], 'phase1_commitment_sha256': None,
            'model_identity': None, 'request_ids': [], 'model_tool_receipts': [],
            'timing': {k: None for k in ('preparation_minutes', 'configuration_minutes', 'review_minutes', 'correction_minutes', 'elapsed_seconds', 'provider_cost_usd')}}
        dump(root / 'templates' / 'submission.json', template)
        dump(root / 'templates' / 'review.json', {'case_id': 'REPLACE', 'reviewer': None,
              'rubric_version': VERSION, 'risks': [], 'claim_support_review': [], 'acceptance': 'not_reviewed'})
        dump(root / 'templates' / 'execution-manifest.json', {
            'status': 'not_ready_for_inference', 'study_manifest_sha256': None,
            'provider_model': 'modal/zai-org/GLM-5.3', 'returned_model_identity': None,
            'system_prompt_sha256': None, 'common_tool_schema_sha256': None,
            'mechanistic_tool_schema_sha256': None, 'runtime_source_sha256': None,
            'hardware': None, 'arm_order': None, 'repeats_per_case': None,
            'max_calls_per_session': None, 'max_tokens_per_request': None,
            'max_session_seconds': None, 'pilot_spend_usd': None, 'remaining_budget_usd': None,
            'provider_maximum_total_charge_usd': None, 'provider_cost_enforcement_receipt': None,
            'filesystem_denial_probe': None, 'network_denial_probe': None,
            'phase_commitment_probe': None, 'process_reviewer': None,
            'note': 'Complete and freeze separately before inference; this template does not enable paid runs.'})
        with (root / 'templates' / 'human-effort.csv').open('w', newline='') as f:
            csv.writer(f).writerow(['case_id', 'arm', 'participant_id', 'phase', 'started_utc', 'ended_utc', 'active_minutes', 'interruptions_minutes', 'artifact_sha256', 'accepted', 'correction_reason'])
        shutil.copy2(REPO / 'docs/research/tech-transfer-experiment-protocol-20261101.md', root / 'protocol.md')
        files = {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
        manifest = {'version': VERSION, 'frozen_utc': datetime.now(timezone.utc).isoformat(),
            'classification': 'retrospective_exploratory_preparation_not_agent_results',
            'source_sha256': source_hashes, 'files_sha256': files,
            'case_ids': [r['case_id'] for r in references], 'arms': ['agent_alone', 'model_workflow', 'agent_plus_model'],
            'human_comparator': 'matched_conventional_workflow; must be observed for labor claim',
            'pilot': 'separate integration rehearsal; no efficacy-based case replacement or pooling',
            'scientific_outcome_holdout': 'Excluded from future worker inputs; inspected by developers, not analyst-blind.',
            'isolation_enforced': False, 'paid_runs_authorized_by_this_command': False,
            'new_model_requests': 0, 'provider_cost_usd': 0,
            'budget_ceiling_usd': 50, 'provider_spend_bound_verified': False,
            'comparison_status': 'not_run', 'publication_status': 'not_validated',
            'execution_gates': ['provider-only network and allowlisted filesystem isolation verified',
                                'phase1 commitment enforced before release of phase2 inputs',
                                'expert review of source facts and scientific rubric',
                                'provider-enforced cost bound fits remaining total50USD budget; include pilot/retries',
                                'matched human timing required only for human-effort savings claim']}
        dump(root / 'freeze-manifest.json', manifest)
        root.rename(output)
    validate(output)
    return {'output': str(output), 'cases': 5, 'studies': 3, 'model_requests': 0,
            'manifest_sha256': sha(output / 'freeze-manifest.json')}


def validate(root, check_sources=True):
    root = Path(root)
    manifest = json.loads((root / 'freeze-manifest.json').read_text())
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()} - {'freeze-manifest.json'}
    if actual != set(manifest['files_sha256']):
        raise ValueError('Unexpected or missing frozen files')
    for relative, digest in manifest['files_sha256'].items():
        if sha(root / relative) != digest:
            raise ValueError(f'Frozen file changed: {relative}')
    if check_sources:
        for relative, digest in manifest['source_sha256'].items():
            if sha(REPO / relative) != digest:
                raise ValueError(f'Source changed; create a new version: {relative}')
    staged = list((root / 'agent-input').rglob('*')) + list((root / 'phase2-input').rglob('*'))
    for path in staged:
        if path.is_file() and path.suffix not in ('.json', '.csv'):
            raise ValueError('Original answer-bearing sources must not be staged')
    for path in (root / 'agent-input').rglob('*.json'):
        text = path.read_text()
        if 'validation.evaluator' in text or '250 L culture!E' in text or 'receiving-gas.csv' in text:
            raise ValueError('Evaluator lineage leaked into public packet')
    if list((root / 'agent-input').rglob('*250*csv')):
        raise ValueError('Receiver CSV leaked into agent input')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'validate', 'score'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--submission', type=Path)
    parser.add_argument('--review', type=Path)
    parser.add_argument('--result', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(json.dumps(prepare(args.output), indent=2))
    elif args.action == 'validate':
        m = validate(args.output)
        print(json.dumps({'verified': True, 'files': len(m['files_sha256']), 'cases': m['case_ids']}))
    else:
        from .score import score_case
        validate(args.output)
        if not args.submission or not args.result:
            parser.error('score requires --submission and --result; keep outputs outside frozen directory')
        if args.result.resolve().is_relative_to(args.output.resolve()) or args.result.exists():
            parser.error('Use a new result path outside the frozen study')
        submission = json.loads(args.submission.read_text())
        references = json.loads((args.output / 'evaluator-only/references.json').read_text())
        reference = next((r for r in references if r['case_id'] == submission.get('case_id')), None)
        if reference is None:
            raise ValueError('Unknown case')
        review = json.loads(args.review.read_text()) if args.review else None
        score = score_case(reference, submission, review)
        score.update({'submission_sha256': sha(args.submission), 'freeze_manifest_sha256': sha(args.output / 'freeze-manifest.json'),
                      'review_sha256': sha(args.review) if args.review else None})
        dump(args.result, score)
        print(json.dumps({'scored': str(args.result), 'case_id': score['case_id']}))


if __name__ == '__main__':
    main()
