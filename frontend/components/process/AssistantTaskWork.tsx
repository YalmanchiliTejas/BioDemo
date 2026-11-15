'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight, Loader2, Play, RefreshCw, Search } from 'lucide-react';
import { ProcessApiError, processRequest } from '@/lib/process-api';
import { emptyTask, getTaskCatalog, getTaskResult, routeRequest, runTask, type DecisionModel, type SourceRef, type SuggestedTask, type TaskCatalog, type TaskContext, type TaskDecision, type TaskResult, type TaskRoute, type TaskSpec } from '@/lib/assistant-workflows';

export const workButton = 'inline-flex items-center justify-center gap-1.5 rounded-control border border-border-strong bg-surface px-3 py-2 text-xs font-medium text-text-secondary hover:bg-surface-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-teal disabled:opacity-40';
const field = 'mt-1 block w-full rounded-control border border-border-strong bg-surface px-2.5 py-2 text-sm text-text-primary';
const th = 'border-b border-border-hairline p-2 font-medium text-text-tertiary', td = 'max-w-xs break-words border-b border-border-hairline p-2 align-top';
/** A provisional delivery is still in review: its values are used only when the person asks, and the result says so. */
export type TaskDataset = { id: string; delivery_name?: string | null; cmo?: string; measurements?: number; status?: string; batches?: string[] | null; parameters?: string[] | null;
  verification?: 'verified' | 'provisional'; review?: { pending_values?: number; rejected_values?: number; open_issues?: number } | null };
const list = (text: string) => [...new Set(text.split(',').map(s => s.trim()).filter(Boolean))];
const count = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const words = (text: string) => text.replaceAll('_', ' ');
/** Four significant figures: enough to read a difference, without implying more precision than was recorded. */
const fig = (value: unknown, digits = 4) => typeof value === 'number' && Number.isFinite(value) ? String(Number(value.toPrecision(digits))) : value == null ? '—' : String(value);
const hours = (value: unknown) => fig(value, 6); // Recorded times are shown as recorded, without floating-point noise.
const RECORD_KINDS: Record<string, string> = { deviation_signal: 'Deviation signal', case: 'Case', batch: 'Batch', sample: 'Sample', evidence: 'Evidence' };
const MEASURED = ['compare', 'reconcile', 'check_gaps'];

