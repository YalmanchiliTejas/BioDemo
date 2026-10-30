'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowUp, FlaskConical, MessageSquare, Plus, RotateCcw, ChevronDown, Workflow, Check, Circle, Loader2, Paperclip, X, ArrowUpRight, ShieldCheck } from 'lucide-react';
import { processRequest } from '@/lib/process-api';
import { useOptionalCompanion, type AttachedDataset, type DisplayContext } from '@/lib/companion-context';
import { usePathname } from 'next/navigation';
import { SCREENS } from '@/lib/routes';
import { AnalysisArtifact, type ArtifactRef } from './AnalysisArtifact';
import { BioprocessArtifact } from './BioprocessArtifact';

type Step = { node_id: string; title: string; task_kind: string; depends_on: string[]; status: string; issues: string[] };
type Turn = { display_context?: DisplayContext | null; id: string; user_text: string; status: string; reply: string | null; questions: string[]; system_message?: string; issues: string[]; artifacts: ArtifactRef[]; steps?: Step[]; elapsed_seconds?: number; basis_status?: string; gateway_runs: { route?: { unqualified?: boolean } | null; [key: string]: unknown }[] };
type Thread = { id: string; revision: number; title: string; turns: Turn[]; turn_ids: string[]; demo_enabled: boolean; source_ids: string[]; dataset_ids?: string[] };
type PublishedDataset = { id: string; cmo: string; delivery_name: string | null; measurements: number; batches: string[] };
const datasetLabel = (d: PublishedDataset) => d.delivery_name ?? d.cmo;
type Recent = { id: string; title: string };
type Source = { id: string; audience: string; provenance: string };
const storageKey = 'biodemo.engineering.conversation.v1';
const EXAMPLES = [
  { label: 'Freeze-drying transfer', prompt: 'Use the published and reconstructed freeze-drying example. Assess transferring the source process to the receiving equipment, choose an appropriate registered model, simulate current conditions, and show constraints with charts and a 3D vial review. Clearly distinguish published values from assumptions.' },
  { label: 'Penicillin batch decision', prompt: 'Use the simulated PenSim demo case NC-03ce17b48c95. We are 60 h into the batch and air is limited to 1.0×. Which operating plan should we run for the rest of the batch, and what will penicillin and dissolved oxygen look like?' },
  { label: 'Antibody recipe transfer', prompt: 'Use the simulated SMPL antibody demo case NC-09861ef65be7. Before the receiving run starts, which flow and nutrient plan stays within the receiving limits and gives the most antibody? Compare the current plan with the alternatives.' },
];
const active = (turn?: Turn) => !!turn && ['queued', 'running'].includes(turn.status);
const action = 'inline-flex items-center gap-2 rounded-control px-3 py-2 text-xs text-text-secondary hover:bg-surface-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-teal disabled:opacity-40';

