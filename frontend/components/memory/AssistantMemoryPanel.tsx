'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Button, Pill, type Tone } from '@/components/ui';
import { assistantMemory, BASIS_LABEL, consolidateMemory, formatDate, NOTE_KIND_LABEL, proposeSiteRule, setNoteStatus,
  type AssistantMemory, type MemoryNote } from '@/lib/memory-api';

// People see record names, not system IDs such as sig_01M6… (those identify a signal to software, not to a person).
const source = (s: { kind: string; id: string }) => `${s.kind.replace(/_/g, ' ')}${/^[a-z]+_[0-9A-Z]{16,}$/.test(s.id) ? '' : ` ${s.id}`}`;
const STATUS_TONE: Record<MemoryNote['status'], Tone> = { active: 'success', stale: 'warning', superseded: 'muted', forgotten: 'muted', wrong: 'muted' };

/** What the assistant remembers for you: its notes (each with the records it rests on), entity pages, and controls. */
export function AssistantMemoryPanel() {
  const [data, setData] = useState<AssistantMemory | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState('');
  const load = useCallback(async () => {
    try { setData(await assistantMemory()); setError(''); } catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  async function act(run: () => Promise<unknown>, message = '') {
    setBusy(true); setError(''); setDone('');
    try { await run(); await load(); setDone(message); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const current = data?.notes.filter(n => n.status === 'active' || n.status === 'stale') ?? [];
  const retired = data?.notes.filter(n => !['active', 'stale'].includes(n.status)) ?? [];
  const inIndex = new Set(data?.index.map(i => i.id));

  return <section className="workspace-panel" aria-labelledby="assistant-memory">
    <div className="flex flex-wrap items-start justify-between gap-3 px-4 pt-4">
      <div>
        <h2 id="assistant-memory" className="text-[14px] font-medium">What your assistant remembers</h2>
        <p className="mt-1 max-w-2xl text-[12.5px] text-text-secondary">Notes the assistant kept from your conversations: lessons, decisions, your preferences and open threads.
          Each rests on records it read, or on something you said. Records stay the source of truth: when a record changes, its notes are marked stale until checked again.</p>
      </div>
      <Button size="sm" disabled={busy} onClick={() => void act(consolidateMemory, 'Memory tidied: stale notes marked, duplicates merged, pages rebuilt.')}>Tidy now</Button>
    </div>
    {error && <div role="alert" className="workspace-alert mx-4 mt-3">{error}</div>}
    {done && <p role="status" className="mx-4 mt-3 text-[12.5px] text-brand-teal">{done}</p>}
    {!data && !error && <p role="status" className="px-4 py-3 text-[13px] text-text-tertiary">Loading…</p>}
    {data && <p className="px-4 pt-2 text-[11.5px] text-text-tertiary">
      {data.last_consolidated_at ? `Last tidied ${formatDate(data.last_consolidated_at)}` : 'Not tidied yet'}
      {' · '}{data.semantic_search ? 'Searched by meaning and by words' : 'Searched by words (meaning search unavailable)'}</p>}

    {data && !current.length && <p className="px-4 pb-4 pt-2 text-[13px] text-text-tertiary">Nothing yet. As you work with the assistant, it keeps what will matter next time.</p>}
    {!!current.length && <ul className="divide-y divide-border-hairline px-4 pb-2">{current.map(n => <li key={n.id} className="py-3">
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <Pill tone={n.kind === 'warning' ? 'warning' : 'muted'}>{NOTE_KIND_LABEL[n.kind]}</Pill>
        <span className="text-text-tertiary">{BASIS_LABEL[n.basis]}{n.origin === 'dreaming' ? ' · found while tidying' : ''} · {formatDate(n.updated_at)}</span>
        {n.status === 'stale' && <Pill tone={STATUS_TONE.stale}>stale</Pill>}
        {inIndex.has(n.id) && <span className="text-text-tertiary">· always in view</span>}
      </div>
      <p className="mt-1 text-[13.5px] text-text-primary">{n.text}</p>
      {n.status === 'stale' && <p className="mt-1 text-[12px] text-amber-700">{n.stale_because.join('; ')}. The assistant re-checks the records before relying on it.</p>}
      {!!n.sources.length && <p className="mt-1 text-[12px] text-text-tertiary">Based on {n.sources.map(source).join(', ')}</p>}
      <div className="mt-2 flex gap-2">
        <Link href={`/home/?conversation=${encodeURIComponent(n.conversation_id)}`} className="text-[12px] text-brand-teal underline">From this conversation</Link>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => void act(() => setNoteStatus(n.id, 'wrong', 'Marked wrong by owner'), 'Marked wrong. The assistant will not use it.')}>This is wrong</Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => void act(() => setNoteStatus(n.id, 'forgotten'), 'Forgotten.')}>Forget</Button>
      </div>
    </li>)}</ul>}

    {!!data?.rule_suggestions.length && <div className="mx-4 mb-3 rounded-md border border-border-hairline p-3">
      <p className="text-[13px] font-medium">Make it a standing rule?</p>
      <p className="text-[12px] text-text-secondary">These came up repeatedly. A site rule applies to everyone’s assistant at the site and needs approval from someone with authority.</p>
      <ul className="mt-2 space-y-2">{data.rule_suggestions.map(s => {
        const note = data.notes.find(n => n.id === s.note_id);
        return <li key={s.note_id} className="flex flex-wrap items-center justify-between gap-2 text-[13px]"><span>{s.text}</span>
          <Button size="sm" disabled={busy || !note} onClick={() => note && void act(() => proposeSiteRule(s.text, note.site_id), 'Proposed as a site rule; it applies once approved under Assistant rules.')}>Propose as site rule</Button></li>;
      })}</ul></div>}

    {!!data?.pages.length && <details className="mx-4 mb-3 text-[13px]"><summary className="cursor-pointer text-text-secondary">By batch, lot, equipment or case ({data.pages.length})</summary>
      <ul className="mt-2 space-y-2">{data.pages.map(pg => <li key={pg.page_id}><span className="font-medium">{pg.entity}</span>
        <span className="text-text-tertiary"> · {pg.note_ids.length} note{pg.note_ids.length === 1 ? '' : 's'}</span></li>)}</ul></details>}

    {!!retired.length && <details className="mx-4 mb-4 text-[12.5px] text-text-secondary"><summary className="cursor-pointer">Retired notes ({retired.length})</summary>
      <ul className="mt-2 space-y-1">{retired.map(n => <li key={n.id} className="flex flex-wrap items-center gap-2">
        <Pill tone={STATUS_TONE[n.status]}>{n.status}</Pill><span>{n.text}</span>
        {(n.status === 'forgotten' || n.status === 'wrong') && <Button size="sm" variant="ghost" disabled={busy}
          onClick={() => void act(() => setNoteStatus(n.id, 'active', 'Restored by owner'))}>Restore</Button>}</li>)}</ul></details>}
  </section>;
}