export function TaskFields({ task, onChange, catalog, datasets, fixedOperation = false }: {
  task: TaskSpec; onChange: (task: TaskSpec) => void; catalog: TaskCatalog; datasets: TaskDataset[]; fixedOperation?: boolean;
}) {
  const edit = <K extends keyof TaskSpec>(key: K, value: TaskSpec[K]) => onChange({ ...task, [key]: value });
  const operation = catalog.find(item => item.id === task.operation);
  const selectedSeries = task.series ?? [];
  const selected = datasets.filter(dataset => task.dataset_ids.includes(dataset.id));
  // Names are offered from the ticked deliveries, or from every listed delivery while none is ticked.
  const recorded = (key: 'parameters' | 'batches') => [...new Set((selected.length ? selected : datasets).flatMap(dataset => dataset[key] ?? []))];
  function toggleDataset(id: string, checked: boolean) {
    const series = selectedSeries.filter(value => checked || value.dataset_id !== id);
    onChange({ ...task, dataset_ids: checked ? [...task.dataset_ids, id] : task.dataset_ids.filter(value => value !== id), series,
      record_refs: task.record_refs.filter(ref => checked || ref.kind !== 'evidence' || ref.id !== id),
      batches: selectedSeries.length ? [...new Set(series.map(value => value.batch))] : task.batches });
  }
  const arrayField = (key: 'batches' | 'kinds' | 'expected_parameters' | 'expected_document_kinds', label: string, placeholder?: string) =>
    <label className="block text-xs text-text-secondary">{label}<input aria-label={label} disabled={key === 'batches' && selectedSeries.length > 0} className={field} value={task[key].join(', ')} onChange={e => edit(key, e.target.value.split(',').map(s => s.trimStart()))} placeholder={placeholder} onBlur={() => edit(key, list(task[key].join(',')))} /><span className="mt-1 block text-[11px] text-text-tertiary">{key === 'batches' && selectedSeries.length ? 'Using the exact delivery and batch pairs listed above.' : 'Separate entries with commas.'}</span></label>;
  const textField = (key: 'query' | 'parameter' | 'target_unit' | 'process_stage' | 'effective_at' | 'record_id' | 'record_kind', label: string, placeholder?: string) =>
    <label className="block text-xs text-text-secondary">{label}<input className={field} value={task[key] ?? ''} onChange={e => edit(key, e.target.value || (key === 'query' ? '' : null))} placeholder={placeholder} /></label>;
  // Recorded names are ticked, not typed. Typing remains only while no delivery lists its names.
  const pick = (key: 'batches' | 'expected_parameters', label: string, hint: string) => {
    const names = recorded(key === 'batches' ? 'batches' : 'parameters'), locked = key === 'batches' && selectedSeries.length > 0;
    if (!names.length) return arrayField(key, label);
    return <fieldset aria-label={label} disabled={locked} className="min-w-0 text-xs text-text-secondary"><legend>{label}</legend>
      <div className="mt-1 max-h-32 space-y-1.5 overflow-y-auto rounded-control border border-border-strong bg-surface px-2.5 py-2">{[...new Set([...names, ...task[key].filter(Boolean)])].map(name =>
        <label key={name} className="flex items-start gap-2 text-text-primary"><input type="checkbox" checked={task[key].includes(name)} onChange={e => edit(key, e.target.checked ? [...task[key], name] : task[key].filter(value => value !== name))} /><span className="min-w-0 break-words">{name}</span></label>)}</div>
      <span className="mt-1 block text-[11px] text-text-tertiary">{locked ? 'Using the exact delivery and batch pairs listed above.' : hint}</span></fieldset>;
  };
  const parameters = recorded('parameters');
  const parameterField = !parameters.length ? textField('parameter', 'Parameter', 'e.g. pH') : <label className="block text-xs text-text-secondary">Parameter<select aria-label="Parameter" className={field} value={task.parameter ?? ''} onChange={e => edit('parameter', e.target.value || null)}>
    <option value="">All parameters</option>{parameters.map(name => <option key={name} value={name}>{name}</option>)}
    {task.parameter && !parameters.includes(task.parameter) && <option value={task.parameter}>{task.parameter} (not listed in these deliveries)</option>}</select></label>;
  const batchHint = task.operation === 'compare' ? 'Tick two or more to compare, or none for every batch.' : 'None ticked means every batch.';
  return <div className="space-y-4">
    <label className="block text-xs text-text-secondary">Task<select aria-label="Task" className={field} value={task.operation} disabled={fixedOperation} onChange={e => edit('operation', e.target.value as TaskSpec['operation'])}>
      {catalog.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
    </select>{operation && <span className="mt-1.5 block text-xs leading-5 text-text-tertiary">{operation.description}</span>}</label>
    {['find_records', 'select_evidence', 'prepare_review', 'review_changes'].includes(task.operation) && textField('query', 'Search or review focus', 'A record, batch, or topic')}
    <fieldset className="rounded-control border border-border-hairline p-3"><legend className="px-1 text-xs font-medium">Delivery scope</legend>
      <div className="max-h-36 space-y-2 overflow-y-auto">{[...new Set([...task.dataset_ids, ...datasets.map(d => d.id)])].map(id => {
        const dataset = datasets.find(d => d.id === id), review = dataset?.verification === 'provisional';
        return <label key={id} className="flex items-start gap-2 text-xs"><input type="checkbox" aria-label={`Use delivery ${dataset?.delivery_name ?? dataset?.cmo ?? id}`} checked={task.dataset_ids.includes(id)} onChange={e => toggleDataset(id, e.target.checked)} />
          <span className="min-w-0 break-words">{dataset?.delivery_name ?? dataset?.cmo ?? id}{review && <span className="ml-1.5 rounded-pill bg-status-warning-bg px-1.5 py-0.5 text-[10px] font-medium text-status-warning">In review</span>}{dataset?.status === 'stale_basis' ? ' · evidence changed' : ''}
            <span className="block text-[10px] text-text-tertiary">{!dataset ? id : review ? `${count(dataset.review?.pending_values ?? 0, 'value')} still in review · ${count(dataset.review?.open_issues ?? 0, 'open check')}`
              : [dataset.measurements != null && count(dataset.measurements, 'value'), dataset.batches?.length && count(dataset.batches.length, 'batch', 'batches'), dataset.parameters?.length && count(dataset.parameters.length, 'parameter')].filter(Boolean).join(' · ')}</span></span></label>;
      })}</div>
      {!datasets.length && !task.dataset_ids.length && <p className="text-xs text-text-tertiary">No published deliveries in this site. <Link href="/cmo/" className="text-brand-teal underline">Review a delivery</Link> to use its accepted values.</p>}
      {operation?.requires_dataset && !task.dataset_ids.length && <p className="mt-2 text-xs text-status-warning">Choose a delivery for this task.</p>}
      {(task.include_unverified || selected.some(dataset => dataset.verification === 'provisional')) && <label className="mt-3 flex items-start gap-2 rounded-control bg-status-warning-bg p-2 text-xs"><input type="checkbox" aria-label="Include values still in review" checked={!!task.include_unverified} onChange={e => edit('include_unverified', e.target.checked)} />
        <span><span className="font-medium">Include values still in review</span><span className="mt-0.5 block text-text-secondary">Results will be marked as using unreviewed values. Nothing is accepted on the reviewer’s behalf.</span></span></label>}
    </fieldset>
    {selectedSeries.length > 0 && <section aria-label="Selected batch series" className="rounded-control bg-brand-teal-light/40 p-3 text-xs"><h4 className="font-medium">Exact batch selection</h4><ul className="mt-2 space-y-1">{selectedSeries.map(series => <li key={`${series.dataset_id}:${series.batch}`}>{series.batch} · {datasets.find(dataset => dataset.id === series.dataset_id)?.delivery_name ?? series.dataset_id}<span className="ml-1 text-text-tertiary">({series.dataset_id})</span></li>)}</ul><p className="mt-2 text-text-tertiary">Only these delivery and batch pairs are included. Other batches with the same name remain outside this task.</p><button type="button" onClick={() => onChange({ ...task, series: [], batches: [] })} className="mt-2 text-brand-teal underline">Use all batches in selected deliveries</button></section>}
    {MEASURED.includes(task.operation) && <div className="grid gap-3 sm:grid-cols-2">
      {parameterField}{pick('batches', 'Batches', batchHint)}
      {task.operation === 'reconcile' && textField('target_unit', 'Target unit', 'e.g. mg/L')}
      {task.operation === 'check_gaps' && pick('expected_parameters', 'Expected parameters', 'Tick each parameter that should have been reported.')}
    </div>}
    {task.operation === 'trace_impact' && <div className="grid gap-3 sm:grid-cols-2">{textField('record_id', 'Changed record ID')}{textField('record_kind', 'Changed record type', 'e.g. evidence')}</div>}
    {task.operation === 'suggest_causes' && <div className="grid gap-3 sm:grid-cols-2">
      {textField('record_id', 'Record or identifier', 'A deviation, case, batch or lot number')}
      <label className="block text-xs text-text-secondary">Record type<select aria-label="Record type" className={field} value={task.record_kind ?? ''} onChange={e => edit('record_kind', e.target.value || null)}>
        <option value="">Find it from the identifier</option>{Object.entries(RECORD_KINDS).map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}
        {task.record_kind && !RECORD_KINDS[task.record_kind] && <option value={task.record_kind}>{words(task.record_kind)}</option>}</select></label>
      <div className="sm:col-span-2">{textField('query', 'Description', 'What happened, in a few words')}</div>
    </div>}
    <details className="text-xs text-text-secondary"><summary className="cursor-pointer">More scope and coverage options</summary><div className="mt-3 grid gap-3 sm:grid-cols-2">
      {arrayField('kinds', 'Record types', 'e.g. case, evidence')}
      {!MEASURED.includes(task.operation) && pick('batches', 'Batches', 'None ticked means every batch.')}
      {task.operation !== 'check_gaps' && pick('expected_parameters', 'Expected parameters', 'Tick each parameter that should have been reported.')}
      {arrayField('expected_document_kinds', 'Expected document types')}
      <label className="block">Expected sample times (hours)<input className={field} defaultValue={task.expected_times.join(', ')} key={task.expected_times.join(',')} placeholder="e.g. 0, 12, 24" onBlur={e => {
        const values = list(e.target.value).map(Number); e.target.setCustomValidity(values.some(v => !Number.isFinite(v) || v < 0) ? 'Enter non-negative hours separated by commas.' : '');
        if (values.every(v => Number.isFinite(v) && v >= 0)) edit('expected_times', values);
      }} /></label>
      {textField('process_stage', 'Process stage')}{textField('effective_at', 'Effective time', 'ISO date and time, including timezone')}
      <label className="block">{MEASURED.includes(task.operation) ? 'Rows shown at a time' : 'Maximum records'}<input className={field} type="number" min={1} max={100} required value={task.limit} onChange={e => edit('limit', Number(e.target.value))} /></label>
      {!!task.record_refs.length && <p className="break-words text-text-tertiary">Pinned sources: {task.record_refs.map(ref => `${ref.kind} ${ref.id} · revision ${ref.revision}`).join('; ')}</p>}
    </div></details>
  </div>;
}

type Series = { dataset_id?: string; batch: string; parameter: string; unit: string | null; n: number; min: number; max: number; first_time_h: number; last_time_h: number };
type ComparisonSummary = { parameter: string; unit: string | null; left_batch: string; right_batch: string; left_dataset_id?: string; right_dataset_id?: string; matched_times: number;
  first_time_h: number; last_time_h: number; mean_difference: number; largest_difference: { time_h: number; difference: number; left_value: number; right_value: number }; difference_definition: string };
type Verification = { dataset_id: string; state: 'verified' | 'provisional'; values_still_in_review_used?: number; open_checks?: number | null; rejected_values_excluded?: number | null; meaning?: string };
type Factor = { id: string; record: { kind: string }; label: string | null; time: string | null; time_basis: string | null; link: string; shared_identifiers: string[]; screening: string };
export type Causes = { establishing_a_cause: string; subject: { record_id: string; kind: string | null; label?: string; time: string | null; time_basis: string | null } | null; chronology: Factor[];
  hypotheses: { id: string; statement: string; supported_by: string[]; not_established: string[]; next_check: string }[]; contrary_evidence: { factor_id: string; finding: string; caveat: string }[];
  precedents: { case_id: string | null; status: string | null; recorded_root_cause: string | null; cause_status: string | null; similarity: { shared_identifiers: string[] }; label: string | null }[];
  precedent_reuse?: string | null; unknowns: string[]; coverage?: string | null; next_step?: string };
const rows = <T,>(value: unknown) => Array.isArray(value) ? value as T[] : [];
const PHASES: Record<string, string> = { authorize: 'checking access', retrieve: 'reading sources', calculate: 'calculating', decision_model: 'decision model', route: 'matching the request' };
const TIME_BASIS: Record<string, string> = { opened_at: 'when the case was opened', event_time: 'event time', first_at: 'when first seen', created_at: 'when the record was created' };
const SCREENING: Record<string, string> = { not_ruled_out: 'Not ruled out by timing', weakened_by_timing: 'Weakened by timing: recorded after the subject', cannot_be_ordered: 'Cannot be placed in order: no usable time' };
const DECISION_TASKS: Record<string, string> = { field_meaning: 'Matching a parameter name', route_request: 'Reading the typed request', rerank_records: 'Ordering the records found', applicability_match: 'Checking whether records apply', impact_link: 'Checking how records are linked' };
const ANSWER_STATUS: Record<string, string> = { accepted: 'applied (inside its calibrated threshold)', advisory: 'suggestion only (not calibrated for this task)', flagged: 'not used' };
const ANSWERS: Record<string, string> = { true: 'Yes', false: 'No', unknown: 'Could not tell', needs_assistant: 'Needs the assistant', applies: 'Applies', does_not_apply: 'Does not apply' };
const moment = (time: string | null, basis: string | null) => time ? `${time.replace('T', ' ').replace(/(\.\d+)?(Z|\+00:00)$/, ' UTC')}${basis ? ` (${TIME_BASIS[basis] ?? words(basis)})` : ''}` : 'No recorded time';
function question(task: string, name: string) {
  const nth = Number(/\d+$/.exec(name)?.[0] ?? 0) + 1;
  if (task === 'rerank_records') return `How relevant candidate record ${nth} is to the request`;
  if (task === 'applicability_match') return `Whether candidate record ${nth} says it covers the requested batch, stage or period`;
  if (task === 'impact_link') return `Whether linked record ${nth} documents actual use, not only a mention`;
  if (name === 'parameter') return task === 'field_meaning' ? 'Which recorded parameter is the same quantity as the name given' : 'Which recorded parameter the request refers to';
  return name === 'operation' ? 'Which task the request asks for' : name === 'dataset' ? 'Which delivery the request refers to' : name.startsWith('batch_') ? `Whether the request names recorded batch ${nth}` : words(name);
}

/** What the optional decision model answered and whether the host used each answer. A probability is the model's own estimate. */
function Decisions({ decisions }: { decisions: TaskDecision[] }) {
  const answers = decisions.reduce((total, decision) => total + decision.answers.length, 0);
  return <details className="text-xs"><summary className="cursor-pointer text-text-secondary">Decision model: {answers ? count(answers, 'suggestion') : 'not used'}</summary>
    <p className="mt-2 text-text-tertiary">Each probability is the model’s own estimate for its answer, not a measured accuracy.</p>
    <ul className="mt-2 space-y-2">{decisions.flatMap((decision, i) => decision.status === 'fallback'
      ? [<li key={i} className="rounded-control bg-surface-secondary p-2">{DECISION_TASKS[decision.task] ?? words(decision.task)} · decision model not used: {decision.reason}</li>]
      : decision.answers.map((answer, j) => <li key={`${i}-${j}`} className="rounded-control bg-surface-secondary p-2"><p className="text-text-tertiary">{question(decision.task, answer.question)}{answer.about ? ` · ${answer.about}` : ''}</p>
        <p className="mt-1"><span className="font-medium">{ANSWERS[String(answer.value)] ?? fig(answer.value)}</span>{answer.probability != null && ` · model probability ${Number((answer.probability * 100).toFixed(1))}%`}</p>
        <p className="mt-1 text-text-tertiary">{ANSWER_STATUS[answer.status] ?? words(answer.status)}{answer.reason ? ` · ${answer.reason}` : ''}</p></li>))}</ul></details>;
}

/** Candidates to check, never a finding: a cause is established only by the case review. */
export function CausesView({ data, action }: { data: Causes;
  /** Rendered under each hypothesis, e.g. a button that turns its next check into a planned step. */
  action?: (hypothesis: Causes['hypotheses'][number]) => React.ReactNode }) {
  const factor = (id: string) => data.chronology.find(item => item.id === id)?.label ?? 'A linked record';
  const heading = 'font-medium text-text-primary', item = 'rounded-control bg-surface-secondary p-2';
  return <div className="space-y-4 text-xs leading-5 text-text-secondary">
    <div role="note" className="rounded-control bg-status-warning-bg p-3"><p className="font-medium text-text-primary">Hypotheses to check. No cause is established.</p><p className="mt-1">{data.establishing_a_cause}</p></div>
    {data.subject && <p>About <span className={heading}>{data.subject.label ?? data.subject.record_id}</span>{data.subject.kind ? ` · ${RECORD_KINDS[data.subject.kind] ?? words(data.subject.kind)}` : ''} · {moment(data.subject.time, data.subject.time_basis)}</p>}
    <section aria-label="Hypotheses"><h4 className={heading}>Hypotheses · {data.hypotheses.length}</h4>
      {!data.hypotheses.length && <p className="mt-1 text-text-tertiary">No linked record or similar closed case gives a candidate to check.</p>}
      <ol className="mt-2 space-y-2">{data.hypotheses.map(h => <li key={h.id} className={item}><p className={heading}>{h.statement}</p>
        <p className="mt-1"><span className="font-medium">Supported by:</span> {h.supported_by.join(' ')}</p><p className="mt-1"><span className="font-medium">Not established:</span> {h.not_established.join(' ')}</p>
        <p className="mt-1"><span className="font-medium">Next check:</span> {h.next_check}</p>{action && <div className="mt-2">{action(h)}</div>}</li>)}</ol></section>
    {!!data.contrary_evidence.length && <section aria-label="Weakened by timing"><h4 className={heading}>Weakened by timing · {data.contrary_evidence.length}</h4>
      <ul className="mt-2 space-y-2">{data.contrary_evidence.map(c => <li key={c.factor_id} className={item}><p className={heading}>{factor(c.factor_id)}</p><p className="mt-1">{c.finding}</p>
        <p className="mt-1 text-text-tertiary">{c.caveat.replace(/\b[a-z]+_[a-z_]+\b/g, basis => TIME_BASIS[basis] ?? words(basis))}</p></li>)}</ul></section>}
    {!!data.chronology.length && <section aria-label="Timeline"><h4 className={heading}>Timeline · {count(data.chronology.length, 'linked record')}</h4>
      <ol className="mt-2 space-y-2">{data.chronology.map(f => <li key={f.id} className={item}><p className="text-text-tertiary">{moment(f.time, f.time_basis)}</p><p className={heading}>{f.label ?? RECORD_KINDS[f.record.kind] ?? 'Linked record'}</p>
        <p className="mt-1">Linked by {f.shared_identifiers.join(', ') || 'an identifier'}: {f.link}.</p><p className={`mt-1 ${f.screening === 'not_ruled_out' ? '' : 'text-status-warning'}`}>{SCREENING[f.screening] ?? words(f.screening)}</p></li>)}</ol></section>}
    {!!data.precedents.length && <section aria-label="Similar closed cases"><h4 className={heading}>Similar closed cases · {data.precedents.length}</h4>
      <ul className="mt-2 space-y-2">{data.precedents.map((p, i) => <li key={p.case_id ?? i} className={item}><p className={heading}>{p.label ?? p.case_id}{p.status ? ` · ${words(p.status)}` : ''}</p>
        <p className="mt-1">{p.recorded_root_cause ? `Recorded root cause: ${p.recorded_root_cause}` : 'No root cause is recorded for this case.'}{p.cause_status ? ` (${p.cause_status})` : ''}</p>
        <p className="mt-1 text-text-tertiary">{p.similarity?.shared_identifiers?.length ? `Shares ${p.similarity.shared_identifiers.join(', ')} with the subject.` : 'Similar wording only; no shared identifier.'}</p></li>)}</ul>
      {data.precedent_reuse && <p className="mt-2 text-text-tertiary">{data.precedent_reuse}</p>}</section>}
    <section aria-label="What was not checked"><h4 className={heading}>What was not checked</h4><ul className="mt-1 list-disc space-y-1 pl-4">{data.unknowns.map(unknown => <li key={unknown}>{unknown}</li>)}</ul>
      {data.coverage && <p className="mt-2 text-text-tertiary">{data.coverage}</p>}</section>
    {data.next_step && <p>{data.next_step}</p>}
  </div>;
}

export function TaskResultCard({ result: initial, task, onAsk, onEdit, names }: { result: TaskResult; task?: TaskSpec; onAsk?: (text: string, siteId?: string) => void;
  /** Puts a corrected selection back in the form. It never runs: the person confirms by running the task. */
  onEdit?: (task: TaskSpec) => void; names?: Record<string, string> }) {
  const [result, setResult] = useState(initial), [refreshing, setRefreshing] = useState(false), [error, setError] = useState('');
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => setResult(initial), [initial]);
  const stale = result.status !== 'current';
  const data = result.data, spec = result.task ?? task, causes = result.operation === 'suggest_causes';
  const series = rows<Series>(data.series), summary = rows<ComparisonSummary>(data.comparison_summary), verification = rows<Verification>(data.verification).filter(v => v.state === 'provisional');
  const tables = causes ? [] : Object.entries(data).filter(([name, values]) => Array.isArray(values) && !['series', 'comparison_summary', 'verification'].includes(name));
  const paged: Record<string, [unknown, unknown]> = { measurements: [data.measurements_offset, data.measurement_count], comparisons: [data.comparisons_offset, data.comparison_count] };
  const offset = Number(data.measurements_offset ?? 0), nextOffset = (data.comparisons_next_offset ?? data.next_offset ?? null) as number | null;
  const timing = result.timing, seconds = timing?.seconds ?? result.elapsed_seconds, over = timing?.within_target === false;
  const recorded = result.data.deliveries as Record<string, string> | undefined;  // names saved with the result
  const delivery = (id: string) => names?.[id] ?? recorded?.[id] ?? (spec?.dataset_ids.includes(id) ? `Delivery ${spec.dataset_ids.indexOf(id) + 1}` : 'Selected delivery');
  const batch = (name: string, datasetId?: string) => datasetId ? `${name} (${delivery(datasetId)})` : name;
  const unmatched = Object.entries((data.unmatched_counts ?? {}) as Record<string, number>).filter(([, n]) => n > 0);
  async function refresh() {
    setRefreshing(true); setError('');
    try { setResult(await getTaskResult(result.id)); setUnavailable(false); }
    catch (e) { setError((e as Error).message); if (e instanceof ProcessApiError && [403, 404].includes(e.status)) setUnavailable(true); }
    finally { setRefreshing(false); }
  }
  async function page(to: number) {
    if (!spec) return; setRefreshing(true); setError('');
    try { setResult(await runTask({ ...emptyTask(spec.site_id, spec), offset: to })); }
    catch (e) { setError((e as Error).message); } finally { setRefreshing(false); }
  }
  const askText = `Review saved workspace task ${result.id} (${result.operation}) at site ${result.site_id}. ${result.summary} Check its source evidence and remaining gaps.`;
  if (unavailable) return <section aria-label="Task result" className="rounded-card border border-border-hairline bg-surface p-4"><p role="alert" className="text-xs text-status-warning">This saved result is no longer available under your current access. {error}</p><button type="button" className={`${workButton} mt-3`} disabled={refreshing} onClick={() => void refresh()}>Check access again</button></section>;
  return <section aria-label="Task result" className="space-y-3 rounded-card border border-border-hairline bg-surface p-4" data-testid="task-result">
    <div className="flex items-start justify-between gap-3"><div><p className={`text-[11px] font-medium ${stale || result.task_status === 'needs_information' ? 'text-status-warning' : 'text-brand-teal'}`}>{stale ? 'Evidence changed · refresh or rerun before use' : result.task_status === 'needs_information' ? 'Needs information' : 'Completed'}</p><h3 className="mt-1 text-sm font-medium">{result.summary}</h3>
      {typeof seconds === 'number' && <p className={`mt-1 text-[11px] ${over ? 'font-medium text-status-warning' : 'text-text-tertiary'}`}>{over ? `Took ${seconds.toFixed(1)} s · over the ${timing!.target_seconds} s target` : `Answered in ${seconds.toFixed(2)} s`}</p>}</div><button type="button" className={workButton} aria-label="Refresh result status" disabled={refreshing} onClick={() => void refresh()}><RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} /></button></div>
    {error && <p role="alert" className="text-xs text-status-critical">{error}</p>}
    {result.evidence_state === 'provisional' && <div role="status" className="rounded-control bg-status-warning-bg p-3 text-xs leading-5"><p className="font-medium">Uses values still in review</p>
      <ul className="mt-1">{verification.map(v => <li key={v.dataset_id}>{delivery(v.dataset_id)}: {count(v.values_still_in_review_used ?? 0, 'value')} still in review used · {count(v.open_checks ?? 0, 'open check')} · {count(v.rejected_values_excluded ?? 0, 'rejected value')} left out</li>)}</ul>
      <p className="mt-1 text-text-secondary">{verification[0]?.meaning ?? 'Nothing here was accepted on a reviewer’s behalf. Verify the delivery before relying on these values.'}</p></div>}
    {!!result.issues.length && <ul className="space-y-1 rounded-control bg-status-warning-bg p-3 text-xs leading-5">{result.issues.map((issue, i) => <li key={`${issue.code}-${i}`}>{issue.message}
      {issue.code === 'parameter_needs_confirmation' && typeof issue.suggested === 'string' && <span className="mt-1 flex flex-wrap items-center gap-2"><span className="font-medium">Did you mean {issue.suggested}?</span>
        {onEdit && spec && <button type="button" className={workButton} onClick={() => onEdit({ ...emptyTask(spec.site_id, spec), parameter: issue.suggested as string, offset: 0 })}>Use {issue.suggested}</button>}</span>}</li>)}</ul>}
    {typeof data.parameter_used === 'string' && <p className="text-xs text-text-secondary">Calculated on the recorded parameter {data.parameter_used}{spec?.parameter ? `, matched from “${spec.parameter}”` : ''}.</p>}
    {causes && <CausesView data={data as unknown as Causes} />}
    {!!summary.length && <div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="mb-2 text-left font-medium">Differences between batches<span className="block font-normal text-text-tertiary">Each difference is {summary[0].difference_definition}.</span></caption>
      <thead><tr>{['Parameter', 'Batches', 'Matching times', 'Largest difference', 'Mean difference'].map(name => <th key={name} scope="col" className={th}>{name}</th>)}</tr></thead>
      <tbody>{summary.map((row, i) => { const unit = row.unit ? ` ${row.unit}` : '', largest = row.largest_difference; return <tr key={i}><td className={td}>{row.parameter}</td>
        <td className={td}>{batch(row.right_batch, row.right_dataset_id)} − {batch(row.left_batch, row.left_dataset_id)}</td><td className={td}>{row.matched_times}<span className="block text-text-tertiary">{hours(row.first_time_h)} to {hours(row.last_time_h)} h</span></td>
        <td className={td}>{fig(largest.difference)}{unit} at {hours(largest.time_h)} h<span className="block text-text-tertiary">{row.right_batch} {fig(largest.right_value)} · {row.left_batch} {fig(largest.left_value)}{unit}</span></td>
        <td className={td}>{fig(row.mean_difference)}{unit}</td></tr>; })}</tbody></table>
      {!!unmatched.length && <p className="mt-2 text-[11px] text-text-tertiary">Values with no matching time in another batch: {unmatched.map(([name, n]) => `${name.replace(/ \(([^()]+)\)$/, (_, id: string) => ` (${delivery(id)})`)}: ${n}`).join(' · ')}</p>}</div>}
    {!!series.length && <div className="max-h-72 overflow-auto"><table className="w-full text-left text-xs"><caption className="mb-2 text-left font-medium">Values by batch and parameter</caption>
      <thead><tr>{['Batch', 'Parameter', 'Values', 'From–to (hours)', 'Min–max'].map(name => <th key={name} scope="col" className={th}>{name}</th>)}</tr></thead>
      <tbody>{series.map((s, i) => <tr key={i}><td className={td}>{batch(s.batch, s.dataset_id)}</td><td className={td}>{s.parameter}</td><td className={td}>{s.n}</td><td className={td}>{hours(s.first_time_h)} to {hours(s.last_time_h)}</td>
        <td className={td}>{fig(s.min)} to {fig(s.max)}{s.unit ? ` ${s.unit}` : ''}</td></tr>)}</tbody></table></div>}
    {data.series_complete === false ? <p role="status" className="rounded-control bg-status-warning-bg p-2 text-xs">Not every selected value is included: the selection is larger than one result holds. Select fewer batches or one parameter.</p>
      : !!series.length && <p className="text-[11px] text-text-tertiary">All {Number(data.measurement_count ?? series.reduce((total, s) => total + s.n, 0))} values are included.</p>}
    {tables.map(([name, values]) => <ResultTable key={name} name={name} values={values as unknown[]} offset={Number(paged[name]?.[0] ?? 0)} total={typeof paged[name]?.[1] === 'number' ? paged[name][1] as number : undefined} />)}
    {spec && (nextOffset != null || offset > 0) && <div className="flex flex-wrap items-center gap-2 text-[11px] text-text-tertiary">
      {offset > 0 && <button type="button" className={workButton} disabled={refreshing} onClick={() => void page(Math.max(0, offset - (spec.limit || 50)))}>Show previous rows</button>}
      {nextOffset != null && <button type="button" className={workButton} disabled={refreshing} onClick={() => void page(nextOffset)}>Show next rows</button>}
      <span>{refreshing ? 'Loading rows…' : 'Summaries above cover every row.'}</span></div>}
    {!!result.decisions?.length && <Decisions decisions={result.decisions} />}
    <details className="text-xs"><summary className="cursor-pointer text-text-secondary">Sources · {result.source_refs.length} references</summary><ul className="mt-2 space-y-2">{result.source_refs.map(ref => <SourceReference key={`${ref.kind}:${ref.id}:${ref.revision}`} source={ref} />)}</ul>{!result.source_refs.length && <p className="mt-2 text-text-tertiary">No supporting source references were returned.</p>}</details>
    <div className="flex flex-wrap gap-2">{spec?.parameter && <Link href={`/trends/?parameter=${encodeURIComponent(spec.parameter)}`} className={workButton}>Open trends<ArrowUpRight size={13} /></Link>}{onAsk && <button type="button" className={workButton} onClick={() => onAsk(askText, result.site_id)}>{causes ? 'Continue in the assistant' : 'Ask about this result'}</button>}</div>
    <details className="text-xs text-text-tertiary"><summary className="cursor-pointer">Calculation and source record</summary><p className="mt-2">{result.elapsed_seconds.toFixed(2)} s · {result.model_calls} reasoning model calls · {result.decision_model_calls ?? 0} decision model calls · Site {result.site_id} · Result {result.id}</p>
      {timing && <p className="mt-1">Time by step: {Object.entries(timing.phases).map(([name, value]) => `${PHASES[name] ?? words(name)} ${value.toFixed(2)} s`).join(' · ') || 'not recorded'}{timing.includes ? `. The total covers ${timing.includes}.` : ''}</p>}
      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-control bg-surface-secondary p-3">{JSON.stringify(result, (key, value) => key === 'points' && Array.isArray(value) ? `${value.length} time and value pairs, summarised in the table above` : value, 2)}</pre></details>
  </section>;
}

