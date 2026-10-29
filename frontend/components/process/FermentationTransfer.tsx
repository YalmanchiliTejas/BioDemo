'use client';

import { useEffect, useState } from 'react';
import { Card, CardBody, CardHeader, Callout, Pill, Segmented } from '@/components/ui';
import { ScientificPlot } from '@/components/ScientificPlot';
import { processRequest } from '@/lib/process-api';
import { useCompanion } from '@/lib/companion-context';

type Equipment = { working_volume_l?: number; total_volume_l?: number; nominal_volume?: { value: number }; model: string; manufacturer: string;
  submerged_impellers?: number; impeller_diameter_mm?: number; initial_volume_as_reported?: { value: number }; agitation_operating_range?: { value: number[] }; aeration_operating_range?: { value: number[] } };
type Project = { id: string; title: string; url: string; doi: string; classification: string; equipment: Equipment[]; calibration: unknown[]; conditions: unknown; cultivation_conditions?: unknown;
  limitations: string[]; missing: string[]; citation_locations: string[]; data_hash: string; source_manifest: unknown };
type Scenario = { receiver_l?: number; rpm?: number; airflow_l_min?: number; predicted_kla_h_inv?: number; power_w_m3?: number; status?: string;
  label?: string; pressure_gauge_kpa?: number; pressure_absolute_kpa?: number; cstar_mg_l?: number; otr_mg_l_h?: number; our_margin_mg_l_h?: number; compressor_kw?: number; partial_cost_usd_h?: number };
type ValidationRow = { receiver_l: number; metric: string; unit: string; measured: number; predicted: number; residual: number; relative_error: number;
  measured_sd?: number; source_location: string; sensitivity_low?: number; sensitivity_high?: number; uncertainty?: string };
export type Analysis = { id: string; status: string; execution_status: string; issues: string[]; assumptions: Record<string, number | null>; plan_hash: string;
  model_manifest: { id: string; version: string; implementation_digest: string }[];
  prediction: { recommendations?: { receiver_l: number; candidate: Scenario | null; rated_equipment_feasibility: string }[]; scenarios: Scenario[]; selected_scenario?: Scenario;
    pressure_curve?: { pressure_gauge_kpa: number; saturation_ratio: number }[]; pressure_saturation_ratio_air_only?: number;
    economics?: { oxygen_delivery_savings_usd_h: number; oxygen_delivery_savings_usd_basis: number; common_basis_hours: number; break_even_oxygen_usd_nm3: number | null;
      excluded: string[]; flow_basis: string; net_after_extra_feed_usd: number | null }; warnings: string[]; rationale?: string; recommendation?: string; equations: string[]; missing_inputs: string[] };
  validation: { rows: ValidationRow[]; conclusion: string; rmse: number; split: unknown; target_hash: string; prediction_commitment: string; published_outcomes?: unknown };
  resource_usage: { runtime_seconds: number; solver_calls: number; human_preparation_minutes: null } };
type Agent = { output?: { analysis: { report_type?: string; assessment?: string; verification?: { status?: string } }; citations?: unknown[] }; status: string; scientific_scores: unknown; adapter_result: { issues?: string[]; run_id?: string }; score_boundary: string };
type Review = { proposal_id: string; status: string; execution_status: string; required_roles: string[] };
type Tab = 'evidence' | 'equipment' | 'analysis' | 'review';
const button = 'rounded-control border border-border-strong bg-surface px-3 py-2 text-xs font-medium text-text-secondary hover:bg-surface-secondary disabled:opacity-40';
const fmt = (value: number | null | undefined, digits=2) => value == null ? 'Unavailable' : value.toLocaleString(undefined, { maximumFractionDigits: digits });

