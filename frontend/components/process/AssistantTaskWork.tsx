'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight, Loader2, Play, RefreshCw } from 'lucide-react';
import { ProcessApiError, processRequest } from '@/lib/process-api';
import { emptyTask, getTaskCatalog, getTaskResult, runTask, type SourceRef, type TaskCatalog, type TaskContext, type TaskResult, type TaskSpec } from '@/lib/assistant-workflows';

export const workButton = 'inline-flex items-center justify-center gap-1.5 rounded-control border border-border-strong bg-surface px-3 py-2 text-xs font-medium text-text-secondary hover:bg-surface-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-teal disabled:opacity-40';
const field = 'mt-1 block w-full rounded-control border border-border-strong bg-surface px-2.5 py-2 text-sm text-text-primary';
export type TaskDataset = { id: string; delivery_name?: string | null; cmo?: string; measurements?: number; status?: string };
const list = (text: string) => [...new Set(text.split(',').map(s => s.trim()).filter(Boolean))];

export function TaskFields({ task, onChange, catalog, datasets, fixedOperation = false }: {
  task: TaskSpec; onChange: (task: TaskSpec) => void; catalog: TaskCatalog; datasets: TaskDataset[]; fixedOperation?: boolean;
}) {
  const edit = <K extends keyof TaskSpec>(key: K, value: TaskSpec[K]) => onChange({ ...task, [key]: value });
  const operation = catalog.find(item => item.id === task.operation);
  const selectedSeries = task.series ?? [];
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
  return <div className="space-y-4">
    <label className="block text-xs text-text-secondary">Task<select aria-label="Task" className={field} value={task.operation} disabled={fixedOperation} onChange={e => edit('operation', e.target.value as TaskSpec['operation'])}>
      {catalog.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
    </select>{operation && <span className="mt-1.5 block text-xs leading-5 text-text-tertiary">{operation.description}</span>}</label>
    {['find_records', 'select_evidence', 'prepare_review', 'review_changes'].includes(task.operation) && textField('query', 'Search or review focus', 'A record, batch, or topic')}
    <fieldset className="rounded-control border border-border-hairline p-3"><legend className="px-1 text-xs font-medium">Delivery scope</legend>
      <div className="max-h-36 space-y-2 overflow-y-auto">{[...new Set([...task.dataset_ids, ...datasets.map(d => d.id)])].map(id => {
        const dataset = datasets.find(d => d.id === id);
        return <label key={id} className="flex items-start gap-2 text-xs"><input type="checkbox" aria-label={`Use delivery ${dataset?.delivery_name ?? dataset?.cmo ?? id}`} checked={task.dataset_ids.includes(id)} onChange={e => toggleDataset(id, e.target.checked)} />
          <span className="min-w-0 break-words">{dataset?.delivery_name ?? dataset?.cmo ?? id}{dataset?.status === 'stale_basis' ? ' · evidence changed' : ''}<span className="block text-[10px] text-text-tertiary">{id}</span></span></label>;
      })}</div>
      {!datasets.length && !task.dataset_ids.length && <p className="text-xs text-text-tertiary">No published deliveries in this site. <Link href="/cmo/" className="text-brand-teal underline">Review a delivery</Link> to use its accepted values.</p>}
      {operation?.requires_dataset && !task.dataset_ids.length && <p className="mt-2 text-xs text-status-warning">Choose a delivery for this task.</p>}
    </fieldset>
    {selectedSeries.length > 0 && <section aria-label="Selected batch series" className="rounded-control bg-brand-teal-light/40 p-3 text-xs"><h4 className="font-medium">Exact batch selection</h4><ul className="mt-2 space-y-1">{selectedSeries.map(series => <li key={`${series.dataset_id}:${series.batch}`}>{series.batch} · {datasets.find(dataset => dataset.id === series.dataset_id)?.delivery_name ?? series.dataset_id}<span className="ml-1 text-text-tertiary">({series.dataset_id})</span></li>)}</ul><p className="mt-2 text-text-tertiary">Only these delivery and batch pairs are included. Other batches with the same name remain outside this task.</p><button type="button" onClick={() => onChange({ ...task, series: [], batches: [] })} className="mt-2 text-brand-teal underline">Use all batches in selected deliveries</button></section>}
    {['compare', 'reconcile', 'check_gaps'].includes(task.operation) && <div className="grid gap-3 sm:grid-cols-2">
      {textField('parameter', 'Parameter', 'e.g. pH')}{arrayField('batches', 'Batches', 'Leave empty for all selected batches')}
      {task.operation === 'reconcile' && textField('target_unit', 'Target unit', 'e.g. mg/L')}
      {task.operation === 'check_gaps' && arrayField('expected_parameters', 'Expected parameters', 'e.g. pH, viability')}
    </div>}
    {task.operation === 'trace_impact' && <div className="grid gap-3 sm:grid-cols-2">{textField('record_id', 'Changed record ID')}{textField('record_kind', 'Changed record type', 'e.g. evidence')}</div>}
    <details className="text-xs text-text-secondary"><summary className="cursor-pointer">More scope and coverage options</summary><div className="mt-3 grid gap-3 sm:grid-cols-2">
      {arrayField('kinds', 'Record types', 'e.g. case, evidence')}
      {!['compare', 'reconcile', 'check_gaps'].includes(task.operation) && arrayField('batches', 'Batches')}
      {task.operation !== 'check_gaps' && arrayField('expected_parameters', 'Expected parameters')}
      {arrayField('expected_document_kinds', 'Expected document types')}
      <label className="block">Expected sample times (hours)<input className={field} defaultValue={task.expected_times.join(', ')} key={task.expected_times.join(',')} placeholder="e.g. 0, 12, 24" onBlur={e => {
        const values = list(e.target.value).map(Number); e.target.setCustomValidity(values.some(v => !Number.isFinite(v) || v < 0) ? 'Enter non-negative hours separated by commas.' : '');
        if (values.every(v => Number.isFinite(v) && v >= 0)) edit('expected_times', values);
      }} /></label>
      {textField('process_stage', 'Process stage')}{textField('effective_at', 'Effective time', 'ISO date and time, including timezone')}
      <label className="block">Maximum records<input className={field} type="number" min={1} max={100} required value={task.limit} onChange={e => edit('limit', Number(e.target.value))} /></label>
      {!!task.record_refs.length && <p className="break-words text-text-tertiary">Pinned sources: {task.record_refs.map(ref => `${ref.kind} ${ref.id} · revision ${ref.revision}`).join('; ')}</p>}
    </div></details>
  </div>;
}

export function TaskResultCard({ result: initial, task, onAsk }: { result: TaskResult; task?: TaskSpec; onAsk?: (text: string, siteId?: string) => void }) {
  const [result, setResult] = useState(initial), [refreshing, setRefreshing] = useState(false), [error, setError] = useState('');
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => setResult(initial), [initial]);
  const stale = result.status !== 'current';
  const tables = Object.entries(result.data).filter(([, rows]) => Array.isArray(rows));
  async function refresh() {
    setRefreshing(true); setError('');
    try { setResult(await getTaskResult(result.id)); setUnavailable(false); }
    catch (e) { setError((e as Error).message); if (e instanceof ProcessApiError && [403, 404].includes(e.status)) setUnavailable(true); }
    finally { setRefreshing(false); }
  }
  if (unavailable) return <section aria-label="Task result" className="rounded-card border border-border-hairline bg-surface p-4"><p role="alert" className="text-xs text-status-warning">This saved result is no longer available under your current access. {error}</p><button type="button" className={`${workButton} mt-3`} disabled={refreshing} onClick={() => void refresh()}>Check access again</button></section>;
  return <section aria-label="Task result" className="space-y-3 rounded-card border border-border-hairline bg-surface p-4" data-testid="task-result">
    <div className="flex items-start justify-between gap-3"><div><p className={`text-[11px] font-medium ${stale || result.task_status === 'needs_information' ? 'text-status-warning' : 'text-brand-teal'}`}>{stale ? 'Evidence changed · refresh or rerun before use' : result.task_status === 'needs_information' ? 'Needs information' : 'Completed'}</p><h3 className="mt-1 text-sm font-medium">{result.summary}</h3></div><button type="button" className={workButton} aria-label="Refresh result status" disabled={refreshing} onClick={() => void refresh()}><RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} /></button></div>
    {error && <p role="alert" className="text-xs text-status-critical">{error}</p>}
    {!!result.issues.length && <ul className="space-y-1 rounded-control bg-status-warning-bg p-3 text-xs leading-5">{result.issues.map((issue, i) => <li key={`${issue.code}-${i}`}>{issue.message}</li>)}</ul>}
    {tables.map(([name, values]) => <ResultTable key={name} name={name} values={values as unknown[]} />)}
    <details className="text-xs"><summary className="cursor-pointer text-text-secondary">Sources · {result.source_refs.length} references</summary><ul className="mt-2 space-y-2">{result.source_refs.map(ref => <SourceReference key={`${ref.kind}:${ref.id}:${ref.revision}`} source={ref} />)}</ul>{!result.source_refs.length && <p className="mt-2 text-text-tertiary">No supporting source references were returned.</p>}</details>
    <div className="flex flex-wrap gap-2">{task?.parameter && <Link href={`/trends/?parameter=${encodeURIComponent(task.parameter)}`} className={workButton}>Open trends<ArrowUpRight size={13} /></Link>}{onAsk && <button type="button" className={workButton} onClick={() => onAsk(`Review saved workspace task ${result.id} (${result.operation}) at site ${result.site_id}. ${result.summary} Check its source evidence and remaining gaps.`, result.site_id)}>Ask about this result</button>}</div>
    <details className="text-xs text-text-tertiary"><summary className="cursor-pointer">Calculation and source record</summary><p className="mt-2">{result.elapsed_seconds.toFixed(2)} s · {result.model_calls} model calls · Site {result.site_id} · Result {result.id}</p><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-control bg-surface-secondary p-3">{JSON.stringify(result, null, 2)}</pre></details>
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

