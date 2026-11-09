'use client';
import { useState } from 'react';
import { ScientificPlot } from '@/components/ScientificPlot';

type Json = Record<string, unknown>;
type Manifest = { id: string; title: string; version: string; analysis_contract: { axis: string; observables: Record<string,string> } };
export type LibraryResult = { id?: string; status?: string; execution_status?: string; spec?: { mode?: string; operation?: string }; output?: Json;
  model_manifest?: Manifest[]; pinned_models?: Manifest[]; configuration_contract?: { axis: string; observables: Record<string,string> };
  input_bundle?: { config?: Json; family?: string }; checkpoint?: Json; interval_calibration?: Json; partition_counts?: Json;
  resource_usage?: { solver_calls: number; runtime_seconds: number }; error?: { type: string; message: string }; warnings?: string[]; artifacts?: {kind:string;id:string}[] };

export function ModelLibraryResult({ data }: { data: LibraryResult }) {
  const manifest=data.model_manifest?.[0] ?? data.pinned_models?.[0];
  const contract=manifest?.analysis_contract ?? data.configuration_contract;
  const [selected,setSelected]=useState('');
  const observable=selected || Object.keys(contract?.observables ?? {})[0] || '';
  const output=data.output ?? data.checkpoint ?? data.interval_calibration ?? {};
  const simulation=output.simulation as {trajectory?: Record<string,number>[]; violations?: unknown[];hybrid?:{out_of_domain:boolean}} | undefined;
  const curve=simulation?.trajectory;
  const interval=output as {mean?:number[];basis?:[string,string,number][];calibration_status?:string;calibrated_lower?:number[]|null;calibrated_upper?:number[]|null;whole_run_coverage?:number|null;scored_coverage_batches?:number;abstentions?:number;failed_predictions?:number;constraint_violations?:number};
  const stale=['stale','quarantined'].includes(data.status ?? '');
  const checkpoint=(output.checkpoint ?? data.checkpoint) as {negative_transfer?:boolean;selected_model?:string;classification?:string} | undefined;
  const calibration=(output.interval_calibration ?? data.interval_calibration) as {status?:string;independent_calibration_groups?:number;reason?:string} | undefined;
  return <section className="space-y-4 rounded-card border border-border-hairline bg-surface p-5" aria-label="Pharmaceutical model result">
    <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-base font-medium">{manifest?.title ?? 'Pharmaceutical model analysis'}</h3><span className="text-xs text-text-secondary">{stale?'Evidence changed · reassessment required':data.execution_status ?? data.status ?? 'Saved draft'}</span></div>
    {stale ? <p>Predictions are withheld because contributing evidence changed. Refresh the configuration and reassess the affected analysis.</p> : <>
      {data.error && <p role="alert" className="text-status-critical">{data.error.type}: {data.error.message}</p>}
      {checkpoint && <p role="status">{checkpoint.negative_transfer ? 'Negative transfer detected. Adapted predictions are withheld pending review.' : `Checkpoint saved · selected model: ${checkpoint.selected_model ?? 'review required'}.`} {checkpoint.classification?.replaceAll('_',' ')}</p>}
      {calibration && <p role="status"><strong>Interval status: {calibration.status?.replaceAll('_',' ')}</strong>. {calibration.independent_calibration_groups ?? 0} eligible independent calibration batches. {calibration.reason}</p>}
      {simulation?.hybrid?.out_of_domain && <p role="status">Operating conditions extend beyond the learned feature support. Calibrated intervals and risk probabilities are withheld.</p>}
      {curve && contract && <><label className="block text-sm">Observable<select className="ml-3 rounded border border-border-strong bg-surface p-2" value={observable} onChange={e=>setSelected(e.target.value)}>{Object.entries(contract.observables).filter(([key])=>key in curve[0]).map(([key,unit])=><option key={key} value={key}>{key.replaceAll('_',' ')} ({unit})</option>)}</select></label>{observable in curve[0] && <ScientificPlot variableName={observable.replaceAll('_',' ')} unit={contract.observables[observable]} xLabel={contract.axis.replaceAll('_',' ')} xCoordinateName={contract.axis} xDomain={[0,Math.max(1,curve[curve.length-1][contract.axis])]} batches={[{id:'Conditional model calculation',color:'#0e7490',dataPoints:curve.map(row=>({elapsedHours:row[contract.axis],value:row[observable]}))}]}/>}</>}
      {interval.mean && interval.basis && <div className="overflow-auto"><table className="w-full text-left text-xs"><caption className="mb-3 text-left">Prediction intervals · {interval.calibration_status?.replaceAll('_',' ') ?? 'uncalibrated'}</caption><thead><tr><th>Observable / coordinate</th><th>Mean</th><th>Calibrated lower</th><th>Calibrated upper</th></tr></thead><tbody>{interval.mean.map((v,i)=><tr key={i} className="border-t border-border-hairline"><th className="py-2 font-normal">{interval.basis?.[i]?.[0]} @ {interval.basis?.[i]?.[2]}</th><td>{v.toPrecision(4)} {interval.basis?.[i]?.[1]}</td><td>{interval.calibrated_lower?.[i]?.toPrecision(4) ?? 'Withheld'}</td><td>{interval.calibrated_upper?.[i]?.toPrecision(4) ?? 'Withheld'}</td></tr>)}</tbody></table></div>}
      {interval.scored_coverage_batches !== undefined && <p className="text-sm">Empirical whole-run coverage: {interval.whole_run_coverage == null ? 'unavailable' : `${(100*interval.whole_run_coverage).toFixed(1)}%`} across {interval.scored_coverage_batches} scored batches. Abstentions: {interval.abstentions ?? 0}; failed predictions: {interval.failed_predictions ?? 0}; constraint violations: {interval.constraint_violations ?? 0}.</p>}
      {simulation?.violations && <p className="text-sm">Constraint violations: {simulation.violations.length ? JSON.stringify(simulation.violations) : 'None reported within this model and numerical resolution'}</p>}
      {data.partition_counts && <dl className="grid grid-cols-2 gap-3 text-sm">{Object.entries(data.partition_counts).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{String(value)} source-identified groups</dd></div>)}</dl>}
      {data.resource_usage && <p className="text-xs text-text-secondary">{data.resource_usage.solver_calls} solver calls · {data.resource_usage.runtime_seconds.toFixed(2)} s · saved for engineering review.</p>}
      <p className="text-xs leading-6 text-text-secondary">Model outputs are conditional calculations. Ensemble spread and sensitivity ranges alone are not calibrated uncertainty. Conversion does not establish desired-product yield, product quality or release suitability.</p>
      {data.artifacts?.map(a=><p className="text-xs" key={a.id}>Saved {a.kind.replaceAll('_',' ')}: <code>{a.id}</code></p>)}
      <details className="text-xs"><summary className="cursor-pointer">Inspect results, model version, assumptions and evidence lineage</summary><pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-words rounded bg-surface-secondary p-4">{JSON.stringify(data,null,2)}</pre></details>
    </>}
  </section>;
}
