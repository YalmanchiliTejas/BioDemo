'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { Check, Loader2, Pencil, Plus, RotateCcw, X } from 'lucide-react';
import { workButton } from '@/components/process/AssistantTaskWork';
import { STEP_KINDS, actionLabel, count, listActions, proposeAction, roles, sentence,
  type ActionCatalog, type Plan, type PlanStep, type Proposal, type StepKind } from '@/lib/workbench';
import type { Work } from './Findings';
import { field, primaryButton, Region } from './parts';

type StepChange = { status?: PlanStep['status']; text?: string; outcome?: string };
/** A proposal that is waiting, or approved and not carried out, is not finished work: its step cannot be ticked off. */
const pending = (step: PlanStep) => step.can_complete != null ? step.status === 'open' && !step.can_complete
  : step.stands === 'waiting for approval' || step.stands === 'approved, not yet carried out';
const standing = (step: PlanStep) => step.stands === 'to do' ? 'text-text-secondary bg-surface-secondary' : step.status === 'done' ? 'text-emerald-700 bg-status-success-bg'
  : step.status === 'dropped' ? 'text-text-tertiary bg-surface-secondary' : 'text-amber-800 bg-status-warning-bg';

export function NextSteps({ plan, work, onStep, batches, canCite }: {
  plan: Plan | null; work: Work; onStep: (stepId: string, change: StepChange) => Promise<void>;
  /** Batches in view, offered as targets. */ batches: string[]; /** A proposal has to rest on a calculated result. */ canCite: boolean;
}) {
  const steps = plan?.steps ?? [];
  const open = steps.filter(step => step.status === 'open'), done = steps.filter(step => step.status === 'done'), dropped = steps.filter(step => step.status === 'dropped');
  const [catalog, setCatalog] = useState<ActionCatalog | null>(null);
  return <Region number={4} id="next-steps" title="Next steps" hint={plan ? undefined : 'Kept as your work from the first step you add.'}>
    {!steps.length && <p className="text-xs leading-5 text-text-tertiary">Nothing planned yet. Add a step here, or from a finding in “Gaps and findings”.</p>}
    {!!open.length && <ol className="space-y-2" aria-label="Steps to do">{open.map(step => <Step key={step.step_id} step={step} catalog={catalog} onStep={onStep} />)}</ol>}
    {!!done.length && <><h3 className="mb-1.5 mt-4 text-[11px] font-medium uppercase tracking-wide text-text-tertiary">Done · {done.length}</h3>
      <ol className="space-y-2" aria-label="Steps done">{done.map(step => <Step key={step.step_id} step={step} catalog={catalog} onStep={onStep} />)}</ol></>}
    {!!dropped.length && <details className="mt-3 text-xs text-text-tertiary"><summary className="cursor-pointer">Dropped · {dropped.length}</summary>
      <ol className="mt-2 space-y-2" aria-label="Steps dropped">{dropped.map(step => <Step key={step.step_id} step={step} catalog={catalog} onStep={onStep} />)}</ol></details>}
    <AddStepForm work={work} />
    <ProposeForm work={work} catalog={catalog} onCatalog={setCatalog} batches={batches} canCite={canCite} />
  </Region>;
}