function ResultTable({ name, values }: { name: string; values: unknown[] }) {
  const rows = values.slice(0, 50).map(value => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : { value });
  const columns = [...new Set(rows.flatMap(row => Object.keys(row)))].slice(0, 12);
  const cell = (value: unknown) => value == null ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  return <div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="mb-2 text-left font-medium capitalize">{name.replaceAll('_', ' ')} · {values.length}</caption><thead><tr>{columns.map(key => <th key={key} scope="col" className="border-b border-border-hairline p-2 font-medium text-text-tertiary">{key.replaceAll('_', ' ')}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map(key => <td key={key} className="max-w-xs break-words border-b border-border-hairline p-2 align-top">{cell(row[key])}</td>)}</tr>)}</tbody></table>{values.length > 50 && <p className="mt-2 text-[11px] text-text-tertiary">First 50 rows shown. Inspect the calculation record for the full bounded result.</p>}</div>;
}

export function AssistantTaskWork({ siteId, context, storageScope, onRoutine, onAsk }: { siteId: string; context: TaskContext; storageScope: string; onRoutine: (task: TaskSpec) => void; onAsk: (text: string, siteId?: string) => void }) {
  const [catalog, setCatalog] = useState<TaskCatalog>([]), [datasets, setDatasets] = useState<TaskDataset[]>([]);
  const [task, setTask] = useState(() => emptyTask(siteId, context.task));
  const [results, setResults] = useState<{ result: TaskResult; task?: TaskSpec }[]>([]);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [loaded, setLoaded] = useState(false), [attempt, setAttempt] = useState(0);
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
    Promise.allSettled([getTaskCatalog(), processRequest<{ datasets: TaskDataset[] }>(`/v1/cmo-datasets?site_id=${encodeURIComponent(siteId)}`)]).then(([tasks, deliveries]) => {
      if (!alive) return;
      if (tasks.status === 'fulfilled') setCatalog(tasks.value.operations); else setError(tasks.reason.message);
      if (deliveries.status === 'fulfilled') setDatasets(deliveries.value.datasets); else setError(previous => [previous, 'Delivery list unavailable. Your selected IDs are retained.'].filter(Boolean).join(' '));
      setLoaded(true);
    }); return () => { alive = false; };
  }, [siteId, attempt]);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); if (inFlight.current) return; inFlight.current = true; setBusy(true); setError('');
    try { const result = await runTask(task); setResults(current => {
      const next = [{ result, task }, ...current.filter(item => item.result.id !== result.id)].slice(0, 10);
      try { localStorage.setItem(resultKey, JSON.stringify(next.map(item => item.result.id))); } catch { /* Results remain on the server. */ }
      return next;
    }); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); inFlight.current = false; }
  }
  const requiresData = catalog.find(item => item.id === task.operation)?.requires_dataset;
  return <section className="space-y-4 py-4" aria-label="Direct work">
    <div><h2 className="text-lg font-medium">Run a task</h2><p className="mt-1 text-xs leading-5 text-text-secondary">Find records, compare values, or prepare a review from authorized sources. Site {siteId} · {context.label}</p></div>
    {error && <div role="alert" className="rounded-control bg-status-warning-bg p-3 text-xs">{error}<button type="button" onClick={() => setAttempt(value => value + 1)} className="ml-2 underline">Reload options</button></div>}
    {!loaded && <p role="status" className="text-xs text-text-tertiary">Loading available tasks…</p>}
    {!!catalog.length && <form onSubmit={submit} className="space-y-4 rounded-card border border-border-hairline bg-surface p-4">
      <fieldset disabled={busy} className="min-w-0"><TaskFields task={task} onChange={setTask} catalog={catalog} datasets={datasets} /></fieldset>
      <div className="flex flex-wrap gap-2"><button type="submit" disabled={busy || (!!requiresData && !task.dataset_ids.length)} className={`${workButton} !border-brand-teal !bg-brand-teal !text-white`}>{busy ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}{busy ? 'Running task…' : 'Run task'}</button><button type="button" className={workButton} disabled={busy} onClick={() => onRoutine(task)}>Save as routine</button></div>
      {busy && <p role="status" className="text-xs text-text-tertiary">Checking sources and calculating. You can return to Chat while this runs.</p>}
    </form>}
    {results.map(item => <TaskResultCard key={item.result.id} {...item} onAsk={onAsk} />)}
    {!results.length && <p className="text-xs leading-5 text-text-tertiary">Results and missing information appear here with the source references. A task result is available for review; it does not approve a manufacturing action.</p>}
  </section>;
}
