"""Run a frozen Prime suite through a conservative Modal request admission gate.

No prompts, response content or credentials are written by this proxy. Every
forwarded request reserves its full worst-case cost, even on error/timeout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODEL = 'zai-org/GLM-5.3'
# Verified 2026-10-31 at https://modal.com/library/zai/glm-5-3.
# Reserve for a full 1,048,576 input tokens plus 131,072 output tokens at
# $1.40/$4.40 per million: $2.0447232, rounded up to $2.25. No cache discount.
RESERVATION_USD = 2.25
MAX_REQUESTS = 100
CAMPAIGN_USD = 10.0


def response_usage(wire):
    """Read only provider token counters from JSON or SSE; never retain content."""
    candidates = [wire]
    candidates += [line[5:].strip() for line in wire.splitlines() if line.startswith(b'data:')]
    usage = None
    response_models = set()
    for value in candidates:
        try:
            item = json.loads(value)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(item, dict) and isinstance(item.get('model'), str):
            response_models.add(item['model'])
        proposed = item.get('usage') if isinstance(item, dict) else None
        if not isinstance(proposed, dict):
            continue
        prompt, completion = proposed.get('prompt_tokens'), proposed.get('completion_tokens')
        if type(prompt) is int and type(completion) is int and 0 <= prompt <= 1048576 and 0 <= completion <= 131072:
            details=proposed.get('prompt_tokens_details') or {}
            cached=details.get('cached_tokens',0) if isinstance(details,dict) else 0
            if type(cached) is not int or not 0 <= cached <= prompt: cached=0
            usage = {'prompt_tokens': prompt, 'completion_tokens': completion,
                     'cached_prompt_tokens':cached,
                     'uncached_rate_estimate_usd':(prompt * 1.4 + completion * 4.4) / 1e6,
                     'conservative_cost_usd': ((prompt-cached)*1.4 + cached*.26 + completion*4.4) / 1e6}
    if usage is not None:
        usage['response_models'] = sorted(response_models)
    return usage


def drain_response(response, writer):
    """Finish reading provider usage even when an SDK cancellation closes its sink."""
    wire=bytearray();complete=True;disconnected=False
    while chunk := response.read1(8192):
        if len(wire)+len(chunk)<=4_000_000:wire.extend(chunk)
        else:complete=False
        if not disconnected:
            try:writer(chunk)
            except OSError:disconnected=True
    return response_usage(bytes(wire)) if complete else None, disconnected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--method', choices=['full_rlm', 'retrieval_llm'], default='full_rlm')
    parser.add_argument('--limit', type=int, default=1)
    parser.add_argument('--provider-env', type=Path, help='Inference-only environment file read by the existing suite runner')
    parser.add_argument('--campaign-module', choices=['benchmarks.common.pilot_benchmark', 'benchmarks.workflow_agents.campaign'], default='benchmarks.common.pilot_benchmark')
    parser.add_argument('--budget-usd', type=float, default=CAMPAIGN_USD)
    parser.add_argument('--max-requests', type=int, default=MAX_REQUESTS)
    parser.add_argument('--command', nargs=argparse.REMAINDER,
                        help='Run an explicitly supplied benchmark command through the same admission gate')
    args = parser.parse_args()
    if not 1 <= args.limit <= 60:
        parser.error('limit must be 1..60')
    if not 2.25 <= args.budget_usd <= 20 or not 1 <= args.max_requests <= 5000:
        parser.error('budget must be $2.25..$20 and request ceiling 1..5000')
    campaign_cap, request_cap = args.budget_usd, args.max_requests
    suite = args.suite.resolve()
    admission = suite / 'modal-admission.jsonl'
    if admission.exists():
        raise ValueError('An admission ledger already exists; preserve it and use a new frozen suite')
    settings = json.loads((Path.home() / '.prime/agent/models.json').read_text())
    provider = settings['providers']['modal']
    upstream = provider['baseUrl'].rstrip('/')
    if upstream != 'https://gauntlet--ep-glm-5-3-server.us-west.modal.direct/v1':
        raise ValueError('Endpoint changed; reverify shared billing and model prices')
    state = {'admitted': 0, 'held_usd': 0.0, 'active': 0}
    lock = threading.Condition()

    def record(entry):
        with admission.open('a') as receipt:
            receipt.write(json.dumps(entry, sort_keys=True) + '\n')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def fail(self, status, reason):
            payload = json.dumps({'error': {'message': reason, 'type': 'benchmark_admission'}}).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            length = int(self.headers.get('Content-Length', '0'))
            if self.path != '/v1/chat/completions' or not 0 < length <= 8_000_000:
                return self.fail(400, 'Unsupported route or request size')
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw)
            except ValueError:
                return self.fail(400, 'Invalid JSON')
            limits = [body[k] for k in ('max_tokens', 'max_completion_tokens') if k in body]
            bounded = bool(limits) and all(type(value) is int and 1 <= value <= 131072 for value in limits)
            maximum = max(limits) if bounded else None
            if body.get('model') != MODEL or not bounded or body.get('n', 1) != 1:
                with lock:
                    record({'event': 'rejected', 'reason': 'unsupported_or_unbounded_request'})
                return self.fail(400, 'Unbounded model/output request rejected; runtime settings were not modified')
            with lock:
                # Temporary in-flight reservations must queue, not masquerade
                # as exhausted funds and abort otherwise affordable child calls.
                while state['held_usd'] + RESERVATION_USD > campaign_cap and state['active'] > 0:
                    lock.wait(timeout=1)
                if state['admitted'] >= request_cap or state['held_usd'] + RESERVATION_USD > campaign_cap:
                    record({'event': 'denied', 'reason': 'campaign_admission_cap'})
                    return self.fail(402, 'Campaign admission cap reached; no additional paid dispatch')
                state['admitted'] += 1
                state['active'] += 1
                state['held_usd'] += RESERVATION_USD
                ordinal = state['admitted']
                record({'event': 'reserved', 'ordinal': ordinal, 'reserved_usd': RESERVATION_USD,
                        'total_reserved_usd': state['held_usd'],
                        'request_bytes': length, 'max_output_tokens': maximum, 'model': MODEL})
            started = time.monotonic()
            status = None
            usage = None
            try:
                req = urllib.request.Request(upstream + '/chat/completions', data=raw, method='POST',
                    headers={'Authorization': self.headers.get('Authorization', ''), 'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=900) as response:
                    status = response.status
                    self.send_response(status)
                    self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                    self.end_headers()
                    def write(chunk):
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    usage, disconnected = drain_response(response,write)
                    if disconnected:record({'event':'client_disconnected','ordinal':ordinal})
            except urllib.error.HTTPError as exc:
                status = exc.code
                self.fail(status, f'Upstream HTTP {status}; reservation retained')
            except Exception as exc:
                # Do not persist exception strings: network errors can contain endpoint details.
                record({'event': 'transport_error', 'ordinal': ordinal, 'error_type': type(exc).__name__})
                try:
                    self.fail(502, 'Upstream transport error; reservation retained')
                except OSError:
                    pass
            finally:
                with lock:
                    if usage:
                        state['held_usd'] -= RESERVATION_USD - usage['conservative_cost_usd']
                        record({'event': 'settled', 'ordinal': ordinal, **usage,
                                'total_reserved_usd': state['held_usd'],
                                'basis': 'provider token counts at verified input/cached/output list rates; not an invoice'})
                    record({'event': 'finished', 'ordinal': ordinal, 'http_status': status,
                            'elapsed_seconds': time.monotonic() - started})
                    state['active'] -= 1
                    lock.notify_all()

    class AdmissionServer(ThreadingHTTPServer):
        # Child-agent bursts must not overflow the default five-connection backlog.
        request_queue_size = 64

    server = AdmissionServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = dict(os.environ, BIODEMO_MODAL_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1')
    policy = {'model': MODEL, 'serving_mode': 'shared', 'pricing_source': 'https://modal.com/library/zai/glm-5-3',
              'input_usd_per_million': 1.4, 'output_usd_per_million': 4.4,
              'cached_input_usd_per_million': .26,
              'proxy_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'maximum_admitted_requests': request_cap, 'reservation_per_request_usd': RESERVATION_USD,
              'maximum_campaign_reservation_usd': campaign_cap,
              'usage_status': 'conservative reservations, not a paid invoice',
              'runtime_difference': 'Loopback forwarding gate; bodies unchanged; full reservations retained unless provider usage settles them at uncached list rates.',
              'ledger': admission.name}
    (suite / 'modal-budget-policy.json').write_text(json.dumps(policy, indent=2) + '\n')
    try:
        command = args.command or [sys.executable, '-m', args.campaign_module, 'run',
            '--suite', str(suite), '--methods', args.method, '--limit', str(args.limit),
            '--operator-id', 'bounded-modal-benchmark']
        if args.provider_env and not args.command:
            command += ['--provider-env', str(args.provider_env.resolve())]
        completed = subprocess.run(command, env=env)
        if completed.returncode:
            raise SystemExit(completed.returncode)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
