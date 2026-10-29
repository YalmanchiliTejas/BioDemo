"""Three matched paths; actual Prime attempts, frozen targets and no invented human timing."""
from pathlib import Path
import json
import hashlib
import os
import re
from datetime import datetime
from time import perf_counter
from ..gateway import TaskRequest
from ..prime_adapter import PrimeInvestigationAdapter
from ..ids import content_hash
from .data import project, CASE_IDS, DATA
from .schemas import Assumptions
from .model import VERSION
from .research_route import hosted_research_profile

MANUAL_STEPS=['Find lawful article and supplements','Check nominal versus working volume and units',
 'Transcribe source measurements with exact locations','Build receiver equipment profiles and flag missing ratings',
 'Separate calibration from receiving evaluation outcomes','Fit only identifiable source parameters',
 'Run matched physical scenarios and record assumptions','Review applicability, discrepancies, economics and follow-up experiments']
TASK='Reconstruct the transfer problem from the scoped literature excerpts. Reconcile source and receiver parameters; identify missing characterization. Use the host fermentation_transfer(assumptions={...}) tool through the existing bridge for numerical calculations. Compare conditional operating strategies, cite the retrieved source evidence and distinguish measurements, fitted values and assumptions. Report limitations and engineering follow-up; never approve or control equipment. Do not retrieve external literature or infer the withheld receiving answers.'

class ExistingIsolatedPrime:
    model=None
    def __init__(self,public,directory,blinded=True,assumptions=None):
        self.public,self.directory=public,Path(directory).resolve(); self.last_output=None; self.blinded=blinded
        self.assumptions=Assumptions.model_validate(assumptions or {}).model_dump()
        # The shared harness reserves at least90s for synthesis. A120s research
        # run leaves only30s for retrieval and physics, which the live trace exhausted.
        self.budgets={'tool_calls':48,'wall_clock_seconds':120 if blinded else 600}
    def run(self,*,incident_id,problem,new_evidence_ids,as_of):
        from benchmarks.common.isolated_runner import run_isolated
        if self.blinded:
            # The shared runner denies hidden files, but its network can reach public papers and local APIs.
            # Fail closed rather than calling this a blinded experimental benchmark.
            raise RuntimeError('Blinded fermentation agent evaluation requires provider-only network isolation in addition to the existing filesystem denial. No agent process was started; scores are withheld.')
        # Existing runner requires an owned benchmark-case-* workspace and probes hidden-file denial.
        work=self.directory/('benchmark-case-fermentation-'+self.public['id'])
        package=work/'agent_input'; package.mkdir(parents=True,exist_ok=True)
        (package/'model-input.json').write_text(json.dumps(self.public,indent=2))
        (package/'scenario-assumptions.json').write_text(json.dumps(self.assumptions,indent=2))
        (package/'literature-excerpts.txt').write_text('Reviewed, calibration-only literature excerpt package. Full article is evaluator-only.\n'+
            'DOI: '+self.public['doi']+'\nSource locations: '+json.dumps(self.public['citation_locations'])+'\n'+
            json.dumps({'calibration':self.public['calibration'],'conditions':self.public['conditions'],'equipment':self.public['equipment']},indent=2))
        # These are newly prepared excerpts, not original source files. Use the existing
        # benchmark's virtual availability convention so the scoped store can retrieve them.
        stamp=datetime.fromisoformat(as_of.replace('Z','+00:00')).timestamp()
        for path in package.iterdir():
            os.utime(path,(stamp,stamp))
        configuration={'mode':'full_rlm','scientific_tool_family':'aerobic_fermentation','prime_model':self.model,
            'scientific_default_assumptions':self.assumptions,
            'case_id':self.public['id'],'run_id':incident_id,'access_scope':'fermentation-benchmark','state_key':incident_id,
            'evaluation_time':as_of,'state_directory':str(work/'state'),'artifact_directory':str(work/'runtime-artifacts'),
            'execution_policy':{'mode':'fixed_v1'},'budgets':self.budgets,
            'hidden_paths':[str((DATA/'validation.evaluator.json').resolve()),str(Path(__file__).resolve()),
                str((Path(__file__).resolve().parents[4]/'docs/research/fermentation').resolve()),str((self.directory/'results.json').resolve())]}
        try:
            self.last_output=run_isolated(package,problem,as_of,configuration)
        except RuntimeError as exc:
            # Preserve the full host logs, but give the product a useful recovery message.
            match=re.search(r'stderr: (/[^\n]+?) tools:',str(exc))
            log=Path(match.group(1)) if match else None
            if log and log.is_relative_to(work) and log.is_file() and 'Modal proxy authentication is missing or has the wrong format' in log.read_text():
                raise RuntimeError('Hosted Modal authentication is unavailable. Set MODAL_PROXY_TOKEN in the backend launch environment or backend/.env.local, then restart the backend. The read-only research route is enabled; no production qualification is needed for this case assessment.') from exc
            raise
        return {**self.last_output.get('analysis',{}),'rollout_metrics':self.last_output.get('usage',{})}

