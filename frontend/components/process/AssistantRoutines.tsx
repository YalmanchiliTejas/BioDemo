'use client';

import { useEffect, useRef, useState } from 'react';
import { Loader2, Pause, Play, Plus, RefreshCw } from 'lucide-react';
import { ProcessApiError, processRequest } from '@/lib/process-api';
import { activateRoutine, emptyTask, getRoutine, getRoutines, getTaskCatalog, pauseRoutine, runRoutine, saveRoutine, TRIGGERS,
  type AssistantRoutine, type RoutineDefinition, type TaskCatalog, type TaskContext, type TaskSpec } from '@/lib/assistant-workflows';
import { TaskFields, TaskResultCard, workButton, type TaskDataset } from './AssistantTaskWork';

export function AssistantRoutines({ siteId, context, draftTask, reviewId, visible, onAsk, onReviewConsumed, onDraftConsumed }: {
  siteId: string; context: TaskContext; draftTask: TaskSpec | null; reviewId: string | null; visible: boolean; onAsk: (text: string, siteId?: string) => void;
  onReviewConsumed: () => void; onDraftConsumed: () => void;
}) {
  const [routines, setRoutines] = useState<AssistantRoutine[]>([]), [selected, setSelected] = useState<AssistantRoutine | null>(null);
  const [catalog, setCatalog] = useState<TaskCatalog>([]), [datasets, setDatasets] = useState<TaskDataset[]>([]);
  const [editing, setEditing] = useState<RoutineDefinition | null>(null), [editingRecord, setEditingRecord] = useState<AssistantRoutine | undefined>();
  const [runTask, setRunTask] = useState<TaskSpec | null>(null), [reviewing, setReviewing] = useState(false), [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState(''), [attempt, setAttempt] = useState(0);
  const inFlight = useRef(false);
  const request = useRef(0);
  function adopt(routine: AssistantRoutine) {
    setSelected(routine); setRoutines(previous => [routine, ...previous.filter(value => value.id !== routine.id)]);
  }
  function draft(task = emptyTask(siteId, context.task)) {
    request.current++; setSelected(null); setEditingRecord(undefined); setEditing({ name: '', description: '', task, triggers: [], every_minutes: null, max_runs: 3 });
    setRunTask(null); setReviewing(false); setAck(false); setError('');
  }
  useEffect(() => { if (draftTask) { draft(draftTask); onDraftConsumed(); } }, [draftTask]);
  useEffect(() => {
    let alive = true; setLoading(true); setError('');
    Promise.allSettled([getRoutines(siteId), getTaskCatalog(), processRequest<{ datasets: TaskDataset[] }>(`/v1/cmo-datasets?site_id=${encodeURIComponent(siteId)}`)]).then(([saved, tasks, deliveries]) => {
      if (!alive) return;
      if (saved.status === 'fulfilled') setRoutines(saved.value.routines); else setError(saved.reason.message);
      if (tasks.status === 'fulfilled') setCatalog(tasks.value.operations); else setError(previous => [previous, tasks.reason.message].filter(Boolean).join(' '));
      if (deliveries.status === 'fulfilled') setDatasets(deliveries.value.datasets);
      else setError(previous => [previous, 'Delivery list unavailable. Saved routine scope is retained.'].filter(Boolean).join(' '));
      setLoading(false);
    }); return () => { alive = false; };
  }, [siteId, attempt]);
  async function open(id: string) {
    const version = ++request.current; setError(''); setSelected(null); setEditing(null); setRunTask(null); setReviewing(false); setAck(false);
    try { const value = await getRoutine(id); if (request.current === version) adopt(value); }
    catch (e) { if (request.current === version) setError((e as Error).message); }
  }
  // Navigation requests are consumed once; switching views must preserve unsaved edits.
  useEffect(() => { if (reviewId) { void open(reviewId); onReviewConsumed(); } }, [reviewId]);
  useEffect(() => {
    if (!visible || !selected || editing || busy || reviewing || runTask) return;
    let alive = true; const id = selected.id;
    const timer = window.setInterval(() => { getRoutine(id).then(value => { if (alive) adopt(value); }).catch(e => { if (alive) { setError((e as Error).message); if (e instanceof ProcessApiError && [403, 404].includes(e.status)) setSelected(null); } }); }, 10000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [visible, selected?.id, editing, busy, reviewing, runTask]);
  useEffect(() => () => { request.current++; }, []);
  async function mutate(action: () => Promise<AssistantRoutine>) {
    if (inFlight.current) return; inFlight.current = true; setBusy(true); setError('');
    try { const value = await action(); adopt(value); setEditing(null); setReviewing(false); setAck(false); }
    catch (e) { setError((e as Error).message); } finally { inFlight.current = false; setBusy(false); }
  }
  async function execute() {
    if (!selected || !runTask || inFlight.current) return; inFlight.current = true; setBusy(true); setError('');
    try {
      const result = await runRoutine(selected.id, runTask); adopt({ ...selected, latest_result: result }); setRunTask(null);
      // Admission and publication advance the routine revision. Fetch it before another mutation.
      try { adopt(await getRoutine(selected.id)); } catch { setError('The result is saved. Refresh current state before editing or changing this routine.'); }
    }
    catch (e) { setError((e as Error).message); } finally { inFlight.current = false; setBusy(false); }
  }
  const latestRun = selected?.runs?.at(-1);
  const previousResult = !!selected?.latest_result && !!latestRun && latestRun.result_id !== selected.latest_result.id;
  return <section className="space-y-4 py-4" aria-label="Reusable routines">
    <div className="flex items-start justify-between gap-3"><div><h2 className="text-lg font-medium">Routines</h2><p className="mt-1 text-xs leading-5 text-text-secondary">Name repeatable work, run it with new parameters, or authorize follow-up on relevant events. Site {siteId}.</p></div><button type="button" className={workButton} disabled={busy} onClick={() => draft()}><Plus size={14} />New routine</button></div>
    {error && <div role="alert" className="rounded-control bg-status-warning-bg p-3 text-xs">{error}<button type="button" className="ml-2 underline" onClick={() => { setAttempt(value => value + 1); if (selected) void open(selected.id); }}>Refresh current state</button></div>}
    {loading && <p role="status" className="text-xs text-text-tertiary">Loading your routines…</p>}
    {!!routines.length && <nav aria-label="Saved routines" className="flex flex-wrap gap-2">{routines.map(routine => <button key={routine.id} type="button" disabled={busy} aria-pressed={selected?.id === routine.id} onClick={() => void open(routine.id)} className={`${workButton} ${selected?.id === routine.id ? '!border-brand-teal !bg-brand-teal-light' : ''}`}>{routine.name}<span className="text-[10px] font-normal capitalize">{routine.status}</span></button>)}</nav>}
    {!loading && !routines.length && !editing && !selected && <div className="rounded-card border border-dashed border-border-strong p-5 text-sm"><h3 className="font-medium">Keep a useful check ready to run.</h3><p className="mt-2 text-xs leading-5 text-text-secondary">For example, check expected samples when a batch changes, prepare evidence after an alarm, or respond to a team request. Save a draft here, or ask the assistant to propose one in Chat.</p><button type="button" className={`${workButton} mt-3`} onClick={() => onAsk('Help me define a reusable routine. Ask what outcome and source scope I need, then propose a draft routine for my review.', siteId)}>Define with the assistant</button></div>}
    {editing && <form className="space-y-4 rounded-card border border-border-hairline bg-surface p-4" onSubmit={e => { e.preventDefault(); void mutate(() => saveRoutine(editing, editingRecord)); }}>
      <fieldset disabled={busy} className="min-w-0 space-y-4"><legend className="mb-3 text-sm font-medium">{editingRecord ? 'Edit routine definition' : 'New routine draft'}</legend>
        <label className="block text-xs">Routine name<input required maxLength={120} value={editing.name} onChange={e => setEditing({ ...editing, name: e.target.value })} className="mt-1 block w-full rounded-control border border-border-strong p-2 text-sm" placeholder="e.g. Early batch review" /></label>
        <label className="block text-xs">Purpose<textarea maxLength={2000} rows={2} value={editing.description} onChange={e => setEditing({ ...editing, description: e.target.value })} className="mt-1 block w-full rounded-control border border-border-strong p-2 text-sm" placeholder="What should this check help the reviewer decide?" /></label>
        <TaskFields task={editing.task} onChange={task => setEditing({ ...editing, task })} catalog={catalog} datasets={datasets} />
        <fieldset><legend className="mb-2 text-xs font-medium">Relevant events</legend><div className="grid gap-2 sm:grid-cols-2">{TRIGGERS.map(([kind, label]) => <label key={kind} className="flex items-start gap-2 text-xs"><input type="checkbox" checked={editing.triggers.includes(kind)} onChange={e => setEditing({ ...editing, triggers: e.target.checked ? [...editing.triggers, kind] : editing.triggers.filter(value => value !== kind) })} />{label}</label>)}</div></fieldset>
        <label className="flex items-start gap-2 text-xs"><input type="checkbox" checked={editing.every_minutes != null} onChange={e => setEditing({ ...editing, every_minutes: e.target.checked ? 60 : null })} />Also check on a schedule</label>
        {editing.every_minutes != null && <label className="flex items-center gap-2 text-xs">Every (minutes)<input type="number" required min={15} max={10080} value={editing.every_minutes} onChange={e => setEditing({ ...editing, every_minutes: Number(e.target.value) })} className="w-24 rounded-control border border-border-strong p-2" /></label>}
        <label className="flex items-center gap-2 text-xs">Background run allowance<input type="number" required min={1} max={100} value={editing.max_runs} onChange={e => setEditing({ ...editing, max_runs: Number(e.target.value) })} className="w-20 rounded-control border border-border-strong p-2" /></label>
      </fieldset>
      <p className="text-xs leading-5 text-text-tertiary">Saving keeps this definition inactive. Review and activate it to grant standing permission. Editing an active routine pauses it until you review the changed scope.</p>
      <div className="flex gap-2"><button type="submit" disabled={busy || !editing.name.trim() || !catalog.length} className={`${workButton} !bg-brand-teal !text-white`}>{busy && <Loader2 size={13} className="animate-spin" />}Save draft</button><button type="button" className={workButton} disabled={busy} onClick={() => { setEditing(null); if (editingRecord) setSelected(editingRecord); }}>Cancel</button></div>
    </form>}
    {selected && !editing && <article className="space-y-4 rounded-card border border-border-hairline bg-surface p-4">
      <header><div className="flex items-center justify-between gap-2"><h3 className="text-base font-medium">{selected.name}</h3><span className={`rounded-pill px-2 py-1 text-[11px] capitalize ${selected.status === 'active' ? 'bg-brand-teal-light text-brand-teal' : 'bg-surface-secondary text-text-secondary'}`}>{selected.status === 'active' ? 'Active' : selected.status === 'paused' ? 'Paused' : 'Draft'}</span></div>{selected.description && <p className="mt-2 text-xs leading-5 text-text-secondary">{selected.description}</p>}</header>
      {latestRun && <LatestRoutineRun run={latestRun} />}
      <RoutineScope routine={selected} catalog={catalog} />
      <div className="flex flex-wrap gap-2"><button type="button" className={workButton} disabled={busy} onClick={() => { setRunTask(selected.task); setReviewing(false); }}><Play size={13} />Run once</button>
        {selected.status === 'active' ? <button type="button" className={workButton} disabled={busy} onClick={() => void mutate(() => pauseRoutine(selected))}><Pause size={13} />Pause routine</button> : <button type="button" className={workButton} disabled={busy} onClick={() => { setReviewing(true); setAck(false); setRunTask(null); }}>Review activation</button>}
        <button type="button" className={workButton} disabled={busy} onClick={() => { setEditingRecord(selected); setEditing({ name: selected.name, description: selected.description, task: selected.task, triggers: selected.triggers, every_minutes: selected.every_minutes, max_runs: selected.max_runs }); }}>Edit routine</button>
        <button type="button" className={workButton} aria-label="Refresh routine" disabled={busy} onClick={() => void open(selected.id)}><RefreshCw size={13} /></button>
      </div>
      {reviewing && <div className="space-y-3 rounded-control border border-brand-teal bg-brand-teal-light/40 p-3"><h4 className="text-sm font-medium">Review standing permission</h4><p className="text-xs leading-5">This activates the task and source scope above for the selected events{selected.every_minutes ? ` and every ${selected.every_minutes} minutes` : ''}, within its remaining run allowance. Reads, calculations and review drafts run under your current access. Manufacturing decisions and external messages retain their approvals.</p>
        {!selected.triggers.length && !selected.every_minutes && <p className="text-xs text-status-warning">Choose an event or schedule before activating. You can still run it once.</p>}
        <label className="flex items-start gap-2 text-xs leading-5"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} className="mt-1" />I authorize this routine to read sources and run calculations for the displayed scope, triggers, and run allowance.</label>
        <div className="flex gap-2"><button type="button" className={`${workButton} !bg-brand-teal !text-white`} disabled={!ack || busy || (!selected.triggers.length && !selected.every_minutes)} onClick={() => void mutate(() => activateRoutine(selected))}>Activate routine</button><button type="button" className={workButton} disabled={busy} onClick={() => setReviewing(false)}>Cancel activation</button></div>
      </div>}
      {runTask && <form className="space-y-3 rounded-control border border-border-hairline p-3" onSubmit={e => { e.preventDefault(); void execute(); }}><h4 className="text-sm font-medium">Parameters for this run</h4><fieldset disabled={busy} className="min-w-0"><TaskFields task={runTask} onChange={setRunTask} fixedOperation catalog={catalog} datasets={datasets} /></fieldset><p className="text-xs text-text-tertiary">Runs once with these parameters. The saved definition and standing permission stay as reviewed.</p><div className="flex gap-2"><button type="submit" className={`${workButton} !bg-brand-teal !text-white`} disabled={busy}>{busy ? 'Running…' : 'Run routine'}</button><button type="button" className={workButton} disabled={busy} onClick={() => setRunTask(null)}>Cancel run</button></div></form>}
      {selected.latest_result && <div className="space-y-2">{previousResult && <p className="text-xs font-medium text-text-secondary">Previous completed result</p>}<TaskResultCard result={selected.latest_result} task={selected.task} onAsk={onAsk} /></div>}
      <details className="text-xs text-text-secondary"><summary className="cursor-pointer">Run history and definition</summary><p className="mt-2 text-text-tertiary">Revision {selected.revision} · Updated {selected.updated_at}</p>{selected.runs?.length ? <ol className="mt-3 space-y-2">{selected.runs.map((run, index) => <li key={index} className="rounded bg-surface-secondary p-2"><pre className="overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(run, null, 2)}</pre></li>)}</ol> : <p className="mt-2 text-text-tertiary">No background run history has been recorded.</p>}<pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(selected.task, null, 2)}</pre></details>
    </article>}
  </section>;
}

function LatestRoutineRun({ run }: { run: Record<string, unknown> }) {
  const status = typeof run.status === 'string' ? run.status : 'unknown';
  const attention = ['failed', 'blocked', 'needs_information', 'source_limit_exceeded'].includes(status);
  const statusLabels: Record<string, string> = { completed: 'Completed', cancelled: 'Cancelled', running: 'Running', queued: 'Queued', needs_information: 'Needs information', failed: 'Failed', blocked: 'Blocked', source_limit_exceeded: 'Source limit exceeded' };
  const issueLabels: Record<string, string> = { source_limit_exceeded: 'Source selection exceeded the allowed limit.', source_limit: 'Source selection exceeded the allowed limit.', evidence_required: 'Required evidence is missing.', stale_basis: 'Source evidence changed; prepare a current result.', permission_denied: 'Current source access needs review.', conflicting_measurements: 'Conflicting measurements need review.', missing_unit: 'A declared measurement unit is missing.' };
  const issues = Array.isArray(run.issues) ? run.issues : [];
  const reasons = [...new Set(issues.map(issue => {
    const code = issue && typeof issue === 'object' && 'code' in issue ? String(issue.code) : '';
    return issueLabels[code] ?? 'The task could not complete all checks. Review its source scope and current access.';
  }))];
  const at = typeof run.finished_at === 'string' ? new Date(run.finished_at) : null;
  return <div role="status" className={`space-y-1 rounded-control p-3 text-xs ${attention || status === 'cancelled' ? 'bg-status-warning-bg' : 'bg-surface-secondary'}`}>
    <p className="font-medium">{attention ? 'Latest run needs attention' : `Latest run · ${statusLabels[status] ?? 'Status unavailable'}`}</p>
    {attention && <p>{statusLabels[status] ?? 'Needs review'}</p>}
    {reasons.map(reason => <p key={reason}>{reason}</p>)}
    {at && !Number.isNaN(at.getTime()) && <p className="text-text-tertiary">Finished {at.toLocaleString()}</p>}
  </div>;
}

function RoutineScope({ routine, catalog }: { routine: AssistantRoutine; catalog: TaskCatalog }) {
  const task = routine.task;
  return <dl className="grid gap-3 rounded-control bg-surface-secondary p-3 text-xs sm:grid-cols-2">
    <div><dt className="text-text-tertiary">Task</dt><dd className="mt-1">{catalog.find(item => item.id === task.operation)?.title ?? task.operation.replaceAll('_', ' ')}</dd></div>
    <div><dt className="text-text-tertiary">Scope</dt><dd className="mt-1 break-words">Site {task.site_id}{task.dataset_ids.length ? ` · deliveries ${task.dataset_ids.join(', ')}` : ' · authorized site records'}{task.batches.length ? ` · batches ${task.batches.join(', ')}` : ''}{task.parameter ? ` · ${task.parameter}` : ''}</dd></div>
    <div><dt className="text-text-tertiary">When to run</dt><dd className="mt-1">{routine.triggers.map(kind => TRIGGERS.find(([key]) => key === kind)?.[1] ?? kind).join(', ') || 'Manual run'}{routine.every_minutes ? ` · every ${routine.every_minutes} minutes` : ''}</dd></div>
    <div><dt className="text-text-tertiary">Background allowance</dt><dd className="mt-1">{routine.runs_admitted} of {routine.max_runs} runs used</dd></div>
    {task.query && <div><dt className="text-text-tertiary">Search or review focus</dt><dd className="mt-1">{task.query}</dd></div>}
    {!!task.record_refs.length && <div><dt className="text-text-tertiary">Pinned records</dt><dd className="mt-1 break-words">{task.record_refs.map(ref => `${ref.kind} ${ref.id} · revision ${ref.revision}`).join('; ')}</dd></div>}
    {!!task.series?.length && <div><dt className="text-text-tertiary">Exact batch selection</dt><dd className="mt-1 break-words">{task.series.map(series => `${series.batch} in ${series.dataset_id}`).join('; ')}</dd></div>}
    {!!task.kinds.length && <div><dt className="text-text-tertiary">Record types</dt><dd className="mt-1">{task.kinds.join(', ')}</dd></div>}
    {(task.expected_parameters.length > 0 || task.expected_document_kinds.length > 0 || task.expected_times.length > 0) && <div><dt className="text-text-tertiary">Expected evidence</dt><dd className="mt-1">{[task.expected_parameters.join(', '), task.expected_document_kinds.join(', '), task.expected_times.length ? `sample hours ${task.expected_times.join(', ')}` : ''].filter(Boolean).join(' · ')}</dd></div>}
    <div><dt className="text-text-tertiary">Additional limits</dt><dd className="mt-1">Up to {task.limit} records{task.process_stage ? ` · ${task.process_stage}` : ''}{task.effective_at ? ` · effective ${task.effective_at}` : ''}{task.target_unit ? ` · convert to ${task.target_unit}` : ''}{task.record_id ? ` · changed ${task.record_kind ?? 'record'} ${task.record_id}` : ''}</dd></div>
  </dl>;
}
