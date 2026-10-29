'use client';

import { useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { Callout, Card, CardBody, CardHeader } from '@/components/ui';
import { ScientificPlot } from '@/components/ScientificPlot';
import { processRequest } from '@/lib/process-api';
import type { GeometryRecord } from './VialScene';

const VialScene = dynamic(() => import('./VialScene'), { ssr: false, loading: () => <p>Loading the 3D review renderer…</p> });
type Model = { id: string; title: string; version: string; implementation_digest: string; description: string; limitations: string[]; required_inputs: string[]; applicability?: { applicable: boolean; missing_inputs: string[] } };
type Plan = { id: string; status: string; authored_by: { kind: string; gateway_run_id: string | null }; plan_hash: string; steps: { id: string; depends_on: string[] }[]; pinned_models: (Model & { rationale: string })[]; spec: { calibration_until_h: number; evidence_cutoff_h: number; temperature_observable: string }; source_snapshot: { observation_provenance: string } };
type Point = { time_h: number; interface_temperature_c: number; remaining_ice_kg_per_vial: number };
type Output = { model_id: string; status: string; error?: string; applicability?: { missing_inputs: string[] }; rationale: string; prediction?: { completion_time_h: number | null; minimum_critical_margin_c: number | null; trajectory: Point[]; violations: { constraint: string; first_time_h: number }[]; warnings: string[] }; holdout_evaluation?: { rmse_c: number | null; points: number; coverage: number | null; pairs: { time_h: number; residual_c: number }[] }; calibration?: { estimate?: number; training_points?: number }; uncertainty?: { samples: number; completion_p05_p50_p95_h: number[] | null; constraint_sample_frequency: number; interpretation: string }; geometry?: GeometryRecord };
type Analysis = { id: string; status: string; execution_status: string; models: Output[]; ranking: string[]; ranking_basis: string; warnings: string[]; holdout_observations: { time_h: number; product_temperature_c: number }[]; resource_usage: { solver_calls: number; maximum_solver_calls: number; runtime_seconds: number } };
type HistoryOutput = Output & { evaluation_prediction?: { trajectory: Point[] } | null };
type Assessment = { summary: string; model_tradeoffs: string[]; limitations: string[]; verification_experiments: string[] };

const field = 'block w-full mt-1 border border-border rounded bg-surface p-2';
const button = 'rounded border border-teal-700 px-3 py-2 text-teal-900 bg-teal-50 disabled:opacity-40';
const number = (value: number | null | undefined) => value == null ? 'Unavailable' : value.toFixed(3);

export function AnalysisWorkbench({ simulationId, candidateIndex, sourceStale, hasObservations }: { simulationId: string; candidateIndex: number; sourceStale: boolean; hasObservations: boolean }) {
  const [catalog, setCatalog] = useState<Model[]>([]);
  const [selected, setSelected] = useState(['lyo.kv_rp', 'lyo.transient_lumped']);
  const [objective, setObjective] = useState('Compare primary-drying models, evaluate their discrepancies and prepare a reviewable engineering analysis.');
  const [thermal, setThermal] = useState(false);
  const [heatCapacity, setHeatCapacity] = useState(3);
  const [initialTemp, setInitialTemp] = useState(-43);
  const [calibration, setCalibration] = useState('none');
  const [sampleCount, setSampleCount] = useState(4);
  const [randomSeed, setRandomSeed] = useState(2025);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [agentNote, setAgentNote] = useState('');
  const [review, setReview] = useState('');
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [assessmentNote, setAssessmentNote] = useState('');
  const [activeModel, setActiveModel] = useState('lyo.kv_rp');
  const [window, setWindow] = useState<'full' | 'validation'>('full');
  const [adapterTitle, setAdapterTitle] = useState('');
  const [equations, setEquations] = useState('');
  const [inputs, setInputs] = useState('');
  const [license, setLicense] = useState('');
  const [validation, setValidation] = useState('');
  const draftRevision = useRef(0);

  useEffect(() => {
    let current = true;
    draftRevision.current += 1;
    setPlan(null); setAnalysis(null); setReview(''); setAgentNote(''); setError(''); setAssessment(null); setAssessmentNote('');
    processRequest<{ models: Model[] }>(`/v1/process-model/catalog?simulation_id=${encodeURIComponent(simulationId)}&candidate_index=${candidateIndex}`)
      .then(data => { if (current) setCatalog(data.models); }).catch(e => { if (current) setError(String(e)); });
    return () => { current = false; };
  }, [simulationId, candidateIndex]);

  function invalidateDraft() { draftRevision.current += 1; setPlan(null); setAnalysis(null); setReview(''); setAssessment(null); setAssessmentNote(''); }
  const assumptions = thermal ? { vial_heat_capacity_j_k: heatCapacity, initial_temperature_c: initialTemp } : null;

  async function prepare(agent: boolean) {
    const revision = draftRevision.current;
    setBusy(true); setError(''); setAgentNote(''); setAnalysis(null); setReview('');
    try {
      const common = { simulation_id: simulationId, candidate_index: candidateIndex, objective, thermal_assumptions: assumptions };
      if (agent) {
        const result = await processRequest<{ status: string; plan: Plan | null; issues?: string[]; note?: string; gateway_run: { run_id: string; issues: string[] } }>('/v1/process-model/pipelines/agent-plan', common);
        if (revision !== draftRevision.current) return;
        setPlan(result.plan);
        if (!result.plan) setAgentNote(`${result.note ?? result.issues?.join('; ') ?? result.status} Gateway record ${result.gateway_run.run_id}: ${result.gateway_run.issues.join('; ')}`);
      } else {
        const result = await processRequest<Plan>('/v1/process-model/pipelines', { ...common, calibration, samples: sampleCount, seed: randomSeed, max_solver_calls: 64,
          models: selected.map(model_id => ({ model_id, rationale: model_id === 'lyo.kv_rp' ? 'Use a rapid quasi-steady screening baseline and inspect its missing thermal dynamics.' : 'Evaluate finite thermal response to the schedule, subject to explicit thermal input assumptions.' })) });
        if (revision !== draftRevision.current) return;
        setPlan(result);
      }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function run() {
    if (!plan) return;
    const revision = draftRevision.current;
    setBusy(true); setError(''); setReview(''); setAssessment(null); setAssessmentNote('');
    try {
      const result = await processRequest<Analysis>(`/v1/process-model/pipelines/${plan.id}/execute`, {});
      if (revision !== draftRevision.current) return;
      setAnalysis(result); setActiveModel(result.models.find(m => m.status === 'completed')?.model_id ?? 'lyo.kv_rp');
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function sendReview() {
    if (!analysis) return;
    setBusy(true); setError('');
    try {
      const result = await processRequest<{ proposal_id: string; status: string; execution_status: string }>(`/v1/process-model/analyses/${analysis.id}/review`, { owner_id: 'priya' });
      setReview(`Engineering review proposal ${result.proposal_id} · ${result.status} · execution ${result.execution_status}`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function proposeAdapter() {
    setBusy(true); setError('');
    try {
      const result = await processRequest<{ proposal_id: string }>('/v1/process-model/adapter-proposals', {
        simulation_id: simulationId, model_id: `proposed.${adapterTitle.toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 60)}`,
        title: adapterTitle, governing_equations: equations, required_inputs_and_units: inputs.split('\n').filter(Boolean),
        source_and_license: license, verification_and_validation_plan: validation,
        intended_use_and_limits: objective, owner_id: 'priya' });
      setReview(`Adapter review proposal ${result.proposal_id}. No model was registered and no new code was executed.`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function assess() {
    if (!analysis) return;
    const revision = draftRevision.current;
    setBusy(true); setError(''); setAssessmentNote('');
    try {
      const result = await processRequest<{ status: string; interpretation: Assessment | null; gateway_run: { issues: string[] } }>(`/v1/process-model/analyses/${analysis.id}/agent-assessment`, {});
      if (revision !== draftRevision.current) return;
      setAssessment(result.interpretation);
      if (!result.interpretation) setAssessmentNote(`Agent assessment unavailable: ${result.gateway_run.issues.join('; ') || result.status}. Numerical evidence remains available for engineer review.`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  const completed = analysis?.models.filter(m => m.status === 'completed' && m.prediction) ?? [];
  const active = completed.find(m => m.model_id === activeModel);
  const color = ['#0f766e', '#b45309'];
  const domain: [number, number] = window === 'validation' ? [0, plan?.spec.evidence_cutoff_h ?? 6] : [0, 75];
  const trajectories = completed.map((model, i) => {
    const m = model as HistoryOutput;
    const prediction = window === 'validation' && m.evaluation_prediction ? m.evaluation_prediction : m.prediction!;
    return { id: m.model_id, color: color[i], dataPoints: prediction.trajectory.map(p => ({ elapsedHours: p.time_h, value: p.interface_temperature_c })) };
  });
  if (analysis?.holdout_observations.length) trajectories.push({ id: 'Holdout observations · provenance below', color: '#7c3aed', dataPoints: analysis.holdout_observations.map(p => ({ elapsedHours: p.time_h, value: p.product_temperature_c })) });

  function exportBundle() {
    const url = URL.createObjectURL(new Blob([JSON.stringify({ plan, analysis, assessment }, null, 2)], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = `${analysis?.id ?? plan?.id}-pipeline.json`; a.click(); URL.revokeObjectURL(url);
  }

  return <Card><CardHeader title="Model selection and analysis pipeline" subtitle="The agent selects registered models and proposes a reproducible plan. Engineers can inspect and edit model choices before running." />
    <CardBody><div className="space-y-4">
      <label className="block">Engineering objective<textarea className={field} value={objective} rows={2} onChange={e => { setObjective(e.target.value); invalidateDraft(); }} /></label>
      <div className="grid gap-3 md:grid-cols-2">{catalog.map(m => <div key={m.id} className="border rounded p-3"><label className="font-medium flex gap-2"><input type="checkbox" checked={selected.includes(m.id)} onChange={e => { setSelected(values => e.target.checked ? [...values, m.id] : values.filter(id => id !== m.id)); invalidateDraft(); }} />{m.title}</label><p className="mt-2">{m.description}</p><p className="mt-1 text-xs text-text-secondary">{m.version} · {m.id}</p>{m.required_inputs.length > 0 && <p className="mt-2 text-xs">Additional inputs: {m.required_inputs.join(', ')}</p>}<details className="mt-2 text-xs"><summary>Applicability and limitations</summary><ul className="list-disc pl-5 mt-1">{m.limitations.map(text => <li key={text}>{text}</li>)}</ul></details></div>)}</div>
      <div className="rounded border p-3"><label className="flex items-center gap-2"><input type="checkbox" checked={thermal} onChange={e => { setThermal(e.target.checked); invalidateDraft(); }} />Use explicit thermal assumptions for the transient model</label><p className="text-xs mt-1 text-text-secondary">These inputs are synthetic assumptions requiring characterization. Leaving them absent blocks the transient calculation while keeping the screening model available.</p>{thermal && <div className="grid gap-3 sm:grid-cols-2 mt-3"><label>Assumed vial heat capacity (J/K)<input type="number" min={.1} max={100} step={.1} value={heatCapacity} className={field} onChange={e => { setHeatCapacity(+e.target.value); invalidateDraft(); }} /></label><label>Assumed initial product temperature (°C)<input type="number" min={-65} max={-1} value={initialTemp} className={field} onChange={e => { setInitialTemp(+e.target.value); invalidateDraft(); }} /></label></div>}</div>
      <div className="flex flex-wrap items-end gap-3"><label>Calibration<select aria-label="Pipeline calibration" className={field} value={calibration} onChange={e => { setCalibration(e.target.value); invalidateDraft(); }}><option value="none">Use supplied parameters unchanged</option><option value="kv_scale" disabled={!hasObservations}>Fit Kv on observations ≤3 h</option></select></label><label>Pipeline uncertainty samples<select aria-label="Pipeline uncertainty samples" className={field} value={sampleCount} onChange={e => { setSampleCount(+e.target.value); invalidateDraft(); }}>{[0, 4, 8, 16].map(n => <option key={n}>{n}</option>)}</select></label><label>Pipeline random seed<input type="number" min={0} className={field} value={randomSeed} onChange={e => { setRandomSeed(+e.target.value); invalidateDraft(); }} /></label></div>
      <div className="flex flex-wrap items-end gap-3"><button className={button} disabled={busy || sourceStale} onClick={() => prepare(true)}>Ask agent to plan analysis</button><button className={button} disabled={busy || sourceStale || selected.length === 0} onClick={() => prepare(false)}>Save engineer-authored pipeline</button></div>
      <p className="text-xs text-text-secondary">Model selection can change; numerical calculations remain reproducible. Agent planning uses the existing qualified investigation route. New adapters require review; generated solver code is not executed.</p>
      {busy && <p role="status">Preparing or executing the requested analysis…</p>}
      {agentNote && <Callout tone="warning" title="Agent planning unavailable">{agentNote}</Callout>}
      {error && <div role="alert"><Callout tone="critical" title="Analysis needs attention">{error}</Callout></div>}
      {plan && <div className="border rounded p-3 space-y-3"><p className="font-medium">Saved pipeline · authored by {plan.authored_by.kind} · {plan.id}</p><ol className="grid gap-2 md:grid-cols-3">{plan.steps.map((s, i) => <li key={s.id} className="bg-slate-50 rounded p-2 text-xs">{i+1}. {s.id.replaceAll('_', ' ')}</li>)}</ol>{plan.pinned_models.map(m => <p key={m.id} className="text-xs"><strong>{m.title}</strong>: {m.rationale}</p>)}<p className="text-xs">Evaluation observable: {plan.spec.temperature_observable}. Training window ends at {plan.spec.calibration_until_h} h; holdout ends at {plan.spec.evidence_cutoff_h} h. Observation provenance: {plan.source_snapshot.observation_provenance}.</p><button className={button} disabled={busy || sourceStale || plan.status !== 'current'} onClick={run}>{busy ? 'Executing bounded pipeline…' : 'Execute saved pipeline'}</button></div>}
      {analysis && <div className="space-y-4">
        <div className="flex flex-wrap gap-3 items-center"><p className="font-medium">Analysis result: {analysis.execution_status} · {analysis.id}</p><button className="underline" onClick={exportBundle}>Export reproducible pipeline</button><button className={button} disabled={busy || sourceStale || !completed.length} onClick={assess}>Ask agent to assess results</button><button className={button} disabled={busy || sourceStale || !completed.length || !!review} onClick={sendReview}>Create engineering review</button></div>
        <p className="text-xs">{analysis.resource_usage.solver_calls}/{analysis.resource_usage.maximum_solver_calls} solver calls · {analysis.resource_usage.runtime_seconds.toFixed(2)} s. {analysis.ranking.length ? `Holdout discrepancy order: ${analysis.ranking.join(' → ')}.` : 'No model ranking is supported by the available holdout coverage.'} {analysis.ranking_basis}</p>
        <div className="overflow-x-auto"><table className="text-xs w-full text-left"><caption className="sr-only">Physical model evaluation</caption><thead><tr>{['Model', 'Status', 'Completion h', 'Critical margin °C', 'Holdout RMSE °C', 'Coverage', 'Constraints / missing inputs'].map(h => <th className="p-2 border-b" key={h}>{h}</th>)}</tr></thead><tbody>{analysis.models.map(m => <tr key={m.model_id}><td className="p-2">{m.model_id}</td><td className="p-2">{m.status}</td><td className="p-2">{number(m.prediction?.completion_time_h)}</td><td className="p-2">{number(m.prediction?.minimum_critical_margin_c)}</td><td className="p-2">{number(m.holdout_evaluation?.rmse_c)}</td><td className="p-2">{number(m.holdout_evaluation?.coverage)}</td><td className="p-2">{m.error ?? m.applicability?.missing_inputs.join(', ') ?? m.prediction?.violations.map(v => `${v.constraint} at ${v.first_time_h.toFixed(2)} h`).join('; ') ?? 'Unavailable'}</td></tr>)}</tbody></table></div>
        {completed.length > 0 && <><div className="flex flex-wrap gap-3"><label>Chart window<select aria-label="Pipeline chart window" value={window} className={field} onChange={e => setWindow(e.target.value as 'full' | 'validation')}><option value="full">Full primary-drying trajectory</option><option value="validation">Training / holdout window</option></select></label><label>Model for 3D and uncertainty<select aria-label="Model for 3D and uncertainty" className={field} value={activeModel} onChange={e => setActiveModel(e.target.value)}>{completed.map(m => <option key={m.model_id}>{m.model_id}</option>)}</select></label></div>
        <div className="grid gap-4 xl:grid-cols-2"><div><h3 className="font-medium mb-2">Selected-model temperature predictions</h3><ScientificPlot batches={trajectories} variableName="Model comparison temperature" unit="°C" xDomain={domain} kalmanStateActive={false} xLabel="Primary drying time (h)" markers={[{ hour: plan?.spec.calibration_until_h ?? 3, label: 'Fit / holdout split' }]} /></div><div><h3 className="font-medium mb-2">Holdout residuals</h3>{analysis.holdout_observations.length ? <ScientificPlot batches={completed.map((m, i) => ({ id: m.model_id, color: color[i], dataPoints: m.holdout_evaluation!.pairs.map(p => ({ elapsedHours: p.time_h, value: p.residual_c })) }))} variableName="Predicted minus observed" unit="°C" xDomain={[0, plan?.spec.evidence_cutoff_h ?? 6]} referenceEnvelope={{ min: 0, max: 0 }} kalmanStateActive={false} xLabel="Primary drying time (h)" /> : <p>No holdout observations exist for this source. The pipeline cannot report measured model error.</p>}</div></div>
        {active?.geometry && <div className="border rounded p-3"><h3 className="font-medium mb-2">3D engineering review · {active.model_id}</h3><VialScene geometry={active.geometry} recordId={analysis.id} /></div>}
        {active?.uncertainty && <p className="text-xs">{active.uncertainty.samples} assumed-distribution samples. Completion P05/P50/P95: {active.uncertainty.completion_p05_p50_p95_h?.map(v => v.toFixed(2)).join(' / ') ?? 'Unavailable'} h. Constraint sample frequency: {(active.uncertainty.constraint_sample_frequency*100).toFixed(1)}%. {active.uncertainty.interpretation}</p>}</>}
        <details><summary className="cursor-pointer">Scientific limits and source manifest</summary><ul className="mt-2 list-disc pl-5 text-xs">{analysis.warnings.map(w => <li key={w}>{w}</li>)}</ul><pre className="overflow-auto max-h-64 mt-2 text-xs">{JSON.stringify(plan?.pinned_models, null, 2)}</pre></details>
        <p className="text-xs text-text-secondary">Holdout scores use the original observed operating history and newly fitted parameters. Proposed interventions are shown as forecasts and are not graded as if they had been executed.</p>
        {assessmentNote && <Callout tone="warning" title="Agent result assessment">{assessmentNote}</Callout>}
        {assessment && <div className="border rounded p-3 space-y-2"><h3 className="font-medium">Agent interpretation · draft requiring engineer review</h3><p>{assessment.summary}</p><h4 className="font-medium">Model trade-offs</h4><ul className="list-disc pl-5">{assessment.model_tradeoffs.map(text => <li key={text}>{text}</li>)}</ul><h4 className="font-medium">Limits and next experiments</h4><ul className="list-disc pl-5">{[...assessment.limitations, ...assessment.verification_experiments].map(text => <li key={text}>{text}</li>)}</ul></div>}
      </div>}
      {review && <p role="status" className="p-3 rounded bg-teal-50">{review}</p>}
      <details className="border-t pt-3"><summary className="cursor-pointer font-medium">Propose a new model adapter for review</summary><div className="grid gap-3 mt-3 md:grid-cols-2"><label>Proposed model title<input value={adapterTitle} className={field} onChange={e => setAdapterTitle(e.target.value)} /></label><label>Sources and license<input value={license} className={field} onChange={e => setLicense(e.target.value)} /></label><label>Governing equations<textarea rows={3} value={equations} className={field} onChange={e => setEquations(e.target.value)} /></label><label>Required inputs and units (one per line)<textarea rows={3} value={inputs} className={field} onChange={e => setInputs(e.target.value)} /></label><label className="md:col-span-2">Verification and independent validation plan<textarea rows={3} value={validation} className={field} onChange={e => setValidation(e.target.value)} /></label><button className={button} disabled={busy || sourceStale} onClick={proposeAdapter}>Submit adapter review proposal</button></div></details>
    </div></CardBody>
  </Card>;
}