def attempt(p,ctx,public,directory,*,blinded=True,assumptions=None):
    host=ExistingIsolatedPrime(public,directory,blinded=blinded,assumptions=assumptions)
    adapter=PrimeInvestigationAdapter(p.gateway,host,max_cost_usd=5.,
        research_profile=hosted_research_profile() if not blinded else None)
    start=perf_counter()
    result=adapter.run(TaskRequest('investigation_planning',ctx,prompt=TASK,use_cache=False),
        incident_id='fermentation-'+public['id'],as_of='2026-10-27T00:00:00+00:00',evidence_ids=[])
    gateway_record=p.store.read().get(ctx.tenant_id,'model_run',result['run_id'])
    return {'status':result['status'],'adapter_result':result,'runtime_seconds':perf_counter()-start,
            'execution_mode':'blinded_benchmark' if blinded else 'read_only_research',
            'same_registered_physics':True,'data_hash':public['data_hash'],'output':host.last_output,
            'assumptions_hash':content_hash(host.assumptions),
            'runtime_limits':host.budgets,
            'blinded_evaluation_requested':blinded,
            'gateway_record':gateway_record.state if gateway_record else None,
            'human_minutes':None,'unsupported_recommendations':None,
            'scientific_scores':None,'publication_eligible':False,
            'score_boundary':'Read-only research drafts can use the hosted model without production qualification. Agent uplift is not scored here: independent claim review and external-retrieval isolation are required for a blinded benchmark; filesystem denial alone does not exclude public-paper retrieval or model pretraining.'}

