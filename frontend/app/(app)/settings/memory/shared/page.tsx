'use client';

import Link from 'next/link';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Eye } from 'lucide-react';
import { SettingsFrame } from '@/components/shell/SettingsFrame';
import { Markdown } from '@/components/process/Markdown';
import { formatDate, listGrants, SCOPE_LABEL, sharedConversation, sharedConversations, sharedCorrections, sharedRules,
  type Grant, type MemoryScope } from '@/lib/memory-api';

type Thread = Awaited<ReturnType<typeof sharedConversation>>;

/** Read-only view of a colleague's memory under an access grant they approved. No composer: nothing is written. */
function SharedMemory() {
  const owner = useSearchParams().get('owner') ?? '';
  const [grant, setGrant] = useState<Grant | null>(null);
  const [tab, setTab] = useState<MemoryScope>('conversations');
  const [conversations, setConversations] = useState<{ id: string; title: string; updated_at?: string }[]>([]);
  const [thread, setThread] = useState<Thread | null>(null);
  const [corrections, setCorrections] = useState<{ correction_id: string; text: string; at?: string }[]>([]);
  const [rules, setRules] = useState<{ rule_id: string; text: string; status?: string }[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    listGrants().then(g => {
      const found = g.shared_with_me.find(x => x.owner_id === owner && x.status === 'active') ?? null;
      setGrant(found);
      if (found && !found.scopes.includes('conversations')) setTab(found.scopes[0]);
    }).catch(e => setError((e as Error).message));
  }, [owner]);
  useEffect(() => {
    if (!grant) return;
    setError('');
    const fail = (e: unknown) => setError((e as Error).message);
    if (tab === 'conversations') sharedConversations(owner).then(r => setConversations(r.conversations)).catch(fail);
    if (tab === 'corrections') sharedCorrections(owner).then(r => setCorrections(r.corrections)).catch(fail);
    if (tab === 'rules') sharedRules(owner).then(r => setRules(r.rules)).catch(fail);
  }, [grant, tab, owner]);

  const name = grant?.owner_email || owner;
  return <SettingsFrame title="Shared memory" description="What a colleague shared with you. Read-only: nothing you do here changes their memory.">
    {error && <div role="alert" className="workspace-alert">{error}</div>}
    {!grant ? <p className="text-[13px] text-text-secondary">{error ? '' : 'You don’t have active access to this person’s memory.'} <Link href="/settings/memory/" className="text-brand-teal underline">Back to Memory & sharing</Link></p> : <>
      <p role="note" className="mb-4 flex items-center gap-2 rounded-card border border-brand-teal/30 bg-brand-teal-light/40 px-4 py-2.5 text-[13px] text-text-primary">
        <Eye size={15} className="text-brand-teal" />Shared by {name} · read-only · access until {formatDate(grant.expires_at)}</p>
      <div role="tablist" className="mb-4 flex gap-2">{grant.scopes.map(s => <button key={s} role="tab" type="button" aria-selected={tab === s} onClick={() => { setTab(s); setThread(null); }}
        className={`rounded-control px-3 py-1.5 text-[13px] ${tab === s ? 'bg-ink text-white' : 'border border-border-hairline text-text-secondary hover:text-ink'}`}>{SCOPE_LABEL[s]}</button>)}</div>

      {tab === 'conversations' && <div className="grid gap-4 md:grid-cols-[240px_minmax(0,1fr)]">
        <ul className="space-y-0.5">{conversations.length ? conversations.map(c => <li key={c.id}>
          <button type="button" onClick={() => sharedConversation(owner, c.id).then(setThread).catch(e => setError((e as Error).message))}
            className={`block w-full truncate rounded-control px-2 py-2 text-left text-[13px] ${thread?.id === c.id ? 'bg-brand-teal-light/60 font-medium' : 'text-text-secondary hover:bg-surface-secondary'}`}>{c.title || 'Untitled conversation'}</button></li>)
          : <li className="px-2 text-[13px] text-text-tertiary">No conversations.</li>}</ul>
        <section className="workspace-panel p-4">{thread ? <>
          <h2 className="mb-4 text-[15px] font-medium">{thread.title}</h2>
          <div className="space-y-6">{thread.turns.map(t => <article key={t.id} className="space-y-3">
            <p className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-2xl bg-surface-secondary px-4 py-3 text-sm">{t.user_text}</p>
            {t.reply ? <Markdown text={t.reply} /> : <p className="text-[13px] text-text-tertiary">{t.status ? `No answer (${t.status.replaceAll('_', ' ')})` : 'No answer'}</p>}
          </article>)}</div></> : <p className="text-[13px] text-text-tertiary">Choose a conversation to read it.</p>}</section>
      </div>}

      {tab === 'corrections' && <ul className="space-y-2">{corrections.length ? corrections.map(c => <li key={c.correction_id} className="workspace-panel px-4 py-3 text-[13px]">
        {c.text}{c.at && <span className="ml-2 text-text-tertiary">· {formatDate(c.at)}</span>}</li>)
        : <li className="text-[13px] text-text-tertiary">No corrections.</li>}</ul>}

      {tab === 'rules' && <ul className="space-y-2">{rules.length ? rules.map(r => <li key={r.rule_id} className="workspace-panel px-4 py-3 text-[13px]">
        {r.text}{r.status && <span className="ml-2 text-text-tertiary">· {r.status}</span>}</li>)
        : <li className="text-[13px] text-text-tertiary">No personal rules.</li>}</ul>}
    </>}
  </SettingsFrame>;
}

export default function SharedMemoryPage() {
  return <Suspense fallback={null}><SharedMemory /></Suspense>;
}
