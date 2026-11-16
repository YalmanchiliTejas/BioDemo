"""Reproduce existing evals with inference-only credentials and isolated stores.

Live commands must be launched behind the existing admission proxy. No provider
response, benchmark answer, application tool or grader is replaced here.
"""
from pathlib import Path
import json
import os
import runpy
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent
proxy = os.environ.get('BIODEMO_MODAL_BASE_URL', '')
mode = sys.argv[1]
for key in list(os.environ):
    if key not in {'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'LC_CTYPE', 'SYSTEMROOT'}:
        os.environ[key] = ''
os.environ.update(
    PYTHONPATH=str(ROOT / 'backend'),
    LIFESCI_ENV_FILE='/dev/null', LIFESCI_DATABASE_URL='', DATABASE_URL='',
    CMO_DATABASE_URL='', CMO_TEST_DATABASE_URL='',
    CMO_HOSTED_INFERENCE_APPROVED='0', MODAL_EMBEDDINGS_URL='',
    BIODEMO_KEEP_RUNTIME='1', PYTHONDONTWRITEBYTECODE='1',
    LYOPRONTO_CHECKOUT='/private/tmp/lyohub-rerun-source',
)
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]
from src.lifesci import envfile
from src.manufacturing_data.cmo import settings
settings.load_local_settings = lambda *a, **k: None
envfile.load_env_file = lambda *a, **k: []

if mode.endswith('-live'):
    parsed = urlparse(proxy)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path != '/v1':
        raise RuntimeError('Live execution requires the existing local admission gate')
    local = envfile.parse_env((ROOT / 'backend/.env.local').read_text())
    for key in ('MODAL_PROXY_TOKEN', 'BIODEMO_MODAL_PROXY_TOKEN'):
        if local.get(key):
            os.environ[key] = local[key]
    if not any(os.environ.get(k) for k in ('MODAL_PROXY_TOKEN', 'BIODEMO_MODAL_PROXY_TOKEN')):
        raise RuntimeError('Modal inference credentials are unavailable')
    # Both provider adapters must use the same gate, despite different precedence.
    os.environ.update(MODAL_BASE_URL=proxy, BIODEMO_MODAL_BASE_URL=proxy,
                      BIODEMO_PRIME_MODEL='modal/zai-org/GLM-5.3',
                      LIFESCI_LLM_PROVIDER='modal', LIFESCI_LLM_MODEL='zai-org/GLM-5.3')

if mode == 'native-generate':
    sys.argv = ['native', 'generate', '--output', str(OUTPUT / 'native/frozen')]
    runpy.run_module('benchmarks.lyopronto_native.run', run_name='__main__')
elif mode == 'native-preflight':
    sys.argv = ['native', 'preflight', '--output', str(OUTPUT / 'native/preflight')]
    runpy.run_module('benchmarks.lyopronto_native.run', run_name='__main__')
elif mode == 'native-live':
    sys.argv = ['native', 'run', '--base', str(OUTPUT / 'native/frozen'),
                '--output', str(OUTPUT / 'native/agent')]
    runpy.run_module('benchmarks.lyopronto_native.run', run_name='__main__')
elif mode == 'cho-live':
    from src.prime_runtime.compare import run_comparison
    destination = ROOT / 'backend/runs/cho-comparison'
    if destination.exists():
        raise RuntimeError('Preserve prior CHO attempt; do not overwrite or retry scored work')
    result = run_comparison(
        package=ROOT / 'backend/benchmarks/cho/raw/workbooks',
        output=destination,
        objective=('Investigate the supplied published CHO cultivation workbooks. '
                   'Summarize measured growth, glucose and lactate variability across cultivations. '
                   'Identify the strongest evidence-backed investigation leads and missing information. '
                   'Compare values only at stated compatible measured times and units; cite original '
                   'sources. Distinguish observed facts from proposed mechanisms. These records do '
                   'not establish a verified root cause, product disposition, or approved action.'),
        scope='published-cultivation-evaluation',
        progress=lambda message: print(message, flush=True),
    )
    (OUTPUT / 'cho-result-pointer.json').write_text(json.dumps({
        'comparison': str(destination / 'comparison.json'),
        'agent_report': str(destination / 'agent_report.json'),
        'scope': result['claim_status'],
        'causal_accuracy': None,
    }, indent=2) + '\n')
else:
    raise ValueError('Unknown evaluation command')
