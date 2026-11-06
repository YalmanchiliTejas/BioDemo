'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { Archive, ArrowUp, BookOpen, PanelLeftClose, FlaskConical, History, MoreHorizontal, Pencil, Plus, RotateCcw, ChevronDown, Workflow, Check, Circle, Loader2, Paperclip, X, ArrowUpRight, ShieldCheck } from 'lucide-react';
import { Markdown } from './Markdown';
import { QuestionCard } from './QuestionCard';
import { SignalCard } from './SignalCard';
import { InvestigationProposal } from './InvestigationProposal';
import { processRequest } from '@/lib/process-api';
import { cached } from '@/lib/cache';
import { useOptionalCompanion, type AttachedDataset, type DisplayContext } from '@/lib/companion-context';
import { usePathname } from 'next/navigation';
import { SCREENS } from '@/lib/routes';
import { AnalysisArtifact, type ArtifactRef } from './AnalysisArtifact';
import { BioprocessArtifact } from './BioprocessArtifact';
import { projectThread } from '@/lib/work-results';
import { WorkspaceArtifact } from './WorkspaceArtifact';
import { DemoDeviationsArtifact } from './DemoDeviationsArtifact';
import { AssistantResponsibility, type Responsibility } from './AssistantResponsibility';

type Step = { node_id: string; title: string; task_kind: string; depends_on: string[]; status: string; issues: string[]; started_at?: string | null; ended_at?: string | null };
const seconds = (a?: string | null, b?: string | null) => a && b ? Math.max(0, (new Date(b).getTime() - new Date(a).getTime()) / 1000) : null;
type Grounding = { status: string; unsupported_numbers?: number[]; derived_numbers?: number[]; claims?: { text: string; kind?: string; source_id: string; quote: string; verified: boolean; problem: string | null }[] };
// Host-verified provenance of the reply's factual statements (quote exists in an inspected source).
function GroundingNote({ g }: { g: Grounding }) {
  if (g.status === 'no_claims') return null;
  const claims = g.claims ?? [], unverified = claims.filter(c => !c.verified), numbers = g.unsupported_numbers ?? [];
  const ok = g.status === 'grounded';
  const label = g.status === 'evaluation_unavailable' ? 'Source check unavailable for this reply'
    : ok ? `${claims.length} statement${claims.length === 1 ? '' : 's'} traced to inspected sources`
    : `${unverified.length + numbers.length} item${unverified.length + numbers.length === 1 ? '' : 's'} not traced to an inspected source — verify before relying on ${unverified.length + numbers.length === 1 ? 'it' : 'them'}`;
  return <details className={`mt-3 text-xs ${ok ? 'text-text-tertiary' : 'rounded-control bg-status-warning-bg px-3 py-2 text-text-secondary'}`}>
    <summary className="cursor-pointer">{label}</summary>
    <ul className="mt-2 space-y-2">
      {claims.map((c, i) => <li key={i}><span className={c.verified ? 'text-status-success' : 'text-status-warning'}>{c.verified ? 'Quoted' : 'Not found'}{c.kind === 'derived' ? ' · calculated' : ''}</span> · {c.text}<br /><span className="text-text-tertiary">“{c.quote}” — {c.source_id}</span></li>)}
      {numbers.map(n => <li key={n}><span className="text-status-warning">Number not in any inspected source</span> · {n}</li>)}
    </ul>
  </details>;
}
type Turn = { origin?: string; triage_signal_id?: string | null; responsibility_objective?: string; display_context?: DisplayContext | null; id: string; user_text: string; status: string; reply: string | null; questions: string[]; system_message?: string; issues: string[]; artifacts: ArtifactRef[]; steps?: Step[]; elapsed_seconds?: number; basis_status?: string; grounding?: Grounding | null; context_used?: ContextUsed | null; held_back?: string[]; gateway_runs: { route?: { unqualified?: boolean } | null; [key: string]: unknown }[] };
type ContextUsed = { rules: { rule_id: string; scope: string; text: string }[]; corrections: { correction_id: string; text: string }[]; earlier_corrections: { correction_id: string; text: string }[] };
type Thread = { id: string; site_id?: string; mission_id?: string; revision: number; title: string; turns: Turn[]; turn_ids: string[]; demo_enabled: boolean; source_ids: string[]; dataset_ids?: string[]; responsibility?: Responsibility | null; mission_status?: string };
type PublishedDataset = { id: string; cmo: string; delivery_name: string | null; measurements: number; batches: string[] };
const datasetLabel = (d: PublishedDataset) => d.delivery_name ?? d.cmo;
type Recent = { id: string; title: string; updated_at?: string; archived?: boolean };
type Source = { id: string; audience: string; provenance: string };
const storageKey = 'biodemo.engineering.conversation.v1';
const EXAMPLES = [
  { label: 'Freeze-drying transfer', prompt: 'Use the published and reconstructed freeze-drying example. Assess transferring the source process to the receiving equipment, choose an appropriate registered model, simulate current conditions, and show constraints with charts and a 3D vial review. Clearly distinguish published values from assumptions.' },
  { label: 'Penicillin batch decision', prompt: 'Use the simulated PenSim demo case NC-03ce17b48c95. We are 60 h into the batch and air is limited to 1.0×. Which operating plan should we run for the rest of the batch, and what will penicillin and dissolved oxygen look like?' },
  { label: 'Antibody recipe transfer', prompt: 'Use the simulated SMPL antibody demo case NC-09861ef65be7. Before the receiving run starts, which flow and nutrient plan stays within the receiving limits and gives the most antibody? Compare the current plan with the alternatives.' },
];
function friendlyNote(turn: Turn): string | null {
  if (turn.status === 'agent_unavailable') return 'I couldn’t reach the model just now, so nothing has run yet. Your message is saved, so you can try again in a moment.';
  if (turn.status === 'blocked') return turn.reply ? 'I stopped before finishing. What I found so far is above, and Details shows where it stopped.' : 'I got stuck before I could answer. Details shows where it stopped. Try again, or tell me a bit more.';
  if (turn.status === 'completed') return null; // results speak for themselves
  return turn.system_message ?? null;
}
const active = (turn?: Turn) => !!turn && ['queued', 'running'].includes(turn.status);
const action = 'inline-flex items-center gap-2 rounded-control px-3 py-2 text-xs text-text-secondary hover:bg-surface-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-teal disabled:opacity-40';

