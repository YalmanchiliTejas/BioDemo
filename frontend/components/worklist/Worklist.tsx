'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { ArrowRight, Check, CircleCheck, CircleDashed, ClipboardCheck, FolderKanban, Loader2, MessageCircleQuestion, MessageSquare, MessageSquareReply, PackageCheck, PackageSearch, Radar, RotateCw, ShieldCheck, type LucideIcon } from 'lucide-react';
import { QuestionCard } from '@/components/process/QuestionCard';
import { workButton } from '@/components/process/AssistantTaskWork';
import { field, primaryButton } from '@/components/workbench/parts';
import { cached, remember } from '@/lib/cache';
import { ProcessApiError } from '@/lib/process-api';
import { acknowledgeSignal } from '@/lib/signals-api';
import { ago, answerAssistant, answerRequest, decideProposal, getWorklist, headline, listPeople, sendDraftedRequest, type Group, type Person, type SendRequest, type WorkItem, type Worklist as List } from '@/lib/worklist-api';

const ICON: Record<WorkItem['kind'], LucideIcon> = { approval: ShieldCheck, proposal: ClipboardCheck, request: MessageSquareReply, question: MessageCircleQuestion,
  assistant: MessageSquare, signal: Radar, quality: FolderKanban, delivery: PackageCheck, missing_evidence: PackageSearch };
const GROUPS: { key: Group; title: string; empty: string }[] = [
  { key: 'needs_you', title: 'Needs you', empty: 'Nothing is waiting on you.' },
  { key: 'in_progress', title: 'In progress', empty: 'Nothing is in progress for you.' },
  { key: 'done', title: 'Done in the last week', empty: 'Nothing was finished for you in the last week.' },
];
const STALE_MS = 60_000;
const list = (items: string[]) => items.length > 1 ? `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}` : items[0] ?? '';

/**
 * What needs the signed-in person, what is in progress for them and what was finished, across the product.
 * Decisions are made here, in place; each goes to the service that owns the record. Nothing is polled: the list is read on
 * arrival, after each decision, and when the person comes back to the tab.
 */
