'use client';

import { useEffect, useState } from 'react';
import { Check, TriangleAlert } from 'lucide-react';
import { ScientificPlot } from '@/components/ScientificPlot';
import { processRequest } from '@/lib/process-api';
import type { ArtifactRef } from './AnalysisArtifact';

type Prediction = { value: number; unit: string; time_h: number; state: string };
type Row = { action: string; plan: Record<string, unknown>; status: string; error?: string; predictions?: Record<string, Prediction>; feasible?: boolean | null; violations?: string[]; objective?: number | null };
type History = { time_h: number; [state: string]: unknown };
type CaseInfo = { case_id: string; simulator: string; task_description: string; stratum: string; decision_time_h: number; objective_definition: string; constraints: Record<string, unknown>; action_plans: Record<string, Record<string, unknown>>; forecast_targets: Record<string, { time_h: number; state: string; unit: string }>; completed_source_batch: History[]; current_batch_observations: History[] };
type Comparison = { time_h: number; field: string; unit: string; measured: number; predicted: number; absolute_error: number; sources: string[] };
type Data = {
  id: string; status: string; warnings?: string[]; description?: string;
  // demo case
  case?: CaseInfo;
  // experiment-model forecast
  model?: { id: string; title: string; limitations: string[] }; rows?: Row[]; decision_time_h?: number; objective_definition?: string;
  observed?: { completed_source_batch: History[]; current_batch: History[] }; targets?: Record<string, { time_h: number; state: string; unit: string }>;
  // CHO fit
  batch?: string; cutoff_h?: number; horizon_h?: number; delivery_name?: string; dataset_id?: string; equations?: string;
  fit?: { parameters: Record<string, number>; training_batches: string[]; optimizer_converged: boolean; parameters_at_bounds: string[] };
  trajectory?: { time_h: number; viable_cell_density: number; glucose: number }[];
  holdout_comparison?: Comparison[]; holdout_errors?: Record<string, { readings: number; mean_absolute_error: number; median_measured: number; unit: string }>;
};

const COLORS = ['#0e7490', '#c26a31', '#7c3aed', '#15803d', '#be123c', '#475569', '#a16207', '#0f766e', '#9333ea', '#1d4ed8'];
const fmt = (v: number | null | undefined, d = 2) => v == null ? '—' : Math.abs(v) >= 1e5 ? v.toExponential(2) : v.toFixed(d);
const label = (s: string) => s.replaceAll('_', ' ');
const STATES: Record<string, { name: string; unit: string }> = {
  P: { name: 'Penicillin', unit: 'g/L' }, DO2: { name: 'Dissolved oxygen', unit: 'mg/L' },
  mAb_reactor: { name: 'Reactor antibody', unit: 'mg/L' }, viable_cells_reactor: { name: 'Viable cells', unit: 'cells/L' },
};

function Shell({ artifact, kindLabel, stale, children }: { artifact: ArtifactRef; kindLabel: string; stale: boolean; children: React.ReactNode }) {
  return <section className="my-4 overflow-hidden rounded-card border border-border-hairline bg-surface" aria-label={artifact.title}>
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-hairline px-5 py-3">
      <h3 className="text-sm font-semibold text-text-primary">{artifact.title}</h3>
      <span className={`text-xs ${stale ? 'text-status-critical' : 'text-text-tertiary'}`}>{stale ? 'Evidence changed · rebuild required' : kindLabel}</span>
    </div>
    <div className="p-5 text-sm text-text-secondary">{children}</div>
  </section>;
}

function series(rows: History[], state: string) {
  return rows.filter(r => typeof r[state] === 'number').map(r => ({ elapsedHours: r.time_h, value: r[state] as number }));
}

function CaseView({ info }: { info: CaseInfo }) {
  const states = Object.values(info.forecast_targets).map(t => t.state).filter((s, i, a) => a.indexOf(s) === i);
  const history = info.current_batch_observations.length ? info.current_batch_observations : info.completed_source_batch;
  return <>
    <p>{info.task_description}. Decision at {info.decision_time_h} h. {info.objective_definition}</p>
    <p className="mt-2 text-xs">Limits: {Object.entries(info.constraints).filter(([k]) => k !== 'definition').map(([k, v]) => `${label(k)} ${fmt(v as number)}`).join(' · ')}</p>
    <div className="mt-4 space-y-3">{states.map(s => <ScientificPlot key={s} variableName={STATES[s]?.name ?? s} unit={STATES[s]?.unit ?? ''} xLabel="Time (h)" xDomain={[0, Math.max(1, ...Object.values(info.forecast_targets).map(t => t.time_h), ...[...info.completed_source_batch, ...info.current_batch_observations].map(r => r.time_h))]}
      batches={[{ id: 'Completed source batch', color: '#94a3b8', dataPoints: series(info.completed_source_batch, s) },
        ...(info.current_batch_observations.length ? [{ id: 'Current batch (observed)', color: '#0e7490', dataPoints: series(info.current_batch_observations, s) }] : [])]}
      markers={info.decision_time_h ? [{ hour: info.decision_time_h, label: 'Decision', tone: 'neutral' }] : undefined} />)}</div>
    <p className="mt-3 text-xs text-text-tertiary">{history.length} recorded time points · simulated case from the physics A/B experiment, not plant data.</p>
  </>;
}