/** Corrections are kept by the owner's mission and carried into later conversations (shown as "Built on"). */
function CorrectAnswer({ missionId }: { missionId: string }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [state, setState] = useState<'idle' | 'busy' | 'saved'>('idle');
  const [error, setError] = useState('');
  if (state === 'saved') return <p role="status" className="mt-2 text-xs text-status-success">Correction saved. I’ll keep it in mind here and in your future conversations.</p>;
  if (!open) return <button type="button" onClick={() => setOpen(true)} className="mt-2 text-xs text-text-tertiary underline-offset-2 hover:text-text-secondary hover:underline">Correct this</button>;
  async function save(e: React.FormEvent) {
    e.preventDefault(); if (!text.trim()) return; setState('busy'); setError('');
    try { await processRequest(`/v1/missions/${encodeURIComponent(missionId)}/corrections`, { text: text.trim() }); setState('saved'); }
    catch (err) { setError((err as Error).message); setState('idle'); }
  }
  return <form onSubmit={save} className="mt-2 rounded-card border border-border-hairline bg-surface p-3 text-xs">
    <label htmlFor={`correct-${missionId}`} className="font-medium text-text-secondary">What’s wrong or missing?</label>
    <textarea id={`correct-${missionId}`} autoFocus rows={2} value={text} onChange={e => setText(e.target.value)} maxLength={2000}
      placeholder="e.g. Valve V-12 was inspected on 2 Nov and ruled out" className="mt-1.5 block w-full rounded-control border border-border-strong p-2 text-sm outline-none focus:border-brand-teal" />
    {error && <p role="alert" className="mt-1 text-status-critical">{error}</p>}
    <div className="mt-2 flex gap-2"><button type="submit" disabled={!text.trim() || state === 'busy'} className="rounded-control bg-brand-teal px-3 py-1.5 font-medium text-white disabled:opacity-40">Save correction</button>
      <button type="button" onClick={() => setOpen(false)} className="px-2 py-1.5 text-text-secondary">Cancel</button></div>
  </form>;
}

/** What this answer built on beyond the message itself: standing rules, carried-over corrections,
 *  identifier links followed and precedents checked. Recorded when the prompt was built, not inferred. */
function DrewOn({ turn }: { turn: Turn }) {
  const used = turn.context_used;
  const links = turn.artifacts.filter(a => a.title.startsWith('Linked records'));
  const precedents = turn.artifacts.filter(a => a.title === 'Similar closed cases');
  const corrections = [...(used?.corrections ?? []), ...(used?.earlier_corrections ?? [])];
  const chips: [string, number][] = ([['rule', used?.rules.length ?? 0], ['correction', corrections.length],
    ['link lookup', links.length], ['precedent search', precedents.length]] as [string, number][]).filter(([, n]) => n > 0);
  if (!chips.length) return null;
  return <details className="group mt-3 text-xs">
    <summary className="flex cursor-pointer list-none flex-wrap items-center gap-1.5 text-text-tertiary hover:text-text-secondary">
      <BookOpen size={13} className="text-brand-teal" />Built on
      {chips.map(([label, n]) => <span key={label} className="rounded-pill border border-border-hairline bg-surface px-2 py-0.5 text-text-secondary">{n} {label}{n === 1 ? '' : 's'}</span>)}
      <ChevronDown size={12} className="transition-transform group-open:rotate-180" /></summary>
    <div className="mt-2 space-y-3 rounded-card bg-surface p-4 shadow-[0_1px_3px_rgba(16,24,40,0.06)]">
      {!!used?.rules.length && <div><p className="font-medium text-text-secondary">Standing rules it followed</p>
        <ul className="mt-1 space-y-1">{used.rules.map(r => <li key={r.rule_id}>{r.text} <span className="text-text-tertiary">· {r.scope} rule</span></li>)}</ul>
        <a href="/settings/assistant-rules/" className="mt-1 inline-block text-brand-teal underline">Manage rules</a></div>}
      {!!corrections.length && <div><p className="font-medium text-text-secondary">Corrections it kept honouring</p>
        <ul className="mt-1 space-y-1">{used?.corrections.map(c => <li key={c.correction_id}>{c.text} <span className="text-text-tertiary">· this conversation</span></li>)}
          {used?.earlier_corrections.map(c => <li key={c.correction_id}>{c.text} <span className="text-text-tertiary">· from an earlier conversation</span></li>)}</ul></div>}
      {!!(links.length || precedents.length) && <p className="text-text-secondary">It also followed {links.length ? `identifier links (${links.map(l => l.title.replace('Linked records · ', '')).join(', ')})` : ''}{links.length && precedents.length ? ' and ' : ''}{precedents.length ? 'searched closed cases for precedents' : ''}. Details are under “How I worked this out”.</p>}
    </div>
  </details>;
}

/** Everything the assistant did to reach its answer, folded into one place: steps, records it checked
 *  and technical details. Open while it is working; one quiet line afterwards. */
