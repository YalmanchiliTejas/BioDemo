'use client';

import { useEffect, useState } from 'react';
import { ArrowDownToLine, ArrowRight, FileText, FlaskConical } from 'lucide-react';
import { Button, Card, Pill } from '@/components/ui';
import { ScientificPlot } from '@/components/ScientificPlot';
import { useCompanion } from '@/lib/companion-context';

type Task = 'diagnosis' | 'optimization' | 'resolution' | 'pretransfer';
type Metrics = {
  attempted:number; completed:number; failed_or_unsubmitted:number; top_rank_matches:number;
  mean_hypothesis_set_size:number|null; mean_authored_cause_coverage:number|null;
  mean_agent_wall_seconds:number|null; physical_model_calls:number;
  actions_committed?:number; feasible_selected_actions?:number; deferrals?:number;
  mean_feasible_grid_regret?:number|null;
  warnings?:Record<'TP'|'FP'|'FN'|'TN'|'abstained',number>;
  verified_simulated_resolutions?:number; mean_simulated_resolution_h?:number|null;
  mean_synthetic_measurement_rounds?:number|null;
};
type Outcome = {feasible_full_batch:boolean; first_issue_h:number|null; capacity_onset_h:number|null; thermal_or_oxygen_onset_h:number|null; completion_time_h:number|null; objective_value:number|null};
type Run = {
  case_id:string; task:Task; arm:'A'|'B'; status:string; wall_seconds:number; model_calls:number; tool_calls:number; physical_model_calls:number;
  submission:{hypotheses:string[]; action_id?:string; decision?:string; requested_measurements?:string[]; rationale:string; uncertainty:string; evidence:string[]}|null;
  score:{authored_cause_coverage:number; hypothesis_set_size:number; warning_result?:string; independently_replayed_outcome?:Outcome|null;
    feasible_objective_regret?:number|null; resolution_verification?:{outcome:Outcome;verified_process_constraint_resolution_h:number|null;synthetic_measurement_rounds:number}}|null;
  error:string|null;
};
type ProcessCase = {case_id:string;domain:string;family:string;authored_causes:string[];completion_h:number;
  constraint_value:number;
  optimization_grid_has_feasible_action:boolean;
  action_labels:Record<Task,Record<string,string>>;
  observed_trace:{time_h:number;value:number}[];reference_trace:{time_h:number;value:number}[];original_plan:Outcome};
type Snapshot = {
  status:string; planned_attempts:number; attempted:number; completed:number; complete_pairs:number; pair_inputs_match:boolean;
  shared_tool_schemas_match:boolean|null;schema_pairs_audited:number;
  computational_review:{passed:boolean;attempts_reviewed:number;physical_calls_replayed:number;measurements_replayed:number;accepted_decisions_replayed:number}|null;
  findings:{A_completed:number;B_completed:number;planned_per_arm:number;control_cases:number;B_warned_every_case:boolean;
    paired_completed_sensitivity:Record<Task,{pairs:number;A:{feasible_actions:number;verified_outcomes:number|null};B:{feasible_actions:number;verified_outcomes:number|null}}>};
  dataset_cases:number;dataset_task_packets:number;source_sha256:string;dataset_manifest_sha256:string;notice:string;
  protocol:{model:string;wall_seconds:number;tool_calls:number;max_output_tokens:number;known_limits:string[];arm_difference:string};
  tasks:Record<Task,Record<'A'|'B',Metrics>>; records:Run[];cases:ProcessCase[];
  domain_tasks:Record<string,Record<Task,Record<'A'|'B',Metrics>>>;
  assets:{protocol:string;dataset_manifest:string;isolation:string;summary:string;archive:string;computational_review?:string};
};

const TASKS:{id:Task;label:string;question:string}[] = [
  {id:'diagnosis',label:'Diagnosis',question:'Does the agent rank the authored mechanism more accurately?'},
  {id:'optimization',label:'Optimization',question:'Does its selected action satisfy the independent simulation constraints?'},
  {id:'resolution',label:'Issue resolution',question:'Does investigation lead to a verified simulated outcome?'},
  {id:'pretransfer',label:'Before transfer',question:'Does it warn before a receiving batch starts, or request characterization?'},
];
const eyebrow='text-[10px] font-semibold uppercase tracking-[0.16em] text-text-tertiary';
const pretty=(s:string)=>s.replaceAll('_',' ');
const format=(v:number|null|undefined,digits=1)=>v==null?'Not measured':v.toLocaleString(undefined,{maximumFractionDigits:digits});
const ratio=(n:number|undefined,d:number)=>`${n??0} / ${d}`;