function ForecastView({ data }: { data: Data }) {
  const rows = data.rows ?? [];
  const done = rows.filter(r => r.status === 'completed');
  const targets = Object.entries(data.targets ?? {});
  const states = targets.map(([, t]) => t.state).filter((s, i, a) => a.indexOf(s) === i);
  const best = done.filter(r => r.feasible).sort((a, b) => (b.objective ?? -Infinity) - (a.objective ?? -Infinity))[0];
  const final = targets.filter(([, t]) => t.time_h === Math.max(...targets.map(([, x]) => x.time_h)));
  return <>
    <div className="overflow-x-auto"><table className="w-full text-left text-xs">
      <caption className="sr-only">Forecast for each operating plan</caption>
      <thead><tr className="border-b border-border-hairline text-text-tertiary"><th className="py-2 pr-3">Plan</th><th className="pr-3">Settings</th>{final.map(([f, t]) => <th key={f} className="pr-3">{STATES[t.state]?.name ?? t.state} at {t.time_h} h</th>)}<th className="pr-3">Objective</th><th>Limits</th></tr></thead>
      <tbody>{rows.map(r => <tr key={r.action} className={`border-b border-border-hairline ${r === best ? 'bg-brand-teal-light/40' : ''}`}>
        <th className="py-2.5 pr-3 font-medium">{r.action}{r === best && <span className="ml-1.5 text-[10px] font-normal text-brand-teal">best feasible</span>}</th>
        <td className="pr-3 text-text-tertiary">{Object.entries(r.plan).filter(([k]) => !k.startsWith('apply') && k !== 'change_after_h').map(([k, v]) => `${label(k).replace(' factor', '')} ${v}×`).join(', ')}</td>
        {r.status !== 'completed' ? <td colSpan={final.length + 2} className="text-status-critical">Failed: {r.error}</td> : <>
          {final.map(([f, t]) => <td key={f} className="pr-3 tabular-nums">{fmt(r.predictions?.[f]?.value)} {t.unit}</td>)}
          <td className="pr-3 tabular-nums">{fmt(r.objective)}</td>
          <td>{r.feasible ? <span className="inline-flex items-center gap-1 text-status-success"><Check size={13} />within</span> : <span className="inline-flex items-center gap-1 text-status-critical"><TriangleAlert size={13} />{(r.violations ?? []).map(label).join(', ')}</span>}</td>
        </>}
      </tr>)}</tbody>
    </table></div>
    <p className="mt-2 text-xs text-text-tertiary">Objective: {data.objective_definition}</p>
    <div className="mt-4 space-y-3">{states.map(s => {
      const observed = [...(data.observed?.completed_source_batch.length && !data.observed.current_batch.length ? [{ id: 'Completed source batch', color: '#94a3b8', dataPoints: series(data.observed.completed_source_batch, s) }] : []),
        ...(data.observed?.current_batch.length ? [{ id: 'Observed', color: '#334155', dataPoints: series(data.observed.current_batch, s) }] : [])];
      const last = observed.at(-1)?.dataPoints.at(-1);
      const forecasts = done.map((r, i) => ({ id: r.action, color: COLORS[i % COLORS.length], dataPoints: [
        ...(last && data.observed?.current_batch.length ? [last] : []),
        ...targets.filter(([, t]) => t.state === s).map(([f, t]) => ({ elapsedHours: t.time_h, value: r.predictions?.[f]?.value ?? NaN })).filter(p => Number.isFinite(p.value)).sort((a, b) => a.elapsedHours - b.elapsedHours)] }));
      const end = Math.max(1, ...targets.map(([, t]) => t.time_h), ...observed.flatMap(o => o.dataPoints.map(d => d.elapsedHours)));
      return <ScientificPlot key={s} variableName={`${STATES[s]?.name ?? s} · forecast by plan`} unit={STATES[s]?.unit ?? ''} xLabel="Time (h)" xDomain={[0, end]} batches={[...observed, ...forecasts]}
        markers={data.decision_time_h ? [{ hour: data.decision_time_h, label: 'Decision', tone: 'neutral' }] : undefined} />;
    })}</div>
  </>;
}

