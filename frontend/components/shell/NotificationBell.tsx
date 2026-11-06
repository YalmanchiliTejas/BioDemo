'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Bell } from 'lucide-react';
import { inbox, markRead, SEVERITY_LABEL, type InboxItem } from '@/lib/alerts-api';

const DOT: Record<InboxItem['severity'], string> = { warning: 'bg-amber-400', action: 'bg-orange-500', critical: 'bg-red-600', info: 'bg-brand-teal' };
const LABEL: Record<InboxItem['severity'], string> = { ...SEVERITY_LABEL, info: 'Request' };
const when = (iso: string) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }); };

/** Deviation-signal alerts for the signed-in person. Polls every 30 s; a signal is for review, not a confirmed deviation. */
export function NotificationBell() {
  const [data, setData] = useState<{ items: InboxItem[]; unread: number } | null>(null);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const load = useCallback(() => inbox().then(setData).catch(() => undefined), []);
  useEffect(() => { void load(); const t = window.setInterval(load, 30000); return () => window.clearInterval(t); }, [load]);
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', outside); document.addEventListener('keydown', key);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', key); };
  }, [open]);
  const unread = data?.unread ?? 0;
  async function read(item: InboxItem) {
    if (!item.read_at) { try { await markRead(item.inbox_id); void load(); } catch { /* the link still opens */ } }
    setOpen(false);
  }
  return <div ref={box} className="chrome-dropdown">
    <button type="button" className="chrome-icon relative" aria-label={unread ? `Alerts: ${unread} unread` : 'Alerts'} aria-expanded={open}
      onClick={() => { setOpen(o => !o); if (!open) void load(); }}>
      <Bell size={18} />
      {unread > 0 && <span className="absolute right-1 top-1 min-w-[16px] rounded-full bg-red-600 px-1 text-center text-[10px] font-semibold leading-4 text-white">{unread > 9 ? '9+' : unread}</span>}
    </button>
    {open && <div className="chrome-popover !w-[360px]" aria-label="Alerts">
      <div className="popover-label flex items-center justify-between">Alerts{unread > 0 && <span className="normal-case tracking-normal text-text-tertiary">{unread} unread</span>}</div>
      {!data && <p role="status" className="px-3 py-2 text-xs text-text-tertiary">Loading…</p>}
      {data && !data.items.length && <p className="px-3 py-3 text-xs text-text-tertiary">No alerts. Deviation signals routed to you will appear here.</p>}
      <ul className="max-h-[420px] overflow-y-auto">{data?.items.map(item => <li key={item.inbox_id}>
        <Link href={item.link} onClick={() => void read(item)} className={`block rounded-md px-3 py-2.5 hover:bg-surface-secondary ${item.read_at ? '' : 'bg-brand-teal-light/30'}`}>
          <span className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-text-tertiary">
            <span className={`h-2 w-2 rounded-full ${DOT[item.severity]}`} aria-hidden />{LABEL[item.severity]}{item.site_id ? ` · ${item.site_id}` : ''}</span>
          <span className="mt-1 block text-[13px] font-medium text-text-primary">{item.subject?.id ? `${item.subject.kind ?? ''} ${item.subject.id}`.trim() : item.title}</span>
          <span className="mt-0.5 block text-xs text-text-secondary">{item.rule}</span>
          {item.updates.map(u => <span key={u.at} className="mt-1 block text-xs text-brand-teal">{u.text}</span>)}
          <span className="mt-1 block text-[11px] text-text-tertiary">{when(item.created_at)}{item.signal_id ? ' · signal for review, not a confirmed deviation' : ''}</span>
        </Link></li>)}</ul>
    </div>}
  </div>;
}
