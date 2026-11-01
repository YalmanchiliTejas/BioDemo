"""The paid dispatch gate must account for concurrent requests and failures."""
import http.client
import importlib.util
import io
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import pytest


@pytest.mark.parametrize('settled', [False, True])
def test_proxy_caps_all_requests_preserves_payload_and_never_logs_secrets(tmp_path, monkeypatch, settled):
    script = Path(__file__).resolve().parents[1] / 'scripts/run_bounded_agent_benchmark.py'
    spec = importlib.util.spec_from_file_location('bounded_benchmark', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'MAX_REQUESTS', 15 if settled else 8)
    monkeypatch.setattr(module, 'CAMPAIGN_USD', 2.26 if settled else 18.0)
    config = tmp_path / '.prime/agent'
    config.mkdir(parents=True)
    (config / 'models.json').write_text(json.dumps({'providers': {'modal': {
        'baseUrl': 'https://gauntlet--ep-glm-5-3-server.us-west.modal.direct/v1'}}}))
    suite = tmp_path / 'suite'
    suite.mkdir()
    monkeypatch.setattr(module.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(sys, 'argv', [str(script), '--suite', str(suite)])
    forwarded = []
    guard = threading.Lock()

    class Reply:
        status = 200
        headers = {'Content-Type': 'application/json'}
        def __init__(self):
            self.stream = io.BytesIO(b'{"usage":{"prompt_tokens":10,"completion_tokens":1}}' if settled else b'{"choices":[]}')
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read1(self, size):
            return self.stream.read(size)

    def upstream(request, timeout):
        assert request.headers['Authorization'] == 'Bearer private-test-token'
        body = json.loads(request.data)
        assert body['messages'][0]['content'] == 'private-test-prompt'
        with guard:
            forwarded.append(body)
            first = len(forwarded) == 1
        # Even upstream failures must consume their reservation.
        if first and not settled:
            raise OSError('private-test-network-error')
        return Reply()

    monkeypatch.setattr(module.urllib.request, 'urlopen', upstream)

    def run_child(command, env):
        from urllib.parse import urlsplit
        target = urlsplit(env['BIODEMO_MODAL_BASE_URL'])
        def send(body):
            connection = http.client.HTTPConnection(target.hostname, target.port, timeout=10)
            connection.request('POST', '/v1/chat/completions', json.dumps(body),
                {'Authorization': 'Bearer private-test-token', 'Content-Type': 'application/json'})
            reply = connection.getresponse()
            reply.read()
            status = reply.status
            connection.close()
            return status
        valid = {'model': module.MODEL, 'max_tokens': 131072,
                 'messages': [{'role': 'user', 'content': 'private-test-prompt'}]}
        assert send({**valid, 'max_tokens': 131073}) == 400
        assert send({**valid, 'model': 'another-model'}) == 400
        assert send({k: v for k, v in valid.items() if k != 'max_tokens'}) == 400
        completion_limit = {**valid, 'max_completion_tokens': valid['max_tokens']}
        del completion_limit['max_tokens']
        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(lambda i: send(valid if i % 2 else completion_limit), range(15)))
        assert statuses.count(402) == (0 if settled else 7)
        assert statuses.count(502) == (0 if settled else 1)
        assert statuses.count(200) == (15 if settled else 7)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, 'run', run_child)
    module.main()
    assert len(forwarded) == (15 if settled else 8)
    records = [json.loads(line) for line in (suite / 'modal-admission.jsonl').read_text().splitlines()]
    reserved = [r for r in records if r['event'] == 'reserved']
    assert len(reserved) == (15 if settled else 8)
    assert max(r['total_reserved_usd'] for r in reserved) <= module.CAMPAIGN_USD
    if not settled:
        assert max(r['total_reserved_usd'] for r in reserved) == 18
    assert 1048576 * 1.4 / 1e6 + 131072 * 4.4 / 1e6 < module.RESERVATION_USD
    for path in suite.iterdir():
        assert 'private-test' not in path.read_text()


def test_usage_settlement_requires_complete_bounded_provider_counters():
    script = Path(__file__).resolve().parents[1] / 'scripts/run_bounded_agent_benchmark.py'
    spec = importlib.util.spec_from_file_location('bounded_usage', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.response_usage(b'data: {"usage":{"prompt_tokens":1000,"completion_tokens":500}}\n\ndata: [DONE]\n')['conservative_cost_usd'] == .0036
    assert module.response_usage(b'{"usage":{"prompt_tokens":1000}}') is None
    assert module.response_usage(b'{"usage":{"prompt_tokens":-1,"completion_tokens":0}}') is None
    assert module.response_usage(b'{"usage":{"prompt_tokens":2000000,"completion_tokens":0}}') is None
    cached=module.response_usage(b'{"usage":{"prompt_tokens":1000,"completion_tokens":500,"prompt_tokens_details":{"cached_tokens":500}}}')
    assert cached['conservative_cost_usd']==.00303
    assert cached['uncached_rate_estimate_usd']==.0036


def test_cancelled_sdk_sink_still_drains_provider_usage():
    script=Path(__file__).resolve().parents[1]/'scripts/run_bounded_agent_benchmark.py'
    spec=importlib.util.spec_from_file_location('bounded_drain',script);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    class Reply:
        def __init__(self):self.chunks=iter([b'data: {"choices":[]}\n',b'data: {"usage":{"prompt_tokens":1000,"completion_tokens":500}}\n',b''])
        def read1(self,size):return next(self.chunks)
    def closed(chunk):raise BrokenPipeError()
    usage,disconnected=module.drain_response(Reply(),closed)
    assert disconnected and usage['conservative_cost_usd']==.0036