def run(output, *, research=False):
    from ..container import Platform
    from ..store import RecordStore
    from ..devseed import seed,TENANT
    from .evaluation import grade
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    p=Platform(RecordStore()); seed(p); ctx=p.identity.context_for(TENANT,'priya')
    # Configuration must be deliberate. Do not qualify a route or load hidden credentials to obtain a favorable answer.
    targets=json.loads((DATA/'validation.evaluator.json').read_text())
    frozen={'protocol':targets['protocol'],'protocol_hash':content_hash(targets['protocol']),'target_hash':content_hash(targets),
        'source_hashes':{case:project(case)['data_hash'] for case in CASE_IDS},'model_version':VERSION,
        'manual_workflow':MANUAL_STEPS,'freeze_before_model_runs':True,'target_access':'evaluator-only; not supplied to Prime'}
    frozen['software_sha256']={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ('model.py','schemas.py','service.py','evaluation.py','benchmark.py')}
    (output/'freeze-manifest.json').write_text(json.dumps(frozen,indent=2)+'\n')
    rows=[]
    for case in CASE_IDS:
        start=perf_counter(); physics=p.fermentation.evaluate(ctx,case,{})
        seconds=perf_counter()-start
        public=project(case)
        # Agent workspace must be outside the evaluator-only research archive.
        # Placing it under output would make its own inputs unreadable by design.
        agent=attempt(p,ctx,public,Path('.cache/fermentation-benchmark')/content_hash(str(output.resolve())),blinded=not research)
        rows.append({'case_id':case,'manual':{'status':'not_observed','steps':MANUAL_STEPS,'human_minutes':None,'measured_time_savings':None},
            'physics_only':{'status':physics['execution_status'],'runtime_seconds':seconds,'inference_cost_usd':0,
                'human_minutes':None,'analysis':physics,'extraction_mode':'reviewed engineer-prepared literature transcriptions'},
            'agent_plus_same_physics':agent})
    result={'version':VERSION,'execution_mode':'read_only_research' if research else 'blinded_benchmark','freeze':frozen,'cases':rows,'measured_engineering_hours_saved':None,'experiments_eliminated':None,
            'incremental_agent_value':'unavailable without completed qualified agent runs and observed matched human workflow timings'}
    (output/'results.json').write_text(json.dumps(result,indent=2,default=str)+'\n')
    lines=['# Experimental fermentation transfer benchmark','',
      'Repository audit: docs/research/fermentation/repository-audit.md. Original literature sources and reviewed transcriptions are preserved with hashes in docs/research/fermentation/.',
      '', '## What executed',
      'Both cases executed through the existing model catalog, bounded deterministic runner, FlowService, versioned evidence and review records. No production write occurred.',
      'Source extraction was reviewed manually. Autonomous raw-publication ingestion performance and engineering time savings have not been established.',
      '', '## Sulfolobus']
    a=rows[0]['physics_only']['analysis']
    for row in a['validation']['rows']:
        lines.append(f"- {row['receiver_l']}L: predicted kLa {row['predicted']:.3f}h^-1 versus measured {row['measured']:.1f}h^-1; error {row['relative_error']:.1%}. Source: Rastädter et al. (2023) Table2. Assumed sensitivity range {row['sensitivity_low']:.2f}–{row['sensitivity_high']:.2f}h^-1, not a confidence interval.")
    lines += ['',a['validation']['conclusion'],'No 200 L viability measurement or biological forecast was invented. Source kLa is water characterization at 75°C. Full receiving characterization must establish broth effects, gassed power, sparger response and certified limits.',
              '', '## Pichia']
    b=rows[1]['physics_only']['analysis']; e=b['prediction']['economics']
    lines += [f"- Same-composition Henry saturation ratio at 100 versus 50 kPa gauge: {b['prediction']['pressure_saturation_ratio_air_only']:.5f}, using 101.325 kPa ambient.",
      f"- Under the recorded hypothetical flow/efficiency/price assumptions: oxygen-delivery cost difference ${e['oxygen_delivery_savings_usd_h']:.4f}/h, or ${e['oxygen_delivery_savings_usd_basis']:.2f} over the common {e['common_basis_hours']:g}h basis. This is partial modeled cost, not experimental dollars or complete batch COGS. Methanol, occupancy and other excluded costs can reverse the result.",
      b['validation']['conclusion'],
      'Table 1 direct comparison is 30 L and uses different durations. Published 100 / 1,000 L Table 2 production summaries are held out; a constant 10 L endpoint comparator is explicitly empirical, not pressure-based kinetics. The 1,000 L / 112 h endpoint is not peak or harvest.',
      '', '## Agent comparison and operational boundary']
    lines += [f"- {x['case_id']}: actual Prime adapter attempt = {x['agent_plus_same_physics']['status']}; scientific uplift, unsupported-recommendation count and human timing remain unavailable." for x in rows]
    lines += ['The existing Prime harness, bridge, ingestion and native subagents are retained. No fake reports, fake model qualification or synthetic agent success are substituted. External retrieval/pretraining remain additional concerns for a published blinded score.',
      'Blinded trials fail closed before starting an agent until provider-only network isolation is available; the existing filesystem boundary alone is insufficient.',
      '', '## IndPenSim and optional industrial case',
      'Existing IndPenSim integration is retained. The prior successful-prefix/failed-full-run feasibility gate remains authoritative; the previously isolated executable environment is absent on this host. No simulator was rebuilt and no new stress-run result is claimed. Bernemann is deferred until the two required cases and their scientific limitations have been reviewed.',
      '', '## Sources',
      '- Rastädter et al. (2023), https://doi.org/10.3389/fbioe.2023.1160012 and supplementary TableS1.',
      '- Liu et al. (2016), https://doi.org/10.1038/srep18439, Methods and Tables1–2.',
      '- Per-file SHA256, source locations, summary SD interpretations and source conflicts are in the research manifests.',
      '', '## Required follow-up',
      'Receiver broth kLa/OUR/DO characterization, rated motor/pressure/torque limits, replicated product and feed measurements, actual utility quotations, observed conventional-workflow timing, and qualified isolated Prime execution with blinded scientific review are needed before an incremental-agent efficiency or production-readiness claim.']
    if (output/'verification.json').exists():
        lines += ['', '## Recorded verification',
            'See verification.json and ui/checks.json for the executed commands and scope. The platform/Prime regression run passed414 tests; the targeted fermentation suite passed14. Production build and real-API desktop/mobile browser checks passed.',
            'The separate case-study regression run passed114 tests and skipped2. Four CHO checks fail because the recorded pilot and aligned-reference files are absent locally; the saved static report consequently differs and the series endpoint returns404. Those fixtures and case-study implementations were not regenerated or changed by this feature.',
            'The existing parser indexed3 original PDF/DOCX files (1,495 observations) without extraction errors; scoped lexical retrieval verified9 excerpts against original files. These are parser/retrieval checks, not autonomous extraction accuracy or saved human effort.']
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    return result

if __name__=='__main__':
    import argparse
    from ..envfile import load_env_file
    load_env_file(os.environ.get('LIFESCI_ENV_FILE',Path(__file__).resolve().parents[3]/'.env.local'))
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='../docs/research/fermentation/results')
    parser.add_argument('--research',action='store_true',help='Use the saved hosted Modal model for read-only exploratory drafts; never report blinded agent scores.')
    args=parser.parse_args()
    value=run(args.output,research=args.research)
    print(json.dumps({'cases':[{ 'case':r['case_id'],'physics':r['physics_only']['status'],'agent':r['agent_plus_same_physics']['status']} for r in value['cases']],'report':str(Path(args.output)/'report.md')},indent=2))