export function FermentationTransfer({ initialCase = 'sulfolobus', initialTab = 'evidence', embedded = false }: { initialCase?: string; initialTab?: Tab; embedded?: boolean }) {
  const companion = useCompanion();
  const [projects, setProjects] = useState<Project[]>([]);
  const [caseId, setCaseId] = useState(initialCase);
  const [tab, setTab] = useState<Tab>(initialTab);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [settings, setSettings] = useState<Record<string, number | null>>({});
  const [result, setResult] = useState<Analysis | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [agent, setAgent] = useState<Agent | null>(null);
  const project = projects.find(p => p.id === caseId);
  const pichia = caseId === 'pichia';
  const partialAgentReport = agent?.output?.analysis?.report_type === 'partial_investigation';
  const agentReportStatus = partialAgentReport ? 'partial investigation' : agent?.status;
  useEffect(() => { setTab(initialTab); }, [initialTab]);
  useEffect(() => {
    let current=true;
    processRequest<{ projects: Project[] }>('/v1/process-model/fermentation/projects')
      .then(r => { if (current) setProjects(r.projects); }).catch(e => { if(current) setError(String(e)); });
    return () => { current=false; };
  }, []);
  function setting(key: string, fallback: number) { return settings[key] ?? fallback; }
  function field(label: string, key: string, fallback: number, min: number, max: number, step=1) {
    return <label key={key} className="text-xs text-text-secondary">{label}<input type="number" required min={min} max={max} step={step} value={setting(key, fallback)}
      onChange={e => { setSettings(s => ({ ...s, [key]: Number(e.target.value) })); setDirty(true); setReview(null); }}
      className="mt-1 block w-full rounded-control border border-border-strong bg-surface px-3 py-2 text-sm" /></label>;
  }
  async function run() {
    setBusy(true); setError(''); setReview(null);
    try {
      const value = await processRequest<Analysis>(`/v1/process-model/fermentation/projects/${caseId}/evaluate`, { assumptions: settings });
      if (value.execution_status !== 'completed') { setError(value.issues?.join(' ') || 'The calculation did not complete.'); return; }
      setResult(value); setDirty(false);
    } catch(e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function propose() {
    if (!result || dirty) return;
    setBusy(true); setError('');
    try { setReview(await processRequest<Review>(`/v1/process-model/fermentation/results/${result.id}/review`, {})); }
    catch(e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function askPrime() {
    setBusy(true); setError('');
    try { setAgent(await processRequest<Agent>(`/v1/process-model/fermentation/projects/${caseId}/agent-assessment`, { assumptions: settings })); }
    catch(e) { setError(String(e)); } finally { setBusy(false); }
  }
  const columns = 'w-full text-left text-xs [&_th]:p-2 [&_td]:p-2 [&_th]:font-medium [&_th]:text-text-secondary [&_tr]:border-b [&_tr]:border-border-hairline';
  return <Card className="mb-6" data-testid="fermentation-transfer">
    <CardHeader className="flex-col sm:flex-row" title={embedded ? 'Explore the engineering assessment' : 'Published fermentation transfer projects'} subtitle="Change assumptions, run the model, or request an agent assessment" actions={!embedded && <select aria-label="Fermentation transfer project" value={caseId} disabled={busy}
      className="max-w-full rounded-control border border-border-strong bg-surface px-3 py-2 text-xs" onChange={e => { setCaseId(e.target.value); setResult(null); setReview(null); setAgent(null); setDirty(false); setSettings({}); setError(''); }}>
      <option value="sulfolobus">Sulfolobus · 2 → 20 / 200 L</option><option value="pichia">Pichia · pressure and oxygen cost</option>
    </select>} />
    <CardBody className="space-y-4">
      {error && <p role="alert" className="rounded-control bg-status-critical-bg p-3 text-xs text-status-critical">{error}</p>}
      {!project ? <p className="text-xs text-text-tertiary">{error ? 'The literature project API is unavailable. Existing transfer records remain below.' : 'Loading source-grounded projects…'}</p> : <>
        <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-base font-semibold">{project.title}</h2><a href={project.url} target="_blank" rel="noreferrer" className="text-xs text-brand-teal underline">Original publication · {project.doi}</a></div><Pill tone="warning">Characterization required</Pill></div>
        <Segmented<Tab> value={tab} onChange={setTab} options={[{ value: 'evidence', label: 'Evidence' }, { value: 'equipment', label: 'Reactors' }, { value: 'analysis', label: 'Assess' }, { value: 'review', label: 'Review' }]} />
        {tab === 'evidence' && <div className="space-y-3 text-xs leading-6">
          <p>Published summaries were transcribed and reviewed with source locations. Full experimental trajectories are unavailable. This is distinct from autonomous extraction or experimentally validated receiving-site control.</p>
          <ul className="list-disc pl-5">{project.citation_locations.map(location => <li key={location}>{location}</li>)}</ul>
          <details><summary className="cursor-pointer font-medium">Inspect source measurements and units</summary><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-control bg-surface-secondary p-3">{JSON.stringify(project.calibration, null, 2)}</pre></details>
          <details><summary className="cursor-pointer font-medium">Culture and characterization conditions</summary><pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-words bg-surface-secondary p-3">{JSON.stringify({conditions:project.conditions,cultivation:project.cultivation_conditions},null,2)}</pre></details><details><summary className="cursor-pointer font-medium">Source manifest, hashes and acquisition</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all bg-surface-secondary p-3">{JSON.stringify(project.source_manifest, null, 2)}</pre><p>Input snapshot: {project.data_hash}</p></details>
          <ul className="list-disc pl-5 text-text-secondary">{project.limitations.map(line => <li key={line}>{line}</li>)}</ul>
          <button className={button} type="button" onClick={() => companion.show({ kind:'text', label:project.title, page_path:'/tech-transfer', captured_at:new Date().toISOString(), content:JSON.stringify({ doi:project.doi, calibration:project.calibration, equipment:project.equipment, missing:project.missing }) })}>Discuss this evidence with the companion</button>
        </div>}
        {tab === 'equipment' && <div className="space-y-3"><div className="overflow-x-auto"><table className={columns}><caption className="mb-2 text-left text-xs text-text-tertiary">Published reactor profiles. Operating settings are not certified equipment limits.</caption><thead><tr><th>Scale</th><th>Reactor</th><th>{pichia ? 'Reported RPM envelope' : 'Submerged impellers'}</th><th>{pichia ? 'Reported air L/min' : 'Impeller diameter'}</th></tr></thead><tbody>{project.equipment.map((e,i) => <tr key={i}><td>{e.working_volume_l ? `${e.working_volume_l} L working / ${e.total_volume_l} L nominal` : `${e.nominal_volume?.value} L nominal`}</td><td>{e.manufacturer} · {e.model}</td><td>{pichia ? e.agitation_operating_range?.value.join('–') || 'Not reported' : `${e.submerged_impellers} Rushton`}</td><td>{pichia ? e.aeration_operating_range?.value.join('–') || 'Not reported' : `${e.impeller_diameter_mm} mm`}</td></tr>)}</tbody></table></div><p className="text-xs text-text-secondary">Working volume, geometry, sparger performance and certified pressure/motor limits must be reconciled. Copying agitation speed or airflow alone does not preserve oxygen capacity.</p><details className="text-xs"><summary className="cursor-pointer">Inspect complete equipment records</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words bg-surface-secondary p-3">{JSON.stringify(project.equipment,null,2)}</pre></details></div>}
        {tab === 'analysis' && <div className="space-y-4">
          <form onSubmit={e => { e.preventDefault(); void run(); }} className="space-y-3">
            <p className="text-xs text-text-secondary">Inputs below are editable scenario assumptions. Run the calculation to update outputs.</p>
            <div className="grid gap-3 sm:grid-cols-3">
              {pichia ? <>{field('Pressure (kPa gauge)','pressure_gauge_kpa',100,50,150)}{field('Air (Nm³/h)','air_nm3_h',36,.1,1000,.1)}{field('Supplemental oxygen (Nm³/h)','oxygen_nm3_h',2,0,100,.1)}{field('Electricity ($/kWh)','electricity_usd_kwh',.12,0,5,.01)}{field('Oxygen ($/Nm³)','oxygen_usd_nm3',.2,0,10,.01)}{field('Common comparison time (h)','comparison_hours',120,1,1000)}</> : <>
                <label className="text-xs text-text-secondary">Receiving working volume<select aria-label="Receiving working volume" value={setting('selected_receiver_l',20)} className="mt-1 block w-full rounded-control border border-border-strong bg-surface px-3 py-2 text-sm" onChange={e => {setSettings(s=>({...s,selected_receiver_l:+e.target.value}));setDirty(true);setReview(null);}}><option value={20}>20 L</option><option value={200}>200 L</option></select></label>
                {field('Scenario agitation (rpm)','rpm',300,20,1000)}{field('Scenario aeration (vvm)','airflow_vvm',.25,.05,1,.01)}{field('Unidentified gas exponent β','gas_exponent',.5,0,1,.05)}{field('Assumed power screen (W/m³)','power_screen_w_m3',1000,50,10000,50)}
              </>}
            </div>
            {pichia && <details className="text-xs"><summary className="cursor-pointer">Oxygen characterization and additional cost assumptions</summary><div className="mt-3 grid gap-3 sm:grid-cols-3">{field('Assumed kLa (h⁻¹)','kla_h_inv',20,.1,1000,.1)}{field('Assumed OUR (mg/L/h)','our_mg_l_h',50,.1,10000,.1)}{field('Absolute DO (mg/L)','dissolved_oxygen_mg_l',1.5,0,30,.1)}{field('Reference air solubility (mg/L)','air_saturation_mg_l',7.5,.1,20,.1)}{field('Broth solubility factor','broth_solubility_factor',.7,.01,1,.01)}{field('Compressor efficiency','compressor_efficiency',.65,.2,1,.01)}{field('Extra methanol (L; omitted until supplied)','extra_methanol_l',0,0,100000)}{field('Methanol ($/L)','methanol_usd_l',.5,0,100,.01)}</div><p className="mt-2 text-text-tertiary">Gas volumes are normalized to 273.15 K and 101.325 kPa; compressor inlet defaults to 303.15 K. Paper airflow reference conditions are unspecified. These assumptions require measured site inputs.</p></details>}
            <button disabled={busy} type="submit" className={`${button} !bg-brand-teal !text-white`}>{busy ? 'Working…' : 'Run deterministic assessment'}</button>
          </form>
          {dirty && result && <Callout tone="warning">Inputs changed. Displayed results describe the previous assumptions; rerun before review.</Callout>}
          {result && <div className="space-y-4" data-testid="fermentation-results">
            <h3 className="text-sm font-semibold">Withheld experimental comparison</h3>
            <div className="overflow-x-auto"><table className={columns}><thead><tr><th>Receiver</th><th>Prediction</th><th>Published summary</th><th>Error</th><th>Reference</th></tr></thead><tbody>{result.validation.rows.map(row => <tr key={row.receiver_l}><td>{row.receiver_l} L</td><td>{fmt(row.predicted)} {row.unit}</td><td>{fmt(row.measured)}{row.measured_sd != null ? ` ± ${fmt(row.measured_sd)} SD` : ''} {row.unit}</td><td>{fmt(row.relative_error*100)}%</td><td>{row.source_location}</td></tr>)}</tbody></table></div>
            <p className="text-xs leading-6 text-text-secondary">{result.validation.conclusion} Only tabulated endpoints are shown; connecting lines are visual guides.</p>
            <ScientificPlot variableName={pichia ? 'Enzyme mass · empirical endpoint baseline' : 'kLa · water characterization'} unit={pichia ? 'mg/L' : 'h⁻¹'} xDomain={[0,pichia?1100:220]} xLabel="Receiver volume (L)" xCoordinateName="receiver_volume_l" batches={[{id:'Published withheld summaries',color:'#64748b',dataPoints:result.validation.rows.map(r=>({elapsedHours:r.receiver_l,value:r.measured}))},{id:pichia?'Constant10L empirical baseline':'Source-only correlation',color:'#0e7490',dataPoints:result.validation.rows.map(r=>({elapsedHours:r.receiver_l,value:r.predicted}))}]} />
            {!pichia && <><p className="text-xs">Your scenario: {fmt(result.prediction.selected_scenario?.rpm)} rpm · {fmt(result.prediction.selected_scenario?.airflow_l_min)} L/min → predicted kLa {fmt(result.prediction.selected_scenario?.predicted_kla_h_inv)} h⁻¹. Receiver behavior remains uncharacterized.</p><div className="space-y-2">{result.prediction.recommendations?.map(r => <p key={r.receiver_l} className="text-xs leading-6"><strong>{r.receiver_l} L conditional candidate:</strong> {r.candidate ? `${fmt(r.candidate.rpm)} rpm, ${fmt(r.candidate.airflow_l_min)} L/min; predicted kLa ${fmt(r.candidate.predicted_kla_h_inv)} h⁻¹, ${fmt(r.candidate.power_w_m3)} W/m³.` : 'No candidate passed the assumed screen.'} Rated equipment feasibility: {r.rated_equipment_feasibility}. Characterize before use.</p>)}</div><details className="text-xs"><summary className="cursor-pointer">Published biological summary and measurement gaps</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words bg-surface-secondary p-3">{JSON.stringify(result.validation.published_outcomes,null,2)}</pre></details><details className="text-xs"><summary className="cursor-pointer">Sensitivity and complete candidate screen</summary><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words bg-surface-secondary p-3">{JSON.stringify(result.prediction.scenarios,null,2)}</pre></details></>}
            {pichia && result.prediction.economics && <><div className="overflow-x-auto"><table className={columns}><caption className="mb-2 text-left">Conditional oxygen delivery and partial operating cost</caption><thead><tr><th>Strategy</th><th>C* mg/L</th><th>OTR mg/L/h</th><th>OUR margin</th><th>Compressor kW</th><th>$/h</th></tr></thead><tbody>{result.prediction.scenarios.map(row => <tr key={row.label}><td>{row.label} · {row.pressure_gauge_kpa} kPa gauge</td><td>{fmt(row.cstar_mg_l)}</td><td>{fmt(row.otr_mg_l_h)}</td><td>{fmt(row.our_margin_mg_l_h)}</td><td>{fmt(row.compressor_kw,3)}</td><td>{fmt(row.partial_cost_usd_h,3)}</td></tr>)}</tbody></table></div><p className="text-xs leading-6">Modeled oxygen-delivery difference: ${fmt(result.prediction.economics.oxygen_delivery_savings_usd_basis)} over a common {result.prediction.economics.common_basis_hours} h basis. Break-even oxygen price: ${fmt(result.prediction.economics.break_even_oxygen_usd_nm3,3)}/Nm³. Excludes {result.prediction.economics.excluded.join(', ')}. These are assumed costs, not measured experimental savings.</p><p className="text-xs">Net after extra methanol: {result.prediction.economics.net_after_extra_feed_usd == null ? 'Unavailable until consumption is supplied' : `$${fmt(result.prediction.economics.net_after_extra_feed_usd)}`}</p><details className="text-xs"><summary className="cursor-pointer">Published 30 L oxygen/pressure comparison and confounding</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words bg-surface-secondary p-3">{JSON.stringify(result.validation.published_outcomes,null,2)}</pre></details></>}
            <details className="text-xs"><summary className="cursor-pointer">Equations, assumptions, model version and frozen evaluation split</summary><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words bg-surface-secondary p-3">{JSON.stringify({models:result.model_manifest,assumptions:result.assumptions,equations:result.prediction.equations,split:result.validation.split,plan_hash:result.plan_hash,prediction_commitment:result.validation.prediction_commitment,target_hash:result.validation.target_hash},null,2)}</pre></details>
            <p className="text-[11px] text-text-tertiary">{fmt(result.resource_usage.runtime_seconds,3)} s deterministic execution · {result.resource_usage.solver_calls} model call. Human preparation time and engineering hours saved were not measured.</p>
          </div>}
        </div>}
        {tab === 'review' && <div className="space-y-4 text-xs leading-6"><p>Review source applicability, missing characterization and any proposed operating conditions before engineering use. These literature projects cannot dispatch production changes.</p><ul className="list-disc pl-5">{project.missing.map(line=><li key={line}>{line}</li>)}</ul><div className="flex flex-wrap gap-2"><button className={button} type="button" disabled={!result || dirty || busy} onClick={()=>void propose()}>Draft engineering review</button><button className={button} type="button" disabled={busy} onClick={()=>void askPrime()}>Ask existing Prime agent</button></div>{review && <Callout tone="info">Proposal {review.proposal_id}: {review.status}. Required roles: {review.required_roles.join(', ')}. Execution: {review.execution_status}.</Callout>}{agent && <Callout tone={agent.status==='completed'&&!partialAgentReport?'info':'warning'} title={`Prime assessment: ${agentReportStatus}`}><p>Run execution: {agent.status}. {partialAgentReport ? 'The agent saved a partial report; scientific verification remains incomplete.' : 'Independent engineering review is required.'}</p><p>{agent.adapter_result.issues?.join(' ')}</p>{agent.output?.analysis?.assessment && <p className="whitespace-pre-wrap">{agent.output.analysis.assessment}</p>}<p>{agent.score_boundary}</p><p>Gateway run: {agent.adapter_result.run_id}. No agent performance scores are substituted.</p>{agent.output && <details><summary className="cursor-pointer">Inspect Prime report and source citations</summary><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(agent.output,null,2)}</pre></details>}</Callout>}<p className="text-text-tertiary">Benchmark paths: conventional engineer workflow (timing unobserved), engineer-prepared physics, and the existing Prime runtime with the same model. Raw-publication extraction accuracy and incremental agent savings require a completed, independently reviewed benchmark.</p></div>}
      </>}
    </CardBody>
  </Card>;
}
