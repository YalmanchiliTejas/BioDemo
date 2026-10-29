'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { ScientificPlot } from '@/components/ScientificPlot';
import { processRequest } from '@/lib/process-api';
import type { GeometryRecord } from './VialScene';

const VialScene = dynamic(() => import('./VialScene'), { ssr: false, loading: () => <p>Loading 3D review…</p> });
export type ArtifactRef = { id: string; kind: string; title: string; status?: string };
type Point = { time_h: number; interface_temperature_c: number; rate_kg_s_per_vial: number; remaining_ice_kg_per_vial: number; capacity_margin_kg_h: number };
type Model = { model_id: string; status: string; error?: string; applicability?: { missing_inputs: string[] }; rationale: string; prediction?: { completion_time_h: number | null; minimum_critical_margin_c: number | null; minimum_capacity_margin_kg_h: number | null; trajectory: Point[]; violations: { constraint: string; first_time_h: number }[] }; geometry?: GeometryRecord; holdout_evaluation?: { rmse_c: number | null; points: number }; uncertainty?: { completion_p05_p50_p95_h: number[] | null; interpretation: string } };
type RecordData = { id: string; status: string; models?: Model[]; warnings?: string[]; spec?: { views: string[] }; resource_usage?: { solver_calls: number; runtime_seconds: number }; series?: { id: string; trajectory: Point[] }[]; rows?: { label: string; result_id: string; model_id: string; completion_time_h: number | null; minimum_critical_margin_c: number | null; minimum_capacity_margin_kg_h: number | null; violations: { constraint: string; first_time_h: number; last_time_h: number }[]; holdout_rmse_c: number | null }[]; source_snapshot?: unknown; pinned_models?: { title: string; rationale: string }[]; scenario_changes?: { label: string; rationale: string }; input_bundle?: { observation_provenance: string; parameter_manifest: unknown[] }; workspace?: { audience: string }; summary?: string; verification_experiments?: string[]; proposal_id?: string; operation?: string; expected_result?: string; constraints?: string[] };
const fmt = (v: number | null | undefined) => v == null ? '—' : v.toFixed(2);
const colors = ['#0e7490', '#c26a31', '#7c3aed'];

