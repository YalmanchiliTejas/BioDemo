"""Twelve of the 16 November freeze-drying cases (the first three of each family by id) at each
reasoning level, one case at a time. Same cases, reference answers and grader as that run. Not run under its frozen
protocol: the application code has changed since, so this is a comparison between levels made today, nothing more."""
import json
import os
import statistics
import sys
import time
from pathlib import Path

for key in ('LIFESCI_DATABASE_URL', 'DATABASE_URL', 'SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'MODAL_EMBEDDINGS_URL',
            'ASSISTANT_LOOP', 'MODAL_REASONING_EFFORT', 'LIFESCI_INTERPRETER_REASONING_EFFORT'):
    os.environ.pop(key, None)
os.environ.update(ASSISTANT_LOOP='tools', MODAL_EMBEDDINGS_URL='', LIFESCI_LLM_PROVIDER='modal')
BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))
from benchmarks.agent_pilot.runner import MODEL, CampaignBudget, RecordedProvider  # noqa: E402

os.environ['LIFESCI_LLM_MODEL'] = MODEL
from benchmarks.lyopronto_native import run as native  # noqa: E402

BASE = BACKEND / 'results' / 'live-evals-20261116' / 'native' / 'frozen'
ROOT = BACKEND / 'results' / 'reasoning-effort-20261116'
levels = sys.argv[1].split(',')
caps = dict(zip(levels, map(float, sys.argv[2].split(','))))
by_family = {}
for path in sorted((BASE / 'public').glob('*.json')):
    by_family.setdefault(json.loads(path.read_text())['family'], []).append(path)
chosen = [path for family in sorted(by_family) for path in by_family[family][:3]]
only = set(sys.argv[3].split(',')) if len(sys.argv) > 3 else None   # rerun named cases only, into a folder of their own
if only:
    chosen = [path for path in chosen if path.stem in only]
for level in levels:
    out = ROOT / (f'multistep-{level}' + ('-rest' if only else '') + os.environ.get('MULTISTEP_SUFFIX', ''))
    if out.exists():
        print('SKIP', level, '(already there)', flush=True)
        continue
    # The endpoint and token, from the same local files the other live evaluations read; nothing else.
    from benchmarks.workflow_trial.live import load_settings
    cfg = {k: v for k, v in load_settings().items() if k in ('MODAL_BASE_URL', 'MODAL_PROXY_TOKEN', 'BIODEMO_MODAL_BASE_URL', 'BIODEMO_MODAL_PROXY_TOKEN', 'MODAL_MIN_MAX_TOKENS')}
    from src.lifesci.gateway.providers import modal_settings
    assert all(modal_settings(cfg)), 'endpoint not configured'
    if level != 'max-default':
        cfg['MODAL_REASONING_EFFORT'] = level
    budget = CampaignBudget(caps[level], 200, reserve_per_request=.4, receipt_dir=out / 'requests')
    deadline, results, started = time.monotonic() + 3300, [], time.time()
    for path in chosen:
        case, reference = json.loads(path.read_text()), json.loads((BASE / 'reference' / path.name).read_text())
        result = native.episode(case, reference, out / case['id'], RecordedProvider(cfg, budget, case['id'], deadline))
        results.append(result)
        native.write(out / 'results.json', {'reasoning_effort': cfg.get('MODAL_REASONING_EFFORT') or 'not sent (max)', 'cases': [p.stem for p in chosen],
                                            'records': results, 'budget': budget.snapshot()})
        print(json.dumps({'level': level, 'done': len(results), 'of': len(chosen), 'family': case['family'], 'passed': result['verdict']['passed'],
                          'turn': result['trace']['turn_status'], 'seconds': round(result['elapsed_seconds'], 1)}), flush=True)
    snap = budget.snapshot()
    seconds = [r['elapsed_seconds'] for r in results]
    print(json.dumps({'LEVEL': level, 'passed': sum(r['verdict']['passed'] for r in results), 'of': len(results),
                      'completed_turns': sum(r['trace']['turn_status'] == 'completed' for r in results),
                      'mean_seconds': round(statistics.mean(seconds), 1), 'median_seconds': round(statistics.median(seconds), 1),
                      'slowest': round(max(seconds), 1), 'requests': snap['requests'], 'accounted_usd': round(snap['accounted_usd'], 3),
                      'minutes': round((time.time() - started) / 60, 1)}), flush=True)