function Step({ step, catalog, onStep }: { step: PlanStep; catalog: ActionCatalog | null; onStep: (stepId: string, change: StepChange) => Promise<void> }) {
  const [mode, setMode] = useState<'view' | 'done' | 'edit'>('view'), [text, setText] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function save(change: StepChange) {
    setBusy(true); setError('');
    try { await onStep(step.step_id, change); setMode('view'); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const isOpen = step.status === 'open', proposal = step.proposal, request = step.request;
  const icon = 'inline-flex h-7 w-7 items-center justify-center rounded-control text-text-tertiary hover:bg-surface-secondary hover:text-text-primary disabled:opacity-40';
  return <li className={`rounded-control border border-border-hairline p-3 text-xs leading-5 ${isOpen ? 'bg-surface' : 'bg-surface-secondary/60'}`} data-testid="plan-step" data-status={step.status}>
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1"><span className="text-[10px] font-semibold uppercase tracking-wide text-text-tertiary">{STEP_KINDS[step.kind] ?? 'Step'}</span>
      <span className={`rounded-pill px-1.5 py-0.5 text-[10px] font-medium ${standing(step)}`} data-testid="step-stands">{sentence(step.stands)}</span></div>
    {mode === 'edit' ? <form className="mt-1.5" onSubmit={e => { e.preventDefault(); if (text.trim()) void save({ text: text.trim() }); }}>
      <textarea aria-label="Step text" className={`${field} !mt-0 leading-5`} rows={3} maxLength={600} value={text} autoFocus onChange={e => setText(e.target.value)} />
      <div className="mt-2 flex gap-2"><button type="submit" className={primaryButton} disabled={busy || !text.trim()}>Save</button><button type="button" className={workButton} disabled={busy} onClick={() => setMode('view')}>Cancel</button></div></form>
      : <p className={`mt-1 break-words text-[13px] ${step.status === 'dropped' ? 'text-text-tertiary line-through' : 'text-text-primary'}`}>{step.text}</p>}
    {step.basis && <p className="mt-1 break-words text-text-tertiary">Prompted by: {step.basis}</p>}
    {proposal && <p className="mt-1 text-text-secondary">{proposal.status === 'not_available' ? 'The proposal is not available under your current access.'
      : <>Proposal: {actionLabel(proposal.operation ?? '', catalog)}{proposal.target_id ? ` · ${proposal.target_id}` : ''} · approval by {roles(proposal.required_roles)}</>}</p>}
    {request && <p className="mt-1 text-text-secondary">{request.status === 'not_available' ? 'The request is not available under your current access.' : <>Sent to {request.owner_id}{request.title ? `: ${request.title}` : ''}</>}</p>}
    {step.status === 'done' && <p className="mt-1 text-text-primary"><span className="font-medium">Outcome:</span> {step.outcome || 'not recorded'}</p>}
    {mode === 'done' && <form className="mt-2" onSubmit={e => { e.preventDefault(); void save({ status: 'done', outcome: text.trim() }); }}>
      <label className="block text-text-secondary">What was the outcome?<input aria-label="Outcome" className={field} maxLength={600} value={text} autoFocus placeholder="One line: what you found or did" onChange={e => setText(e.target.value)} /></label>
      <div className="mt-2 flex gap-2"><button type="submit" className={primaryButton} disabled={busy}>{busy && <Loader2 size={13} className="animate-spin" />}Save as done</button><button type="button" className={workButton} disabled={busy} onClick={() => setMode('view')}>Cancel</button></div></form>}
    {error && <p role="alert" className="mt-1 text-status-warning">{error}</p>}
    {mode === 'view' && <div className="mt-1.5 flex flex-wrap items-center gap-1">
      {isOpen && !pending(step) && <button type="button" className={`${workButton} !py-1`} disabled={busy} onClick={() => { setText(''); setMode('done'); }}><Check size={13} />Mark done</button>}
      {isOpen && <button type="button" className={icon} aria-label="Edit step" title="Edit" disabled={busy} onClick={() => { setText(step.text); setMode('edit'); }}><Pencil size={13} /></button>}
      {isOpen && <button type="button" className={icon} aria-label="Drop step" title="Drop this step" disabled={busy} onClick={() => void save({ status: 'dropped' })}><X size={14} /></button>}
      {!isOpen && <button type="button" className={icon} aria-label="Reopen step" title="Reopen" disabled={busy} onClick={() => void save({ status: 'open' })}><RotateCcw size={13} /></button>}
    </div>}
  </li>;
}

function AddStepForm({ work }: { work: Work }) {
  const [kind, setKind] = useState<StepKind>('check'), [text, setText] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function add(e: FormEvent) {
    e.preventDefault(); if (!text.trim() || busy) return;
    setBusy(true); setError('');
    try { await work.addStep({ kind, text: text.trim() }); setText(''); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <form onSubmit={add} aria-label="Add a step" className="mt-4 border-t border-border-hairline pt-3">
    <p className="text-xs font-medium text-text-secondary">Add a step</p>
    <div className="mt-1.5 flex flex-wrap gap-2">
      <select aria-label="Kind of step" className={`${field} !mt-0 !w-auto`} value={kind} onChange={e => setKind(e.target.value as StepKind)}>{(Object.keys(STEP_KINDS) as StepKind[]).map(value => <option key={value} value={value}>{STEP_KINDS[value]}</option>)}</select>
      <input aria-label="Step" className={`${field} !mt-0 min-w-0 flex-1 basis-40`} value={text} maxLength={600} placeholder="What to do next" onChange={e => setText(e.target.value)} />
      <button type="submit" className={workButton} disabled={busy || !text.trim()}>{busy ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}Add</button></div>
    {error && <p role="alert" className="mt-1 text-xs text-status-warning">Not added. {error}</p>}
  </form>;
}

function ProposeForm({ work, catalog, onCatalog, batches, canCite }: { work: Work; catalog: ActionCatalog | null; onCatalog: (catalog: ActionCatalog) => void; batches: string[]; canCite: boolean }) {
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(''), [loadError, setLoadError] = useState(''), [attempt, setAttempt] = useState(0);
  const [operation, setOperation] = useState(''), [target, setTarget] = useState(''), [rationale, setRationale] = useState(''), [expected, setExpected] = useState(''), [measure, setMeasure] = useState('');
  const [sent, setSent] = useState<{ proposal: Proposal; saved: boolean } | null>(null);
  useEffect(() => {
    if (catalog) return; let alive = true; setLoadError('');
    listActions().then(value => { if (alive) onCatalog(value); }).catch(e => { if (alive) setLoadError((e as Error).message); });
    return () => { alive = false; };
  }, [catalog, attempt, onCatalog]);
  async function propose(e: FormEvent) {
    e.preventDefault(); if (busy) return;
    setBusy(true); setError('');
    try {
      const saved = await work.ensureSaved();
      if (!saved.compare) throw new Error('The comparison could not be saved, so the proposal has nothing to rest on.');
      const proposal = await proposeAction(saved.compare, { operation, target_id: target.trim(), rationale: rationale.trim(), expected_result: expected.trim(), ...(measure.trim() ? { follow_up_measure: measure.trim() } : {}) });
      // The proposal exists from here on. The step keeps it in view; if adding it fails, say so without hiding the proposal.
      try { await work.addStep({ kind: 'action', text: `${actionLabel(proposal.operation, catalog)}: ${proposal.target_id}`.slice(0, 600), result_id: saved.compare, proposal_id: proposal.proposal_id, basis: rationale.trim().slice(0, 600) }); setSent({ proposal, saved: true }); }
      catch (stepError) { setSent({ proposal, saved: false }); setError(`The proposal was created, but it could not be added to next steps. ${(stepError as Error).message}`); }
      setOpen(false); setTarget(''); setRationale(''); setExpected(''); setMeasure('');
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const chosen = catalog?.operations.find(item => item.operation === operation);
  return <div className="mt-4 border-t border-border-hairline pt-3">
    {sent && <div role="status" className="mb-3 rounded-control bg-brand-teal-light/60 p-2.5 text-xs leading-5 text-text-primary" data-testid="proposal-sent">
      <p className="font-medium">Proposed for review: {actionLabel(sent.proposal.operation, catalog)} · {sent.proposal.target_id}</p>
      <p>Waiting for approval from {roles(sent.proposal.required_roles)}. Nothing has been carried out.</p>
      {!!sent.proposal.constraints?.length && <><p className="mt-1 text-text-secondary">The reviewer will see these cautions with it:</p><ul className="list-disc pl-4 text-text-secondary">{sent.proposal.constraints.map((line, i) => <li key={i}>{line}</li>)}</ul></>}</div>}
    {error && !open && <p role="alert" className="mb-2 text-xs text-status-warning">{error}</p>}
    {!open && <><button type="button" className={workButton} disabled={!canCite} onClick={() => { setOpen(true); setError(''); }}>Propose an action for review</button>
      {!canCite && <p className="mt-1 text-[11px] text-text-tertiary">A proposal has to rest on a calculated result. Bring values into view first.</p>}</>}
    {open && <form onSubmit={propose} aria-label="Propose an action for review" className="space-y-3 rounded-control bg-surface-secondary p-3 text-xs">
      <p className="text-[13px] font-medium text-text-primary">Propose an action for review</p>
      {loadError && <p role="alert" className="text-status-warning">The list of actions could not be read. {loadError} <button type="button" className="text-brand-teal underline" onClick={() => setAttempt(n => n + 1)}>Try again</button></p>}
      <label className="block text-text-secondary">Action<select aria-label="Action" className={field} required value={operation} onChange={e => setOperation(e.target.value)}>
        <option value="">{catalog ? 'Choose an action' : 'Reading actions…'}</option>
        {catalog?.operations.map(item => <option key={item.operation} value={item.operation}>{actionLabel(item.operation, catalog)} · approved by {item.approved_by_words?.join(' and ') ?? roles(item.approved_by)}</option>)}</select></label>
      <label className="block text-text-secondary">What it applies to<input aria-label="What it applies to" className={field} required maxLength={300} list="workbench-targets" value={target} placeholder="The deviation, batch or lot number" onChange={e => setTarget(e.target.value)} />
        <datalist id="workbench-targets">{batches.map(batch => <option key={batch} value={batch} />)}</datalist></label>
      <label className="block text-text-secondary">Why<textarea aria-label="Why" className={`${field} leading-5`} required rows={3} maxLength={2000} value={rationale} placeholder="What in the picture supports this" onChange={e => setRationale(e.target.value)} /></label>
      <label className="block text-text-secondary">Expected result<input aria-label="Expected result" className={field} required maxLength={1000} value={expected} placeholder="What should be true afterwards" onChange={e => setExpected(e.target.value)} /></label>
      <label className="block text-text-secondary">How you will check it worked <span className="text-text-tertiary">(optional)</span><input aria-label="How you will check it worked" className={field} maxLength={600} value={measure} onChange={e => setMeasure(e.target.value)} /></label>
      {chosen && <p className="text-text-secondary">{count(chosen.approved_by.length, 'approval')} needed: {chosen.approved_by_words?.join(' and ') ?? roles(chosen.approved_by)}. The proposal cites the comparison in view, with its open checks.</p>}
      {error && <p role="alert" className="text-status-warning">{error}</p>}
      <div className="flex flex-wrap gap-2"><button type="submit" className={primaryButton} disabled={busy || !catalog}>{busy && <Loader2 size={13} className="animate-spin" />}{busy ? 'Proposing…' : 'Propose for review'}</button>
        <button type="button" className={workButton} disabled={busy} onClick={() => setOpen(false)}>Cancel</button></div>
      {catalog?.note && <p className="text-[11px] leading-4 text-text-tertiary">{catalog.note}</p>}
    </form>}
    {!open && <p className="mt-1.5 text-[11px] leading-4 text-text-tertiary">{catalog?.note ?? 'Nothing is carried out from this page.'}</p>}
  </div>;
}