export function EngineeringChat({ companion = false, compact = false }: { companion?: boolean; compact?: boolean }) {
  const companionState = useOptionalCompanion();
  const selection = companionState?.selection;
  const pending = companionState?.datasets ?? [];
  const pathname = usePathname().replace(/\/$/, '');
  const pageName = SCREENS.find(s => s.href === pathname)?.title ?? 'Current workspace';
  const [thread, setThread] = useState<Thread | null>(null);
  const [recent, setRecent] = useState<Recent[]>([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [sources, setSources] = useState<Source[]>([]);
  const [published, setPublished] = useState<PublishedDataset[]>([]);
  const [attachment, setAttachment] = useState('');
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [demoConsent, setDemoConsent] = useState(false);
  const current = useRef<string | null>(null);
  const inFlight = useRef(false);
  const end = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const last = thread?.turns.at(-1);
  const busy = sending || active(last);

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
    if (saved) void open(saved);
    processRequest<{ conversations: Recent[] }>('/v1/process-model/conversations')
      .then(r => setRecent(r.conversations)).catch(e => setError(String(e)));
    return () => { current.current = null; };
  // Restore once; subsequent selection is explicit.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!thread || !active(last)) return;
    const id = thread.id;
    let mounted = true;
    const timer = window.setInterval(() => {
      processRequest<Thread>(`/v1/process-model/conversations/${id}`)
        .then(data => { if (mounted && current.current === id) setThread(data); })
        .catch(e => { if (mounted) setError(String(e)); });
    }, 1000);
    return () => { mounted = false; window.clearInterval(timer); };
  }, [thread?.id, last?.status]);
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

  return <div className={`mx-auto flex w-full flex-col ${compact ? 'min-h-full px-4' : 'min-h-[calc(100dvh-7rem)] max-w-4xl px-2 sm:px-8'}`} data-testid="engineering-chat">
    <header className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="flex min-w-0 items-center gap-3">{compact ? <p className="max-w-[190px] truncate text-xs text-text-tertiary" title={pageName}>{pageName}</p> : <>{companion ? <span className="companion-mark" aria-hidden /> : <FlaskConical size={20} className="text-brand-teal" />}<div><h1 className="text-sm font-medium text-text-primary">{companion ? compact ? 'In your workspace' : 'Your work companion' : 'Process engineering'}</h1><p className="mt-0.5 max-w-[260px] truncate text-xs text-text-tertiary">{companion ? compact ? pageName : 'Aster Biologics · Demo workspace' : 'Problem → evidence → simulation → review'}</p></div></>}</div>
      <div className="flex items-center gap-1">
        <details className="relative"><summary className={`${action} cursor-pointer list-none`}><MessageSquare size={14} /><span className={compact ? 'sr-only' : ''}>Conversations</span><ChevronDown size={12} /></summary><div className="absolute right-0 top-10 z-20 w-72 rounded-card border border-border-hairline bg-surface p-2 shadow-lg">{recent.length ? recent.map(r => <button key={r.id} className="block w-full truncate rounded p-2 text-left text-xs hover:bg-surface-secondary" onClick={() => void open(r.id)}>{r.title}</button>) : <p className="p-2 text-xs text-text-tertiary">Your conversations will be saved here.</p>}</div></details>
        <button type="button" onClick={newConversation} className={action} aria-label="New conversation"><Plus size={16} /><span className={compact ? 'sr-only' : 'hidden sm:inline'}>New</span></button>
      </div>
    </header>

    <div className="flex-1 pb-6">
      {!thread?.turns.length && <section className={`mx-auto max-w-2xl ${compact ? 'pb-5 pt-8' : 'pb-8 pt-16 sm:pt-24'}`}>
        <h2 className={`font-medium leading-tight tracking-tight text-text-primary ${compact ? 'text-2xl' : 'text-3xl sm:text-[38px]'}`}>{pending.length ? 'Ask about this delivery.' : selection ? 'Let’s look at this together.' : companion ? 'What are we working on?' : 'What process problem are you working on?'}</h2>
        <p className="mt-4 max-w-lg text-sm leading-6 text-text-secondary">{pending.length ? 'The verified values, their batches and source files are attached below. Ask about trends, gaps or differences between batches.' : selection ? 'Your selection is attached below. Ask a question or describe what you’d like to do.' : companion ? 'Bring a question, explore an idea, or select something in your workspace. We’ll take it from there.' : 'Describe the decision you need to make. The agent will identify the evidence and models needed.'}</p>
        {companion && !compact && <p className="mt-6 flex items-center gap-2 text-xs text-text-tertiary"><span className="inline-block h-1.5 w-1.5 rounded-full bg-brand-teal" />Here throughout your workspace · highlight text or select a chart range</p>}
      </section>}

      <div role="log" aria-label="Engineering conversation" aria-live="polite" aria-relevant="additions text" className={thread?.turns.length ? 'space-y-8 py-6' : ''}>
        {thread?.turns.map((turn, index) => <article key={turn.id} data-testid="conversation-turn">
          <div className="mb-6 flex justify-end"><div className="min-w-0 max-w-[90%] rounded-2xl rounded-br-sm bg-surface-secondary px-5 py-4 text-sm leading-6 text-text-primary"><span className="sr-only">You: </span><p className="whitespace-pre-wrap">{turn.user_text}</p>{turn.display_context && <details className="mt-3 border-t border-border-hairline pt-2 text-xs"><summary className="cursor-pointer">{turn.display_context.kind === 'chart' ? 'Chart' : 'Text'} from {turn.display_context.label}</summary><p className="mt-2 text-text-tertiary">Screen snapshot · {turn.display_context.page_path} · {turn.display_context.captured_at}</p><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words font-sans">{turn.display_context.content}</pre></details>}</div></div>
          <div className="flex gap-3 sm:gap-4"><div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border-hairline text-brand-teal"><FlaskConical size={14} /></div><div className="min-w-0 flex-1">
            {['stale', 'quarantined'].includes(turn.basis_status ?? '') && <p role="status" className="mb-3 rounded-control bg-status-warning-bg px-4 py-3 text-sm text-text-secondary">Contributing evidence changed or was withdrawn. Rebuild this analysis before using its findings.</p>}
            {turn.gateway_runs.some(r => r.route?.unqualified) && <p className="mb-2 text-xs text-status-warning">Development LLM run · route unqualified · review required</p>}
            {turn.reply && <p className="whitespace-pre-wrap text-sm leading-7 text-text-primary">{turn.reply}</p>}
            {!!turn.questions.length && <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6">{turn.questions.map(q => <li key={q}>{q}</li>)}</ul>}
            {active(turn) && <div><p role="status" className="mt-3 flex items-center gap-2 text-sm text-brand-teal"><Loader2 size={15} className="motion-safe:animate-spin" />{turn.steps?.length ? 'Running the assembled workflow…' : 'Reviewing context and assembling the analysis…'}</p><details className="mt-2 text-xs text-text-tertiary"><summary className="cursor-pointer">Work interrupted?</summary><p className="mt-2">Your work is saved. A running worker keeps its lease for up to five minutes; after it expires you can resume from the last completed step.</p><button type="button" disabled={sending} className={action} onClick={() => void retry()}><RotateCcw size={13} />Resume saved work</button></details></div>}
            {!!turn.steps?.length && <details className="my-4 rounded-card border border-border-hairline bg-surface p-4" open={active(turn)}><summary className="flex cursor-pointer items-center gap-2 text-xs font-medium text-text-secondary"><Workflow size={15} />{turn.steps.length} workflow steps · {turn.status.replaceAll('_', ' ')}<ChevronDown size={12} className="ml-auto" /></summary><ol className="mt-4 space-y-3">{turn.steps.map(step => <li className="flex gap-3 text-xs" key={step.node_id}>{step.status === 'completed' ? <Check size={14} className="shrink-0 text-status-success" /> : <Circle size={14} className={`shrink-0 ${step.status === 'blocked' ? 'text-status-critical' : 'text-text-muted'}`} />}<div><p className="font-medium">{step.title} <span className="ml-2 font-normal text-text-tertiary">{step.status}</span></p><p className="mt-1 text-text-tertiary">{step.task_kind.replaceAll('_', ' ')}{step.depends_on.length ? ` · after ${step.depends_on.join(', ')}` : ''}</p>{step.issues.map(issue => <p key={issue} className="mt-1 text-status-critical">{issue}</p>)}</div></li>)}</ol></details>}
            {turn.system_message && <div className={`mt-3 rounded-control border-l-2 px-4 py-3 text-sm leading-6 ${turn.status === 'agent_unavailable' || turn.status === 'blocked' ? 'border-status-warning bg-status-warning-bg' : 'border-brand-teal bg-brand-teal-light'}`}><p>{turn.system_message}</p>{index === (thread?.turns.length ?? 0)-1 && ['agent_unavailable', 'blocked'].includes(turn.status) && <button type="button" disabled={busy} onClick={() => void retry()} className={`${action} mt-2 border border-border-strong`}><RotateCcw size={13} />Retry this request</button>}</div>}
            {turn.artifacts.map(artifact => { const View = artifact.kind.startsWith('bioprocess_') ? BioprocessArtifact : AnalysisArtifact; return ['physical_analysis_plan', 'physical_analysis_context', 'bioprocess_case'].includes(artifact.kind) ? <details className="my-3 text-xs" key={artifact.id}><summary className="cursor-pointer text-text-secondary">{artifact.title}</summary><View threadId={thread.id} artifact={artifact} /></details> : <View key={artifact.id} threadId={thread.id} artifact={artifact} />; })}
            {!!turn.gateway_runs.length && <details className="mt-3 text-xs text-text-tertiary"><summary className="cursor-pointer">Execution record{turn.elapsed_seconds != null ? ` · ${turn.elapsed_seconds.toFixed(1)} s` : ''}</summary><pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-all bg-surface-secondary p-3">{JSON.stringify({ gateway_runs: turn.gateway_runs, issues: turn.issues, artifacts: turn.artifacts }, null, 2)}</pre></details>}
          </div></div>
        </article>)}
        <div ref={end} />
      </div>
    </div>

    <div className={`sticky bottom-0 z-10 pb-4 pt-2 ${compact ? 'bg-surface' : 'bg-canvas'}`}>
      {error && <p role="alert" className="mb-3 rounded-control bg-status-critical-bg p-3 text-xs text-status-critical">{error}</p>}
      {sourcesOpen && <div className="mb-3 rounded-card border border-border-hairline bg-surface p-3 text-xs"><label htmlFor="engineering-source" className="block mb-2 font-medium">Attach an existing input context (optional)</label><select id="engineering-source" className="w-full rounded-control border border-border-strong p-2" value={attachment} onChange={e => setAttachment(e.target.value)}><option value="">No additional context</option>{sources.map(s => <option key={s.id} value={s.id}>{s.id} · {s.audience.replaceAll('_', ' ')} · {s.provenance}</option>)}</select><label className="mt-3 flex items-center gap-2"><input type="checkbox" checked={demoConsent || !!thread?.demo_enabled} disabled={!!thread?.demo_enabled} onChange={e => setDemoConsent(e.target.checked)} />Allow demo examples in this conversation: the reconstructed freeze-drying case and the simulated PenSim / SMPL cases from the physics experiment</label><p className="mt-2 text-text-tertiary">Only authorized contexts appear. Selecting one supplies its recorded inputs and provenance.</p>
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
        <textarea ref={composer} id="engineering-message" value={draft} maxLength={4000} rows={2} onChange={e => setDraft(e.target.value)} placeholder={last?.questions.length ? 'Answer the questions or refine the analysis…' : pending.length ? 'For example: which batches had the lowest viability, and when?' : selection ? 'What would you like to do with this?' : companion ? 'Ask or describe what you’d like to do…' : 'Describe your process problem or ask a follow-up…'} className="block min-h-[52px] w-full resize-none bg-transparent px-2 py-1 text-sm leading-6 text-text-primary outline-none placeholder:text-text-muted" onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); } }} />
        <div className="mt-2 flex items-center justify-between"><button type="button" onClick={() => void loadSources()} className={action} aria-expanded={sourcesOpen}><Paperclip size={14} />{attachment || pending.length ? 'Context attached' : 'Context'}</button><div className="flex items-center gap-3"><span className="hidden text-[11px] text-text-muted sm:inline">{busy ? 'Work in progress · saved as it runs' : 'Enter to send · Shift + Enter for a new line'}</span><button type="submit" aria-label="Send message" disabled={!draft.trim() || busy} className="flex h-9 w-9 items-center justify-center rounded-control bg-brand-teal text-white hover:bg-brand-teal-dark disabled:opacity-40"><ArrowUp size={18} /></button></div></div>
      </form>
      <div className="mt-2 flex flex-wrap justify-between gap-4 px-1 text-[11px] text-text-tertiary"><p>Evidence stays inspectable. Production changes require review.</p><Link className="shrink-0 underline underline-offset-2 hover:text-brand-teal" href="/process-simulation">Process simulation</Link></div>
    </div>
    {!thread?.turns.length && <div className={`mx-auto w-full max-w-2xl ${compact ? 'pb-5' : 'pb-10 pt-4'}`}>
      {companion && !compact && <div className="mb-6 grid gap-3 sm:grid-cols-2">
        <Link href="/workbench/AN-104" className="flex items-center justify-between border-b border-border-hairline py-3 text-xs text-text-secondary hover:text-brand-teal">Explore the sample workbench<ArrowUpRight size={14} /></Link>
        <Link href="/reviews/REV-01" className="flex items-center justify-between border-b border-border-hairline py-3 text-xs text-text-secondary hover:text-brand-teal">2 sample items awaiting review<ArrowUpRight size={14} /></Link>
      </div>}
      <details className="text-xs text-text-tertiary"><summary className="cursor-pointer">Try an engineering example</summary>
        <p className="mt-3 leading-5">Examples use published or simulated data, labelled as such. The penicillin and antibody cases come from the physics A/B experiment; the CHO example needs a verified delivery attached from Deliveries.</p>
        <div className="mt-2 flex flex-wrap gap-2">{EXAMPLES.map(e => <button key={e.label} type="button" disabled={busy} onClick={() => void send(e.prompt, true)} className={`${action} border border-border-hairline`}><FlaskConical size={14} />{e.label}</button>)}</div>
      </details>
    </div>}
  </div>;
}
