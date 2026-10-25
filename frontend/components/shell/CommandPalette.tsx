'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { CornerDownLeft, Search } from 'lucide-react';
import { SCREENS } from '@/lib/routes';
import { cn } from '@/lib/cn';

const ENTITIES = [
  { id: 'MES-26073', title: 'Batch MES-26073 · in execution, QA hold', href: '/batches/MES-26073' },
  { id: 'PM-204', title: 'Feed pump PM-204 · head pressure alert', href: '/equipment/PM-204' },
  { id: 'Q-DEV-031', title: 'Deviation Q-DEV-031 · major tier 2', href: '/quality/Q-DEV-031' },
  { id: 'QC-948', title: 'Sample QC-948 · titer out of trend', href: '/laboratory/QC-948' },
  { id: 'INV-104', title: 'Investigation INV-104 · yield decline', href: '/investigations/INV-104' },
  { id: 'TT-006', title: 'Tech transfer TT-006 · Gate 2 blocker', href: '/tech-transfer/TT-006' },
  { id: 'WO-8819', title: 'Work order WO-8819 · clamp torque adjustment', href: '/equipment/PM-204' },
  { id: 'SOP-UP-014', title: 'SOP-UP-014 Rev 7 · feed pump operation', href: '/knowledge' },
];

/** FIND mode of the global command overlay: jump to records and screens. */
export function FindPanel({ onClose, onAsk }: { onClose: () => void; onAsk: (text: string) => void }) {
  const router = useRouter();
  const [q, setQ] = useState('');
  const [idx, setIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const results = useMemo(() => {
    const term = q.trim().toLowerCase();
    const all = [
      ...ENTITIES.map((e) => ({ group: 'Records', key: e.id, label: e.title, code: e.id, href: e.href })),
      ...SCREENS.map((s) => ({ group: 'Screens', key: s.id, label: s.title, code: s.id, href: s.href, kw: s.keywords })),
    ];
    if (!term) return all;
    return all.filter((r) => `${r.label} ${r.code} ${r.href} ${'kw' in r ? r.kw ?? '' : ''}`.toLowerCase().includes(term));
  }, [q]);

  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 0);
  }, []);

  useEffect(() => setIdx(0), [q]);

  const go = (href: string) => {
    onClose();
    router.push(href);
  };

  return (
    <>
      <div className="flex items-center gap-2 px-3 border-b border-border-hairline">
        <Search className="h-4 w-4 text-text-tertiary" aria-hidden />
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') onClose();
            if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((i) => Math.min(i + 1, results.length - 1)); }
            if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
            if (e.key === 'Enter') { if (results[idx]) go(results[idx].href); else if (q.trim()) onAsk(q.trim()); }
          }}
          placeholder="Jump to a batch, equipment tag, deviation or screen…"
          className="flex-1 h-11 bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none"
          aria-label="Search"
        />
        <kbd className="text-[10px] font-mono text-text-tertiary border border-border-hairline rounded px-1">ESC</kbd>
      </div>
      <ul className="max-h-[52vh] overflow-y-auto py-1" role="listbox">
        {results.length === 0 && (
          <li className="px-4 py-5 text-center text-xs text-text-tertiary">
            No matching records or screens.
            {q.trim() && <button type="button" onClick={() => onAsk(q.trim())} className="block mx-auto mt-2 text-[12.5px] text-brand-teal hover:underline">Ask the agent: “{q.trim()}” →</button>}
          </li>
        )}
        {results.map((r, i) => (
          <li key={r.group + r.key} role="option" aria-selected={i === idx}>
            {(i === 0 || results[i - 1].group !== r.group) && (
              <p className="px-3 pt-2 pb-1 text-[10.5px] font-semibold uppercase tracking-wider text-text-muted">{r.group}</p>
            )}
            <button
              onMouseEnter={() => setIdx(i)}
              onClick={() => go(r.href)}
              className={cn('w-full flex items-center gap-3 px-3 py-2 text-left text-[13px]', i === idx ? 'bg-brand-teal-light' : '')}
            >
              <code className="w-24 shrink-0 text-[11px] font-mono text-text-tertiary">{r.code}</code>
              <span className="flex-1 truncate text-text-primary">{r.label}</span>
              {i === idx && <CornerDownLeft className="h-3.5 w-3.5 text-text-tertiary" aria-hidden />}
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