function WorkLog({ turn, threadId, running }: { turn: Turn; threadId: string; running: boolean }) {
  const reads = turn.artifacts.filter(a => a.kind === 'assistant_workspace_result');
  const steps = turn.steps ?? [];
  if (!steps.length && !reads.length && !turn.gateway_runs.length) return null;
  const parts = [steps.length && `${steps.length} step${steps.length === 1 ? '' : 's'}`, reads.length && `${reads.length} record lookup${reads.length === 1 ? '' : 's'}`,
    turn.elapsed_seconds != null && `${turn.elapsed_seconds.toFixed(1)} s`].filter(Boolean).join(' · ');
  return <details className="group mt-4 text-xs" open={running}>
    <summary className="flex cursor-pointer list-none items-center gap-2 text-text-tertiary hover:text-text-secondary">
      <Workflow size={14} />{running ? `Working${steps.find(x => x.status !== 'completed') ? ` · ${steps.find(x => x.status !== 'completed')!.title}` : ''}` : 'How I worked this out'}{parts && <span className="text-text-muted">· {parts}</span>}<ChevronDown size={12} className="transition-transform group-open:rotate-180" /></summary>
    <div className="mt-3 space-y-3 rounded-card bg-surface p-4 shadow-[0_1px_3px_rgba(16,24,40,0.06)]">
      {!!steps.length && <ol className="space-y-2">{steps.map(step => <li className="flex gap-2.5" key={step.node_id}>
        {step.status === 'completed' ? <Check size={14} className="mt-0.5 shrink-0 text-status-success" /> : running && step.status !== 'blocked' ? <Loader2 size={14} className="mt-0.5 shrink-0 text-brand-teal motion-safe:animate-spin" /> : <Circle size={14} className={`mt-0.5 shrink-0 ${step.status === 'blocked' ? 'text-status-critical' : 'text-text-muted'}`} />}
        <div><p className="text-text-primary">{step.title}
          {step.status === 'completed' && seconds(step.started_at, step.ended_at) != null && <span className="ml-2 text-text-tertiary">{seconds(step.started_at, step.ended_at)!.toFixed(1)} s</span>}
          {step.status !== 'completed' && <span className="ml-2 text-text-tertiary">{running && step === steps.find(x => x.status !== 'completed') ? 'working on this now' : step.status.replaceAll('_', ' ')}</span>}</p>
          {step.issues.map(issue => <p key={issue} className="mt-1 text-status-critical">{issue}</p>)}</div></li>)}</ol>}
      {!!reads.length && <div className="space-y-1 border-t border-border-hairline pt-3 first:border-0 first:pt-0"><p className="mb-1 font-medium text-text-secondary">Records checked</p>
        {reads.map(a => <WorkspaceArtifact key={a.id} threadId={threadId} artifact={a} />)}</div>}
      {!!turn.gateway_runs.length && <details className="border-t border-border-hairline pt-3 text-text-tertiary"><summary className="cursor-pointer">Technical details (for audit)</summary>
        {turn.system_message && <p className="mt-2">{turn.system_message}</p>}
        <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-all rounded-card bg-surface-secondary p-3">{JSON.stringify({ gateway_runs: turn.gateway_runs, issues: turn.issues, artifacts: turn.artifacts }, null, 2)}</pre></details>}
    </div>
  </details>;
}

type ListActions = { onOpen: (id: string) => void; onNew: () => void; onRename: (id: string, title: string) => Promise<void>;
  onArchive: (id: string, archived: boolean) => Promise<void>; loadArchived: () => Promise<Recent[]> };

function groupLabel(iso?: string) {
  if (!iso) return 'Older';
  const day = 86400000, start = new Date(); start.setHours(0, 0, 0, 0);
  const t = new Date(iso).getTime();
  return t >= start.getTime() ? 'Today' : t >= start.getTime() - day ? 'Yesterday' : t >= start.getTime() - 6 * day ? 'Previous 7 days' : 'Older';
}

function ConversationItem({ item, current, actions, archived }: { item: Recent; current: boolean; actions: ListActions; archived?: boolean }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [menu, setMenu] = useState(false);
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  async function save() {
    if (saving.current) return; // Enter saves, then the input's blur fires: one request only
    saving.current = true;
    const next = title.trim();
    if (!next || next === item.title) { setEditing(false); setTitle(item.title); saving.current = false; return; }
    setBusy(true); try { await actions.onRename(item.id, next); setEditing(false); } finally { setBusy(false); saving.current = false; }
  }
  if (editing) return <li><input autoFocus onFocus={() => { saving.current = false; }} value={title} maxLength={90} disabled={busy} aria-label="Conversation name"
    onChange={e => setTitle(e.target.value)} onBlur={() => void save()}
    onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); void save(); } if (e.key === 'Escape') { setEditing(false); setTitle(item.title); } }}
    className="w-full rounded-control border border-brand-teal bg-surface px-2 py-1.5 text-xs outline-none" /></li>;
  return <li className="group relative">
    <button type="button" onClick={() => archived ? undefined : actions.onOpen(item.id)} aria-current={current ? 'page' : undefined} title={item.title}
      className={`block w-full truncate rounded-control py-2 pl-2 pr-8 text-left text-xs ${current ? 'bg-brand-teal-light/60 font-medium text-text-primary' : 'text-text-secondary hover:bg-surface-secondary'} ${archived ? 'cursor-default' : ''}`}>{item.title || 'Untitled conversation'}</button>
    {archived
      ? <button type="button" onClick={() => void actions.onArchive(item.id, false)} className="absolute right-1 top-1/2 -translate-y-1/2 rounded px-1.5 py-1 text-[11px] text-brand-teal hover:bg-surface-secondary">Restore</button>
      : <button type="button" aria-label={`Manage ${item.title}`} aria-expanded={menu} onClick={() => setMenu(m => !m)}
          className={`absolute right-1 top-1/2 -translate-y-1/2 rounded p-1 text-text-tertiary hover:bg-surface hover:text-text-primary focus:opacity-100 ${menu || current ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}><MoreHorizontal size={14} /></button>}
    {menu && <>
      <button type="button" aria-label="Close menu" className="fixed inset-0 z-30 cursor-default" onClick={() => setMenu(false)} />
      <div role="menu" className="absolute right-1 top-full z-40 w-36 rounded-card border border-border-hairline bg-surface p-1 shadow-lg">
        <button role="menuitem" type="button" onClick={() => { setMenu(false); setEditing(true); }} className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-surface-secondary"><Pencil size={13} />Rename</button>
        <button role="menuitem" type="button" onClick={() => { setMenu(false); void actions.onArchive(item.id, true); }} className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-surface-secondary"><Archive size={13} />Archive</button>
      </div></>}
  </li>;
}

function ConversationList({ recent, currentId, actions }: { recent: Recent[]; currentId: string | null; actions: ListActions }) {
  const [filter, setFilter] = useState('');
  const [archived, setArchived] = useState<Recent[] | null>(null);
  const shown = filter.trim() ? recent.filter(r => r.title.toLowerCase().includes(filter.trim().toLowerCase())) : recent;
  const groups: [string, Recent[]][] = [];
  for (const r of shown) { const label = groupLabel(r.updated_at); const g = groups.find(([l]) => l === label); if (g) g[1].push(r); else groups.push([label, [r]]); }
  return <nav aria-label="Conversation history" className="flex h-full flex-col">
    <button type="button" onClick={actions.onNew} className="flex w-full items-center gap-2 rounded-control bg-brand-teal px-3 py-2 text-xs font-medium text-white hover:bg-brand-teal-dark"><Plus size={14} />New conversation</button>
    {recent.length > 6 && <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Find a conversation" aria-label="Find a conversation"
      className="mt-3 w-full rounded-control border border-border-hairline bg-surface px-2.5 py-1.5 text-xs outline-none focus:border-brand-teal" />}
    <div className="mt-3 min-h-0 flex-1 overflow-y-auto">
      {groups.map(([label, items]) => <section key={label} className="mb-3">
        <p className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">{label}</p>
        <ul className="space-y-0.5">{items.map(r => <ConversationItem key={r.id} item={r} current={r.id === currentId} actions={actions} />)}</ul>
      </section>)}
      {!recent.length && <p className="px-2 text-xs text-text-tertiary">Your conversations will be saved here.</p>}
      {!!recent.length && !shown.length && <p className="px-2 text-xs text-text-tertiary">No conversation matches “{filter}”.</p>}
      <button type="button" onClick={async () => setArchived(archived ? null : await actions.loadArchived())}
        className="mt-2 flex items-center gap-1.5 px-2 text-[11px] text-text-tertiary hover:text-text-secondary"><Archive size={12} />{archived ? 'Hide archived' : 'Archived'}</button>
      {archived && <ul className="mt-1 space-y-0.5">{archived.length ? archived.map(r => <ConversationItem key={r.id} item={r} current={false} archived
        actions={{ ...actions, onArchive: async (id, value) => { await actions.onArchive(id, value); setArchived(a => a?.filter(x => x.id !== id) ?? null); } }} />)
        : <li className="px-2 py-1 text-[11px] text-text-tertiary">Nothing archived.</li>}</ul>}
    </div>
  </nav>;
}

export function EngineeringChat({ companion = false, compact = false }: { companion?: boolean; compact?: boolean }) {
  const companionState = useOptionalCompanion();
  const selection = companionState?.selection;
  const pending = companionState?.datasets ?? [];
  const pathname = usePathname().replace(/\/$/, '');
  const pageName = SCREENS.find(s => s.href === pathname)?.title ?? 'Current workspace';
  // Last known data renders immediately on navigation; the mount effect refetches it.
  const [thread, setThread] = useState<Thread | null>(() => {
    try { const saved = localStorage.getItem(storageKey); return saved ? cached<Thread>(`/v1/process-model/conversations/${saved}`) ?? null : null; }
    catch { return null; }
  });
  const [recent, setRecent] = useState<Recent[]>(() => cached<{ conversations: Recent[] }>('/v1/process-model/conversations')?.conversations ?? []);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [stoppingTurns, setStoppingTurns] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState('');
  const [sources, setSources] = useState<Source[]>(() => cached<{ sources: Source[] }>('/v1/process-model/conversation-sources')?.sources ?? []);
  const [published, setPublished] = useState<PublishedDataset[]>(() => cached<{ datasets: PublishedDataset[] }>('/v1/cmo-datasets')?.datasets ?? []);
  const [attachment, setAttachment] = useState('');
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [demoConsent, setDemoConsent] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  // Wide screens: the history panel can be hidden; the choice is remembered like the navigation's.
  const [historyHidden, setHistoryHiddenState] = useState(false);
  useEffect(() => { try { setHistoryHiddenState(localStorage.getItem('biodemo.history.v1') === 'hidden'); } catch { /* optional */ } }, []);
  const setHistoryHidden = (hidden: boolean) => {
    setHistoryHiddenState(hidden);
    try { localStorage.setItem('biodemo.history.v1', hidden ? 'hidden' : 'shown'); } catch { /* optional */ }
  };
  const toggleHistory = () => {
    if (!compact && historyHidden && window.matchMedia('(min-width: 768px)').matches) setHistoryHidden(false);
    else setHistoryOpen(o => !o);
  };
  const current = useRef<string | null>(null);
  const inFlight = useRef(false);
  const end = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const last = thread?.turns.at(-1);
  const busy = sending || active(last) || (!!last && stoppingTurns.has(last.id));
  const structuredWork = useMemo(() => new Set(thread ? projectThread(thread).map(r => r.id) : []), [thread]);

  function adopt(data: Thread) {
    current.current = data.id; setThread(data);
    try { localStorage.setItem(storageKey, data.id); } catch { /* Work remains on the server. */ }
  }
  async function open(id: string) {
    current.current = id; setError('');
    try {
      const data = await processRequest<Thread>(`/v1/process-model/conversations/${id}`);
      if (current.current === id) adopt(data);
    } catch (e) { if (current.current === id) setError(String(e)); }
  }
  useEffect(() => {
    let saved: string | null = null;
    try { saved = localStorage.getItem(storageKey); } catch { /* Storage is optional. */ }
    // A link such as /home/?conversation=<id> (e.g. "Open the triage" on a signal) opens that conversation.
    const linked = typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('conversation') : null;
    if (linked) saved = linked;
    if (saved) void open(saved);
    processRequest<{ conversations: Recent[] }>('/v1/process-model/conversations')
      .then(r => setRecent(r.conversations)).catch(e => setError(String(e)));
    return () => { current.current = null; };
  // Restore once; subsequent selection is explicit.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!thread || (!active(last) && (!thread.responsibility?.enabled || thread.mission_status !== 'active'))) return;
    const id = thread.id;
    let mounted = true;
    const timer = window.setInterval(() => {
      processRequest<Thread>(`/v1/process-model/conversations/${id}`)
        .then(data => { if (mounted && current.current === id) setThread(data); })
        .catch(e => { if (mounted) setError(String(e)); });
    }, active(last) ? 1000 : 5000);
    return () => { mounted = false; window.clearInterval(timer); };
  }, [thread?.id, last?.status, thread?.responsibility?.enabled, thread?.mission_status]);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'auto', block: 'nearest' });
  }, [thread?.turns.length, last?.status]);
  useEffect(() => {
    if (composer.current) {
      composer.current.style.height = 'auto';
      composer.current.style.height = `${Math.min(180, composer.current.scrollHeight)}px`;
    }
  }, [draft]);

  useEffect(() => {
    companionState?.setBusy(busy);
  }, [busy, companionState?.setBusy]);
  useEffect(() => {
    if (selection) composer.current?.focus();
  }, [selection]);
  useEffect(() => {
    if (compact && companionState?.open) composer.current?.focus();
  }, [compact, companionState?.open]);

  async function send(text = draft, enableDemo = false) {
    if (!text.trim() || busy || inFlight.current) return;
    inFlight.current = true;
    const sentSelection = selection;
    setSending(true); setError('');
    try {
      let target = thread;
      if (!target) {
        target = await processRequest<Thread>('/v1/process-model/conversations', {});
        adopt(target);
      }
      const id = target.id;
      const data = await processRequest<Thread>(`/v1/process-model/conversations/${id}/messages`, {
        text: text.trim(), expected_revision: target.revision, enable_demo: enableDemo || demoConsent,
        source_ids: attachment ? [attachment] : [],
        dataset_ids: pending.map(d => d.id),
        ...(sentSelection ? { display_context: sentSelection } : {}),
      });
      if (current.current === id) { adopt(data); setDraft(''); setAttachment(''); companionState?.removeDataset(); if (sentSelection) companionState?.clearSelection(sentSelection); }
      const updated = await processRequest<{ conversations: Recent[] }>('/v1/process-model/conversations');
      setRecent(updated.conversations);
    } catch (e) {
      setError(String(e));
      if (current.current) await open(current.current);
    } finally { inFlight.current = false; setSending(false); }
  }
  async function retry() {
    if (!thread || sending) return;
    setSending(true); setError('');
    const id = thread.id;
    try {
      // The persisted turn is resumed; this creates no duplicate user message.
      const queued = await processRequest<Thread>(`/v1/process-model/conversations/${id}/retry`, {});
      if (current.current === id) adopt(queued);
      if (current.current === id) {
        const data = await processRequest<Thread>(`/v1/process-model/conversations/${id}`);
        if (current.current === id) adopt(data);
      }
    } catch (e) { setError(String(e)); }
    finally { setSending(false); }
  }
  async function stop() {
    if (!thread || !last || stoppingTurns.has(last.id)) return;
    const id = thread.id;
    const turnId = last.id;
    setStoppingTurns(value => new Set(value).add(turnId)); setError('');
    try {
      const data = await processRequest<Thread>(`/v1/process-model/conversations/${id}/stop`, {});
      if (current.current === id) adopt(data);
    } catch (e) { if (current.current === id) setError(String(e)); }
    finally { setStoppingTurns(value => { const remaining = new Set(value); remaining.delete(turnId); return remaining; }); }
  }
  function newConversation() {
    current.current = null; setThread(null); setDraft(''); setAttachment(''); setDemoConsent(false); setError('');
    try { localStorage.removeItem(storageKey); } catch { /* Storage is optional. */ }
    companionState?.clearSelection(); composer.current?.focus();
  }
  async function loadSources() {
    setSourcesOpen(!sourcesOpen);
    if (!sourcesOpen) {
      try { setSources((await processRequest<{ sources: Source[] }>('/v1/process-model/conversation-sources')).sources); }
      catch (e) { setError(String(e)); }
      try { setPublished((await processRequest<{ datasets: PublishedDataset[] }>('/v1/cmo-datasets')).datasets); }
      catch { setPublished([]); }
    }
  }

  async function refreshRecent() {
    try { setRecent((await processRequest<{ conversations: Recent[] }>('/v1/process-model/conversations')).conversations); }
    catch (e) { setError(String(e)); }
  }
  const listActions: ListActions = {
    onOpen: id => { setHistoryOpen(false); void open(id); },
    onNew: () => { setHistoryOpen(false); newConversation(); },
    onRename: async (id, title) => {
      try { const data = await processRequest<Thread>(`/v1/process-model/conversations/${id}/update`, { title }); if (current.current === id) adopt(data); await refreshRecent(); }
      catch (e) { setError(String(e)); }
    },
    onArchive: async (id, archived) => {
      try { await processRequest<Thread>(`/v1/process-model/conversations/${id}/update`, { archived }); if (archived && current.current === id) newConversation(); await refreshRecent(); }
      catch (e) { setError(String(e)); }
    },
    loadArchived: async () => {
      try { return (await processRequest<{ conversations: Recent[] }>('/v1/process-model/conversations?archived=true')).conversations; }
      catch (e) { setError(String(e)); return []; }
    },
  };
  const history = <ConversationList recent={recent} currentId={thread?.id ?? null} actions={listActions} />;

  return <div className={`flex w-full ${compact ? 'min-h-full' : 'min-h-[calc(100dvh-7rem)]'}`} data-testid="engineering-chat">
    {!compact && !historyHidden && <aside className="sticky top-0 hidden max-h-[calc(100dvh-7rem)] w-64 shrink-0 self-start border-r border-border-hairline py-4 pl-2 pr-3 md:flex md:flex-col">
      <button type="button" onClick={() => setHistoryHidden(true)} aria-label="Hide conversation history" title="Hide conversation history"
        className="mb-2 flex items-center gap-1.5 self-end rounded-control px-2 py-1 text-[11px] text-text-tertiary hover:bg-surface-secondary hover:text-text-secondary"><PanelLeftClose size={14} />Hide</button>
      <div className="min-h-0 flex-1">{history}</div>
    </aside>}
    <div className={`mx-auto flex w-full min-w-0 flex-col ${compact ? 'px-4' : 'max-w-4xl px-2 sm:px-8'}`}>
    <header className={`sticky z-20 flex items-center justify-between gap-3 py-3 ${compact ? 'top-0 bg-surface' : '-top-7 bg-canvas'}`}>
      <div className="flex min-w-0 items-center gap-2">
        <span className={`flex items-center ${compact || historyHidden ? '' : 'md:hidden'}`}>
          <button type="button" onClick={toggleHistory} aria-expanded={historyOpen || (!compact && !historyHidden)} aria-label="Conversation history"
            className={action}><History size={15} /><span className={compact ? 'sr-only' : ''}>History</span></button>
          <button type="button" onClick={newConversation} className={action} aria-label="New conversation"><Plus size={16} /><span className={compact ? 'sr-only' : ''}>New</span></button>
        </span>
        {compact ? <p className="max-w-[190px] truncate text-xs text-text-tertiary" title={pageName}>{thread?.title || pageName}</p>
          : <>{companion ? <span className="companion-mark" aria-hidden /> : <FlaskConical size={20} className="text-brand-teal" />}<h1 className="truncate text-sm font-medium text-text-primary">{thread?.title || (companion ? 'Assistant' : 'Process engineering')}</h1></>}
      </div>
      {historyOpen && <>
        <button type="button" aria-label="Close history" className="fixed inset-0 z-20 cursor-default" onClick={() => setHistoryOpen(false)} />
        <div className="absolute left-0 top-full z-30 max-h-[70vh] w-72 overflow-y-auto rounded-card border border-border-hairline bg-surface p-2 shadow-lg">{history}</div>
      </>}
    </header>
    {thread && <AssistantResponsibility key={thread.id} thread={thread} onChange={adopt} />}

    <div className="flex-1 pb-10">
      {!thread?.turns.length && <section className={`mx-auto max-w-2xl ${compact ? 'pb-5 pt-8' : 'pb-8 pt-16 sm:pt-24'}`}>
        <h2 className={`font-medium leading-tight tracking-tight text-text-primary ${compact ? 'text-2xl' : 'text-3xl sm:text-[38px]'}`}>{pending.length ? 'Ask about this delivery.' : selection ? 'Let’s look at this together.' : companion ? 'What are we working on?' : 'What process problem are you working on?'}</h2>
        <p className="mt-4 max-w-lg text-sm leading-6 text-text-secondary">{pending.length ? 'The verified values, their batches and source files are attached below. Ask about trends, gaps or differences between batches.' : selection ? 'Your selection is attached below. Ask a question or describe what you’d like to do.' : companion ? 'Bring a question, explore an idea, or select something in your workspace. We’ll take it from there.' : 'Describe the decision you need to make. The agent will identify the evidence and models needed.'}</p>
      </section>}

      <div role="log" aria-label="Engineering conversation" aria-live="polite" aria-relevant="additions text" className={thread?.turns.length ? 'space-y-8 py-6' : ''}>
        {thread?.turns.map((turn, index) => <article key={turn.id} data-testid="conversation-turn">
          <div className="mb-6 flex justify-end"><div className="min-w-0 max-w-[90%] rounded-2xl rounded-br-sm bg-surface-secondary px-5 py-4 text-sm leading-6 text-text-primary"><span className="sr-only">{turn.origin === 'background' ? 'Background follow-up: ' : 'You: '}</span><p className="whitespace-pre-wrap">{turn.origin === 'background' ? `Background follow-up · ${turn.responsibility_objective}` : turn.user_text}</p>{turn.display_context && <details className="mt-3 border-t border-border-hairline pt-2 text-xs"><summary className="cursor-pointer">{turn.display_context.kind === 'chart' ? 'Chart' : 'Text'} from {turn.display_context.label}</summary><p className="mt-2 text-text-tertiary">Screen snapshot · {turn.display_context.page_path} · {turn.display_context.captured_at}</p><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words font-sans">{turn.display_context.content}</pre></details>}</div></div>
          <div className="flex gap-3 sm:gap-4"><span className="companion-mark mt-1 shrink-0" aria-hidden /><div className="min-w-0 flex-1">
            {turn.triage_signal_id && <SignalCard id={turn.triage_signal_id} />}
            {['stale', 'quarantined'].includes(turn.basis_status ?? '') && <p role="status" className="mb-3 rounded-control bg-status-warning-bg px-4 py-3 text-sm text-text-secondary">Contributing evidence changed or was withdrawn. Rebuild this analysis before using its findings.</p>}
            {turn.gateway_runs.some(r => r.route?.unqualified) && <p className="mb-2 text-xs text-status-warning">Development LLM run · route unqualified · review required</p>}
            {structuredWork.has(turn.id) ? <>
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border-hairline bg-surface p-4"><div><p className="text-sm font-medium">{turn.status === 'blocked' ? 'Saved work needs attention' : 'Your work is ready to inspect'}</p><p className="mt-1 text-xs text-text-tertiary">Chart, source table, checks and next review step.</p></div><Link href={`/workspaces/#${encodeURIComponent(turn.id)}`} className="inline-flex items-center gap-1.5 rounded-control bg-brand-teal px-3 py-2 text-xs font-medium text-white">Open workspace<ArrowUpRight size={14} /></Link></div>
              {turn.reply && <details className="mt-3 text-xs text-text-secondary"><summary className="cursor-pointer">Read the assistant’s explanation</summary><Markdown className="mt-3" text={turn.reply} /></details>}
            </> : turn.reply && <Markdown text={turn.reply} />}
            {turn.grounding && turn.reply && <GroundingNote g={turn.grounding} />}
            <DrewOn turn={turn} />
            {!!turn.held_back?.length && !active(turn) && <div className="mt-3 rounded-card border border-border-hairline bg-surface px-4 py-3 text-xs">
              <p className="text-text-secondary">Not run this turn (a turn runs at most three of these): {turn.held_back.join(' · ')}</p>
              {index === (thread?.turns.length ?? 0) - 1 && <button type="button" disabled={busy} onClick={() => void send(`Please run the remaining steps: ${turn.held_back!.join('; ')}`)}
                className="mt-2 inline-flex items-center gap-1.5 rounded-control bg-brand-teal px-3 py-1.5 font-medium text-white hover:bg-brand-teal-dark disabled:opacity-50">Run the remaining {turn.held_back.length}</button>}
            </div>}
            {turn.reply && !active(turn) && thread.mission_id && <CorrectAnswer key={`correct-${turn.id}`} missionId={thread.mission_id} />}
            <WorkLog turn={turn} threadId={thread.id} running={active(turn)} />
            {!!turn.questions.length && (index === (thread?.turns.length ?? 0) - 1 && !active(turn)
              ? <QuestionCard key={`questions-${turn.id}`} questions={turn.questions} disabled={busy} onAnswer={text => void send(text)} />
              : <div className="mt-3 rounded-card bg-surface-secondary/60 px-4 py-3 text-xs text-text-secondary"><p className="font-medium">{active(turn) ? 'I may need to ask you' : 'I asked'}</p><ul className="mt-1.5 list-disc space-y-1 pl-4">{turn.questions.map(q => <li key={q}>{q}</li>)}</ul></div>)}
            {(active(turn) || stoppingTurns.has(turn.id)) && <div><p role="status" className="mt-3 flex items-center gap-2 text-sm text-brand-teal"><Loader2 size={15} className="motion-safe:animate-spin" />{stoppingTurns.has(turn.id) ? 'Stopping…' : turn.steps?.length ? 'Working through the steps…' : 'Looking through your records…'}</p><button type="button" disabled={stoppingTurns.has(turn.id)} onClick={() => void stop()} className={action}>{stoppingTurns.has(turn.id) ? 'Stopping…' : 'Stop work'}</button><details className="mt-2 text-xs text-text-tertiary"><summary className="cursor-pointer">Work interrupted?</summary><p className="mt-2">Your work is saved. If it stopped, resume from the last completed step.</p><button type="button" disabled={sending || stoppingTurns.has(turn.id)} className={action} onClick={() => void retry()}><RotateCcw size={13} />Resume saved work</button></details></div>}
            {friendlyNote(turn) && <div className={`mt-3 rounded-card px-4 py-3 text-sm leading-6 ${turn.status === 'agent_unavailable' || turn.status === 'blocked' ? 'bg-status-warning-bg/70 text-text-primary' : 'bg-brand-teal-light/60 text-text-secondary'}`}><p>{friendlyNote(turn)}</p>{index === (thread?.turns.length ?? 0)-1 && ['agent_unavailable', 'blocked'].includes(turn.status) && <button type="button" disabled={busy} onClick={() => void retry()} className={`${action} mt-2 bg-surface shadow-[0_1px_2px_rgba(16,24,40,0.06)]`}><RotateCcw size={13} />Try again</button>}</div>}
            {turn.artifacts.filter(a => a.kind !== 'assistant_workspace_result').map(artifact => { if (artifact.kind === 'investigation_proposal') return <InvestigationProposal key={artifact.id} threadId={thread.id} siteId={thread.site_id ?? 'NF1'} artifact={artifact} />; if (artifact.kind === 'assistant_rule') return <p key={artifact.id} className="my-1.5 text-xs text-text-secondary">{artifact.title} · <a className="underline" href="/settings/assistant-rules/">Review rule</a></p>; const View = artifact.kind === 'assistant_demo_deviations' ? DemoDeviationsArtifact : artifact.kind.startsWith('bioprocess_') ? BioprocessArtifact : AnalysisArtifact; return ['physical_analysis_plan', 'physical_analysis_context', 'bioprocess_case'].includes(artifact.kind) ? <details className="my-3 text-xs" key={artifact.id}><summary className="cursor-pointer text-text-secondary">{artifact.title}</summary><View threadId={thread.id} artifact={artifact} /></details> : <View key={artifact.id} threadId={thread.id} artifact={artifact} />; })}
          </div></div>
        </article>)}
        <div ref={end} />
      </div>
    </div>

    <div className={`sticky bottom-0 z-10 pb-4 pt-2 ${compact ? 'bg-surface' : 'bg-canvas'}`}>
      {error && <p role="alert" className="mb-3 rounded-control bg-status-critical-bg p-3 text-xs text-status-critical">{error}</p>}
      {sourcesOpen && <div className="mb-3 rounded-card border border-border-hairline bg-surface p-3 text-xs"><label htmlFor="engineering-source" className="block mb-2 font-medium">Attach an existing input context (optional)</label><select id="engineering-source" className="w-full rounded-control border border-border-strong p-2" value={attachment} onChange={e => setAttachment(e.target.value)}><option value="">No additional context</option>{sources.map(s => <option key={s.id} value={s.id}>{s.id} · {s.audience.replaceAll('_', ' ')} · {s.provenance}</option>)}</select><label className="mt-3 flex items-center gap-2"><input type="checkbox" checked={demoConsent || !!thread?.demo_enabled} disabled={!!thread?.demo_enabled} onChange={e => setDemoConsent(e.target.checked)} />Allow demo examples in this conversation (published freeze-drying case, simulated PenSim and SMPL cases)</label>
        <p className="mb-2 mt-4 font-medium">Verified CMO deliveries</p>{published.length ? <ul className="space-y-1.5">{published.map(d => { const on = pending.some(p => p.id === d.id) || !!thread?.dataset_ids?.includes(d.id); return <li key={d.id}><button type="button" disabled={on} onClick={() => companionState?.attachDataset({ id: d.id, label: datasetLabel(d), measurements: d.measurements, batches: d.batches.length })} className="flex w-full items-center justify-between gap-3 rounded-control border border-border-hairline px-2.5 py-2 text-left hover:border-brand-teal disabled:opacity-60"><span className="truncate">{datasetLabel(d)} · {d.measurements.toLocaleString()} values · {d.batches.length} batches</span><span className="shrink-0 text-brand-teal">{on ? 'Attached' : 'Attach'}</span></button></li>; })}</ul> : <p className="text-text-tertiary">None yet. Open a verified delivery under <Link href="/cmo" className="underline">Deliveries</Link> and choose Ask the assistant.</p>}</div>}
      {!!thread?.dataset_ids?.length && <p className="mb-2 flex items-center gap-1.5 px-1 text-[11px] text-text-tertiary"><ShieldCheck size={13} className="text-brand-teal" />Using {thread.dataset_ids.length} verified {thread.dataset_ids.length === 1 ? 'delivery' : 'deliveries'} as evidence in this conversation</p>}
      {pending.map((d: AttachedDataset) => <div key={d.id} className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-border-hairline bg-surface px-3 py-2.5" data-testid="attached-dataset">
        <div className="min-w-0"><p className="flex items-center gap-1.5 truncate text-xs font-medium"><ShieldCheck size={13} className="shrink-0 text-brand-teal" />Verified delivery · {d.label}</p><p className="mt-1 text-[11px] text-text-tertiary">{d.measurements.toLocaleString()} values · {d.batches} batches · each value traced to its source file</p></div>
        <button type="button" aria-label={`Remove ${d.label}`} onClick={() => companionState?.removeDataset(d.id)} className="companion-icon-button"><X size={15} /></button>
      </div>)}
      {selection && <div className="mb-3 rounded-lg border border-border-hairline bg-surface px-3 py-2.5" data-testid="selected-context">
        <div className="flex items-center justify-between gap-3"><div className="min-w-0"><p className="truncate text-xs font-medium">{selection.kind === 'chart' ? 'Chart selected' : 'Text selected'} · {selection.label}</p><p className="mt-1 text-[11px] text-text-tertiary">{selection.page_path} · Screen snapshot</p></div><button type="button" aria-label="Remove selected context" onClick={() => companionState?.clearSelection()} className="companion-icon-button"><X size={15} /></button></div>
        <details className="mt-2 text-xs text-text-secondary"><summary className="cursor-pointer">Inspect selection</summary><pre className="mt-2 max-h-36 overflow-auto whitespace-pre-wrap break-words font-sans">{selection.content}</pre><p className="mt-2 text-text-tertiary">Selected display content is unverified. Source records must be checked before relying on it.</p></details>
      </div>}
      <form className="rounded-xl border border-border-strong bg-surface p-3 shadow-sm focus-within:border-brand-teal" onSubmit={e => { e.preventDefault(); void send(); }}>
        <label className="sr-only" htmlFor="engineering-message">Describe your process problem or follow up</label>
        <textarea ref={composer} id="engineering-message" value={draft} maxLength={4000} rows={2} onChange={e => setDraft(e.target.value)} placeholder={last?.questions.length ? 'Or reply in your own words…' : pending.length ? 'For example: which batches had the lowest viability, and when?' : selection ? 'What would you like to do with this?' : companion ? 'Ask or describe what you’d like to do…' : 'Describe your process problem or ask a follow-up…'} className="block min-h-[52px] w-full resize-none bg-transparent px-2 py-1 text-sm leading-6 text-text-primary outline-none placeholder:text-text-muted" onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); } }} />
        <div className="mt-2 flex items-center justify-between"><button type="button" onClick={() => void loadSources()} className={action} aria-expanded={sourcesOpen}><Paperclip size={14} />{attachment || pending.length ? 'Context attached' : 'Context'}</button><div className="flex items-center gap-3"><span className="hidden text-[11px] text-text-muted sm:inline">{busy ? 'Work in progress · saved as it runs' : 'Enter to send · Shift + Enter for a new line'}</span><button type="submit" aria-label="Send message" disabled={!draft.trim() || busy} className="flex h-9 w-9 items-center justify-center rounded-control bg-brand-teal text-white hover:bg-brand-teal-dark disabled:opacity-40"><ArrowUp size={18} /></button></div></div>
      </form>
    </div>
    {!thread?.turns.length && <div className={`mx-auto w-full max-w-2xl ${compact ? 'pb-5' : 'pb-10 pt-4'}`}>
      {companion && !compact && <div className="mb-6 grid gap-3 sm:grid-cols-2">
        <Link href="/workbench/AN-104" className="flex items-center justify-between border-b border-border-hairline py-3 text-xs text-text-secondary hover:text-brand-teal">Explore the sample workbench<ArrowUpRight size={14} /></Link>
        <Link href="/reviews/REV-01" className="flex items-center justify-between border-b border-border-hairline py-3 text-xs text-text-secondary hover:text-brand-teal">2 sample items awaiting review<ArrowUpRight size={14} /></Link>
      </div>}
      <p className="text-xs text-text-tertiary">Or start from an example <span className="text-text-muted">(published or simulated data)</span></p>
      <div className="mt-2 flex flex-wrap gap-2">{EXAMPLES.map(e => <button key={e.label} type="button" disabled={busy} onClick={() => void send(e.prompt, true)} className={`${action} border border-border-hairline`}><FlaskConical size={14} />{e.label}</button>)}</div>
    </div>}
    </div>
  </div>;
}