export function Worklist({ siteId, onState, retryElsewhere }: { siteId: string; onState?: (state: 'ready' | 'failed') => void;
  /** The page already offers one "Try again" that reads this list too. */ retryElsewhere?: boolean }) {
  const key = `worklist:${siteId}`;
  const [data, setData] = useState<List | null>(() => cached<List>(key) ?? null);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [notice, setNotice] = useState(''), [absent, setAbsent] = useState(false);
  const read = useRef(0), report = useRef(onState); report.current = onState;
  const load = useCallback(async () => {
    setBusy(true);
    try { const next = await getWorklist(siteId); remember(key, next); read.current = Date.now(); setData(next); setError(''); report.current?.('ready'); }
    catch (e) {
      // An older server has no worklist yet. That is not a failure to report: the page falls back to its summary.
      if (e instanceof ProcessApiError && e.status === 404) setAbsent(true); else setError((e as Error).message);
      report.current?.('failed');
    }
    finally { setBusy(false); }
  }, [siteId, key]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const back = () => { if (document.visibilityState === 'visible' && Date.now() - read.current > STALE_MS) void load(); };
    document.addEventListener('visibilitychange', back);
    return () => document.removeEventListener('visibilitychange', back);
  }, [load]);
  /** After a decision: say what was recorded, drop the item at once, then read the list again for where it now stands. */
  const decided = (item: WorkItem, message: string) => {
    setNotice(message);
    setData(current => current && { ...current, needs_you: current.needs_you.filter(other => other.id !== item.id),
      counts: { ...current.counts, needs_you: Math.max(0, current.counts.needs_you - 1) } });
    void load();
  };

  if (absent) return null;
  if (!data) return <section className="worklist" aria-label="Your work" data-testid="worklist" aria-busy={!error}>
    {error ? <p role="alert" className="text-xs text-status-warning">The list of what needs you could not be read. {error}{' '}
      {!retryElsewhere && <button type="button" className="text-brand-teal underline" onClick={() => void load()}>Try again</button>}</p>
      : <p role="status" tabIndex={-1} data-guide="overview-worklist-loading" className="text-sm text-text-secondary">Checking what needs you…</p>}
  </section>;

  const rest = [data.counts.in_progress && `${data.counts.in_progress} in progress`, data.counts.done && `${data.counts.done} done in the last week`].filter(Boolean).join(' · ');
  return <section className="worklist" aria-labelledby="worklist-title" data-testid="worklist" aria-busy={busy}>
    <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
      <div className="min-w-0"><h2 id="worklist-title" className="worklist-headline" aria-live="polite">{headline(data)}</h2>
        {rest && <p className="mt-1 text-xs text-text-secondary">{rest}</p>}</div>
      <button type="button" className={workButton} onClick={() => void load()} disabled={busy} aria-label="Read the list again">
        {busy ? <Loader2 size={13} className="animate-spin" /> : <RotateCw size={13} />}Refresh</button>
    </header>
    {notice && <p role="status" className="mt-3 flex items-start gap-2 rounded-control bg-brand-teal-light/60 p-2.5 text-xs leading-5 text-text-primary" data-testid="worklist-notice">
      <Check size={14} className="mt-0.5 shrink-0 text-brand-teal" />{notice}</p>}
    {error && <p role="alert" className="mt-3 text-xs text-status-warning">The list could not be refreshed, so it may be out of date. {error}</p>}
    {!!data.unavailable.length && <p role="alert" className="mt-3 rounded-control border border-amber-200 bg-status-warning-bg p-2.5 text-xs leading-5 text-text-primary" data-testid="worklist-unavailable">
      Could not read {list(data.unavailable.map(u => u.covers))}. Anything waiting there is not listed below.</p>}
    {GROUPS.map(group => <ItemGroup key={group.key} group={group.key} title={group.title} empty={group.empty} items={data[group.key]} total={data.counts[group.key]}
      siteId={siteId} onDecided={decided} onChanged={() => void load()} />)}
    <p className="mt-4 text-[11px] leading-5 text-text-tertiary">This list reads {list(data.covers)}. It does not yet read {list(data.not_covered)}; those still appear where they were raised.</p>
  </section>;
}

function ItemGroup({ group, title, empty, items, total, siteId, onDecided, onChanged }: { group: Group; title: string; empty: string; items: WorkItem[]; total: number; siteId: string;
  onDecided: (item: WorkItem, message: string) => void; onChanged: () => void }) {
  const [all, setAll] = useState(group !== 'done');
  const shown = all ? items : items.slice(0, 3);
  // An empty "in progress" or "done" says nothing a person needs; only "needs you" states that it is empty.
  if (!items.length && group !== 'needs_you') return null;
  return <div className="mt-5" data-testid={`worklist-${group}`}>
    <h3 className="worklist-group-title" tabIndex={group === 'needs_you' ? -1 : undefined} data-guide={group === 'needs_you' ? 'overview-needs-you' : undefined}>{title}{total > 0 && <span className="font-normal"> · {total}</span>}</h3>
    {!items.length ? <p className="mt-2 text-xs text-text-tertiary">{empty}</p>
      : <ul className="mt-2 divide-y divide-border-hairline rounded-control border border-border-hairline">{shown.map(item => <Row key={item.id} item={item} group={group} siteId={siteId} onDecided={onDecided} onChanged={onChanged} />)}</ul>}
    {items.length > shown.length && <button type="button" className="mt-2 text-xs text-brand-teal underline" onClick={() => setAll(true)}>Show all {items.length}</button>}
    {total > items.length && <p className="mt-2 text-[11px] text-text-tertiary">Showing the newest {items.length} of {total}.</p>}
  </div>;
}