function MetricCell({task,m,riskCases,domain}:{task:Task;m:Metrics;riskCases:number;domain:string}) {
  if(!m.completed)return <><strong className="text-lg font-medium">Not scored yet</strong><p className="mt-1 text-[11px] text-text-secondary">No completed decision is available for this condition.</p></>;
  if(task==='diagnosis')return <><strong className="text-xl font-medium tabular-nums">{ratio(m.top_rank_matches,m.attempted)}</strong><p className="mt-1 text-[11px] text-text-secondary">top-ranked mechanism matches · {format(m.mean_hypothesis_set_size)} hypotheses on average</p></>;
  if(task==='optimization')return <><strong className="text-xl font-medium tabular-nums">{ratio(m.feasible_selected_actions,m.attempted)}</strong><p className="mt-1 text-[11px] text-text-secondary">feasible selections · {m.deferrals??0} deferrals</p><p className="mt-1 text-[11px] text-text-secondary">{domain==='all'?'Select a process to compare objective gaps.':`Mean gap from best feasible grid choice: ${format(m.mean_feasible_grid_regret,2)} ${domain==='oxygen'?'modeled USD':'primary-drying vials/h'} (feasible selections only).`}</p></>;
  if(task==='resolution')return <><strong className="text-xl font-medium tabular-nums">{ratio(m.verified_simulated_resolutions,m.attempted)}</strong><p className="mt-1 text-[11px] text-text-secondary">verified simulated outcomes · {format(m.mean_synthetic_measurement_rounds)} measurement rounds on average</p><p className="mt-1 text-[11px] text-text-secondary">{format(m.mean_agent_wall_seconds)} s agent runtime per attempt. {domain!=='all'?`${format(m.mean_simulated_resolution_h)} simulated hours to verification, among verified outcomes.`:''}</p></>;
  return <><strong className="text-xl font-medium tabular-nums">{ratio(m.warnings?.TP,riskCases)} risks detected</strong><p className="mt-1 text-[11px] text-text-secondary">{m.warnings?.FN??0} missed · {m.warnings?.FP??0} false alarms · {m.warnings?.abstained??0} abstentions</p></>;
}

function Decision({run,actionLabel}:{run:Run|undefined;actionLabel?:string}) {
  if(!run)return <p className="text-sm text-text-secondary">This attempt has not been recorded.</p>;
  const s=run.submission;
  const outcome=run.score?.independently_replayed_outcome??run.score?.resolution_verification?.outcome;
  return <div className="min-w-0 space-y-4" data-testid={`physics-decision-${run.arm}`}>
    <div className="flex flex-wrap items-center justify-between gap-2"><h4 className="text-sm font-semibold">{run.arm==='A'?'A · Traces + numerical tools':'B · Same tools + physical models'}</h4><Pill tone={run.status==='completed'?'neutral':'warning'}>{run.status==='completed'?'Execution complete':pretty(run.status)}</Pill></div>
    {s?<><p className="text-lg font-medium leading-snug">{s.decision==='characterize'?'Characterize before committing':s.decision==='abstain'?'Abstain from a transfer decision':s.action_id?(actionLabel??pretty(s.action_id)):'Ranked hypotheses'}</p>
      <p className="text-xs text-text-secondary">{s.hypotheses.length?s.hypotheses.map(pretty).join(' → '):'No specific mechanism asserted'}</p>
      <p className="text-sm leading-6 text-text-secondary whitespace-pre-wrap break-words">{s.rationale}</p>
      <div className="border-l-2 border-border-strong pl-3"><p className="text-xs font-semibold">Uncertainty</p><p className="mt-1 text-xs leading-5 text-text-secondary break-words">{s.uncertainty}</p></div>
      {s.requested_measurements?.length?<p className="text-xs leading-5 text-text-secondary">Requested: {s.requested_measurements.map(pretty).join(', ')}</p>:null}
      {outcome?<p className={`rounded-control px-3 py-2 text-xs ${outcome.feasible_full_batch?'bg-status-success-bg text-emerald-800':'bg-status-warning-bg text-amber-900'}`}>Independent synthetic replay: {outcome.feasible_full_batch?'full-batch constraints satisfied':'full-batch constraints not satisfied'}.{outcome.first_issue_h!=null?` First issue: ${format(outcome.first_issue_h,2)} h.`:''}</p>:null}
      <details className="text-xs text-text-secondary"><summary className="cursor-pointer font-medium">Evidence cited by the agent</summary><ul className="mt-2 list-disc space-y-1 pl-4">{s.evidence.map((e,i)=><li className="break-words leading-5" key={i}>{e}</li>)}</ul><p className="mt-2 text-[11px]">Agent references are retained for review. Independent scientific adjudication is pending.</p></details>
    </>:<p className="text-sm leading-6 text-text-secondary">{run.error??'No scored decision was submitted.'}</p>}
    <p className="border-t border-border-hairline pt-3 text-[11px] text-text-tertiary">{format(run.wall_seconds)} s agent execution · {run.model_calls} model calls · {run.tool_calls} host calls · {run.physical_model_calls} physical-model calls</p>
  </div>;
}

