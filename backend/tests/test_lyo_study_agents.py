"""Boundary tests: rejected decisions, tool isolation and immutable receipts."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def runner():
    try:
        return importlib.import_module('benchmarks.lyo_study.run_agents')
    except ModuleNotFoundError:
        pytest.fail('lyo runner has not been implemented')


@pytest.fixture
def packet():
    return {'case_id': 'case001', 'task': 'forecast', 'cutoff_h': 2,
            'objective': 'predict keep and select safe action', 'config': {},
            'observations': [], 'allowed_actions': [{'id': a, 'shelf_temperature_c': -20}
            for a in ('keep', 'cool', 'moderate', 'warm', 'characterize')]}


def decision(**updates):
    return dict(completion_time_h=12.5, thermal_warning=False, capacity_warning=None,
                action_id='keep', rationale='Observed trend', uncertainty='Unknown Kv',
                evidence=['observations'], **updates)


@pytest.mark.parametrize('key,value', [('completion_time_h', True), ('completion_time_h', float('nan')),
    ('completion_time_h', float('inf')), ('completion_time_h', -1), ('thermal_warning', 1),
    ('capacity_warning', 'false'), ('action_id', 'invented'), ('evidence', 'observations'),
    ('evidence', [3]), ('rationale', None), ('extra', 'unsupported')])
def test_rejects_invalid_submission(packet, tmp_path, key, value):
    host = runner().HostTools(packet, 'A', tmp_path)
    submitted = decision()
    submitted[key] = value
    assert 'error' in host.call('submit_decision', submitted)
    assert host.submission is None


def test_accepts_abstention_and_freezes_deep_copy(packet, tmp_path):
    host = runner().HostTools(packet, 'A', tmp_path)
    submitted = decision()
    submitted['completion_time_h'] = None
    assert host.call('submit_decision', submitted)['accepted'] is True
    submitted['evidence'].append('mutated')
    assert host.submission['evidence'] == ['observations']
    assert 'error' in host.call('submit_decision', decision())


def test_arm_a_cannot_access_model_or_override_actions(packet, tmp_path):
    module = runner()
    host = module.HostTools(packet, 'A', tmp_path)
    assert 'error' in host.call('physical_forward_model', {'action_id': 'keep'})
    host = module.HostTools(packet, 'B', tmp_path)
    assert 'error' in host.call('physical_forward_model', {'action_id': 'keep', 'parameter_overrides': {}})
    assert 'error' in host.call('physical_forward_model', {'action_id': 'unknown'})
    assert 'error' in host.call('physical_forward_model', {})


def test_budget_includes_failed_calls_and_submission(packet, tmp_path):
    host = runner().HostTools(packet, 'A', tmp_path, budget=2)
    host.call('not_a_tool', {})
    host.call('not_a_tool', {})
    assert 'budget' in host.call('submit_decision', decision())['error']
    assert host.submission is None


def test_strict_json_rejects_duplicate_keys_and_nonfinite():
    module = runner()
    for value in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}'):
        with pytest.raises(ValueError):
            module.strict_json(value)


def test_counterbalance_cycles_all_six_orders():
    module = runner()
    orders = [tuple(module.arm_order(i)) for i in range(6)]
    assert len(set(orders)) == 6
    assert all(set(order) == {'A', 'B', 'C'} for order in orders)


def test_existing_output_refused_before_provider_or_inference(tmp_path):
    module = runner()
    output = tmp_path / 'frozen'
    output.mkdir()
    (output / 'receipt.json').write_text('original')
    with pytest.raises(FileExistsError):
        module.execute(tmp_path / 'missing_dataset', output)
    assert (output / 'receipt.json').read_text() == 'original'


def test_completed_or_failed_receipt_never_retried(tmp_path):
    module = runner()
    work = tmp_path / 'attempts/case001/forecast/A'
    work.mkdir(parents=True)
    original = {'status': 'failed', 'error': 'recorded original failure'}
    (work / 'run.json').write_text(json.dumps(original))
    assert module.run_one(tmp_path / 'missing', tmp_path, 'case001', 'forecast', 'A', {}) == original


def test_preexisting_unfinished_attempt_is_recorded_not_retried(tmp_path):
    module = runner()
    work = tmp_path / 'attempts/case001/forecast/A'
    work.mkdir(parents=True)
    (work / 'events.jsonl').write_text('{"type":"model_start"}\n')
    value = module.run_one(tmp_path / 'missing', tmp_path, 'case001', 'forecast', 'A', {})
    assert value['status'] == 'interrupted'
    assert (work / 'events.jsonl').read_text() == '{"type":"model_start"}\n'
    assert json.loads((work / 'run.json').read_text()) == value


def test_run_one_preserves_usage_and_invalid_tool_then_submission(tmp_path, packet, monkeypatch):
    module = runner()
    dataset = tmp_path / 'dataset'
    public = dataset / 'public/case001'
    public.mkdir(parents=True)
    raw = json.dumps(packet, indent=3)
    (public / 'forecast.json').write_text(raw)
    # The fake executable replaces only the external SDK/model boundary.
    node = tmp_path / 'fake_node'
    node.write_text('#!/usr/bin/env python3\n' + '''import json,sys
request=json.loads(input())
print(json.dumps({'type':'model_start','ordinal':1}),flush=True)
print(json.dumps({'type':'model_usage','usage':{'input':10,'output':20}}),flush=True)
print(json.dumps({'type':'tool_request','id':'1','name':'physical_forward_model','args':{'action_id':'keep'}}),flush=True)
assert 'error' in json.loads(input())['result']
submission={'completion_time_h':12.5,'thermal_warning':False,'capacity_warning':None,'action_id':'keep','rationale':'trend','uncertainty':'Kv','evidence':['observations']}
print(json.dumps({'type':'tool_request','id':'2','name':'submit_decision','args':submission}),flush=True)
assert json.loads(input())['result']['accepted']
print(json.dumps({'type':'finished','status':'completed','model_calls':1,'usage':[{'input':10,'output':20}]}),flush=True)
''')
    node.chmod(0o755)
    monkeypatch.setattr(module.shutil, 'which', lambda _: str(node))
    protocol = {'model':'modal/fake','wall_seconds':5,'tool_calls':8,'model_calls':4,'max_output_tokens':4096}
    result = module.run_one(dataset, tmp_path / 'output', 'case001', 'forecast', 'A', protocol)
    assert result['status'] == 'completed'
    assert result['usage'] == [{'input':10,'output':20}]
    assert result['tool_calls'] == 2
    assert result['submission']['completion_time_h'] == 12.5
    work = tmp_path / 'output/attempts/case001/forecast/A'
    assert (work / 'agent-input/packet.json').read_text() == raw
    assert len((work / 'tools.jsonl').read_text().splitlines()) == 2
    assert not (work / 'run.json').read_text().find('hidden_score') >= 0


def test_run_one_timeout_kills_descendants_and_retains_usage(tmp_path, packet, monkeypatch):
    import os
    import time
    module = runner()
    public = tmp_path / 'dataset/public/case001'
    public.mkdir(parents=True)
    (public / 'forecast.json').write_text(json.dumps(packet))
    node = tmp_path / 'sleeping_node'
    child_pid_path = tmp_path / 'child.pid'
    node.write_text('#!/usr/bin/env python3\n' + f'''import json,subprocess,sys,time
input()
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
open({str(child_pid_path)!r},'w').write(str(child.pid))
print(json.dumps({{'type':'model_usage','usage':{{'input':10,'output':1}}}}),flush=True)
time.sleep(60)
''')
    node.chmod(0o755)
    monkeypatch.setattr(module.shutil, 'which', lambda _: str(node))
    protocol = {'model':'modal/fake','wall_seconds':2,'tool_calls':8,'model_calls':4,'max_output_tokens':4096}
    started = time.monotonic()
    result = module.run_one(tmp_path / 'dataset', tmp_path / 'output', 'case001', 'forecast', 'A', protocol)
    assert result['status'] == 'timeout'
    assert result['usage'] == [{'input':10,'output':1}]
    assert time.monotonic() - started < 8
    pid = int(child_pid_path.read_text())
    # macOS reaps the terminated descendant promptly; allow scheduling latency.
    for _ in range(30):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail('SDK descendant survived the timeout')


def test_timeout_kills_child_that_ignores_sigterm(tmp_path, packet, monkeypatch):
    import os
    import signal
    import time
    module = runner()
    public = tmp_path / 'dataset/public/case001'
    public.mkdir(parents=True)
    (public / 'forecast.json').write_text(json.dumps(packet))
    pid_path = tmp_path / 'resistant.pid'
    node = tmp_path / 'resistant_node'
    child_code = 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'
    node.write_text('#!/usr/bin/env python3\n' + f'''import subprocess,sys,time
input()
child=subprocess.Popen([sys.executable,'-c',{child_code!r}])
open({str(pid_path)!r},'w').write(str(child.pid))
time.sleep(60)
''')
    node.chmod(0o755)
    monkeypatch.setattr(module.shutil, 'which', lambda _: str(node))
    protocol = {'model':'modal/fake','wall_seconds':2,'tool_calls':8,'model_calls':4,'max_output_tokens':4096}
    started = time.monotonic()
    result = module.run_one(tmp_path / 'dataset', tmp_path / 'output', 'case001', 'forecast', 'A', protocol)
    assert time.monotonic() - started < 8, 'Resistant child kept inherited pipes open'
    assert result['status'] == 'timeout'
    pid = int(pid_path.read_text())
    survived = True
    for _ in range(30):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            survived = False
            break
        time.sleep(0.02)
    if survived:
        os.kill(pid, signal.SIGKILL)
    assert not survived, 'A child ignoring SIGTERM must be force-killed after parent exit'


def test_resume_interrupted_attempt_recovers_recorded_usage_and_submission(tmp_path):
    module = runner()
    work = tmp_path / 'attempts/case001/forecast/A'
    work.mkdir(parents=True)
    (work / 'events.jsonl').write_text(json.dumps({'type':'model_usage','usage':{'input':7,'output':3}})+'\n')
    (work / 'tools.jsonl').write_text(json.dumps({'name':'submit_decision','arguments':decision(),
                                               'result':{'accepted':True,'decision_frozen':True}})+'\n')
    value = module.run_one(tmp_path / 'missing', tmp_path, 'case001', 'forecast', 'A', {})
    assert value['status'] == 'interrupted'
    assert value['usage'] == [{'input':7,'output':3}]
    assert value['submission'] == decision()


def test_execute_verifies_frozen_dataset_before_creating_output(tmp_path, monkeypatch):
    module = runner()
    from benchmarks.lyo_study import study
    def reject(_dataset):
        raise ValueError('frozen dataset changed')
    monkeypatch.setattr(study, 'verify_dataset', reject)
    output = tmp_path / 'must-not-exist'
    with pytest.raises(ValueError, match='frozen dataset changed'):
        module.execute(tmp_path / 'invalid', output)
    assert not output.exists()


def test_symlink_module_path_resolves_real_backend_sources(tmp_path, packet, monkeypatch):
    module = runner()
    from benchmarks.lyo_study import study
    alias = tmp_path / 'alias/benchmarks/lyo_study/run_agents.py'
    alias.parent.mkdir(parents=True)
    alias.symlink_to(Path(module.__file__).resolve())
    monkeypatch.setattr(module, '__file__', str(alias))
    monkeypatch.setattr(study, 'verify_dataset', lambda _: {'files_verified': 2})
    monkeypatch.setattr(module, 'hosted_research_profile', lambda: SimpleNamespace(provider='modal', model='test'))
    monkeypatch.setattr(module, 'isolation_probe', lambda _: {'passed': True})
    monkeypatch.setattr(module, 'run_one', lambda *args, **kwargs: {'status':'preflight_passed'})
    dataset = tmp_path / 'dataset'
    public = dataset / 'public/case001'
    public.mkdir(parents=True)
    (dataset / 'protocol.json').write_text('{}')
    for task in ('forecast', 'pretransfer'):
        (public / (task + '.json')).write_text(json.dumps(dict(packet, task=task)))
    output = tmp_path / 'result'
    assert module.execute(dataset, output, preflight_only=True)['status'] == 'preflight_passed'
    assert (output / 'runner-source/provider_config.mjs').is_file()
    assert (output / 'runner-source/sdk_experiment.mjs').is_file()


def test_cleanup_reaps_already_exited_process_group():
    import subprocess,sys
    module = runner()
    process = subprocess.Popen([sys.executable, '-c', 'print("finished")'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True, text=True)
    assert process.stdout.read().strip() == 'finished'
    assert hasattr(module, 'cleanup_process'), 'cleanup must be isolated and receipt-safe'
    assert module.cleanup_process(process, []) == []
    assert process.returncode == 0


def test_cleanup_records_close_error_without_raising():
    module = runner()
    class FailedClose:
        def close(self): raise BrokenPipeError('already closed')
    class Process:
        pid = 999999999
        stdin = stdout = stderr = FailedClose()
        def poll(self): return 0
        def wait(self, **kwargs): return 0
    assert hasattr(module, 'cleanup_process'), 'cleanup must be receipt-safe'
    errors = module.cleanup_process(Process(), [])
    assert len(errors) == 3
    assert all('BrokenPipeError' in error for error in errors)


def recovery():
    try: return importlib.import_module('benchmarks.lyo_study.recovery')
    except ModuleNotFoundError: pytest.fail('recovery not implemented')


def test_recovery_preserves_failures_recovers_matched_journals_and_selects_only_untouched(tmp_path, packet):
    module = recovery()
    original = tmp_path / 'original'
    original.mkdir()
    protocol = {'case_ids':['case001'], 'tasks':['forecast','pretransfer'], 'arms':['A','B','C'], 'model':'modal/test'}
    (original / 'protocol.json').write_text(json.dumps(protocol))
    def attempt(task, arm):
        path = original / 'attempts/case001' / task / arm
        path.mkdir(parents=True)
        return path
    failed = {'case_id':'case001','task':'forecast','arm':'A','status':'no_submission','submission':None}
    (attempt('forecast','A') / 'run.json').write_text(json.dumps(failed))
    p = attempt('forecast','B')
    (p / 'agent-input').mkdir()
    (p / 'agent-input/packet.json').write_text(json.dumps(packet))
    finished = {'type':'finished','status':'completed','decision':decision(),'model_calls':2,'usage':[{'input':7,'output':3}]}
    (p / 'events.jsonl').write_text(json.dumps(finished)+'\n')
    (p / 'tools.jsonl').write_text(json.dumps({'name':'submit_decision','arguments':decision(),'result':{'accepted':True}})+'\n')
    bad = attempt('pretransfer','A')
    (bad / 'events.jsonl').write_text(json.dumps(finished)+'\n')
    (bad / 'tools.jsonl').write_text(json.dumps({'name':'submit_decision','arguments':dict(decision(),action_id='cool'),'result':{'accepted':True}})+'\n')
    attempt('pretransfer','B')  # Empty directories are attempts too, never retries.
    audit = module.audit_original(original)
    assert audit['untouched'] == [{'case_id':'case001','task':'forecast','arm':'C'}, {'case_id':'case001','task':'pretransfer','arm':'C'}]
    rows = {(r['task'],r['arm']):r for r in audit['records']}
    assert rows['forecast','A']['status'] == 'no_submission'
    assert rows['forecast','B']['status'] == 'completed'
    assert rows['forecast','B']['model_calls'] == 2
    assert rows['forecast','B']['usage'] == [{'input':7,'output':3}]
    assert rows['forecast','B']['submission'] == decision()
    assert rows['pretransfer','A']['status'] == 'infrastructure_error'
    assert rows['pretransfer','B']['status'] == 'infrastructure_error'
    assert not (p / 'run.json').exists()


def test_recovery_budget_retains_unsettled_finished_reservations(tmp_path):
    module = recovery()
    entries = [{'event':'reserved','ordinal':1,'reserved_usd':2.25},
               {'event':'settled','ordinal':1,'conservative_cost_usd':1.25},
               {'event':'finished','ordinal':1},
               {'event':'reserved','ordinal':2,'reserved_usd':2.25},
               {'event':'finished','ordinal':2}]
    ledger = tmp_path / 'modal-admission.jsonl'
    ledger.write_text(''.join(json.dumps(row)+'\n' for row in entries))
    result = module.campaign_balance(tmp_path)
    assert result['original_held_usd'] == 3.5
    assert result['remaining_cap_usd'] == 6.5
    with ledger.open('a') as handle:
        handle.write(json.dumps({'event':'reserved','ordinal':3,'reserved_usd':2.25})+'\n')
    with pytest.raises(ValueError, match='not all finished'):
        module.campaign_balance(tmp_path)


def test_recovery_preparation_freezes_original_and_rejects_excess_budget(tmp_path, packet, monkeypatch):
    module = recovery()
    original = tmp_path / 'original'
    original.mkdir()
    dataset = tmp_path / 'dataset'
    public = dataset / 'public/case001'
    public.mkdir(parents=True)
    (public / 'forecast.json').write_text(json.dumps(packet))
    (dataset / 'protocol.json').write_text('{}')
    primary = runner()
    from benchmarks.lyo_study import study
    monkeypatch.setattr(study, 'verify_dataset', lambda _: {'files_verified': 2})
    source = Path(primary.__file__).resolve()
    sources = [source,source.with_name('sdk_experiment.mjs'),source.with_name('study.py'),
               source.parents[1]/'physics_value/research_sandbox.py',source.parents[2]/'src/prime_runtime/provider_config.mjs']
    import hashlib
    protocol = {'case_ids':['case001'],'tasks':['forecast'],'arms':['A','B','C'],
        'runner_sha256':{p.name:primary.digest(p) for p in sources},
        'system_prompt_sha256':hashlib.sha256(primary.SYSTEM.encode()).hexdigest(),
        'dataset_protocol_sha256':primary.digest(dataset/'protocol.json'),
        'public_packet_sha256':{'case001/forecast':primary.digest(public/'forecast.json')}}
    (original/'protocol.json').write_text(json.dumps(protocol))
    campaign=tmp_path/'campaign'
    campaign.mkdir()
    (campaign/'modal-admission.jsonl').write_text('\n'.join(json.dumps(row) for row in [
        {'event':'reserved','ordinal':1,'reserved_usd':2.25},
        {'event':'settled','ordinal':1,'conservative_cost_usd':1}, {'event':'finished','ordinal':1}])+'\n')
    output=tmp_path/'recovered'
    result=module.recover(dataset,original,output,campaign)
    assert result['status']=='prepared_no_inference'
    assert len(result['untouched'])==3
    before=(output/'recovery-protocol.json').read_bytes()
    continuation=tmp_path/'continuation'
    continuation.mkdir()
    (continuation/'modal-budget-policy.json').write_text(json.dumps({'maximum_campaign_reservation_usd':10}))
    monkeypatch.setenv('BIODEMO_MODAL_BASE_URL','http://127.0.0.1:9999/v1')
    with pytest.raises(ValueError,match='exceeds remaining'):
        module.recover(dataset,original,output,campaign,execute=True,continuation_campaign=continuation)
    assert (output/'recovery-protocol.json').read_bytes()==before
    assert not (output/'attempts').exists()


def test_versioned_protocol_can_select_sdk_and_common_prompt(tmp_path, packet, monkeypatch):
    module=runner()
    public=tmp_path/'dataset/public/case001'
    public.mkdir(parents=True)
    (public/'forecast.json').write_text(json.dumps(packet))
    node=tmp_path/'fake_node'
    node.write_text('#!/usr/bin/env python3\n'+'''import json,sys
request=json.loads(input())
assert request['system_prompt']=='sensitivity common prompt'
assert sys.argv[1].endswith('sdk_sensitivity.mjs')
assert request['max_model_calls']==8
print(json.dumps({'type':'finished','status':'preflight_passed','usage':[],'model_calls':0}),flush=True)
''')
    node.chmod(0o755)
    monkeypatch.setattr(module.shutil,'which',lambda _:str(node))
    protocol={'model':'modal/fake','wall_seconds':240,'tool_calls':8,'model_calls':8,'max_output_tokens':4096,
              'system_prompt':'sensitivity common prompt','sdk_script':str(tmp_path/'sdk_sensitivity.mjs')}
    row=module.run_one(tmp_path/'dataset',tmp_path/'output','case001','forecast','A',protocol,preflight=True)
    assert row['status']=='preflight_passed'
    import hashlib
    assert row['system_prompt_sha256']==hashlib.sha256(b'sensitivity common prompt').hexdigest()


def test_sensitivity_samples_lexical_case_per_family_without_outcome_selection(tmp_path):
    try: module=importlib.import_module('benchmarks.lyo_study.sensitivity')
    except ModuleNotFoundError: pytest.fail('sensitivity not implemented')
    for case,family,outcome in [('z','nominal',1),('a','nominal',99),('c','capacity',99),('b','capacity',1)]:
        path=tmp_path/'evaluator'/case
        path.mkdir(parents=True)
        (path/'forecast.json').write_text(json.dumps({'family':family,'outcomes':{'irrelevant':outcome}}))
    selected=module.select_cases(tmp_path)
    assert selected=={'capacity':'b','nominal':'a'}


def test_sensitivity_last_provider_request_exposes_only_submission():
    import subprocess
    module_path=Path(runner().__file__).resolve().with_name('sdk_sensitivity_policy.mjs')
    script=f'''import {{ applySubmissionOnlyPolicy }} from {json.dumps(module_path.as_uri())};
const make=()=>({{tools:['python_analysis','submit_decision','physical_forward_model'].map(name=>({{type:'function',function:{{name}}}}))}});
const earlier=make(),final=make();
applySubmissionOnlyPolicy(earlier,7,8); applySubmissionOnlyPolicy(final,8,8);
console.log(JSON.stringify({{earlier,final}}));'''
    result=subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True)
    assert result.returncode==0, result.stderr
    value=json.loads(result.stdout)
    assert len(value['earlier']['tools'])==3
    assert value['final']['tools']==[{'type':'function','function':{'name':'submit_decision'}}]
    assert value['final']['tool_choice']=={'type':'function','function':{'name':'submit_decision'}}
