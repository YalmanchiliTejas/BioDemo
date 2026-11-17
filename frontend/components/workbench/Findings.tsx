'use client';

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import Link from 'next/link';
import { Check, Loader2, Plus } from 'lucide-react';
import { CausesView, workButton, type Causes } from '@/components/process/AssistantTaskWork';
import { GAP_STATUS, count, explainResult, fig, hours, locationText, requestEvidence, seconds, sentence, suggestCauses, traceIdentifier, withUnit,
  type Dataset, type Explanation, type Gap, type GapStatus, type Issue, type Measurement, type NewStep, type Picture, type SavedIds, type Selection, type TaskResult, type Trace, type Verification } from '@/lib/workbench';
import { listPeople, type Person } from '@/lib/worklist-api';
import { DeliveryLink } from './Picture';
import { card, field, primaryButton, Region } from './parts';

/** What a finding needs from the page: the saved results a step must cite, and the plan it is added to. */
export type Work = {
  siteId: string; selection: Selection | null; selectionKey: string; datasets: Dataset[];
  /** Saves the three results for the current selection once, and returns their ids. */
  ensureSaved: () => Promise<SavedIds>;
  /** Adds a step to the plan, creating the plan the first time. Rejects with the reason when it could not be saved. */
  addStep: (step: NewStep) => Promise<void>;
  askAssistant?: (text: string) => void;
};

const warning = 'rounded-control border border-amber-200 bg-status-warning-bg p-3 text-xs leading-5 text-text-secondary';
const heading = 'text-[13px] font-medium text-text-primary';

/** Turns a finding into a planned step and says so in place, because the plan may be off screen. */
function AddStep({ work, step, label = 'Add to next steps' }: { work: Work; step: (saved: SavedIds) => NewStep | Promise<NewStep>; label?: string }) {
  const [state, setState] = useState<'idle' | 'busy' | 'added'>('idle'), [error, setError] = useState('');
  async function add() {
    setState('busy'); setError('');
    try { await work.addStep(await step(await work.ensureSaved())); setState('added'); }
    catch (e) { setError((e as Error).message); setState('idle'); }
  }
  return <span className="inline-flex flex-wrap items-center gap-2">
    <button type="button" className={workButton} disabled={state !== 'idle'} onClick={() => void add()}>{state === 'busy' ? <Loader2 size={13} className="animate-spin" /> : state === 'added' ? <Check size={13} /> : <Plus size={13} />}{state === 'added' ? 'Added to next steps' : label}</button>
    {error && <span role="alert" className="text-xs text-status-warning">Not added. {error}</span>}</span>;
}