export function PhysicsValueStudy() {
  const [data,setData]=useState<Snapshot|null>(null);
  const [error,setError]=useState('');
  const [task,setTask]=useState<Task>('pretransfer');
  const [caseId,setCaseId]=useState('');
  const [domain,setDomain]=useState('all');
  const companion=useCompanion();
  useEffect(()=>{
    const abort=new AbortController();
    fetch('/case-study-results/physics-value.json',{signal:abort.signal}).then(async r=>{
      if(!r.ok)throw Error('The recorded agent comparison has not been exported yet. Results will appear after the experiment finishes.');
      const value:Snapshot=await r.json();
      if(!value.cases.length)throw Error('The recorded comparison contains no process cases.');
      setData(value);setCaseId(value.records.find(row=>row.status==='completed'&&row.task==='pretransfer')?.case_id??value.cases[0].case_id);
    }).catch(e=>{if(e.name!=='AbortError')setError(e.message);});
    return ()=>abort.abort();
  },[]);
  if(error)return <div role="alert" className="rounded-card border border-border-hairline bg-surface p-6"><h2 className="text-xl font-semibold">Physical-model comparison</h2><p className="mt-3 text-sm text-text-secondary">{error}</p></div>;
  if(!data)return <div role="status" aria-label="Loading physical-model comparison" className="space-y-5"><div className="h-9 w-3/4 rounded bg-surface-secondary"/><div className="h-44 rounded-card bg-surface-secondary"/><p className="text-sm text-text-secondary">Loading recorded comparison…</p></div>;
  const selected=data.cases.find(c=>c.case_id===caseId)??data.cases[0];
  const summaryCases=data.cases.filter(c=>domain==='all'||c.domain===domain);
  const riskCases=summaryCases.filter(c=>!c.original_plan.feasible_full_batch).length;
  const summary=domain==='all'?data.tasks:data.domain_tasks[domain];
  const feasibleAtCutoff=summaryCases.filter(c=>c.optimization_grid_has_feasible_action).length;
  const runs=data.records.filter(r=>r.case_id===selected?.case_id&&r.task===task);
  const cutoff=task==='pretransfer'?0:6;
  const points=(rows:{time_h:number;value:number}[])=>rows.map(r=>({elapsedHours:r.time_h,value:r.value,imputed:false}));
  const visible=selected?.observed_trace.filter(r=>r.time_h<=cutoff)??[];
  const plotSeries=selected?[
    {id:selected.domain==='oxygen'?'Withheld actual dissolved oxygen':'Withheld hottest active vial temperature',color:'#64748b',dataPoints:points(selected.reference_trace)},
    ...(visible.length?[{id:selected.domain==='oxygen'?'Available dissolved-oxygen sensor':'Available routine mean thermometry',color:'#0e7490',dataPoints:points(visible)}]:[]),
    ...(selected.constraint_value!=null?[{id:'Declared synthetic constraint',color:'#b45309',dataPoints:points([{time_h:0,value:selected.constraint_value},{time_h:selected.completion_h,value:selected.constraint_value}])}]:[]),
  ]:[];
  function discuss(){companion.show({kind:'text',label:'Physical-model agent comparison',page_path:'/case-studies/#physics-value',captured_at:new Date().toISOString(),content:JSON.stringify({classification:'retrospective_synthetic_experiment_results',question:'Does physical-model access improve agent decisions?',tasks:data?.tasks,selected_case:selected,selected_runs:runs,notice:data?.notice})});}
  return <article className="space-y-8" data-testid="physics-value-study">
    <header className="max-w-3xl"><Pill tone="brand">Paired agent experiment · synthetic processes</Pill><h2 className="mt-4 text-[30px] font-semibold leading-[1.16] tracking-[-0.035em] sm:text-[38px]">Do physical models help agents make better process decisions?</h2><p className="mt-4 text-sm leading-6 text-text-secondary">We gave the same agent the same manufacturing evidence in two conditions. One could use numerical analysis. The other could also run physical models. We checked their decisions against withheld simulations.</p></header>
    <section className="grid gap-6 rounded-2xl bg-[#173c36] p-6 text-white sm:p-8 lg:grid-cols-[1.6fr_1fr]" aria-label="Experiment execution status">
      <div><p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#b7d9cc]">{data.status==='complete'?'Recorded comparison':'Comparison in progress'}</p><h3 className="mt-3 text-2xl font-medium">{data.completed} of {data.planned_attempts} attempts produced scored decisions.</h3><p className="mt-3 text-sm leading-6 text-[#d2e6df]">{data.complete_pairs} pairs have completed decisions from both arms. The results below keep failures, abstentions and model limitations visible. This pilot has no independent scientific adjudication or measured engineer time savings.</p></div>
      <dl className="grid grid-cols-2 gap-5 border-t border-white/20 pt-5 lg:border-l lg:border-t-0 lg:pl-7 lg:pt-0"><div><dt className="text-xs text-[#b7d9cc]">Process cases</dt><dd className="mt-1 text-3xl tabular-nums">{data.dataset_cases}</dd></div><div><dt className="text-xs text-[#b7d9cc]">Decision tasks</dt><dd className="mt-1 text-3xl tabular-nums">{data.dataset_task_packets}</dd></div><div className="col-span-2"><dt className="text-xs text-[#b7d9cc]">Same model in both arms</dt><dd className="mt-1 break-all text-sm">{data.protocol.model}</dd></div></dl>
    </section>
    {data.status==='complete'&&data.findings?<section className="space-y-3 border-l-2 border-brand-teal pl-5" aria-label="Interpretation of the measured results"><h3 className="text-xl font-semibold">More completed decisions, with mixed quality results</h3><p className="max-w-4xl text-sm leading-6 text-text-secondary">The model-enabled arm submitted {data.findings.B_completed}/{data.findings.planned_per_arm} scored decisions; the numerical-tools arm submitted {data.findings.A_completed}/{data.findings.planned_per_arm}. Among {data.findings.paired_completed_sensitivity.optimization.pairs} optimization pairs where both submitted, feasible choices were A: {data.findings.paired_completed_sensitivity.optimization.A.feasible_actions}, B: {data.findings.paired_completed_sensitivity.optimization.B.feasible_actions}. Across {data.findings.paired_completed_sensitivity.resolution.pairs} completed resolution pairs, verified outcomes were A: {data.findings.paired_completed_sensitivity.resolution.A.verified_outcomes}, B: {data.findings.paired_completed_sensitivity.resolution.B.verified_outcomes}. These descriptive completed-pair checks complement the all-attempt counts below.</p>{data.findings.B_warned_every_case?<p className="max-w-4xl text-sm leading-6 text-text-secondary">The model-enabled arm warned on every pre-transfer case, including all {data.findings.control_cases} controls. That matches an always-warn policy. Useful pre-transfer risk discrimination has not been demonstrated.</p>:null}</section>:null}
    <section aria-label="Paired outcome summary"><div className="mb-5 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className={eyebrow}>Four separate questions</p><h3 className="mt-2 text-xl font-semibold">What changed with physical-model access?</h3><p className="mt-2 max-w-3xl text-xs leading-5 text-text-secondary">Mechanism matches use authored synthetic labels. Optimization and resolution use the richer evaluator. Counts describe this pilot; they do not establish general manufacturing accuracy.</p></div><label className="shrink-0 text-xs font-medium">Show outcomes for<select aria-label="Outcome process" className="mt-2 block w-full rounded-control border border-border-strong bg-surface px-3 py-2 text-sm" value={domain} onChange={e=>setDomain(e.target.value)}><option value="all">Both processes</option><option value="oxygen">Oxygen supply</option><option value="freeze_drying">Freeze-drying</option></select></label></div>
      <div tabIndex={0} role="region" aria-label="Agent outcomes table, horizontally scrollable" className="overflow-x-auto rounded-card border border-border-hairline bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"><table className="w-full min-w-[620px] text-left"><caption className="sr-only">Outcomes for agents without and with executable physical models</caption><thead className="border-b border-border-hairline bg-surface-secondary text-xs"><tr><th className="px-5 py-4 font-medium">Question</th><th className="px-5 py-4 font-medium">A · Numerical tools</th><th className="px-5 py-4 font-medium">B · Numerical tools + physical models</th></tr></thead><tbody className="divide-y divide-border-hairline">{TASKS.map(t=><tr key={t.id}><th scope="row" className="max-w-[220px] px-5 py-5 align-top"><p className="text-sm font-semibold">{t.label}</p><p className="mt-1 text-[11px] font-normal leading-5 text-text-secondary">{t.question}</p></th>{(['A','B'] as const).map(arm=><td key={arm} className="px-5 py-5 align-top"><MetricCell task={t.id} m={summary[t.id][arm]} riskCases={riskCases} domain={domain}/><p className="mt-2 text-[10px] text-text-tertiary">{summary[t.id][arm].completed} submitted · {summary[t.id][arm].failed_or_unsubmitted} failed or unsubmitted</p></td>)}</tr>)}</tbody></table></div>
      <p className="mt-3 text-[11px] leading-5 text-text-tertiary">Decision fractions include all attempted runs; failed or unsubmitted attempts remain in the denominator. Hypothesis-set averages use completed decisions. This selection has {riskCases} original plans with simulated risk and {summaryCases.length-riskCases} controls. A feasible fixed-grid action exists at 6 h in {feasibleAtCutoff} of {summaryCases.length} cases; later measurements can narrow that window. Pre-transfer abstentions and deferrals are separate. A later intervention cannot erase an earlier full-batch constraint violation.</p>
    </section>
    <section className="space-y-5" aria-label="Inspect a paired decision"><div><p className={eyebrow}>Inspect the actual decisions</p><h3 className="mt-2 text-xl font-semibold">Follow one case from evidence to outcome</h3></div>
      <div className="grid gap-4 sm:grid-cols-[2fr_1fr]"><label className="text-xs font-medium">Process case<select aria-label="Process case" className="mt-2 block w-full rounded-control border border-border-strong bg-surface px-3 py-2.5 text-sm" value={caseId} onChange={e=>setCaseId(e.target.value)}>{data.cases.map(c=><option key={c.case_id} value={c.case_id}>{pretty(c.domain)} · {pretty(c.family)} · {c.case_id}</option>)}</select></label><label className="text-xs font-medium">Decision task<select aria-label="Decision task" className="mt-2 block w-full rounded-control border border-border-strong bg-surface px-3 py-2.5 text-sm" value={task} onChange={e=>setTask(e.target.value as Task)}>{TASKS.map(t=><option key={t.id} value={t.id}>{t.label}</option>)}</select></label></div>
      {selected?<Card className="overflow-hidden p-4 sm:p-6"><div className="mb-4 flex flex-wrap items-center justify-between gap-3"><h4 className="text-sm font-semibold">{selected.domain==='oxygen'?'Dissolved oxygen':'Hottest active vial temperature'}</h4><Pill tone="neutral">Outcome revealed after evaluation</Pill></div><ScientificPlot batches={plotSeries} variableName={selected.domain==='oxygen'?'Dissolved oxygen':'Hottest active vial temperature'} unit={selected.domain==='oxygen'?'mg/L':'°C'} xDomain={[0,selected.completion_h]} height={250} kalmanStateActive={false} markers={[{hour:cutoff,label:task==='pretransfer'?'Before receiving batch':'Evidence cutoff · 6 h'}]} xLabel="Simulated receiving-batch time (h)"/><p className="mt-3 text-xs leading-5 text-text-secondary">{task==='pretransfer'?'Both agents received source history and receiving specifications, with no receiving-batch measurements.':'Both agents received routine measurements through 6 h. Resolution agents could request later measurements through the same host tool.'} The gray reference was withheld. For freeze-drying, the blue trace is routine mean thermometry and the gray trace is the hottest active vial; these are different quantities. The plot stops at primary-drying completion.</p></Card>:null}
      {selected?.original_plan.capacity_onset_h!=null?<p className="text-xs leading-5 text-text-secondary">The original plan exceeds the simulated receiving vapor-handling limit at {format(selected.original_plan.capacity_onset_h,2)} h. Capacity warnings use a separate vapor-flow constraint.</p>:null}
      <div className="grid gap-7 divide-y divide-border-hairline rounded-card border border-border-hairline bg-surface p-5 sm:p-7 lg:grid-cols-2 lg:divide-x lg:divide-y-0"><div className="min-w-0 pb-6 lg:pb-0 lg:pr-1"><Decision run={runs.find(r=>r.arm==='A')} actionLabel={selected?.action_labels?.[task]?.[runs.find(r=>r.arm==='A')?.submission?.action_id??'']}/></div><div className="min-w-0 pt-6 lg:pl-7 lg:pt-0"><Decision run={runs.find(r=>r.arm==='B')} actionLabel={selected?.action_labels?.[task]?.[runs.find(r=>r.arm==='B')?.submission?.action_id??'']}/></div></div>
    </section>
    <details className="rounded-card border border-border-hairline bg-surface p-5"><summary className="cursor-pointer text-sm font-medium">Methodology, limitations & reproducibility</summary><div className="mt-5 space-y-5 text-xs leading-6 text-text-secondary"><p>{data.notice}</p><dl className="grid gap-4 sm:grid-cols-2"><div><dt className="font-semibold text-text-primary">Controlled comparison</dt><dd>{data.protocol.arm_difference} Common input hashes: {data.pair_inputs_match?'matched':'mismatch detected'}.</dd></div><div><dt className="font-semibold text-text-primary">Same execution ceilings</dt><dd>{data.protocol.wall_seconds} seconds per attempt; {data.protocol.tool_calls} host-tool calls; {format(data.protocol.max_output_tokens,0)} output-token ceiling per model response.</dd></div><div><dt className="font-semibold text-text-primary">Access boundary</dt><dd>Restricted Prime SDK tools. Numerical code runs under verified hidden-file and network denial. Native filesystem, shell, external retrieval and child-agent tools are disabled in both arms.</dd></div><div><dt className="font-semibold text-text-primary">Meaning of resolution time</dt><dd>Measurements and verification advance a synthetic clock. These costs are assumptions. Observed engineer time, production improvements and real failed batches avoided remain unmeasured.</dd></div></dl><ul className="list-disc space-y-1 pl-4">{data.protocol.known_limits.map(s=><li key={s}>{s}</li>)}</ul><div className="flex flex-wrap gap-4"><a className="inline-flex items-center gap-1 text-brand-teal underline" href={data.assets.protocol} target="_blank" rel="noreferrer"><FileText className="h-3 w-3"/>Run protocol</a><a className="text-brand-teal underline" href={data.assets.dataset_manifest} target="_blank" rel="noreferrer">Dataset hashes</a><a className="text-brand-teal underline" href={data.assets.isolation} target="_blank" rel="noreferrer">Isolation checks</a><a className="inline-flex items-center gap-1 text-brand-teal underline" href={data.assets.archive} download><ArrowDownToLine className="h-3 w-3"/>Reproducibility package</a></div><p className="break-all font-mono text-[10px]">Recorded result SHA-256: {data.source_sha256}</p></div></details>
    <div className="flex flex-col justify-between gap-3 border-t border-border-hairline pt-5 sm:flex-row sm:items-start"><p className="max-w-3xl text-xs leading-5 text-text-secondary">Pre-transfer characterization requests were recorded but not executed in this trial. A deferral does not establish that a receiving-site issue was found or prevented.</p><a href={data.assets.summary} target="_blank" rel="noreferrer" className="shrink-0 text-xs font-medium text-brand-teal underline">Case-study evidence sheet</a></div>
    {data.computational_review?<div className="rounded-card border border-border-hairline bg-surface p-5 text-xs leading-6 text-text-secondary"><p className="font-semibold text-text-primary">Computational replay checked</p><p>{data.computational_review.physical_calls_replayed} physical-model calls, {data.computational_review.measurements_replayed} measurement results and {data.computational_review.accepted_decisions_replayed} accepted decisions matched deterministic replay. Shared tool schemas matched in {data.schema_pairs_audited} pairs. This verifies reproducibility; independent scientific review of the interpretations remains pending.</p><a href={data.assets.computational_review} target="_blank" rel="noreferrer" className="mt-2 inline-block text-brand-teal underline">Open computational review</a></div>:null}
    <footer className="flex flex-wrap items-center justify-between gap-4 border-t border-border-hairline pt-5"><p className="max-w-2xl text-[11px] leading-5 text-text-tertiary">Research review only. This is a restricted-tool synthetic comparison. Recommendations, independent review and manufacturing execution remain separate.</p><div className="flex flex-wrap items-center gap-3"><a href="/case-study-results/physics-value.json" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-medium text-brand-teal">Recorded results <ArrowRight className="h-3 w-3"/></a><Button variant="ghost" onClick={discuss}><FlaskConical className="h-3.5 w-3.5"/>Discuss this experiment</Button></div></footer>
  </article>;
}