export function AnalysisArtifact({ threadId, artifact }: { threadId: string; artifact: ArtifactRef }) {
  const [data, setData] = useState<RecordData | null>(null);
  const [error, setError] = useState('');
  const [view, setView] = useState<'charts' | '3d'>('charts');
  const [selected, setSelected] = useState(0);
  useEffect(() => {
    let current = true;
    processRequest<RecordData>(`/v1/process-model/conversations/${threadId}/artifacts/${artifact.kind}/${artifact.id}`)
      .then(result => { if (current) setData(result); }).catch(e => { if (current) setError(String(e)); });
    return () => { current = false; };
  }, [threadId, artifact.id, artifact.kind, artifact.status]);
  const models = data?.models?.filter(m => m.prediction) ?? [];
  const active = models[selected] ?? models[0];
  const stale = ['stale', 'quarantined'].includes(data?.status ?? artifact.status ?? '');
  const maxTime = Math.max(1, ...models.flatMap(m => m.prediction!.trajectory.map(p => p.time_h)));
  return <section className="my-4 overflow-hidden rounded-card border border-border-hairline bg-surface" aria-label={artifact.title}>
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-hairline px-5 py-3">
      <h3 className="text-sm font-semibold text-text-primary">{artifact.title}</h3>
      <span className={`text-xs ${stale ? 'text-status-critical' : 'text-text-tertiary'}`}>{stale ? 'Evidence changed · rebuild required' : artifact.kind === 'physical_analysis_result' ? 'Calculated prediction' : artifact.kind === 'physical_analysis_plan' ? 'Agent-selected plan' : 'Review artifact'}</span>
    </div>
    <div className="p-5 text-sm text-text-secondary">
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p>Loading saved artifact…</p>}
      {stale ? <p>{data?.warnings?.join(' ')}</p> : <>
        {data?.models?.filter(m => m.status !== 'completed').map(m => <p role="status" key={m.model_id} className="mb-3 rounded-control bg-status-warning-bg p-3">{m.model_id}: {m.status.replaceAll('_', ' ')}. {m.error ?? m.applicability?.missing_inputs.join(', ') ?? 'Inspect the saved numerical status before using this result.'}</p>)}
        {!!models.length && <>
          <div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="sr-only">Model predictions and constraints</caption><thead><tr className="border-b border-border-hairline text-text-tertiary"><th className="py-2 pr-3">Model</th><th className="pr-3">Drying completion</th><th className="pr-3">Critical margin</th><th className="pr-3">Vapor capacity margin</th><th>Constraints</th></tr></thead><tbody>{models.map(m => <tr key={m.model_id} className="border-b border-border-hairline"><th className="py-3 pr-3 font-medium">{m.model_id}</th><td>{fmt(m.prediction!.completion_time_h)} h</td><td>{fmt(m.prediction!.minimum_critical_margin_c)} °C</td><td>{fmt(m.prediction!.minimum_capacity_margin_kg_h)} kg/h</td><td>{m.prediction!.violations.length ? m.prediction!.violations.map(v => `${v.constraint} at ${fmt(v.first_time_h)} h`).join('; ') : 'No modeled violations'}</td></tr>)}</tbody></table></div>
          <div className="my-4 flex gap-2" aria-label="Result view">
            <button type="button" aria-pressed={view === 'charts'} onClick={() => setView('charts')} className="rounded-control border border-border-strong px-3 py-1.5">Charts</button>
            {models.some(m => m.geometry) && <button type="button" aria-pressed={view === '3d'} onClick={() => setView('3d')} className="rounded-control border border-border-strong px-3 py-1.5">3D review</button>}
          </div>
          {view === 'charts' ? <div className="space-y-3">
            <ScientificPlot variableName="Predicted interface temperature" unit="°C" xLabel="Elapsed drying time (h)" xDomain={[0, maxTime]} batches={models.map((m, i) => ({ id: m.model_id, color: colors[i % colors.length], dataPoints: m.prediction!.trajectory.map(p => ({ elapsedHours: p.time_h, value: p.interface_temperature_c })) }))} />
            <ScientificPlot variableName="Remaining ice per vial" unit="g" xLabel="Elapsed drying time (h)" xDomain={[0, maxTime]} batches={models.map((m, i) => ({ id: m.model_id, color: colors[i % colors.length], dataPoints: m.prediction!.trajectory.map(p => ({ elapsedHours: p.time_h, value: p.remaining_ice_kg_per_vial * 1000 })) }))} />
            <ScientificPlot variableName="Sublimation rate per vial" unit="mg/h" xLabel="Elapsed drying time (h)" xDomain={[0, maxTime]} batches={models.map((m, i) => ({ id: m.model_id, color: colors[i % colors.length], dataPoints: m.prediction!.trajectory.map(p => ({ elapsedHours: p.time_h, value: p.rate_kg_s_per_vial * 3.6e9 })) }))} />
          </div> : <>
            {models.length > 1 && <label className="block mb-3">Displayed model <select className="ml-2 rounded border border-border-strong p-1" value={selected} onChange={e => setSelected(Number(e.target.value))}>{models.map((m, i) => <option value={i} key={m.model_id}>{m.model_id}</option>)}</select></label>}
            {active?.geometry && <VialScene key={`${artifact.id}-${active.model_id}`} geometry={active.geometry} recordId={artifact.id} />}
          </>}
          {models.map(m => <p className="mt-3 text-xs" key={m.model_id}>{m.model_id}: {m.rationale}{m.uncertainty?.completion_p05_p50_p95_h ? ` Conditional drying time p05 / p50 / p95: ${m.uncertainty.completion_p05_p50_p95_h.map(fmt).join(' / ')} h.` : ''}{m.holdout_evaluation?.rmse_c != null ? ` Holdout RMSE ${fmt(m.holdout_evaluation.rmse_c)} °C (${m.holdout_evaluation.points} observations).` : ' Independent measurement error unavailable.'}</p>)}
          <p className="mt-3 text-xs text-text-tertiary">{data?.resource_usage?.solver_calls} solver calls · {fmt(data?.resource_usage?.runtime_seconds)} s. Primary-drying predictions do not establish final moisture or release suitability.</p>
        </>}
        {data?.rows && <div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="mb-3 text-left">Conditional operating scenario comparison</caption><thead><tr><th>Source result / model</th><th>Completion (h)</th><th>Critical margin (°C)</th><th>Vapor margin (kg/h)</th><th>Constraints</th></tr></thead><tbody>{data.rows.map(r => <tr key={`${r.result_id}-${r.model_id}`} className="border-t border-border-hairline"><th className="py-3 pr-3 font-normal">{r.label} / {r.model_id}</th><td>{fmt(r.completion_time_h)}</td><td>{fmt(r.minimum_critical_margin_c)}</td><td>{fmt(r.minimum_capacity_margin_kg_h)}</td><td>{r.violations.map(v => `${v.constraint}: ${fmt(v.first_time_h)}–${fmt(v.last_time_h)} h`).join("; ") || "No modeled violations"}</td></tr>)}</tbody></table></div>}
        {!!data?.series?.length && <ScientificPlot variableName="Scenario interface temperatures" unit="°C" xLabel="Elapsed drying time (h)" xDomain={[0, Math.max(1, ...data.series.flatMap(s => s.trajectory.map(p => p.time_h)))]} batches={data.series.map((s, i) => ({ id: s.id, color: colors[i % colors.length], dataPoints: s.trajectory.map(p => ({ elapsedHours: p.time_h, value: p.interface_temperature_c })) }))} />}
        {!!data?.series?.length && <ScientificPlot variableName="Scenario vapor-capacity margin" unit="kg/h" xLabel="Elapsed drying time (h)" xDomain={[0, Math.max(1, ...data.series.flatMap(s => s.trajectory.map(p => p.time_h)))]} batches={data.series.map((s, i) => ({ id: s.id, color: colors[i % colors.length], dataPoints: s.trajectory.map(p => ({ elapsedHours: p.time_h, value: p.capacity_margin_kg_h })) }))} />}
        {data?.pinned_models?.map(m => <p className="mb-2" key={m.title}><strong>{m.title}</strong> — {m.rationale}</p>)}
        {data?.input_bundle && <><p>{data.scenario_changes?.rationale ?? 'Source inputs are published values combined with documented reconstruction assumptions.'}</p><p className="mt-2 text-xs">Observations: {data.input_bundle.observation_provenance}. {data.workspace?.audience.replaceAll('_', ' ')}.</p></>}
        {data?.summary && <p className="whitespace-pre-wrap">{data.summary}</p>}
        {data?.verification_experiments && <ul className="mt-3 list-disc pl-5">{data.verification_experiments.map(s => <li key={s}>{s}</li>)}</ul>}
        {data?.proposal_id && <><p>{data.expected_result}</p><p className="mt-2">Status: {data.status}. Responsible engineering review is required.</p></>}
        {!!data?.warnings?.length && <details className="mt-4 text-xs"><summary className="cursor-pointer">Limits and applicability</summary><ul className="mt-2 list-disc pl-5">{data.warnings.map(w => <li key={w}>{w}</li>)}</ul></details>}
        <details className="mt-3 text-xs"><summary className="cursor-pointer text-text-tertiary">Inspect source, parameters and record</summary><pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all rounded bg-surface-secondary p-3">{JSON.stringify(data, null, 2)}</pre></details>
      </>}
    </div>
  </section>;
}