export function Findings({ picture, unavailable, work }: { picture: Picture | null; /** Why there is nothing to judge yet. */ unavailable?: string; work: Work }) {
  const compare = picture?.results.compare, gaps = picture?.results.gaps, reconcile = picture?.results.reconcile;
  const names = { ...Object.fromEntries(work.datasets.map(d => [d.id, d.delivery_name || d.cmo || 'Selected delivery'])), ...(reconcile?.data.deliveries ?? {}) };
  const issues = [...(reconcile?.issues ?? []), ...(compare?.issues ?? []), ...(gaps?.issues ?? [])];
  const once = (code: string, key: (issue: Issue) => string) => issues.filter(issue => issue.code === code).filter((issue, i, all) => all.findIndex(other => key(other) === key(issue)) === i);
  const conflicts = once('conflicting_measurements', issue => `${issue.batch}|${issue.parameter}|${issue.time_h}`);
  const absent = [...once('missing_requested_batch', issue => String(issue.batch)), ...once('missing_requested_series', issue => `${issue.dataset_id}|${issue.batch}`)];
  const cohort = compare?.data.cohort, parameter = work.selection?.parameter ?? 'the values';
  const provisional = [reconcile, compare, gaps].some(result => result?.evidence_state === 'provisional');
  const review = ((compare?.data.verification ?? reconcile?.data.verification ?? []) as Verification[]).filter(v => v.state === 'provisional');
  const found = (gaps?.data.gaps ?? []) as Gap[], basis = gaps?.data.expectation_basis;
  const groups = (Object.keys(GAP_STATUS) as GapStatus[]).map(status => ({ status, items: found.filter(gap => gap.status === status) })).filter(group => group.items.length);
  const differs = cohort?.verdict === 'differs' ? cohort.attributes.filter(a => a.verdict === 'differs') : [];
  const unrecorded = cohort && (compare?.data.comparison_summary?.length ?? 0) > 0 ? cohort.attributes.filter(a => a.verdict === 'not_recorded') : [];
  const quiet = picture && !conflicts.length && !absent.length && !differs.length && !unrecorded.length && !groups.length && !provisional;
  const values = (attribute: { values: Record<string, string | number | null> }) => Object.entries(attribute.values).map(([batch, value]) => `${batch}: ${value ?? 'not recorded'}`).join(', ');

  return <Region number={3} id="findings" title="Gaps and findings" hint="What needs attention in this selection, each with something you can do about it.">
    {!picture && <p className="py-2 text-xs text-text-tertiary">{unavailable ?? 'Findings appear with the picture.'}</p>}
    {picture && <div className="space-y-3">
      {provisional && <div role="status" className={warning} data-testid="finding-in-review"><p className={heading}>This picture uses values still in review</p>
        {!!review.length && <ul className="mt-1">{review.map(v => <li key={v.dataset_id}>{names[v.dataset_id] ?? 'Selected delivery'}: {count(v.values_still_in_review_used ?? 0, 'value')} still in review used · {count(v.open_checks ?? 0, 'open check')} · {count(v.rejected_values_excluded ?? 0, 'rejected value')} left out</li>)}</ul>}
        <p className="mt-1">{review[0]?.meaning ?? 'Nothing here was accepted on a reviewer’s behalf. Finish the delivery review before relying on these values.'}</p></div>}

      {conflicts.map((issue, i) => { const rows = (Array.isArray(issue.values) ? issue.values : []) as Measurement[], evidence = rows[0]?.sources?.[0]?.evidence_id; return <article key={`conflict-${i}`} className={warning} data-testid="finding-conflict">
        <h3 className={heading}>{String(issue.batch)} has {rows.length || 'several'} different {String(issue.parameter)} values at {hours(issue.time_h)} h</h3>
        <ul className="mt-1">{rows.map((row, j) => <li key={j}><span className="font-medium tabular-nums text-text-primary">{withUnit(row.value, row.unit)}</span> · {row.sources?.[0]?.source?.path ?? 'file not recorded'}, {locationText(row.sources?.[0]?.source)}</li>)}</ul>
        <p className="mt-1">Until one is chosen in the delivery, none of them is drawn or compared.</p>
        <p className="mt-2">{evidence ? <DeliveryLink evidenceId={evidence} datasets={work.datasets}>Open the delivery to resolve</DeliveryLink> : <Link href="/cmo/" className="text-brand-teal underline">Open deliveries to resolve</Link>}</p></article>; })}

      {!!differs.length && <article className={warning} data-testid="finding-context"><h3 className={heading}>The batches were not made under the same recorded conditions</h3>
        <ul className="mt-1">{differs.map(attribute => <li key={attribute.attribute}><span className="font-medium text-text-primary">{attribute.label}</span> differs ({values(attribute)}).</li>)}</ul>
        <p className="mt-1">A difference in {parameter} may come from that.</p>
        <p className="mt-2"><AddStep key={work.selectionKey} work={work} label="Add a check to next steps" step={saved => ({ kind: 'check', result_id: saved.compare,
          text: `Check whether the difference in ${differs.map(a => `${a.label.toLowerCase()} (${values(a)})`).join(' and ')} explains the difference in ${parameter}.`.slice(0, 600),
          basis: `The batches differ in ${differs.map(a => a.label.toLowerCase()).join(', ')}.` })} /></p></article>}

      {!!unrecorded.length && <article className={card} data-testid="finding-context-unknown"><h3 className={heading}>Part of the context is not recorded</h3>
        <p className="mt-1">{unrecorded.map(a => a.label).join(', ')} {unrecorded.length === 1 ? 'is' : 'are'} not recorded for every batch, so it is not known whether the batches are comparable on {unrecorded.length === 1 ? 'it' : 'them'}.</p>
        <p className="mt-2"><AddStep key={work.selectionKey} work={work} label="Add a check to next steps" step={saved => ({ kind: 'check', result_id: saved.compare,
          text: `Find the recorded ${unrecorded.map(a => a.label.toLowerCase()).join(', ')} for the batches in view.`.slice(0, 600), basis: `Not recorded: ${unrecorded.map(a => a.label.toLowerCase()).join(', ')}.` })} /></p></article>}

      {!!absent.length && <article className={card} data-testid="finding-absent"><h3 className={heading}>No usable {parameter} values for {absent.map(issue => String(issue.batch)).join(', ')}</h3>
        <p className="mt-1">{absent.length === 1 ? 'This batch is' : 'These batches are'} selected, and the selected deliveries hold no usable values for {absent.length === 1 ? 'it' : 'them'} in this time window.</p></article>}

      {!!groups.length && <MissingEvidence key={work.selectionKey} groups={groups} total={gaps?.data.gap_count ?? found.length} draft={gaps?.data.draft_request} coverage={gaps?.data.coverage} work={work} />}

      {basis === 'none' && <p className={card} data-testid="no-requirements">No requirements are approved for this site yet, so gaps cannot be judged. Approved specifications say which parameters every batch must report.
        {' '}<Link href="/settings/specifications/" className="text-brand-teal underline">Open specifications</Link></p>}
      {basis && basis !== 'none' && !groups.length && <p className="text-xs text-text-secondary" data-testid="no-gaps">No gaps against {basis === 'approved_specifications' ? 'approved requirements' : 'the expected items'} for this selection{gaps?.data.requirements_checked ? ` (${count(gaps.data.requirements_checked, 'requirement')} checked)` : ''}.</p>}
      {quiet && basis !== 'none' && <p className="text-xs text-text-secondary">No conflicting values and no recorded difference in context for this selection.</p>}
    </div>}

    <div className="mt-5 border-t border-border-hairline pt-4">
      <h3 className="text-xs font-medium uppercase tracking-wide text-text-tertiary">Look further</h3>
      <div className="mt-2 space-y-3">
        <TraceTool work={work} />
        <CausesTool work={work} />
        <ExplainTool key={work.siteId} work={work} available={!!picture && !!reconcile?.data.series?.length} summary={compare?.summary ?? ''} />
      </div>
    </div>
  </Region>;
}

