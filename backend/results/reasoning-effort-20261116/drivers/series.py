"""The same two live evaluations at each reasoning level, one after another (never at once: the
endpoint's speed drops when requests overlap). Stops when the running cost estimate passes the cap."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BACKEND = REPO / 'backend'
OUT = BACKEND / 'results' / 'reasoning-effort-20261116'
CAP = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
PY = sys.executable
OUT.mkdir(parents=True, exist_ok=True)
progress = OUT / 'progress.json'
state = json.loads(progress.read_text()) if progress.exists() else {'runs': [], 'spent_usd': 0.0}


def env_for(effort):
    env = {k: v for k, v in os.environ.items() if k not in ('MODAL_REASONING_EFFORT', 'ASSISTANT_LOOP', 'MODAL_EMBEDDINGS_URL')}
    if effort != 'max-default':
        env['MODAL_REASONING_EFFORT'] = effort
    return env


def cost_answers(d):
    return float(json.loads((d / 'report.json').read_text())['budget']['accounted_usd'])


def cost_assistant(d):
    arms = json.loads((d / 'report.json').read_text())['assistant']['by_arm']
    return sum(a['input_tokens'] * 1.40 + a['output_tokens'] * 4.40 for a in arms) / 1e6   # every input token at the uncached rate


PLAN = [(kind, effort) for kind in ('answers', 'assistant') for effort in ('max-default', 'high', 'low')]
for kind, effort in PLAN:
    name = f'{kind}-{effort}'
    if any(r['name'] == name for r in state['runs']):
        continue
    if state['spent_usd'] >= CAP:
        print(f'STOP before {name}: estimated spend {state["spent_usd"]:.2f} has reached the cap {CAP}', flush=True)
        break
    d = OUT / name
    if kind == 'answers':
        cmd = [PY, '-I', 'benchmarks/skills/answers.py', '--execute', '--output', str(d), '--repeats', '1', '--workers', '1',
               '--budget-usd', '2', '--max-requests', '150', '--max-seconds', '1800']
        env = env_for(effort)
    else:
        cmd = [PY, '-m', 'benchmarks.workflow_trial.live', '--output', str(d), '--candidates', 'glm', '--skip', 'explain',
               '--assistant-cases', '3', '--workers', '1']
        env = {**env_for(effort), 'PYTHONPATH': str(BACKEND)}
    started = time.time()
    with open(OUT / f'{name}.log', 'w') as log:
        code = subprocess.run(cmd, cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    try:
        cost = cost_answers(d) if kind == 'answers' else cost_assistant(d)
    except Exception as exc:  # a run that left no report: count nothing, say so
        cost, code = 0.0, f'{code} (no report: {type(exc).__name__})'
    state['runs'].append({'name': name, 'exit': code, 'minutes': round((time.time() - started) / 60, 1), 'estimated_usd': round(cost, 3)})
    state['spent_usd'] = round(state['spent_usd'] + cost, 3)
    progress.write_text(json.dumps(state, indent=2) + '\n')
    print(f'DONE {name}: exit {code}, {state["runs"][-1]["minutes"]} min, about ${cost:.2f}; total about ${state["spent_usd"]:.2f}', flush=True)
print('FINISHED', json.dumps(state), flush=True)
