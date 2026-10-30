"""Experiment models and demo data for the engineering assistant.

* Demo cases: twelve public case packets from the final physics A/B experiment (simulated PenSim
  penicillin and SMPL antibody processes), byte-identical to the experiment dataset. The evaluator
  outcomes are not bundled. A case becomes platform evidence when a conversation loads it.
* Forecasts: the corrected PenSim / SMPL models run each requested operating plan of a loaded case.
* CHO: the simple batch growth/glucose model is fitted to a verified CMO delivery and checked
  against that batch's own later readings.

Every output is a derived record whose inputs are the evidence it used, so it goes stale if that
evidence is corrected or withdrawn.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path
from typing import Any

from ..cmo_datasets import require_dataset
from ..evidence import EvidenceRef
from . import cho
from .simulators import MODELS, SimulatorWorker

DEMO = Path(__file__).with_name('demo')
SOURCE_SYSTEM = 'simulated-bioprocess-case'
CASE_CLASSIFICATION = 'simulated_demo_case_not_measurement'
TASKS = {
    'prediction': 'Forecast the current plan from the observed history',
    'outcome': 'Choose an operating change part-way through the batch',
    'transfer': 'Adapt the source recipe to receiving-site limits before any receiving data exist',
}
KEY_STATES = {'pensim': ('P', 'DO2', 'S', 'Viscosity'), 'mab': ('mAb_reactor', 'viable_cells_reactor', 'glucose_reactor', 'lactate_reactor')}


@cache
def demo_index() -> dict[str, Any]:
    return json.loads((DEMO / 'index.json').read_text())


def packet(case_id: str) -> dict[str, Any]:
    if case_id not in {c['case_id'] for c in demo_index()['cases']}:
        raise ValueError(f'unknown demo case {case_id}')
    return json.loads((DEMO / f'{case_id}.json').read_text())


def describe(case: dict[str, Any]) -> str:
    model = MODELS[case['simulator']]['title'].split(' (')[0]
    return f"{model} · {TASKS[case['task']]} · {case['stratum']} case"


def _history(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{'time_h': round(r['time_h'], 3), **{k: r['state'][k] for k in keys if k in r['state']},
             **({'commands': r['commands']} if r.get('commands') else {})} for r in rows]


def summary(p: dict[str, Any]) -> dict[str, Any]:
    """Everything the assistant needs to reason about the case, without evaluator outcomes."""
    keys = KEY_STATES[p['simulator']]
    return {
        'case_id': p['case_id'], 'simulator': p['simulator'], 'model_id': MODELS[p['simulator']]['id'],
        'task': p['task'], 'task_description': TASKS[p['task']], 'stratum': p['stratum'],
        'decision_time_h': p['decision_time_h'], 'objective': p['objective'], 'objective_definition': p['objective_definition'],
        'time_definition': p['time_definition'], 'operating_specification': p['operating_specification'],
        'source_operating_plan': p.get('source_operating_plan'), 'constraints': p['constraints'],
        'action_plans': p['action_plans'], 'allowed_actions': p['allowed_actions'],
        'forecast_targets': p['forecast_targets'], 'field_units': p['field_units'],
        'completed_source_batch': _history(p['source_history'], keys),
        'current_batch_observations': _history(p['receiving_observations'], keys),
        'classification': 'Simulated case from the physics A/B experiment, not plant data.',
    }


class BioprocessService:
    def __init__(self, platform, worker: SimulatorWorker | None = None):
        self.p = platform
        self.worker = worker or SimulatorWorker.from_env()

    def catalog(self) -> dict[str, Any]:
        return {
            'models': [{**m, 'status': self.worker.status()} for m in MODELS.values()]
            + [{'id': 'cho.monod_batch', 'version': cho.VERSION, 'title': 'CHO batch growth and glucose (Monod)',
                'description': 'Fitted to the viable cell density and glucose readings of a verified CMO delivery; forecasts one batch from its readings up to a cutoff and compares with its later readings.',
                'equations': cho.EQUATIONS, 'limitations': cho.LIMITATIONS, 'status': {'available': True}}],
            'demo_cases': [{'case_id': c['case_id'], 'simulator': c['simulator'], 'task': c['task'], 'stratum': c['stratum'],
                            'description': describe(c), 'allowed_actions': packet(c['case_id'])['allowed_actions']}
                           for c in demo_index()['cases']],
            'demo_source': {k: demo_index()[k] for k in ('source', 'dataset_manifest_sha256', 'experiment_report', 'note')},
        }

    def load_case(self, ctx, case_id: str, site_id: str) -> tuple[dict[str, Any], EvidenceRef]:
        """Record the case packet as evidence (idempotent) and return its summary."""
        p = packet(case_id)
        entry = next(c for c in demo_index()['cases'] if c['case_id'] == case_id)
        ev = self.p.evidence.ingest(ctx, source_system=SOURCE_SYSTEM, source_record_id=case_id,
            content=(DEMO / f'{case_id}.json').read_bytes(), media_type='application/json', site_id=site_id, event_time=None,
            source_revision=entry['packet_sha256'], mapping_version=p['experiment_version'],
            metadata={'classification': CASE_CLASSIFICATION, 'simulator': p['simulator'], 'task': p['task'],
                      'experiment_dataset_manifest_sha256': demo_index()['dataset_manifest_sha256']})
        return summary(p), EvidenceRef('evidence', ev['evidence_id'], ev['revision'], site_id)

    def case_record(self, ctx, case_id: str, site_id: str, basis: list[EvidenceRef]) -> dict[str, Any]:
        info, ref = self.load_case(ctx, case_id, site_id)
        return self.p.evidence.record_derived(ctx, 'bioprocess_case', {
            'site_id': site_id, 'case_id': case_id, 'allowed_actions': info['allowed_actions'], 'case': info, 'description': describe(info),
            'warnings': ['Simulated demonstration case from the physics A/B experiment; no plant data.']},
            inputs=[ref, *basis], produced_by={'method': 'bioprocess-demo-case-1'})

    def forecast(self, ctx, case_id: str, actions: list[str], site_id: str, basis: list[EvidenceRef]) -> dict[str, Any]:
        info, ref = self.load_case(ctx, case_id, site_id)
        p = packet(case_id)
        actions = list(dict.fromkeys(a for a in actions if a != 'abstain'))
        unknown = [a for a in actions if a not in p['allowed_actions']]
        if unknown or not actions:
            raise ValueError(f"choose operating plans from {', '.join(a for a in p['allowed_actions'] if a != 'abstain')}")

        def run(action):
            try:
                return action, self.worker.forward(p, action), None
            except (RuntimeError, ValueError) as exc:
                return action, None, str(exc)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(run, actions))
        rows = []
        for action, out, error in results:
            if out is None:
                rows.append({'action': action, 'plan': p['action_plans'][action], 'status': 'failed', 'error': error})
                continue
            consequences = out.get('operating_consequences') or {}
            fit = (out.get('calibration') or {}).get('physical_fit')
            rows.append({
                'action': action, 'plan': p['action_plans'][action], 'status': 'completed',
                'predictions': {f: {'value': v, **p['forecast_targets'][f]} for f, v in out['predictions'].items()},
                'feasible': consequences.get('feasible'), 'violations': consequences.get('violations', []),
                'objective': consequences.get('objective'), 'resources': consequences.get('resources'),
                'calibration': {k: out['calibration'].get(k) for k in ('applied', 'reason', 'evidence_scope', 'warning')} if out.get('calibration') else None,
                'physical_fit': {k: fit.get(k) for k in ('kla_factor', 'growth_factor', 'production_factor', 'method')} if fit else None,
            })
        model = MODELS[p['simulator']]
        if all(r['status'] == 'failed' for r in rows):
            raise RuntimeError('; '.join(r['error'] for r in rows))
        return self.p.evidence.record_derived(ctx, 'bioprocess_forecast', {
            'site_id': site_id, 'case_id': case_id, 'simulator': p['simulator'], 'task': p['task'],
            'description': describe(info), 'decision_time_h': p['decision_time_h'],
            'model': {k: model[k] for k in ('id', 'version', 'title', 'limitations')},
            'objective_definition': p['objective_definition'], 'constraints': p['constraints'],
            'targets': p['forecast_targets'], 'rows': rows,
            'observed': {'completed_source_batch': info['completed_source_batch'],
                         'current_batch': info['current_batch_observations']},
            'classification': 'model_forecast_on_simulated_case_not_observation',
            'warnings': ['Forecasts are model predictions for a simulated case, not plant measurements.',
                         'Feasibility uses the case\'s declared study limits, not validated manufacturing limits.',
                         *model['limitations']]},
            inputs=[ref, *basis], produced_by={'method': model['id'], 'version': model['version']})

    def cho_forecast(self, ctx, dataset_id: str, batch: str, cutoff_h: float, site_id: str,
                     basis: list[EvidenceRef]) -> dict[str, Any]:
        rec = require_dataset(self.p, ctx, dataset_id, site_id)
        data = json.loads(self.p.evidence.original(ctx, dataset_id, rec.revision))
        result = cho.forecast(data, batch, cutoff_h)
        return self.p.evidence.record_derived(ctx, 'bioprocess_cho_forecast', {
            'site_id': site_id, 'dataset_id': dataset_id, 'delivery_name': data.get('delivery_name'), 'cmo': data.get('cmo'),
            **result, 'classification': 'fitted_model_forecast_from_verified_delivery',
            'warnings': [*result['warnings'], *result['limitations'],
                         'Verified means the values match their source files; it does not mean the process was in control.']},
            inputs=[EvidenceRef('evidence', dataset_id, rec.revision, rec.state['site_id']), *basis],
            produced_by={'method': cho.VERSION})
