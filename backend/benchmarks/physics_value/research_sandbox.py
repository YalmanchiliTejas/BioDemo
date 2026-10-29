"""OS-sandboxed general-purpose numerical tool shared by both research arms."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def _quote(path):
    return json.dumps(str(Path(path).resolve()))


def profile(scratch: Path) -> str:
    # Python/NumPy installed in the existing venv may read their own libraries.
    # No other home-directory files, sibling workspaces or temporary answers.
    allowed = f'(require-any (subpath {_quote(sys.prefix)}) (subpath {_quote(scratch)}))'
    return '\n'.join([
        '(version 1)', '(allow default)', '(deny network*)',
        # Interpreter symlink resolution needs ancestor metadata. Deny file
        # contents/directory listings while permitting those realpath lookups.
        f'(deny file-read-data (require-all (subpath {_quote(Path.home())}) (require-not {allowed})))',
        f'(deny file-read-data (require-all (subpath "/private/tmp") (require-not (subpath {_quote(scratch)}))))',
        f'(deny file-write* (require-not (require-any (subpath {_quote(scratch)}) (literal "/dev/null"))))',
    ]) + '\n'


WORKER = r'''
import contextlib,io,json,math,resource,sys
import numpy as np
from scipy import integrate,optimize,stats
request=json.loads(sys.stdin.read())
resource.setrlimit(resource.RLIMIT_CPU,(5,5))
resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
resource.setrlimit(resource.RLIMIT_NPROC,(1,1))
buffer=io.StringIO()
try:
    with contextlib.redirect_stdout(buffer):
        exec(compile(request['code'],'<agent-numerical-analysis>','exec'),
             {'data':request['packet'],'np':np,'math':math,'json':json,
              'integrate':integrate,'optimize':optimize,'stats':stats})
    print(json.dumps({'ok':True,'stdout':buffer.getvalue()[:16000]}))
except BaseException as exc:
    print(json.dumps({'ok':False,'error':type(exc).__name__+': '+str(exc)[:1000],
                      'stdout':buffer.getvalue()[:16000]}))
'''


def analyze(code: str, packet: dict, scratch: Path) -> dict:
    if not isinstance(code, str) or len(code) > 18000:
        raise ValueError('numerical code must be a string of at most 18000 characters')
    scratch = Path(scratch).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    sandbox = scratch / 'numerical.sb'
    sandbox.write_text(profile(scratch))
    # Numerical workers never inherit the inference credential or other secrets.
    environment = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT') if k in os.environ}
    environment.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                       PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(scratch))
    process = subprocess.run(['sandbox-exec', '-f', str(sandbox), sys.executable, '-I', '-c', WORKER],
                             input=json.dumps({'code': code, 'packet': packet}), text=True,
                             capture_output=True, cwd=scratch, env=environment, timeout=12)
    if process.returncode:
        raise RuntimeError('numerical sandbox process failed: '+process.stderr[-1200:])
    return json.loads(process.stdout)


def probe(dataset: Path, scratch: Path) -> dict:
    packet = {'probe': 7}
    canary = Path(dataset).resolve() / 'evaluator/catalogue.json'
    tests = {
        'arithmetic': 'print(int(np.sum([data["probe"],5])))',
        'hidden_file': f'open({str(canary)!r}).read()',
        'network': 'import socket; socket.socket().connect(("127.0.0.1",9))',
        'credentials': 'import os; print(any("TOKEN" in k or "KEY" in k for k in os.environ))',
    }
    result = {name: analyze(code, packet, scratch) for name, code in tests.items()}
    passed = (result['arithmetic'].get('stdout', '').strip() == '12' and
              'PermissionError' in result['hidden_file'].get('error', '') and
              'PermissionError' in result['network'].get('error', '') and
              result['credentials'].get('stdout', '').strip() == 'False')
    if not passed:
        raise RuntimeError('numerical isolation probes did not pass: '+json.dumps(result))
    return {'passed': True, 'mechanism': 'inherited macOS sandbox-exec for arbitrary numerical Python', 'probes': result}