function Row({ item, group, siteId, onDecided, onChanged }: { item: WorkItem; group: Group; siteId: string; onDecided: (item: WorkItem, message: string) => void; onChanged: () => void }) {
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const Icon = group === 'done' ? CircleCheck : group === 'in_progress' ? CircleDashed : ICON[item.kind] ?? ClipboardCheck;
  const action = group === 'needs_you' ? item.action : null;
  /** Runs one decision. A conflict means the record changed after the list was read: say so and read it again. */
  async function run(work: () => Promise<unknown>, message: string) {
    setBusy(true); setError('');
    try { await work(); onDecided(item, message); }
    catch (e) {
      const stale = e instanceof ProcessApiError && e.status === 409;
      setError(stale ? 'This changed after the list was read. The list has been read again; check it before deciding.' : (e as Error).message);
      if (stale) onChanged();
    } finally { setBusy(false); }
  }
  const toggle = (label: string) => <button type="button" className={open ? workButton : primaryButton} aria-expanded={open} onClick={() => { setOpen(!open); setError(''); }}>{open ? 'Close' : label}</button>;
  return <li className="worklist-row" data-testid="worklist-item" data-kind={item.kind} data-severity={item.severity}>
    <span className="worklist-icon" aria-hidden><Icon size={16} strokeWidth={1.75} /></span>
    <div className="min-w-0">
      <p className="break-words text-[13.5px] font-medium leading-5 text-text-primary">{item.title}</p>
      {item.detail && <p className="mt-0.5 break-words text-xs leading-5 text-text-secondary">{item.detail}</p>}
      <p className="mt-0.5 text-[11px] text-text-tertiary">{[item.by === 'assistant' && (item.kind === 'approval' ? 'Drafted by the assistant' : 'From the assistant'), ago(item.at)].filter(Boolean).join(' · ')}
        {item.at && <span className="sr-only"> ({new Date(item.at).toLocaleString()})</span>}</p>
    </div>
    <div className="worklist-actions">
      {action?.type === 'decide' && toggle('Review')}
      {action?.type === 'reply' && toggle('Reply')}
      {action?.type === 'answer' && toggle('Answer')}
      {action?.type === 'send_request' && toggle('Send request')}
      {action?.type === 'acknowledge' && <button type="button" className={workButton} disabled={busy}
        onClick={() => void run(() => acknowledgeSignal(action.signal_id), `Acknowledged: ${item.title}. It stays open on the Signals page until a case is opened or it is dismissed.`)}>
        {busy && <Loader2 size={13} className="animate-spin" />}Acknowledge</button>}
      {item.href && <Link href={item.href} className={group === 'needs_you' && !action ? primaryButton : workButton}>Open<ArrowRight size={13} /></Link>}
    </div>
    {open && action?.type === 'decide' && item.proposal && <Decision item={item} busy={busy} error={error}
      onDecide={(decision, comment) => void run(() => decideProposal(action, decision, comment), decision === 'approved'
        ? `Approved: ${item.proposal!.action} · ${item.proposal!.target}. Your approval is recorded; carrying it out is a separate step with its own receipt.`
        : `Declined: ${item.proposal!.action} · ${item.proposal!.target}. ${item.proposal!.proposed_by === 'the assistant' ? 'The assistant' : item.proposal!.proposed_by} will see your reason.`)} />}
    {open && action?.type === 'reply' && <ReplyForm busy={busy} error={error} onSend={text => void run(() => answerRequest(action, text), `Reply sent. ${item.title.split(' asks:')[0]} will see it in their list.`)} />}
    {open && action?.type === 'answer' && <div className="worklist-panel">
      <QuestionCard questions={action.questions.length ? action.questions : ['What should the assistant know to continue?']} disabled={busy}
        onAnswer={text => void run(() => answerAssistant(action, text), 'Answer sent. The assistant is continuing; its result will appear here when it is done.')} />
      {error && <p role="alert" className="mt-2 text-xs text-status-warning">{error}</p>}</div>}
    {open && action?.type === 'send_request' && <SendForm action={action} siteId={siteId} busy={busy} error={error}
      onSend={(body, name) => void run(() => sendDraftedRequest(action, body), `Request sent to ${name}. They are notified, and their reply will appear here.`)} />}
    {!open && error && <p role="alert" className="worklist-panel text-xs text-status-warning">{error}</p>}
  </li>;
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return <div className="min-w-0"><dt className="text-[11px] font-medium uppercase tracking-wide text-text-tertiary">{label}</dt><dd className="mt-0.5 break-words text-xs leading-5 text-text-primary">{children}</dd></div>;
}

