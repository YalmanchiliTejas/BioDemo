'use client';

import { useState } from 'react';
import { ArrowDownToLine, Play, FlaskConical } from 'lucide-react';
import { Callout, Card, CardBody, CardHeader, PageHeader, Pill, Stat } from '@/components/ui';
import { ScientificPlot } from '@/components/ScientificPlot';
import { AnalysisWorkbench } from '@/components/process/AnalysisWorkbench';

type Row = { time_h: number; interface_temperature_c: number; remaining_ice_kg_per_vial: number; sublimation_kg_h: number; capacity_margin_kg_h: number; critical_margin_c: number };
type Config = { equipment: { equipment_id: string; site_id: string; revision: string; vapor_capacity_kg_h: number; condenser_capacity_kg: number; shelf_area_m2: number; missing_parameters: string[] }; product: { critical_temperature_c: number }; load_vials: number; schedule: { time_h: number; shelf_temperature_c: number; chamber_pressure_pa: number }[] };
type Uncertainty = { samples: number; seed: number; constraint_sample_frequency: number; not_completed_samples: number; interpretation: string; completion_time_h_p05_p50_p95_conditional_on_completion: number[] | null; active_temperature_intervals: { time_h: number; temperature_c_p05_p50_p95: number[]; active_samples: number }[] };
type Option = { label: string; feasible: boolean; config: Config; load_vials: number; completion_time_h: number | null; throughput_vials_h: number | null; critical_margin_c: number | null; capacity_margin_kg_h: number | null; uncertainty?: Uncertainty; result: { trajectory: Row[]; warnings: string[]; numerical_status: string; violations: { constraint: string; first_time_h: number }[] } };
type Verification = { responsible_reviewer: string; experiments: { experiment: string; acceptance_criteria: string }[]; release_boundary: string };
type Run = { id: string; status: string; model_version: string; source_revision_manifest: { id: string; revision: number }[]; verification: Verification; input_bundle: { parameter_manifest: { parameter: string; value: number; unit: string; category: string; location_or_transformation: string }[] }; workspace: { audience: string; options: Option[]; recommended_index: number | null; runtime_seconds: number; intervention_boundary?: string; evidence_cutoff_h?: number; diagnosis?: { observations: { time_h: number; product_temperature_c: number }[]; hypotheses: { hypothesis: string; estimate: number | null; temperature_rmse_c: number; interpretation: string }[]; ambiguity: string; discriminating_experiment: string } } };
type Proposal = { proposal_id: string; status: string; execution_status: string; required_roles: string[]; rationale: string; expected_result: string; owner_id: string; constraints: string[] };