export function SavedTaskResult({ id, onAsk }: { id: string; onAsk: (text: string, siteId?: string) => void }) {
  const [result, setResult] = useState<TaskResult | null>(null), [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    getTaskResult(id).then(value => { if (alive) setResult(value); }).catch(e => { if (alive) setError((e as Error).message); });
    return () => { alive = false; };
  }, [id]);
  return <div className="my-3">{error ? <p role="alert" className="text-xs text-status-critical">{error}</p> : result ? <TaskResultCard result={result} task={result.task} onAsk={onAsk} /> : <p role="status" className="text-xs text-text-tertiary">Opening saved task result…</p>}</div>;
}

function SourceReference({ source }: { source: SourceRef }) {
  const [record, setRecord] = useState<{ revision: number; state?: Record<string, unknown>; [key: string]: unknown } | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [open, setOpen] = useState(false);
  async function inspect() {
    if (open) { setOpen(false); return; }
    setOpen(true); setBusy(true); setError(''); setRecord(null);
    try { setRecord(await processRequest(`/v1/records/${encodeURIComponent(source.kind)}/${encodeURIComponent(source.id)}`)); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const state = record?.state ?? {};
  const metadata = state.metadata as Record<string, unknown> | undefined;
  const delivery = metadata?.classification === 'verified_cmo_dataset' && typeof state.source_record_id === 'string' ? state.source_record_id : null;
  return <li className="break-words rounded-control bg-surface-secondary p-2"><p className="font-medium">{source.label ?? source.id}</p><p className="mt-1 text-text-tertiary">{source.kind} · {source.id} · revision {source.revision}{source.site_id ? ` · ${source.site_id}` : ''}</p>
    <button type="button" onClick={() => void inspect()} disabled={busy} aria-expanded={open} className="mt-2 text-brand-teal underline">Inspect source {source.id}</button>
    {open && <div className="mt-2 space-y-2">{busy && <p role="status">Loading authorized source record…</p>}{error && <p role="alert" className="text-status-critical">{error}</p>}{record && <>
      {record.revision !== source.revision && <p role="status" className="rounded-control bg-status-warning-bg p-2">Current revision {record.revision} differs from referenced revision {source.revision}. Rerun the task against current evidence before relying on it.</p>}
      {delivery && <Link href={`/cmo/?run=${encodeURIComponent(delivery)}`} className="inline-flex items-center gap-1 text-brand-teal underline">Open original delivery and source viewer<ArrowUpRight size={12} /></Link>}
      {typeof state.original === 'string' && <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-sans">{state.original}</pre>}
      <details><summary className="cursor-pointer">Current record and provenance</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(record, null, 2)}</pre></details>
    </>}</div>}
  </li>;
}

function ResultTable({ name, values, offset = 0, total }: { name: string; values: unknown[]; offset?: number; total?: number }) {
  const rows = values.slice(0, 100).map(value => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : { value });
  const columns = [...new Set(rows.flatMap(row => Object.keys(row)))].slice(0, 12);
  const cell = (value: unknown) => value == null ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  return <div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="mb-2 text-left font-medium"><span className="capitalize">{words(name)}</span> · {total != null && values.length && total > values.length ? `rows ${offset + 1} to ${offset + values.length} of ${total}` : values.length}</caption><thead><tr>{columns.map(key => <th key={key} scope="col" className={th}>{words(key)}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map(key => <td key={key} className={td}>{cell(row[key])}</td>)}</tr>)}</tbody></table>{values.length > 100 && <p className="mt-2 text-[11px] text-text-tertiary">First 100 rows shown. Inspect the calculation record for the full bounded result.</p>}</div>;
}

export function AssistantTaskWork({ siteId, context, storageScope, onRoutine, onAsk }: { siteId: string; context: TaskContext; storageScope: string; onRoutine: (task: TaskSpec) => void; onAsk: (text: string, siteId?: string) => void }) {
  const [catalog, setCatalog] = useState<TaskCatalog>([]), [datasets, setDatasets] = useState<TaskDataset[]>([]), [decisionModel, setDecisionModel] = useState<DecisionModel | null>(null);
  const [task, setTask] = useState(() => emptyTask(siteId, context.task));
  const [results, setResults] = useState<{ result: TaskResult; task?: TaskSpec }[]>([]);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [loaded, setLoaded] = useState(false), [attempt, setAttempt] = useState(0);
  const [request, setRequest] = useState(''), [routing, setRouting] = useState(false), [routed, setRouted] = useState<(TaskRoute & { text: string }) | null>(null), [notice, setNotice] = useState('');
  const inFlight = useRef(false);
  const resultKey = `${storageScope}:task-results:${siteId}`;
  useEffect(() => {
    let alive = true;
    let ids: string[] = [];
    try { const saved: unknown = JSON.parse(localStorage.getItem(resultKey) ?? '[]'); if (Array.isArray(saved)) ids = saved.filter((id): id is string => typeof id === 'string').slice(0, 10); } catch { /* Saved IDs are optional. */ }
    if (ids.length) Promise.allSettled(ids.map(id => getTaskResult(id))).then(loaded => {
      if (!alive) return;
      const recovered = loaded.flatMap(item => item.status === 'fulfilled' ? [{ result: item.value, task: item.value.task }] : []);
      setResults(current => [...current, ...recovered.filter(item => !current.some(existing => existing.result.id === item.result.id))].slice(0, 10));
      if (loaded.some(item => item.status === 'rejected')) setError('Some earlier results are unavailable under your current access. Run a fresh task if needed.');
    });
    return () => { alive = false; };
  }, [resultKey]);
  const contextKey = JSON.stringify(context);
  useEffect(() => { setTask(value => ({ ...value, ...context.task, site_id: siteId })); }, [contextKey, siteId]); // Context is selected explicitly in the workspace.
  useEffect(() => {
    let alive = true; setLoaded(false); setError('');
    // Deliveries still in review are listed and labelled; their values are used only when the person ticks the option.
    Promise.allSettled([getTaskCatalog(), processRequest<{ datasets: TaskDataset[] }>(`/v1/cmo-datasets?site_id=${encodeURIComponent(siteId)}&include_provisional=true`)]).then(([tasks, deliveries]) => {
      if (!alive) return;
      if (tasks.status === 'fulfilled') { setCatalog(tasks.value.operations); setDecisionModel(tasks.value.decision_model ?? null); } else setError(tasks.reason.message);
      if (deliveries.status === 'fulfilled') setDatasets(deliveries.value.datasets); else setError(previous => [previous, 'Delivery list unavailable. Your selected IDs are retained.'].filter(Boolean).join(' '));
      setLoaded(true);
    }); return () => { alive = false; };
  }, [siteId, attempt]);
  async function run(spec: TaskSpec) {
    if (inFlight.current) return; inFlight.current = true; setBusy(true); setError(''); setNotice('');
    try { const result = await runTask(spec); setResults(current => {
      const next = [{ result, task: spec }, ...current.filter(item => item.result.id !== result.id)].slice(0, 10);
      try { localStorage.setItem(resultKey, JSON.stringify(next.map(item => item.result.id))); } catch { /* Results remain on the server. */ }
      return next;
    }); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); inFlight.current = false; }
  }
  // Typed words run only when they are exactly one routine task. Otherwise the reason is shown and the person chooses.
  async function route(e: React.FormEvent) {
    e.preventDefault(); const text = request.trim(); if (!text || routing || inFlight.current) return;
    setRouting(true); setError(''); setRouted(null); setNotice('');
    try {
      const answer = await routeRequest(siteId, text, task.dataset_ids, task.include_unverified); setRouted({ ...answer, text });
      if (answer.route === 'direct' && answer.task) { const next = emptyTask(siteId, answer.task); setTask(next); await run(next); }
    } catch (e) { setError((e as Error).message); } finally { setRouting(false); }
  }
  const fill = (next: TaskSpec, from: string) => { setTask(next); setNotice(`Selection filled in from ${from}. Nothing has run yet: check it, then run the task.`); };
  const names = Object.fromEntries(datasets.map(dataset => [dataset.id, dataset.delivery_name ?? dataset.cmo ?? dataset.id]));
  const describe = (suggested: SuggestedTask) => [catalog.find(item => item.id === suggested.operation)?.title ?? words(suggested.operation), suggested.parameter ?? 'all parameters',
    suggested.batches.length ? suggested.batches.join(', ') : 'all batches', suggested.dataset_ids.map(id => names[id] ?? 'a delivery not listed here').join(', ')].filter(Boolean).join(' · ');
  const sample = datasets.find(dataset => dataset.verification !== 'provisional' && dataset.parameters?.length && (dataset.batches?.length ?? 0) > 1);
  const example = sample ? `compare ${sample.parameters![0]} between ${sample.batches![0]} and ${sample.batches![1]}` : 'compare glucose between CHO-004-R01 and CHO-004-R02';
  const requiresData = catalog.find(item => item.id === task.operation)?.requires_dataset;
  return <section className="space-y-4 py-4" aria-label="Direct work">
    <div><h2 className="text-lg font-medium">Run a task</h2><p className="mt-1 text-xs leading-5 text-text-secondary">Find records, compare values, or prepare a review from authorized sources. Site {siteId} · {context.label}</p></div>
    {error && <div role="alert" className="rounded-control bg-status-warning-bg p-3 text-xs">{error}<button type="button" onClick={() => setAttempt(value => value + 1)} className="ml-2 underline">Reload options</button></div>}
    {!loaded && <p role="status" className="text-xs text-text-tertiary">Loading available tasks…</p>}
    {!!catalog.length && <form onSubmit={route} aria-label="Type a request" className="rounded-card border border-border-hairline bg-surface p-4">
      <label htmlFor={`task-request-${siteId}`} className="block text-xs font-medium text-text-secondary">Type what you need</label>
      <div className="mt-1 flex gap-2"><input id={`task-request-${siteId}`} className={`${field} !mt-0 min-w-0 flex-1`} value={request} maxLength={2000} onChange={e => setRequest(e.target.value)} placeholder={`e.g. ${example}`} />
        <button type="submit" className={workButton} disabled={routing || busy || !request.trim()}>{routing ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}{routing ? 'Matching…' : 'Run'}</button></div>
      <p className="mt-1.5 text-[11px] leading-4 text-text-tertiary">A request that is exactly one routine task runs straight away, on {task.dataset_ids.length ? 'the deliveries ticked below' : 'the verified deliveries at this site'}. Anything else is explained here and nothing runs until you choose.</p>
      {routed && <div role="status" className="mt-3 rounded-control bg-surface-secondary p-3 text-xs leading-5"><p><span className="font-medium">{routed.route === 'direct' ? 'Ran directly' : 'Not run directly'}</span>{routed.reason ? `: ${routed.reason}${/[.!?]$/.test(routed.reason) ? '' : '.'}` : '.'}{routed.basis === 'decision_model' ? ' The decision model read this request; the fixed rules alone did not match it.' : ''}</p>
        {routed.route === 'assistant' && <>{routed.suggested_task && <p className="mt-1 text-text-secondary">Suggested selection: {describe(routed.suggested_task)}</p>}
          <div className="mt-2 flex flex-wrap gap-2">{routed.suggested_task && <button type="button" className={workButton} onClick={() => fill({ ...task, ...routed.suggested_task!, series: [], offset: 0 }, 'the suggestion')}>Use this selection</button>}
            <button type="button" className={workButton} onClick={() => onAsk(routed.text, siteId)}>Ask the assistant</button></div></>}</div>}
    </form>}
    {!!catalog.length && <form onSubmit={e => { e.preventDefault(); void run(task); }} className="space-y-4 rounded-card border border-border-hairline bg-surface p-4">
      <fieldset disabled={busy} className="min-w-0"><TaskFields task={task} onChange={setTask} catalog={catalog} datasets={datasets} /></fieldset>
      {notice && <p role="status" className="rounded-control bg-brand-teal-light/40 p-2 text-xs">{notice}</p>}
      <div className="flex flex-wrap gap-2"><button type="submit" disabled={busy || (!!requiresData && !task.dataset_ids.length)} className={`${workButton} !border-brand-teal !bg-brand-teal !text-white`}>{busy ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}{busy ? 'Running task…' : 'Run task'}</button><button type="button" className={workButton} disabled={busy} onClick={() => onRoutine(task)}>Save as routine</button></div>
      {busy && <p role="status" className="text-xs text-text-tertiary">Checking sources and calculating. You can return to Chat while this runs.</p>}
      {decisionModel?.configuration_issue && <p role="status" className="rounded-control bg-status-warning-bg p-2 text-xs">Decision model setup needs attention: {decisionModel.configuration_issue}</p>}
      {decisionModel?.enabled && <p className="text-[11px] leading-4 text-text-tertiary">Decision model{decisionModel.model ? ` ${decisionModel.model}` : ''} is on for matching names and ordering results. Its suggestions are applied only where calibrated.</p>}
    </form>}
    {results.map(item => <TaskResultCard key={item.result.id} {...item} onAsk={onAsk} names={names} onEdit={next => fill({ ...next, site_id: siteId }, 'the result')} />)}
    {!results.length && <p className="text-xs leading-5 text-text-tertiary">Results and missing information appear here with the source references. A task result is available for review; it does not approve a manufacturing action.</p>}
  </section>;
}