function ChoView({ data }: { data: Data }) {
  const traj = data.trajectory ?? [];
  const observed = (data as unknown as { observed: { time_h: number; field: string; value: number }[] }).observed ?? [];
  const fields = [['viable_cell_density', 'Viable cell density', 'million cells/mL'], ['glucose', 'Glucose', 'g/L']] as const;
  return <>
    <p>Fitted to {data.fit?.training_batches.length} other batches in {data.delivery_name ?? 'the verified delivery'} ({data.fit?.training_batches.join(', ')}). {data.batch} is conditioned on its readings up to {data.cutoff_h} h; later readings are used only to check the forecast.</p>
    <div className="mt-4 grid gap-3 sm:grid-cols-2">{fields.map(([f, name, unit]) => { const e = data.holdout_errors?.[f]; return <div key={f} className="rounded-control border border-border-hairline p-3">
      <p className="text-xs text-text-tertiary">{name} · forecast error after {data.cutoff_h} h</p>
      <p className="mt-1 text-lg font-medium tabular-nums text-text-primary">{e ? `${fmt(e.mean_absolute_error)} ${unit}` : 'No later readings'}</p>
      {e && <p className="text-xs text-text-tertiary">mean absolute error over {e.readings} readings · typical value {fmt(e.median_measured)}</p>}
    </div>; })}</div>
    <div className="mt-4 space-y-3">{fields.map(([f, name, unit]) => <ScientificPlot key={f} variableName={name} unit={unit} xLabel="Culture time (h)" xDomain={[0, data.horizon_h ?? 120]}
      batches={[{ id: 'Model', color: '#0e7490', dataPoints: traj.map(p => ({ elapsedHours: p.time_h, value: p[f] })) },
        { id: 'Measured (verified)', color: '#334155', dataPoints: observed.filter(o => o.field === f).map(o => ({ elapsedHours: o.time_h, value: o.value })) }]}
      markers={[{ hour: data.cutoff_h ?? 72, label: 'Forecast starts', tone: 'neutral' }]} />)}</div>
    {!!data.holdout_comparison?.length && <details className="mt-3 text-xs"><summary className="cursor-pointer">Forecast against each later reading</summary>
      <table className="mt-2 w-full text-left"><thead><tr className="text-text-tertiary"><th className="py-1">Time</th><th>Field</th><th>Measured</th><th>Forecast</th><th>Source</th></tr></thead>
        <tbody>{data.holdout_comparison.map(c => <tr key={`${c.field}-${c.time_h}`} className="border-t border-border-hairline"><td className="py-1.5">{c.time_h} h</td><td>{label(c.field)}</td><td className="tabular-nums">{fmt(c.measured)} {c.unit}</td><td className="tabular-nums">{fmt(c.predicted)}</td><td className="text-text-tertiary">{c.sources.join('; ')}</td></tr>)}</tbody></table>
    </details>}
    <p className="mt-3 text-xs text-text-tertiary">{data.equations}. Fitted parameters: {Object.entries(data.fit?.parameters ?? {}).map(([k, v]) => `${label(k)} ${fmt(v, 4)}`).join(', ')}{data.fit?.parameters_at_bounds.length ? ` (at bound: ${data.fit.parameters_at_bounds.map(label).join(', ')})` : ''}.</p>
  </>;
}

export function BioprocessArtifact({ threadId, artifact }: { threadId: string; artifact: ArtifactRef }) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let current = true;
    processRequest<Data>(`/v1/process-model/conversations/${threadId}/artifacts/${artifact.kind}/${artifact.id}`)
      .then(r => { if (current) setData(r); }).catch(e => { if (current) setError(String(e)); });
    return () => { current = false; };
  }, [threadId, artifact.id, artifact.kind, artifact.status]);
  const stale = ['stale', 'quarantined'].includes(data?.status ?? artifact.status ?? '');
  const kindLabel = artifact.kind === 'bioprocess_case' ? 'Simulated demo case' : artifact.kind === 'bioprocess_cho_forecast' ? 'Fitted to verified delivery' : 'Calculated forecast · simulated case';
  return <Shell artifact={artifact} kindLabel={kindLabel} stale={stale}>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p>Loading saved artifact…</p>}
    {data && (stale ? <p>{data.warnings?.join(' ')}</p> : <>
      {artifact.kind === 'bioprocess_case' && data.case && <CaseView info={data.case} />}
      {artifact.kind === 'bioprocess_forecast' && <ForecastView data={data} />}
      {artifact.kind === 'bioprocess_cho_forecast' && <ChoView data={data} />}
      {!!data.warnings?.length && <details className="mt-4 text-xs"><summary className="cursor-pointer">Limits and applicability</summary><ul className="mt-2 list-disc pl-5">{data.warnings.map(w => <li key={w}>{w}</li>)}</ul></details>}
      <details className="mt-3 text-xs"><summary className="cursor-pointer text-text-tertiary">Inspect inputs and record</summary><pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all rounded bg-surface-secondary p-3">{JSON.stringify(data, null, 2)}</pre></details>
    </>)}
  </Shell>;
}