const API = process.env.NEXT_PUBLIC_LIFESCI_API_URL ?? 'http://127.0.0.1:8100';
const fmt = (n: number | null | undefined, digits = 2) => n == null ? 'Unavailable' : n.toFixed(digits);
const inputStyle = 'mt-1 block w-full rounded border border-border px-3 py-2 bg-surface text-text-primary';
const buttonStyle = 'inline-flex items-center gap-2 rounded bg-teal-700 px-4 py-2 text-white disabled:opacity-50 hover:bg-teal-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2';

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API}${path}`, { method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', 'X-Tenant-Id': 'demo-northfield', 'X-Actor-Id': 'priya',
      ...(body ? { 'Idempotency-Key': crypto.randomUUID() } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail ?? `API request failed (${response.status})`);
  return data;
}

export default function ProcessSimulation() {
  const [audience, setAudience] = useState<'technology_transfer' | 'cdmo_operation'>('technology_transfer');
  const [shelf, setShelf] = useState(-24);
  const [load, setLoad] = useState(11000);
  const [capacity, setCapacity] = useState(.65);
  const [samples, setSamples] = useState(8);
  const [futureShelf, setFutureShelf] = useState(-14);
  const [run, setRun] = useState<Run | null>(null);
  const [analysisContext, setAnalysisContext] = useState<{ id: string; has_observations: boolean } | null>(null);
  const [selected, setSelected] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [stale, setStale] = useState(false);
  const workspace = run?.workspace;
  const option = workspace?.options[selected];
  const chosen = workspace?.recommended_index != null ? workspace.options[workspace.recommended_index] : null;
  const changeInput = () => { setStale(true); setProposal(null); };

  async function calculate() {
    setBusy(true); setError(''); setProposal(null); setStale(true);
    try {
      const result = await request<Run>('/v1/process-model/runs', { audience, shelf_c: shelf, load_vials: load, capacity_kg_h: capacity, samples, seed: 2025, cdmo_future_shelf_c: futureShelf });
      setRun(result); setAnalysisContext(null); setSelected(result.workspace.recommended_index ?? (audience === 'technology_transfer' ? 1 : 0)); setStale(false);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function startModelSelection() {
    setBusy(true); setError(''); setProposal(null); setStale(true);
    try {
      const result = await request<{ id: string; has_observations: boolean }>('/v1/process-model/contexts', { audience, shelf_c: shelf, load_vials: load, capacity_kg_h: capacity, samples, seed: 2025, cdmo_future_shelf_c: futureShelf });
      setAnalysisContext(result); setRun(null); setStale(false);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function propose() {
    if (!run) return;
    setBusy(true); setError('');
    try {
      const p = await request<Proposal>(`/v1/process-model/runs/${run.id}/recommendation`, { owner_id: 'priya' });
      setProposal(p);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function refresh() {
    if (!run) return;
    try { const r = await request<Run>(`/v1/process-model/runs/${run.id}`); setRun(r); if (r.status !== 'current') setStale(true); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify({ simulation: run, proposal }, null, 2)], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = `${run?.id}.json`; a.click(); URL.revokeObjectURL(url);
  }

  const displayed = workspace ? [...new Set([0, audience === 'technology_transfer' ? 1 : 0, selected])].map(i => ({ index: i, option: workspace.options[i] })) : [];
  const colors = ['#64748b', '#b45309', '#0f766e'];
  const series = (key: keyof Row) => displayed.map(({ option: o }, i) => ({ id: o.label, color: colors[i], dataPoints: o.result.trajectory.map(r => ({ elapsedHours: r.time_h, value: r[key] })) }));
  const tempSeries = series('interface_temperature_c');
  if (workspace?.diagnosis) tempSeries.push({ id: 'Synthetic observations · available ≤6 h', color: '#7c3aed', dataPoints: workspace.diagnosis.observations.map(r => ({ elapsedHours: r.time_h, value: r.product_temperature_c })) });
  const bands = option?.uncertainty?.active_temperature_intervals;
  if (bands) for (const q of [0, 2]) tempSeries.push({ id: q === 0 ? 'Sample P05 · active vials' : 'Sample P95 · active vials', color: '#94a3b8', dataPoints: bands.map(r => ({ elapsedHours: r.time_h, value: r.temperature_c_p05_p50_p95[q] })) });

  return <div className="mx-auto max-w-[1320px] space-y-4">
    <PageHeader title="Predictive process engineering" frameId="PROCESS-SIMULATION" agent={false} crumbs={[{ label: 'Improve' }, { label: 'Process simulation' }]}
      status={<Pill tone="info">Executed physics · unqualified demonstration</Pill>}
      description="Select physical models, generate reproducible analysis pipelines, and review predictions for technology transfer and CDMO operation." />
    <Callout tone="warning" title="Published case, reconstructed demonstration">
      <a className="underline" href="https://doi.org/10.1186/s41120-025-00115-5" target="_blank" rel="noreferrer">Vanbillemont et al., AAPS Open (2025)</a> supplies formulation and heat/mass-transfer parameters. Raw experimental trajectories are unavailable. Local capacity derating and CDMO observations are synthetic. This workspace calls the live API; the platform’s general agent dock remains a sample experience.
    </Callout>
    <div className="flex flex-wrap gap-2" role="group" aria-label="Audience">
      {(['technology_transfer', 'cdmo_operation'] as const).map(a => <button key={a} aria-pressed={audience === a} className={`rounded px-4 py-2 border ${audience === a ? 'bg-teal-50 border-teal-700 text-teal-900' : 'bg-surface border-border'}`} onClick={() => { setAudience(a); setRun(null); setAnalysisContext(null); setProposal(null); setError(''); }}>{a === 'technology_transfer' ? 'Technology transfer' : 'CDMO operation'}</button>)}
    </div>
    <Card><CardHeader title={audience === 'technology_transfer' ? 'Assess a receiving dryer' : 'Forecast from an evidence cutoff'} subtitle={audience === 'technology_transfer' ? 'BSA / sucrose / Tris formulation · 2.50 mL in 6R vials · critical interface temperature −28°C' : 'Synthetic current run · observations available through 6 h · known scheduled shelf change at 8 h'} />
      <CardBody>
        {audience === 'technology_transfer' ? <div className="grid gap-4 sm:grid-cols-4">
          <label>Receiving shelf (°C)<input className={inputStyle} type="number" min={-28} max={-20} value={shelf} onChange={e => { setShelf(+e.target.value); changeInput(); }} /></label>
          <label>Receiving load (vials)<input className={inputStyle} type="number" min={100} max={11000} step={100} value={load} onChange={e => { setLoad(+e.target.value); changeInput(); }} /></label>
          <label>Assumed vapor capacity (kg/h)<input className={inputStyle} type="number" min={.1} max={2} step={.05} value={capacity} onChange={e => { setCapacity(+e.target.value); changeInput(); }} /></label>
          <label>Uncertainty samples<select className={inputStyle} value={samples} onChange={e => { setSamples(+e.target.value); changeInput(); }}>{[8, 16, 32].map(n => <option key={n}>{n}</option>)}</select></label>
        </div> : <div className="grid gap-4 md:grid-cols-[1fr_240px]"><p>The same Kv–Rp model tests changed heat transfer, changed product resistance and reduced vapor capacity. Independent transient, two-population calculations generate the labeled synthetic observations. Future outcomes stay outside the analysis inputs.</p><label>Planned shelf at 8 h (°C)<input type="number" min={-24} max={-10} value={futureShelf} className={inputStyle} onChange={e => { setFutureShelf(+e.target.value); changeInput(); }} /></label></div>}
        <div className="mt-4 flex flex-wrap items-center gap-3"><button disabled={busy} onClick={startModelSelection} className={buttonStyle}>Start model selection</button><button disabled={busy} onClick={calculate} className="rounded border px-4 py-2 disabled:opacity-50"><Play size={15} className="inline mr-2" />{busy ? 'Preparing analysis…' : audience === 'technology_transfer' ? 'Run transfer comparison' : 'Run CDMO analysis'}</button><span className="text-xs text-text-secondary">Development API · stored MSAT actor priya · seed 2025</span></div>
        <p className="mt-3 text-xs text-text-secondary">{audience === 'technology_transfer' ? 'Published commercial deposition capacity: 1.49 kg/h. The default 0.65 kg/h represents an uncharacterized derated receiving site. Site names do not enter the equations.' : 'Only information available at the cutoff is fitted. Temperature measurements alone cannot identify vapor capacity; ambiguous causes remain open.'}</p>
      </CardBody>
    </Card>
    {error && <div role="alert"><Callout tone="critical" title="Calculation or review unavailable">{error}. Start the seeded life-sciences API at {API}; no sample results have been substituted.</Callout></div>}
    {stale && run && <Callout tone="warning" title="Inputs changed or result is stale">The plots still show the previous input revision. Run the comparison again before drafting a recommendation.</Callout>}
    {analysisContext && <><p className="text-xs text-text-secondary">Versioned input context prepared. Model choices and executed results appear in the saved pipeline below.</p>{stale && <Callout tone="warning" title="Source inputs changed">Start model selection again to use the changed source revision.</Callout>}<AnalysisWorkbench simulationId={analysisContext.id} candidateIndex={0} sourceStale={stale} hasObservations={analysisContext.has_observations} /></>}
    {workspace && option && run && <>
      <AnalysisWorkbench simulationId={run.id} candidateIndex={selected} sourceStale={stale} hasObservations={!!workspace.diagnosis} />
      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Selected candidate" value={option.feasible ? 'Nominally feasible' : 'Constraint / incomplete'} kind="calculated" />
        <Stat label="Primary drying completion" value={fmt(option.completion_time_h)} unit="h" kind="calculated" />
        <Stat label="Minimum critical margin" value={fmt(option.critical_margin_c)} unit="°C" kind="calculated" />
        <Stat label="Minimum vapor headroom" value={fmt(option.capacity_margin_kg_h)} unit="kg/h" kind="calculated" />
      </div>
      <Card><CardHeader title="Operating comparisons" subtitle="Select a row to inspect its forecast. Feasibility is a nominal model result; throughput covers primary drying only." />
        <CardBody><div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="sr-only">Executed primary drying candidates</caption><thead><tr>{['Candidate', 'Load', 'Completion (h)', 'Critical margin (°C)', 'Vapor margin (kg/h)', 'Vials/h', 'Assessment'].map(h => <th key={h} className="p-2 border-b">{h}</th>)}</tr></thead><tbody>{workspace.options.map((o, i) => <tr key={o.label} className={selected === i ? 'bg-teal-50' : ''}>
          <td className="p-2"><button className="underline text-left" onClick={() => setSelected(i)} aria-pressed={selected === i}>{o.label}{i === workspace.recommended_index ? ' · recommended' : ''}</button></td><td className="p-2">{o.load_vials}</td><td className="p-2">{fmt(o.completion_time_h)}</td><td className="p-2">{fmt(o.critical_margin_c)}</td><td className="p-2">{fmt(o.capacity_margin_kg_h)}</td><td className="p-2">{fmt(o.throughput_vials_h, 1)}</td><td className="p-2">{o.feasible ? 'Nominally feasible' : o.result.violations.map(v => `${v.constraint} at ${fmt(v.first_time_h)} h`).join('; ') || o.result.numerical_status}</td>
        </tr>)}</tbody></table></div></CardBody>
      </Card>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card><CardHeader title="Product temperature" subtitle="Predicted sublimation interface; observed reference thermometry is shown separately." /><CardBody><ScientificPlot batches={tempSeries} variableName="Temperature" unit="°C" xDomain={[0, 75]} referenceEnvelope={{ min: -28, max: -28 }} kalmanStateActive={false} xLabel="Primary drying time (h)" markers={workspace.evidence_cutoff_h ? [{ hour: workspace.evidence_cutoff_h, label: 'Evidence cutoff' }] : []} /></CardBody></Card>
        <Card><CardHeader title="Remaining ice" subtitle="Predicted frozen water per vial; final residual moisture is not modeled." /><CardBody><ScientificPlot batches={series('remaining_ice_kg_per_vial').map(s => ({ ...s, dataPoints: s.dataPoints.map(p => ({ ...p, value: p.value*1000 })) }))} variableName="Ice remaining" unit="g/vial" xDomain={[0, 75]} kalmanStateActive={false} xLabel="Primary drying time (h)" /></CardBody></Card>
        <Card><CardHeader title="Sublimation rate" subtitle="Predicted total batch vapor load." /><CardBody><ScientificPlot batches={series('sublimation_kg_h')} variableName="Sublimation" unit="kg/h" xDomain={[0, 75]} kalmanStateActive={false} xLabel="Primary drying time (h)" /></CardBody></Card>
        <Card><CardHeader title="Vapor capacity margin" subtitle="Negative margin invalidates the imposed-pressure prediction as a controlled operating forecast." /><CardBody><ScientificPlot batches={series('capacity_margin_kg_h')} variableName="Headroom" unit="kg/h" xDomain={[0, 75]} referenceEnvelope={{ min: 0, max: 0 }} kalmanStateActive={false} xLabel="Primary drying time (h)" /></CardBody></Card>
      </div>
      {workspace.diagnosis && <Card><CardHeader title="Deviation investigation" subtitle="Three hypotheses; fit quality is not causal certainty." /><CardBody><div className="grid gap-4 md:grid-cols-3">{workspace.diagnosis.hypotheses.map(h => <div key={h.hypothesis} className="p-3 border rounded"><h3 className="font-medium">{h.hypothesis.replaceAll('_', ' ')}</h3><p className="my-2">Temperature RMSE: {fmt(h.temperature_rmse_c)} °C · parameter: {fmt(h.estimate)}</p><p className="text-xs text-text-secondary">{h.interpretation}</p></div>)}</div><p className="mt-3">{workspace.diagnosis.ambiguity}</p><p className="mt-2 font-medium">Next measurement: {workspace.diagnosis.discriminating_experiment}</p><p className="mt-2">{workspace.intervention_boundary}</p></CardBody></Card>}
      <Card><CardHeader title="Equipment and utility boundary" subtitle="Versioned representation; reconstructed utilities do not imply a characterized facility." /><CardBody><div className="grid gap-4 md:grid-cols-2">{workspace.options.slice(0, audience === 'technology_transfer' ? 2 : 1).map(o => <div key={o.label} className="rounded border p-3"><p className="font-medium">{o.config.equipment.equipment_id} · rev {o.config.equipment.revision}</p><p className="mt-2">Thermal fluid → shelves ({o.config.equipment.shelf_area_m2} m²) → vials → chamber → condenser</p><p className="mt-2">Vapor capacity {o.config.equipment.vapor_capacity_kg_h} kg/h · assumed ice storage {o.config.equipment.condenser_capacity_kg} kg</p><p className="mt-2 text-xs">Missing: {o.config.equipment.missing_parameters.join('; ')}</p></div>)}</div></CardBody></Card>
      <Card><CardHeader title="Recommendation and verification" subtitle={chosen ? `${chosen.label} · proposed engineering option` : 'No feasible recommendation: characterize equipment or assess product damage.'} actions={<button className={buttonStyle} disabled={busy || stale || !chosen || !!proposal} onClick={propose}><FlaskConical size={16} />Draft for review</button>} /><CardBody>
        {chosen && <p>Predicted completion: {fmt(chosen.completion_time_h)} h; critical margin: {fmt(chosen.critical_margin_c)}°C. {audience === 'technology_transfer' ? 'The bounded comparison prioritizes primary-drying throughput. Lower loading reduces batch size; lower shelf temperature extends drying.' : 'The bounded comparison prioritizes cycle duration subject to nominal constraints. Thermometry leaves competing explanations; additional characterization can change the recommendation.'}</p>}
        {chosen?.uncertainty && <p className="mt-3">{chosen.uncertainty.samples} samples · seed {chosen.uncertainty.seed}. Conditional completion P05 / P50 / P95: {chosen.uncertainty.completion_time_h_p05_p50_p95_conditional_on_completion?.map(v => fmt(v)).join(' / ') ?? 'unavailable'} h. {chosen.uncertainty.not_completed_samples} samples did not complete. Constraint sample frequency: {fmt(100*chosen.uncertainty.constraint_sample_frequency, 1)}%. {chosen.uncertainty.interpretation}</p>}
        <p className="mt-3 font-medium">Reviewer: {run.verification.responsible_reviewer}</p><ol className="mt-3 space-y-3 list-decimal pl-5">{run.verification.experiments.map(e => <li key={e.experiment}>{e.experiment}<p className="text-xs text-text-secondary mt-1">Acceptance: {e.acceptance_criteria}</p></li>)}</ol><p className="mt-3">{run.verification.release_boundary}</p>
        {proposal && <div className="mt-4 p-4 bg-teal-50 rounded" role="status"><p className="font-medium">Review package saved · {proposal.proposal_id}</p><p>Status: {proposal.status} · execution: {proposal.execution_status} · required reviewers: {proposal.required_roles.join(', ')}</p><p>Owner: {proposal.owner_id} · {proposal.expected_result}</p><p className="mt-2">This is an existing version-bound proposal. Separate MSAT and QA decisions and required authentication are enforced by the platform. No production action was dispatched.</p></div>}
      </CardBody></Card>
      <Card><CardHeader title="Scientific record" subtitle={`${run.id} · ${run.model_version} · ${run.status} · executed in ${fmt(workspace.runtime_seconds)} s`} actions={<><button onClick={refresh} className="underline text-xs">Check currentness</button><button onClick={download} className="flex items-center gap-1 text-xs underline"><ArrowDownToLine size={14} />Export record</button></>} /><CardBody><p>Input lineage: {run.source_revision_manifest.map(r => `${r.id} @ revision ${r.revision}`).join(', ')}. Parameters, solver settings, source revisions, schedules, uncertainty seed, trajectories and warnings are retained.</p><details className="mt-3"><summary className="cursor-pointer font-medium">Inspect parameters and provenance</summary><div className="overflow-auto max-h-80"><table className="w-full text-xs text-left mt-2"><thead><tr>{['Parameter', 'Value / unit', 'Category', 'Source location / extraction'].map(h => <th className="p-2" key={h}>{h}</th>)}</tr></thead><tbody>{run.input_bundle.parameter_manifest.map(p => <tr key={p.parameter}><td className="p-2">{p.parameter}</td><td className="p-2">{p.value} {p.unit}</td><td className="p-2">{p.category}</td><td className="p-2">{p.location_or_transformation}</td></tr>)}</tbody></table></div></details><details className="mt-3"><summary className="cursor-pointer font-medium">Applicability and numerical warnings</summary><ul className="list-disc pl-5 mt-2 space-y-1">{option.result.warnings.map(w => <li key={w}>{w}</li>)}</ul></details></CardBody></Card>
    </>}
  </div>;
}
