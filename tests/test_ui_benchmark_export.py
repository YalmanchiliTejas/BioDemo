import hashlib
import json
from pathlib import Path
import pytest
from ui.scripts.export_benchmarks import export, trajectory


def record(root,id,case,bid,*,failed=False,pending=False):
    path=root/'results/evaluation'/id;path.mkdir(parents=True)
    analysis={} if failed else {'report_status':'complete_for_available_evidence','investigation_status':'complete',
        'source_verification_status':'human_review_pending' if pending else 'automatically_verified',
        'assessment':'Evidence-grounded investigation; cause unknown.',
        'verification':{'evidence_checks':{'sample':{'source_integrity':True,'value_matches':None if pending else True}},
                        'pending_source_review_count':int(pending),'numerical_metrics_verified':2}}
    output={'analysis':analysis}
    (path/'output.json').write_text(json.dumps(output))
    run={'run_id':id,'case_id':case,'benchmark_id':bid,'condition':'raw','mode':'full_rlm',
         'status':'failed' if failed else 'incomplete' if pending else 'completed',
         'started_at':'2026-10-18T00:00:00Z','ended_at':'2026-10-18T00:01:00Z','wall_clock_seconds':60,
         'execution_budgets':{'wall_clock_seconds':1800,'tool_calls':48},'case':{'task_spec_sha256':'frozen-case'},
         'output':output if not failed else {},'output_sha256':hashlib.sha256((path/'output.json').read_bytes()).hexdigest(),
         'usage':{'total_cost_usd':0,'cost_status':'unknown_provider_or_child_telemetry'}}
    if not failed:run.update(execution_status='completed',investigation_status='complete',source_verification_status=analysis['source_verification_status'])
    (path/'run.json').write_text(json.dumps(run))
    return {'case':case,'run':str(path/'run.json')}


@pytest.fixture
def batch(tmp_path):
    logs=tmp_path/'results/background-logs';logs.mkdir(parents=True)
    cho=[record(tmp_path,'a'*32,'CHO-01','cho',failed=True),record(tmp_path,'b'*32,'CHO-04','cho')]
    fre=[record(tmp_path,'c'*32,'FRE-02','fresenius',pending=True)]
    for bid,entries in [('cho',cho),('fresenius',fre)]:
        (logs/(bid+'-20261017-224014.log')).write_text('\n'.join(json.dumps(e) for e in entries)+'\n')
    return tmp_path


def test_ui_exports_all_attempts_and_separates_source_pending_from_incomplete_work(batch):
    payload=export(batch);runs=payload['runs']
    assert len(runs)==3 and not payload['unavailable_records']
    assert runs[0]['execution_status']=='failed' and runs[0]['calculation_count'] is None
    assert runs[1]['label']=='Final report · source checks passed'
    assert runs[2]['investigation_status']=='complete' and runs[2]['recorded_status']=='incomplete'
    assert runs[2]['label']=='Final report · source review pending'
    assert all(r['usage']['total_cost_usd'] is None for r in runs)
    assert all(not r['scientifically_qualified'] for r in runs)
    assert (batch/'ui/public/benchmarks'/('c'*32+'.json')).exists()


def test_ui_export_works_after_runtime_stores_have_been_offloaded(batch):
    assert not (batch/'benchmarks/runtime').exists()
    assert len(export(batch)['runs'])==3


def test_public_export_redacts_local_paths_without_changing_failure_records(batch):
    path=batch/'results/evaluation'/('a'*32)/'run.json'
    run=json.loads(path.read_text())
    run['reason']='TimeoutError in /Users/alice/Desktop/BioDemo/src/prime_runtime/sdk_runner.mjs'
    path.write_text(json.dumps(run)); original=path.read_bytes()
    export(batch)
    detail=json.loads((batch/'ui/public/benchmarks'/('a'*32+'.json')).read_text())
    assert 'TimeoutError' in detail['diagnostic']
    assert '/Users/alice' not in detail['diagnostic']
    assert path.read_bytes()==original


def test_ui_export_rejects_changed_output_instead_of_displaying_verified_numbers(batch):
    (batch/'results/evaluation'/('b'*32)/'output.json').write_text('changed')
    with pytest.raises(ValueError,match='checksum mismatch'):export(batch)


def test_ui_export_keeps_missing_run_records_visible(batch):
    (batch/'results/evaluation'/('a'*32)/'run.json').unlink()
    payload=export(batch)
    assert len(payload['runs'])==2 and payload['unavailable_records'][0]['run_id']=='a'*32


def test_source_trajectory_requires_matching_frozen_bytes_and_source_times(tmp_path):
    from openpyxl import Workbook
    base=tmp_path/'benchmarks/cho/raw/workbooks';base.mkdir(parents=True);path=base/'example.xlsx'
    book=Workbook();book.remove(book.active)
    for reactor,values in [('R01',[98,95]),('R02',[97,10])]:
        sheet=book.create_sheet(reactor+'_offline');sheet.append(['Time (h)','Viability Mean (%)'])
        for time,value in zip([0,24],values):sheet.append([time,value])
    book.save(path);book.close()
    run={'case':{'allowlist':[{'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]}}
    checks={reactor:{'source_integrity':True,'value_matches':True,'observed':str(value),
        'source_ref':{'path':path.name,'row':3,'sheet':reactor+'_offline','column':'Viability Mean (%)'}} for reactor,value in [('R01',95),('R02',10)]}
    example=trajectory(tmp_path,run,checks)
    assert [s['points'][-1]['value'] for s in example['series']]==[95,10]
    assert all(s['points'][-1]['time_hours']==24 for s in example['series'])
    path.write_bytes(path.read_bytes()+b'changed')
    assert trajectory(tmp_path,run,checks) is None