const DECLINE_REASONS = ['The evidence does not support this yet.', 'More data is needed first.', 'The target or scope is wrong.'];

/** Everything the proposal states, then the decision. Declining needs a reason; approving records a decision and carries nothing out. */
function Decision({ item, busy, error, onDecide }: { item: WorkItem; busy: boolean; error: string; onDecide: (decision: 'approved' | 'rejected', comment: string) => void }) {
  const [comment, setComment] = useState(''), [asked, setAsked] = useState(false);
  const p = item.proposal!, action = item.action as { recent_sign_in: boolean };
  function submit(e: FormEvent, decision: 'approved' | 'rejected') {
    e.preventDefault();
    if (decision === 'rejected' && !comment.trim()) { setAsked(true); return; }
    onDecide(decision, comment.trim());
  }
  return <form className="worklist-panel" aria-label={`Decide: ${p.action} · ${p.target}`} onSubmit={e => submit(e, 'approved')}>
    <dl className="grid gap-3 sm:grid-cols-2">
      <Fact label="Proposed action">{p.action} · {p.target}{p.system ? ` (in ${p.system})` : ''}</Fact>
      <Fact label="Proposed by">{p.proposed_by}</Fact>
      <Fact label="Why">{p.rationale}</Fact>
      <Fact label="Expected result">{p.expected_result}</Fact>
      {p.follow_up_measure && <Fact label="How it will be checked afterwards">{p.follow_up_measure}</Fact>}
      <Fact label="Rests on">{p.rests_on}</Fact>
      {p.result_says && <div className="sm:col-span-2"><Fact label="What the cited result says"><span className="whitespace-pre-line">{p.result_says}</span></Fact></div>}
      <Fact label="Must be approved by">{p.approvers} · {p.risk} risk</Fact>
      {!!p.constraints.length && <Fact label="Conditions">{p.constraints.join(' ')}</Fact>}
    </dl>
    <label className="mt-3 block text-xs text-text-secondary">Your reason (needed to decline)
      <textarea aria-label="Reason" className={`${field} min-h-[64px] leading-5`} maxLength={1000} value={comment} onChange={e => { setComment(e.target.value); setAsked(false); }} /></label>
    {/* Disagreeing must not cost more effort than agreeing, or people stop disagreeing. */}
    <div className="mt-2 flex flex-wrap items-center gap-1.5" role="group" aria-label="Common reasons to decline"><span className="text-[11px] text-text-tertiary">Common reasons:</span>
      {DECLINE_REASONS.map(reason => <button key={reason} type="button" className="rounded-pill border border-border-strong bg-surface px-2 py-0.5 text-[11px] text-text-secondary hover:bg-surface-secondary"
        onClick={() => { setComment(reason); setAsked(false); }}>{reason}</button>)}</div>
    {asked && <p role="alert" className="mt-1 text-xs text-status-warning">Give a reason so the person who proposed this knows what to change.</p>}
    <p className="mt-2 text-[11px] leading-5 text-text-tertiary">Approving records your decision on exactly this version. It does not carry the action out.
      {action.recent_sign_in ? ' Because of its risk, this approval needs a sign-in from the last 15 minutes.' : ''}</p>
    {error && <p role="alert" className="mt-2 text-xs text-status-warning">{error}</p>}
    <div className="mt-3 flex flex-wrap gap-2">
      <button type="submit" className={primaryButton} disabled={busy}>{busy && <Loader2 size={13} className="animate-spin" />}Approve</button>
      <button type="button" className={workButton} disabled={busy} onClick={e => submit(e, 'rejected')}>Decline</button>
    </div>
  </form>;
}

