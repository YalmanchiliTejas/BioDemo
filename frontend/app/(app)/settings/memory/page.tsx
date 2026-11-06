'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { SettingsFrame } from '@/components/shell/SettingsFrame';
import { Button, Pill, table, type Tone } from '@/components/ui';
import { approveGrant, denyGrant, formatDate, listGrants, requestAccess, revokeGrant, SCOPE_LABEL,
  type Grant, type Grants, type MemoryScope } from '@/lib/memory-api';

const TONE: Record<Grant['status'], Tone> = { requested: 'warning', active: 'success', denied: 'muted', revoked: 'muted', expired: 'muted' };
const DURATIONS = [7, 30, 90];
const scopes = (g: Grant) => g.scopes.map(s => SCOPE_LABEL[s] ?? s).join(', ');
const who = (email: string | null | undefined, id: string) => email || id;

export default function MemorySharingPage() {
  const [grants, setGrants] = useState<Grants>({ shared_by_me: [], shared_with_me: [] });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [approveDays, setApproveDays] = useState<Record<string, number>>({});
  const [denying, setDenying] = useState<string | null>(null);
  const [denyReason, setDenyReason] = useState('');
  const [form, setForm] = useState({ email: '', reason: '', days: 30, scopes: ['conversations'] as MemoryScope[] });

  const load = useCallback(async () => {
    try { setGrants(await listGrants()); setError(''); } catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  async function act(run: () => Promise<unknown>) {
    setBusy(true); setError('');
    try { await run(); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  function ask(e: FormEvent) {
    e.preventDefault();
    void act(async () => {
      await requestAccess({ owner_email: form.email.trim(), scopes: form.scopes, reason: form.reason.trim(), days: form.days });
      setForm(f => ({ ...f, email: '', reason: '' }));
    });
  }
  const toggleScope = (s: MemoryScope) =>
    setForm(f => ({ ...f, scopes: f.scopes.includes(s) ? f.scopes.filter(x => x !== s) : [...f.scopes, s] }));

  const waiting = grants.shared_by_me.filter(g => g.status === 'requested');
  const readers = grants.shared_by_me.filter(g => g.status === 'active');
  const given = grants.shared_with_me.filter(g => ['active', 'requested'].includes(g.status));
  const past = [...grants.shared_by_me, ...grants.shared_with_me].filter(g => ['denied', 'revoked', 'expired'].includes(g.status));

  return <SettingsFrame title="Memory & sharing" description="Your assistant memory is private to you: your conversations and the messages in them, the corrections you made, and your personal rules. Nobody else can read it — not administrators, and not other people's assistants — unless you approve a request here. Access is read-only, time-limited, and you can revoke it at any time.">
    {error && <div role="alert" className="workspace-alert">{error}</div>}

    <section className="workspace-panel">
      <h2 className="px-4 pt-4 text-[14px] font-medium">Requests waiting for you</h2>
      {waiting.length ? <div className={table.wrap}><table className={table.root}>
        <thead><tr>{['Colleague', 'Wants to read', 'Why', 'For', ''].map(h => <th key={h} className={table.th}>{h}</th>)}</tr></thead>
        <tbody>{waiting.map(g => <tr key={g.grant_id} className={table.tr}>
          <td className={table.td}>{who(g.grantee_email, g.grantee_id)}</td>
          <td className={table.td}>{scopes(g)}</td>
          <td className={table.td}>{g.reason}</td>
          <td className={table.td}><select aria-label="Access length" value={approveDays[g.grant_id] ?? g.requested_days}
            onChange={e => setApproveDays(d => ({ ...d, [g.grant_id]: Number(e.target.value) }))} className="h-8 rounded border border-border-hairline px-2 text-[13px]">
            {[...new Set([...DURATIONS, g.requested_days])].sort((a, b) => a - b).map(n => <option key={n} value={n}>{n} days</option>)}</select></td>
          <td className={table.td}>{denying === g.grant_id
            ? <span className="flex items-center gap-2"><input aria-label="Reason (optional)" value={denyReason} onChange={e => setDenyReason(e.target.value)}
                placeholder="Reason (optional)" className="h-8 w-40 rounded border border-border-hairline px-2 text-[13px]" />
              <Button size="sm" disabled={busy} onClick={() => void act(async () => { await denyGrant(g.grant_id, denyReason); setDenying(null); setDenyReason(''); })}>Deny</Button>
              <Button size="sm" variant="ghost" onClick={() => setDenying(null)}>Cancel</Button></span>
            : <span className="flex gap-2"><Button size="sm" variant="primary" disabled={busy}
                onClick={() => void act(() => approveGrant(g.grant_id, approveDays[g.grant_id] ?? g.requested_days))}>Approve</Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => setDenying(g.grant_id)}>Deny</Button></span>}</td>
        </tr>)}</tbody></table></div>
        : <p className="px-4 pb-4 pt-2 text-[13px] text-text-tertiary">No one is asking to read your memory.</p>}
    </section>

    <section className="workspace-panel mt-4">
      <h2 className="px-4 pt-4 text-[14px] font-medium">People who can read your memory</h2>
      {readers.length ? <div className={table.wrap}><table className={table.root}>
        <thead><tr>{['Colleague', 'Can read', 'Until', ''].map(h => <th key={h} className={table.th}>{h}</th>)}</tr></thead>
        <tbody>{readers.map(g => <tr key={g.grant_id} className={table.tr}>
          <td className={table.td}>{who(g.grantee_email, g.grantee_id)}<span className="block text-[11px] text-text-tertiary">and their assistant</span></td>
          <td className={table.td}>{scopes(g)}</td>
          <td className={table.td}>{formatDate(g.expires_at)}</td>
          <td className={table.td}><Button size="sm" variant="ghost" disabled={busy} onClick={() => void act(() => revokeGrant(g.grant_id, 'Revoked by owner'))}>Revoke</Button></td>
        </tr>)}</tbody></table></div>
        : <p className="px-4 pb-4 pt-2 text-[13px] text-text-tertiary">Only you can read your memory.</p>}
    </section>

    <section className="workspace-panel mt-4">
      <h2 className="px-4 pt-4 text-[14px] font-medium">Access you’ve been given</h2>
      {given.length ? <div className={table.wrap}><table className={table.root}>
        <thead><tr>{['Whose memory', 'You can read', 'Status', 'Until', ''].map(h => <th key={h} className={table.th}>{h}</th>)}</tr></thead>
        <tbody>{given.map(g => <tr key={g.grant_id} className={table.tr}>
          <td className={table.td}>{who(g.owner_email, g.owner_id)}</td>
          <td className={table.td}>{scopes(g)}</td>
          <td className={table.td}><Pill tone={TONE[g.status]}>{g.status === 'requested' ? 'waiting for approval' : g.status}</Pill></td>
          <td className={table.td}>{g.status === 'active' ? formatDate(g.expires_at) : '—'}</td>
          <td className={table.td}><span className="flex items-center gap-3">
            {g.status === 'active' && <Link className="text-[13px] text-brand-teal underline" href={`/settings/memory/shared/?owner=${encodeURIComponent(g.owner_id)}`}>View</Link>}
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => void act(() => revokeGrant(g.grant_id, g.status === 'requested' ? 'Request withdrawn' : 'Access returned'))}>
              {g.status === 'requested' ? 'Withdraw' : 'Give back'}</Button></span></td>
        </tr>)}</tbody></table></div>
        : <p className="px-4 pb-4 pt-2 text-[13px] text-text-tertiary">You haven’t been given access to anyone’s memory.</p>}
    </section>

    <section className="workspace-panel mt-4">
      <form onSubmit={ask} className="grid gap-3 p-4 sm:grid-cols-2">
        <h2 className="text-[14px] font-medium sm:col-span-2">Ask a colleague for access</h2>
        <p className="-mt-2 text-[12.5px] text-text-secondary sm:col-span-2">They decide. If they approve, you and your assistant can read what you asked for, read-only, until the access ends.</p>
        <label className="flex flex-col gap-1 text-[12px] font-medium text-text-secondary">Colleague’s email
          <input required type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} placeholder="colleague@company.com"
            className="h-9 rounded border border-border-hairline px-2 text-[13px] font-normal text-text-primary" /></label>
        <label className="flex flex-col gap-1 text-[12px] font-medium text-text-secondary">For how long
          <select value={form.days} onChange={e => setForm(f => ({ ...f, days: Number(e.target.value) }))} className="h-9 rounded border border-border-hairline px-2 text-[13px] font-normal">
            {DURATIONS.map(n => <option key={n} value={n}>{n} days</option>)}</select></label>
        <fieldset className="sm:col-span-2"><legend className="text-[12px] font-medium text-text-secondary">What you need to read</legend>
          <div className="mt-1 flex flex-wrap gap-4">{(Object.keys(SCOPE_LABEL) as MemoryScope[]).map(s => <label key={s} className="flex items-center gap-2 text-[13px]">
            <input type="checkbox" checked={form.scopes.includes(s)} onChange={() => toggleScope(s)} />{SCOPE_LABEL[s]}</label>)}</div></fieldset>
        <label className="flex flex-col gap-1 text-[12px] font-medium text-text-secondary sm:col-span-2">Why you need it
          <textarea required rows={2} value={form.reason} onChange={e => setForm(f => ({ ...f, reason: e.target.value }))}
            placeholder="e.g. Taking over the DEV-31 investigation while Priya is away"
            className="rounded border border-border-hairline px-2 py-1.5 text-[13px] font-normal text-text-primary" /></label>
        <div className="flex justify-end sm:col-span-2"><Button type="submit" variant="primary"
          disabled={busy || !form.email.trim() || !form.reason.trim() || !form.scopes.length}>Send request</Button></div>
      </form>
    </section>

    {!!past.length && <details className="mt-4 text-[13px] text-text-secondary"><summary className="cursor-pointer">Past requests and access ({past.length})</summary>
      <ul className="mt-2 space-y-1">{past.map(g => <li key={g.grant_id}>
        {who(g.grantee_email, g.grantee_id)} → {who(g.owner_email, g.owner_id)} · {scopes(g)} · <Pill tone={TONE[g.status]}>{g.status}</Pill></li>)}</ul></details>}
  </SettingsFrame>;
}