function MissingEvidence({ groups, total, draft, coverage, work }: { groups: { status: GapStatus; items: Gap[] }[]; total: number; draft?: { title: string; description: string; questions?: string[]; sending?: string }; coverage?: string; work: Work }) {
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(''), [sent, setSent] = useState<{ owner: string; saved: boolean } | null>(null);
  const [title, setTitle] = useState(draft?.title ?? ''), [owner, setOwner] = useState('');
  // Colleagues who can be asked at this site, by the name they are known by. If they cannot be listed, a name can still be typed.
  const [people, setPeople] = useState<Person[] | null>(null);
  useEffect(() => { if (open && people === null) listPeople(work.siteId).then(setPeople).catch(() => setPeople([])); }, [open, people, work.siteId]);
  // Once colleagues can be chosen from a list, a name typed before it arrived no longer applies.
  useEffect(() => { if (people?.length && owner && !people.some(person => person.id === owner)) setOwner(''); }, [people, owner]);
  const known = (id: string) => people?.find(person => person.id === id)?.label ?? id;
  const [description, setDescription] = useState(() => [draft?.description ?? '', ...(draft?.questions ?? []).map(question => `- ${question}`)].join('\n').slice(0, 2000));
  const item = (gap: Gap) => [gap.parameter ?? gap.document_kind, gap.batch && `batch ${gap.batch}`, gap.time_h != null && `at ${hours(gap.time_h)} h`].filter(Boolean).join(' · ');
  async function send(e: FormEvent) {
    e.preventDefault(); if (busy || !owner.trim()) return;
    setBusy(true); setError('');
    try {
      const saved = await work.ensureSaved();
      if (!saved.gaps) throw new Error('The gap check could not be saved, so there is nothing to attach the request to.');
      const request = await requestEvidence(saved.gaps, { owner_id: owner.trim(), title: title.trim() || undefined, description: description.trim() || undefined });
      // The request is sent at this point. The step only keeps it in view, so a failure to add it is reported separately.
      try {
        await work.addStep({ kind: 'request', text: `Ask ${known(request.owner_id)}: ${request.title}`.slice(0, 600), result_id: saved.gaps, work_request_id: request.id,
          basis: `${count(total, 'expected item')} missing from the selected deliveries.` });
        setSent({ owner: known(request.owner_id), saved: true });
      } catch (stepError) { setSent({ owner: known(request.owner_id), saved: false }); setError(`The request was sent, but it could not be added to next steps. ${(stepError as Error).message}`); }
      setOpen(false);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <article className={card} data-testid="finding-missing"><h3 className={heading}>{count(total, 'expected item')} missing from the selected deliveries</h3>
    <div className="mt-2 space-y-2">{groups.map(group => <div key={group.status}><p><span className="font-medium text-text-primary">{GAP_STATUS[group.status].title} · {group.items.length}</span> <span className="text-text-tertiary">{GAP_STATUS[group.status].meaning}</span></p>
      <ul className="mt-0.5 list-disc pl-4">{group.items.slice(0, 12).map((gap, i) => <li key={i}>{item(gap)}{gap.required_by ? <span className="text-text-tertiary"> · required by {gap.required_by.replace(/^approved specification /, 'the approved specification ')}</span> : null}</li>)}</ul>
      {group.items.length > 12 && <p className="text-text-tertiary">and {group.items.length - 12} more.</p>}</div>)}</div>
    {coverage && <p className="mt-2 text-[11px] text-text-tertiary">This covers the selected deliveries only. It does not show that the evidence is absent from other systems.</p>}
    {sent && <p role="status" className="mt-2 rounded-control bg-brand-teal-light/60 p-2 text-text-primary">Request sent to {sent.owner}.{sent.saved ? ' It is in next steps, waiting for a reply.' : ''}</p>}
    {error && <p role="alert" className="mt-2 text-status-warning">{error}</p>}
    {!open && draft && <p className="mt-2"><button type="button" className={workButton} onClick={() => { setOpen(true); setError(''); }}>{sent ? 'Ask someone else' : 'Ask for this evidence'}</button></p>}
    {open && <form onSubmit={send} aria-label="Ask for this evidence" className="mt-3 space-y-3 rounded-control bg-surface-secondary p-3">
      <p className="text-text-secondary">A draft, written from the gaps above. Change anything before it is sent; the request is theirs to answer and stays attributed to them.</p>
      <label className="block text-text-secondary">Subject<input aria-label="Subject" className={field} value={title} maxLength={160} onChange={e => setTitle(e.target.value)} /></label>
      <label className="block text-text-secondary">Request<textarea aria-label="Request" className={`${field} min-h-[132px] leading-5`} value={description} maxLength={2000} onChange={e => setDescription(e.target.value)} /></label>
      <label className="block text-text-secondary">Who to ask{people?.length
        ? <select aria-label="Who to ask" className={field} value={owner} required onChange={e => setOwner(e.target.value)}><option value="">Choose a colleague…</option>
          {people.map(person => <option key={person.id} value={person.id}>{person.label}</option>)}</select>
        : <input aria-label="Who to ask" className={field} value={owner} maxLength={160} required placeholder="Their sign-in name" onChange={e => setOwner(e.target.value)} />}
        <span className="mt-1 block text-[11px] text-text-tertiary">They are notified and it appears under “Needs you” on their overview. Their reply comes back to this step.</span></label>
      <div className="flex flex-wrap gap-2"><button type="submit" className={primaryButton} disabled={busy || !owner.trim()}>{busy && <Loader2 size={13} className="animate-spin" />}{busy ? 'Sending…' : 'Send request'}</button>
        <button type="button" className={workButton} disabled={busy} onClick={() => setOpen(false)}>Cancel</button></div>
    </form>}
  </article>;
}

/** A small tool: one identifier in, one bounded lookup out. The result stays until another identifier is tried. */
function Lookup<T>({ title, hint, label, placeholder, button, run, children }: { title: string; hint: string; label: string; placeholder: string; button: string;
  run: (value: string) => Promise<T>; children: (result: T, value: string) => ReactNode }) {
  const [value, setValue] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState(''), [result, setResult] = useState<{ value: string; data: T } | null>(null);
  const request = useRef(0);
  async function submit(e: FormEvent) {
    e.preventDefault(); const wanted = value.trim(); if (!wanted) return;
    const mine = ++request.current; setBusy(true); setError('');
    try { const data = await run(wanted); if (request.current === mine) setResult({ value: wanted, data }); }
    catch (e) { if (request.current === mine) setError((e as Error).message); } finally { if (request.current === mine) setBusy(false); }
  }
  return <section aria-label={title} className={card}>
    <h4 className={heading}>{title}</h4><p className="text-text-tertiary">{hint}</p>
    <form onSubmit={submit} className="mt-2 flex flex-wrap items-end gap-2"><label className="min-w-0 flex-1 basis-48 text-text-secondary"><span className="sr-only">{label}</span>
      <input aria-label={label} className={`${field} !mt-0`} value={value} maxLength={500} placeholder={placeholder} onChange={e => setValue(e.target.value)} /></label>
      <button type="submit" className={workButton} disabled={busy || !value.trim()}>{busy && <Loader2 size={13} className="animate-spin" />}{busy ? 'Looking…' : button}</button></form>
    {error && <p role="alert" className="mt-2 text-status-warning">{error}</p>}
    {result && <div className="mt-3">{children(result.data, result.value)}</div>}
  </section>;
}

const when = (time?: string | null) => time ? time.replace('T', ' ').replace(/(\.\d+)?(Z|\+00:00)$/, ' UTC') : 'time not recorded';

function TraceTool({ work }: { work: Work }) {
  return <Lookup<TaskResult> title="Trace a lot or equipment" hint="Which batches a material lot or a piece of equipment is recorded as used in." label="Lot or equipment number" placeholder="e.g. LOT-7781" button="Trace"
    run={value => traceIdentifier(work.siteId, value)}>{(result, identifier) => { const data = result.data as Trace, usage = data.recorded_usage ?? [], mentions = data.records ?? [], affected = data.affected_batches ?? []; return <div className="space-y-3" data-testid="trace-result">
      <div><p className="font-medium text-text-primary">Recorded as used · {count(affected.length, 'batch', 'batches')}</p>
        {usage.length ? <ul className="mt-1 space-y-1">{usage.map((use, i) => <li key={i} className="rounded-control bg-surface-secondary px-2 py-1.5"><span className="font-mono font-medium text-text-primary">{use.batch_id}</span> · used as {use.used_as ?? 'not stated'}{use.step_id ? ` · step ${use.step_id}` : ''} · {when(use.performed_at)}</li>)}</ul>
          : <p className="mt-1">No executed step records {identifier} as used in a batch.</p>}
        {(data.recorded_usage_count ?? usage.length) > usage.length && <p className="mt-1 text-text-tertiary">Showing {usage.length} of {data.recorded_usage_count} recorded uses.</p>}</div>
      <div><p className="font-medium text-text-primary">Only mentioned · {count(mentions.length, 'record')}</p>
        {mentions.length ? <><p className="text-text-tertiary">These records name {identifier} without recording that it was used. Each is a candidate to confirm.</p>
          <ul className="mt-1 space-y-1">{mentions.slice(0, 10).map((record, i) => <li key={i} className="rounded-control border border-dashed border-border-strong px-2 py-1.5">{record.label ?? sentence(record.kind.replaceAll('_', ' '))}{record.time ? ` · ${when(record.time)}` : ''}</li>)}</ul></>
          : <p className="text-text-tertiary">No other record names it.</p>}</div>
      {data.genealogy && <p className={data.genealogy.complete ? 'text-text-tertiary' : 'rounded-control bg-status-warning-bg p-2'}>{data.genealogy.note}</p>}
      {data.limitation && <p className="text-text-tertiary">{data.limitation}</p>}
      {!!affected.length && <AddStep work={work} label="Add affected batches to next steps" step={() => ({ kind: 'check', result_id: result.id,
        text: `Assess whether ${affected.join(', ')} ${affected.length === 1 ? 'is' : 'are'} affected by ${identifier}.`.slice(0, 600), basis: `${identifier} is recorded as used in ${affected.join(', ')}.`.slice(0, 600) })} />}
    </div>; }}</Lookup>;
}

function CausesTool({ work }: { work: Work }) {
  return <Lookup<TaskResult> title="Suggest causes to check" hint="Linked records in time order for a signal, a case or a batch, screened against their recorded times." label="Signal, case or batch number" placeholder="e.g. a deviation or batch number" button="Suggest"
    run={value => suggestCauses(work.siteId, value)}>{result => <div data-testid="causes-result">
      {/* The view opens with its own notice: "Hypotheses to check. No cause is established." */}
      {!!result.issues.length && <ul className="mb-2 rounded-control bg-status-warning-bg p-2">{result.issues.map((issue, i) => <li key={i}>{issue.message}</li>)}</ul>}
      <CausesView data={result.data as unknown as Causes} action={hypothesis => <AddStep work={work} step={() => ({ kind: 'check', result_id: result.id, text: hypothesis.next_check.slice(0, 600), basis: hypothesis.statement.slice(0, 600) })} />} />
    </div>}</Lookup>;
}

function ExplainTool({ work, available, summary }: { work: Work; available: boolean; summary: string }) {
  const [state, setState] = useState<{ key: string; status: 'busy' | 'done' | 'error'; answer?: Explanation; resultId?: string; error?: string } | null>(null), [elapsed, setElapsed] = useState(0);
  const request = useRef(0);
  useEffect(() => { if (state?.status !== 'busy') return; const started = Date.now(), timer = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000); return () => clearInterval(timer); }, [state?.status]);
  useEffect(() => () => { request.current++; }, []);
  async function explain() {
    const mine = ++request.current, key = work.selectionKey; setElapsed(0); setState({ key, status: 'busy' });
    try {
      const saved = await work.ensureSaved();
      if (!saved.compare) throw new Error('The comparison could not be saved, so there is nothing to explain.');
      const answer = await explainResult(saved.compare);
      if (request.current === mine) setState({ key, status: 'done', answer, resultId: saved.compare });
    } catch (e) { if (request.current === mine) setState({ key, status: 'error', error: (e as Error).message }); }
  }
  // The same words the assistant's own "Ask about this result" hands over: the saved result, by its reference.
  async function handOff() {
    try { const saved = await work.ensureSaved(); work.askAssistant?.(`Review saved workspace task ${saved.compare} (compare) at site ${work.siteId}. ${summary} Check its source evidence and remaining gaps.`); }
    catch (e) { setState({ key: work.selectionKey, status: 'error', error: (e as Error).message }); }
  }
  const answer = state?.status === 'done' ? state.answer : null, stale = !!state && state.key !== work.selectionKey && state.status !== 'busy';
  const assistant = work.askAssistant && <button type="button" className="text-brand-teal underline" disabled={!available} onClick={() => void handOff()}>Continue in the assistant</button>;
  return <section aria-label="Explain this picture" className={card}>
    <h4 className={heading}>Explain this picture</h4>
    <p className="text-text-tertiary">One short explanation written by a model from the calculated figures. It cannot add numbers of its own. For a longer investigation, hand this result to the assistant.</p>
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2"><button type="button" className={workButton} disabled={!available || state?.status === 'busy'} onClick={() => void explain()}>{state?.status === 'busy' && <Loader2 size={13} className="animate-spin" />}{answer || state?.status === 'error' ? 'Explain again' : 'Explain this picture'}</button>{assistant}</div>
    {!available && <p className="mt-2 text-text-tertiary">Available once the picture shows values.</p>}
    {state?.status === 'busy' && <p role="status" className="mt-2 text-text-secondary">Writing an explanation… {elapsed} s. This is one model call and can take up to a minute; everything else on the page keeps working.</p>}
    {state?.status === 'error' && <p role="alert" className="mt-2 text-status-warning">No explanation was produced. {state.error}</p>}
    {stale && answer && <p role="status" className="mt-2 rounded-control bg-status-warning-bg p-2">The selection has changed since this was written. It describes the earlier picture.</p>}
    {answer && answer.status !== 'completed' && <div className="mt-3 rounded-control bg-status-warning-bg p-3" data-testid="explanation-withheld">
      <p className="font-medium text-text-primary">{answer.status === 'withheld' ? 'The explanation was withheld' : 'No explanation is available right now'}</p>
      <p className="mt-1">{answer.status === 'withheld' ? 'It did not pass the check that every number comes from the calculated result. ' : ''}Reason: {answer.reason ?? 'not given'}</p>
      {answer.next_step && <p className="mt-1">{answer.next_step}</p>}{assistant && <p className="mt-2">{assistant}</p>}</div>}
    {answer?.status === 'completed' && <div className="mt-3 space-y-3 rounded-control bg-surface-secondary p-3" data-testid="explanation">
      <p className="text-[11px] font-medium uppercase tracking-wide text-text-tertiary">Written by a model · review before relying on it</p>
      <p className="text-[13px] leading-6 text-text-primary">{answer.explanation}</p>
      {!!answer.observations?.length && <div><p className="font-medium text-text-primary">What the figures show</p><ul className="mt-1 list-disc space-y-0.5 pl-4">{answer.observations.map((line, i) => <li key={i}>{line}</li>)}</ul></div>}
      {!!answer.hypotheses?.length && <div><p className="font-medium text-text-primary">Possible explanations · not established</p>
        <ul className="mt-1 space-y-2">{answer.hypotheses.map((h, i) => <li key={i} className="rounded-control bg-surface p-2"><p className="text-text-primary">{h.statement}</p><p className="mt-0.5"><span className="font-medium">To check:</span> {h.check}</p>
          {h.check && <p className="mt-1.5"><AddStep work={work} step={() => ({ kind: 'check', result_id: state?.resultId, text: h.check.slice(0, 600), basis: h.statement.slice(0, 600) })} /></p>}</li>)}</ul></div>}
      {!!answer.unknowns?.length && <div><p className="font-medium text-text-primary">What this cannot tell</p><ul className="mt-1 list-disc space-y-0.5 pl-4">{answer.unknowns.map((line, i) => <li key={i}>{line}</li>)}</ul></div>}
      <p className="text-[11px] leading-4 text-text-tertiary">{answer.grounding} {[answer.model && `Model ${answer.model}`, answer.timing && `${seconds(answer.timing.seconds)}`].filter(Boolean).join(' · ')}
        {answer.timing && !answer.timing.within_target && <span className="font-medium text-status-warning"> · over the {fig(answer.timing.target_seconds)} s target</span>}</p>
    </div>}
  </section>;
}
