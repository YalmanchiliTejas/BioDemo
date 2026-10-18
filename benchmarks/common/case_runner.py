"""Case-based operations called by the existing benchmark entry point."""
from __future__ import annotations

import json
import os
import platform
import shutil
import tempfile
import time
import uuid
import subprocess
from pathlib import Path

from .case_audit import audit_case
from .case_protocol import ROOT, VERSION, GROUPS, digest, load_case, save
from .trace import TraceSink, now
from .objective_scores import score_objective
from .quality import score_review


def run_case(manifest_path, mode, *, output_root=None, isolated=True, operator_id=None, agent_adapter=None, prior_run=None, operational_triage_policy=None):
    if mode not in GROUPS:raise ValueError('unsupported comparison group')
    from src.workflows.triage import validate_policy
    from .case_protocol import stable_hash
    operational_triage_policy=validate_policy(operational_triage_policy)
    manifest_path=Path(manifest_path).resolve();case=load_case(manifest_path)
    run_id=uuid.uuid4().hex
    directory=Path(output_root or ROOT/'results/evaluation')/run_id
    directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    environment={'python':platform.python_version(),'system':platform.system(),'adapter_version':VERSION,
                 'adapter_sha256':digest(ROOT/'benchmarks/common/agent_adapter.py'),
                 'runner_sha256':digest(Path(__file__)),
                 'scorer_sha256':digest(ROOT/'benchmarks/common/objective_scores.py'),
                 'quality_scorer_sha256':digest(ROOT/'benchmarks/common/quality.py'),
                 'full_adapter_sha256':digest(ROOT/'benchmarks/common/full_agent_adapter.py'),
                 'operational_triage_policy_sha256':stable_hash(operational_triage_policy)}
    code=subprocess.run(['git','-c','core.fsmonitor=false','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True)
    sources=[p for base in ('src','prime_skills','benchmarks/common','benchmarks/baselines') for p in (ROOT/base).rglob('*')
             if p.is_file() and p.suffix in {'.py','.mjs','.md','.json'} and '__pycache__' not in p.parts]
    environment.update(code_commit=code.stdout.strip() or None,
        working_tree_code_sha256=stable_hash({str(p.relative_to(ROOT)):digest(p) for p in sorted(sources)}),
        system_prompt_sha256=digest(ROOT/'src/prime_runtime/system_prompt.md'),
        skill_sha256=digest(ROOT/'prime_skills/manufacturing_os/SKILL.md'),
        sampling_settings={'provider_seed':None,'temperature':None,'status':'provider_default_not_pinned'},
        machine=platform.machine(),processor=platform.processor(),
        provider_model_requested=os.environ.get('BIODEMO_PRIME_MODEL'))
    sink=TraceSink(directory/'trace.jsonl',case['case_id'],run_id,environment=environment,budgets=case['budgets'])
    run={'version':VERSION,'run_id':run_id,'case_id':case['case_id'],'benchmark_id':case['benchmark_id'],
         'case':case,'mode':mode,'condition':case['condition'],'started_at':now(),'attempted':False,
         'operator_id':operator_id,'environment':environment,'trace_path':'trace.jsonl',
         'model':None,'prompt_version':None,'execution_budgets':case['budgets'],'seed':case['seed'],
         'seed_scope':'Source generation and format challenge; provider sampling seed is not controlled.',
         'operational_triage_policy':operational_triage_policy}
    shutil.copyfile(manifest_path,directory/'case.json')
    policy=json.loads((manifest_path.parent/case['quality_policy']).read_text());run['quality_policy']=policy
    shutil.copyfile(manifest_path.parent/case['quality_policy'], directory/'quality-policy.json')
    if mode in ('manual','incumbent') or case['condition_status']!='ready' or (case.get('update_requires_prior_run') and not prior_run):
        run.update(status='not_tested',reason='Requires observed hands-on workflow; no marketing comparison or fabricated output.' if mode in ('manual','incumbent') else 'Updated SDK trial requires --prior-run from the earlier completed isolated investigation.' if case.get('update_requires_prior_run') else case['condition_reason'])
        sink.emit(actor='evaluator',stage='setup',action='comparison_not_executed',status='unresolved')
    else:
        with sink.interval(actor='evaluator',stage='verification',action='leakage_and_version_audit'):
            run['audit']=audit_case(manifest_path)
        if not run['audit']['pass']:
            run.update(status='invalid',reason='Package audit failed; execution and scores withheld.')
        else:
            run['attempted']=True
            started=time.monotonic()
            from .persistent_trial import trial_workspace
            try:
                with tempfile.TemporaryDirectory(prefix='benchmark-case-') as temp, trial_workspace(case,run_id,mode,prior_run) as persistent:
                    staged=(persistent or Path(temp))/'agent_input';staged.mkdir(exist_ok=True)
                    if persistent:
                        run['runtime_workspace']=str(persistent)
                        run['prior_run_id']=json.loads(Path(prior_run).read_text())['run_id'] if prior_run else None
                        # Remove only prior generated inputs in this validated owned workspace.
                        allowed={f['path'] for f in case['allowlist']}
                        for existing in staged.rglob('*'):
                            if existing.is_file() and str(existing.relative_to(staged)) not in allowed:existing.unlink()
                    for source in case['allowlist']:
                        destination=staged/source['path'];destination.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copyfile(manifest_path.parent/case['input_root']/source['path'],destination)
                        if case.get('as_of'):
                            from .trace import instant
                            # The independently rebuilt snapshot establishes the
                            # synthetic document cutoff; packaging wall time is not
                            # the document's historical availability.
                            available = instant(case['as_of']).timestamp()
                            os.utime(destination, (available, available))
                    worker_trace=Path(temp)/'trace.jsonl'
                    configuration={'mode':mode,'case_id':case['case_id'],'run_id':run_id,'trace_path':str(worker_trace),
                                   'investigation_baselines':True,
                                   'budgets':case['budgets'],'execution_policy':case.get('execution_policy',{'mode':'fixed_v1'}),'access_scope':case['access_scope'],'tenant':case['tenant'],
                                   'operational_triage_policy':operational_triage_policy,
                                   'evaluation_time':now(),'seed':case['seed'], 'capture_records':True,
                                   'capture_preview_rows':2 if sum(f['bytes'] for f in case['allowlist'])>50*1024*1024 else None,
                                   'summarize_numeric':mode=='retrieval_llm', 'retrieval_max_records':96,
                                   'artifact_directory':str(Path(temp)/'runtime-artifacts'), 'state_directory':str((persistent or Path(temp))/'state'),
                                   'hidden_paths':[str(manifest_path.parent/case[k]) for k in ('reference','quality_policy','triage_policy')]}
                    try:
                        with sink.interval(actor='pipeline' if mode=='conventional' else 'agent',stage='ingestion' if mode=='conventional' else 'investigation',action='execute_case') as event:
                            if agent_adapter:
                                # Dependency injection is for tests; never publication eligible.
                                from .agent_adapter import InvestigationInput
                                output=agent_adapter.run_investigation(InvestigationInput(staged,case['objective'],case.get('as_of'),configuration))
                                output['isolation_audit']={'pass':False,'reason':'Injected test adapter; no OS publication audit.'}
                            elif isolated:
                                from .isolated_runner import run_isolated
                                output=run_isolated(staged,case['objective'],case.get('as_of'),configuration)
                            else:
                                from .agent_adapter import run_investigation
                                output=run_investigation(staged,case['objective'],case.get('as_of'),configuration)
                                output['isolation_audit']={'pass':False,'reason':'Development run without OS isolation.'}
                            event.update(output_refs=['output.json'],input_tokens=output.get('usage',{}).get('input_tokens'),
                                         output_tokens=output.get('usage',{}).get('output_tokens'),
                                         estimated_cost_usd=output.get('usage',{}).get('inference_cost_usd'))
                        save(directory/'output.json',output)
                        run.update(status='completed',output=output,output_sha256=digest(directory/'output.json'),
                                   model=output.get('usage',{}).get('model_id'),
                                   isolation_audit=output.get('isolation_audit',{}),usage=output.get('usage',{}))
                        if output.get('analysis',{}).get('report_status')=='incomplete':
                            run.update(status='incomplete',reason='Execution returned a partial investigation; coverage or verification remains unresolved.')
                        analysis=output.get('analysis',{})
                        run.update(execution_status='completed',investigation_status=analysis.get('investigation_status','incomplete' if analysis.get('report_status')=='incomplete' else 'complete' if analysis.get('report_status')=='complete_for_available_evidence' else 'evaluation_unavailable'),
                                   source_verification_status=analysis.get('source_verification_status','evaluation_unavailable'),
                                   scientific_validation_status='independent_review_pending')
                        if analysis.get('source_verification_status')=='human_review_pending' and analysis.get('investigation_status')=='complete':
                            run.update(status='incomplete',reason='Investigation is complete for available evidence; source verification awaits human review. Scientific qualification remains pending.')
                        with sink.interval(actor='evaluator',stage='verification',action='post_execution_package_audit'):
                            modified=[f['path'] for f in case['allowlist'] if not (staged/f['path']).is_file() or digest(staged/f['path'])!=f['sha256']]
                            extra={str(p.relative_to(staged)) for p in staged.rglob('*') if p.is_file()}-{f['path'] for f in case['allowlist']}
                            if modified or extra:
                                run['audit']['pass']=False;run['audit']['failures'].append('Agent modified or added source files.')
                        if run['audit']['pass'] and run['isolation_audit'].get('pass'):
                            reference=json.loads((manifest_path.parent/case['reference']).read_text())
                            run['objective_scores']=score_objective(output,reference,case,staged)
                        else:
                            run['score_status']='withheld_failed_permission_or_source_audit'
                    except Exception as exc:
                        run.update(status='failed',error_code=type(exc).__name__,reason=str(exc)[-1000:],
                                   isolation_audit=getattr(exc,'isolation_audit',{'pass':False,'reason':'Execution did not complete the isolated worker audit.'}))
                    finally:
                        if worker_trace.exists():
                            with sink.path.open('a') as stream:stream.write(worker_trace.read_text())
                        artifacts=Path(temp)/'runtime-artifacts'
                        if artifacts.exists():shutil.copytree(artifacts,directory/'runtime-artifacts')
                        if not run.get('usage'):
                            from .usage import recover_usage
                            run['usage']=recover_usage(directory/'runtime-artifacts')
            except Exception as exc:
                run.update(status='failed', error_code=type(exc).__name__, reason=str(exc)[-1000:],
                           isolation_audit={'pass':False,'reason':'Case preflight or owned workspace validation failed.'})
                sink.emit(actor='evaluator',stage='setup',action='case_preflight_failed',status='error',error_code=type(exc).__name__)
            run['wall_clock_seconds']=time.monotonic()-started
    run['ended_at']=now()
    run['trace_sha256']=digest(directory/'trace.jsonl')
    run['qualification']=score_review(run,policy)
    save(directory/'run.json',run)
    from .human_work import template
    save(directory/'human-work-template.json',template([run_id]))
    save(directory/'review-template.json',review_template(run))
    if run.get('output'):
        save(directory/'blinded-review-packet.json',blinded_packet(run))
    return directory/'run.json'


def blinded_packet(run):
    """Standardize the review view without changing the original output."""
    output=run['output'];report=output.get('analysis') or {}
    return {'packet_id':uuid.uuid4().hex,
            'objective':run['case']['objective'],'as_of':run['case'].get('as_of'),
            'source_version':run['case'].get('source_version'),
            'required_deliverables':run['case']['required_deliverables'],
            'report':{'assessment':report.get('assessment'),'findings':report.get('findings',report.get('resolved_questions',[])),
                      'observed_facts':report.get('observed_facts',[]),
                      'claims':report.get('claims',[]),'calculated_metrics':report.get('calculated_metrics',[]),
                      'coverage':report.get('coverage',report.get('investigation_review',{}).get('coverage',[])),
                      'candidate_reviews':report.get('candidate_reviews',report.get('investigation_review',{}).get('candidate_reviews',[])),
                      'temporal_claims':report.get('temporal_claims',[]),
                      'cross_scope_synthesis':report.get('cross_scope_synthesis'),
                      'hypotheses':report.get('hypotheses',report.get('causal_hypotheses',[])),
                      'scope':report.get('scope'),'triage':report.get('triage'),
                      'evidence_requests':report.get('evidence_requests',report.get('pending_evidence_requests',[])),
                      'follow_up_actions':report.get('follow_up_actions',report.get('actions_now',[])),
                      'open_questions':report.get('open_questions',[])},
            'citations':[{k:c[k] for k in ('evidence_id','source') if k in c} for c in output.get('citations',report.get('citations',[])) if isinstance(c,dict)],
            'blinding_note':'Model, workflow name, tokens, runtimes and tool traces are withheld. Reviewers must disclose if report content still reveals the method.'}


def review_template(run):
    return {'run_id':run['run_id'],'output_sha256':run.get('output_sha256'),
            'policy_sha256':run['case']['quality_policy_sha256'], 'reviewers':[
                {'reviewer_id':None,'independent_of_operator':False,'blind_to_method':False,'evidence_ref':None,
                 'scores':{d:None for d in run['quality_policy']['dimensions']}}],
            'deliverables':{d:None for d in run['case']['required_deliverables']},
            'objective_checks_pass':None,'integrity_gates':{g:None for g in run['quality_policy']['integrity_gates']},
            'adjudication':None}


def evaluate_run(run_path, review_path=None):
    path=Path(run_path);run=json.loads(path.read_text())
    if run.get('version')!=VERSION:raise ValueError('Legacy task scores are diagnostics, not v2 qualified investigations.')
    from .case_protocol import stable_hash
    if stable_hash({k:v for k,v in run['case'].items() if k not in ('frozen_at','task_spec_sha256')})!=run['case']['task_spec_sha256']:
        raise ValueError('Run case specification changed after freeze')
    policy_path=path.parent/'quality-policy.json'
    if digest(policy_path)!=run['case']['quality_policy_sha256'] or json.loads(policy_path.read_text())!=run['quality_policy']:
        raise ValueError('Run quality policy changed after freeze')
    if digest(path.parent/'trace.jsonl')!=run['trace_sha256']:
        raise ValueError('Execution trace changed after completion')
    if run.get('output_sha256') and digest(path.parent/'output.json')!=run['output_sha256']:
        run['audit']['pass']=False;run['audit']['failures'].append('Output changed after execution.')
    review=json.loads(Path(review_path).read_text()) if review_path else None
    run['qualification']=score_review(run,run['quality_policy'],review)
    save(path,run)
    return run['qualification']