/** The request drafted from what is missing. The person chooses who to ask and may change every word before it is sent. */
function SendForm({ action, siteId, busy, error, onSend }: { action: SendRequest; siteId: string; busy: boolean; error: string;
  onSend: (body: { owner_id: string; title: string; description: string }, name: string) => void }) {
  const [people, setPeople] = useState<Person[] | null>(null), [owner, setOwner] = useState('');
  const [title, setTitle] = useState(action.title), [description, setDescription] = useState(action.description);
  useEffect(() => { let alive = true; listPeople(siteId).then(found => { if (alive) setPeople(found); }).catch(() => { if (alive) setPeople([]); }); return () => { alive = false; }; }, [siteId]);
  const ready = !!owner.trim() && !!title.trim() && !!description.trim();
  return <form className="worklist-panel" aria-label="Send this request" onSubmit={e => { e.preventDefault(); if (ready) onSend({ owner_id: owner.trim(), title: title.trim(), description: description.trim() }, people?.find(p => p.id === owner)?.label ?? owner.trim()); }}>
    <p className="text-xs leading-5 text-text-secondary">Drafted from what the check found missing. Change anything before it is sent; nothing has been sent yet.</p>
    <label className="mt-3 block text-xs text-text-secondary">Who to ask{people === null ? <span className={`${field} text-text-tertiary`}>Reading who can be asked…</span>
      : people.length ? <select aria-label="Who to ask" className={field} value={owner} required onChange={e => setOwner(e.target.value)}><option value="">Choose a colleague…</option>
        {people.map(person => <option key={person.id} value={person.id}>{person.label}</option>)}</select>
      : <input aria-label="Who to ask" className={field} value={owner} maxLength={160} required placeholder="Their sign-in name" onChange={e => setOwner(e.target.value)} />}</label>
    <label className="mt-3 block text-xs text-text-secondary">Subject<input aria-label="Subject" className={field} value={title} maxLength={160} onChange={e => setTitle(e.target.value)} /></label>
    <label className="mt-3 block text-xs text-text-secondary">Request<textarea aria-label="Request" className={`${field} min-h-[132px] leading-5`} value={description} maxLength={2000} onChange={e => setDescription(e.target.value)} /></label>
    {error && <p role="alert" className="mt-2 text-xs text-status-warning">{error}</p>}
    <div className="mt-3"><button type="submit" className={primaryButton} disabled={busy || !ready}>{busy && <Loader2 size={13} className="animate-spin" />}Send request</button></div>
  </form>;
}

function ReplyForm({ busy, error, onSend }: { busy: boolean; error: string; onSend: (text: string) => void }) {
  const [text, setText] = useState('');
  return <form className="worklist-panel" aria-label="Reply to this request" onSubmit={e => { e.preventDefault(); if (text.trim()) onSend(text.trim()); }}>
    <label className="block text-xs text-text-secondary">Your reply
      <textarea aria-label="Your reply" autoFocus className={`${field} min-h-[80px] leading-5`} maxLength={2000} value={text} onChange={e => setText(e.target.value)} /></label>
    <p className="mt-2 text-[11px] leading-5 text-text-tertiary">Your reply is recorded with your name and the time, and cannot be changed afterwards.</p>
    {error && <p role="alert" className="mt-2 text-xs text-status-warning">{error}</p>}
    <div className="mt-3"><button type="submit" className={primaryButton} disabled={busy || !text.trim()}>{busy && <Loader2 size={13} className="animate-spin" />}Send reply</button></div>
  </form>;
}
