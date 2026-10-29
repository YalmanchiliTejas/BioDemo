"""Publish recorded deterministic case results; never execute an agent or invent metrics."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def export(source=None, destination=None):
    source = Path(source or ROOT/'docs/research/fermentation/results/results.json')
    destination = Path(destination or ROOT/'frontend/public/case-study-results/fermentation.json')
    data = json.loads(source.read_text())
    payload = {
        'version': data['version'], 'source_record': str(source.relative_to(ROOT)),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'notice': 'Recorded deterministic results from reviewed literature transcriptions. Receiving measurements are evaluator outputs, not agent inputs. No engineering time savings or agent uplift has been measured.',
        'cases': {},
    }
    for case in data['cases']:
        analysis = case['physics_only']['analysis']
        payload['cases'][case['case_id']] = {key: analysis[key] for key in (
            'project', 'prediction', 'validation', 'assumptions', 'model_manifest',
            'execution_status', 'resource_usage', 'plan_hash')}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2)+'\n')
    return payload


if __name__ == '__main__':
    result = export()
    print(json.dumps({'exported_cases': list(result['cases']), 'source_sha256': result['source_sha256']}))
