'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { CornerDownLeft, HelpCircle, MessageSquare, Plus, Search, type LucideIcon } from 'lucide-react';
import { NAV_GROUPS } from '@/lib/navigation';

type Result = { id: string; group: string; label: string; detail: string; icon: LucideIcon; terms: string; run: () => void };

/** Jump to a destination or start a common action. Lists only places that exist in the navigation. */
export function QuickFind({ open, onClose, onGuide, onAssistant }: { open: boolean; onClose: () => void; onGuide: () => void; onAssistant: () => void }) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const results = useMemo<Result[]>(() => {
    const go = (href: string) => () => router.push(`${href}/`);
    const all: Result[] = [
      { id: 'new-delivery', group: 'Actions', label: 'Check a new delivery', detail: 'Upload CMO files as received', icon: Plus, terms: 'upload new delivery cmo files', run: go('/cmo') },
      { id: 'ask', group: 'Actions', label: 'Ask the assistant', detail: 'Open the companion beside this page', icon: MessageSquare, terms: 'ask chat question companion', run: onAssistant },
      { id: 'guide', group: 'Actions', label: 'Open the workspace guide', detail: 'Short topics, at your pace', icon: HelpCircle, terms: 'help guide tour tutorial', run: onGuide },
      ...NAV_GROUPS.flatMap(group => group.items.map(item => ({ id: item.href, group: 'Pages', label: item.label, detail: `${group.label} · ${item.description}`, icon: item.icon, terms: `${item.label} ${group.label} ${item.description} ${item.keywords ?? ''}`, run: go(item.href) }))),
    ];
    const term = query.trim().toLowerCase();
    return term ? all.filter(result => result.terms.toLowerCase().includes(term)) : all;
  }, [query, router, onAssistant, onGuide]);
  useEffect(() => {
    if (!open) return;
    returnFocus.current = document.activeElement as HTMLElement | null;
    setQuery(''); setIndex(0);
    requestAnimationFrame(() => input.current?.focus());
    return () => returnFocus.current?.focus?.();
  }, [open]);
  useEffect(() => setIndex(0), [query]);
  if (!open) return null;
  const choose = (result?: Result) => { if (!result) return; onClose(); result.run(); };
  return <div className="quick-find-layer">
    <div className="quick-find-scrim" onClick={onClose} aria-hidden />
    <div role="dialog" aria-modal="true" aria-label="Search pages and actions" className="quick-find">
      <label className="quick-find-input"><Search size={16} /><input ref={input} value={query} onChange={e => setQuery(e.target.value)} role="combobox" aria-expanded="true" aria-controls="quick-find-results" aria-activedescendant={results[index] ? `quick-find-${results[index].id}` : undefined} aria-label="Search pages and actions" placeholder="Search pages and actions…"
        onKeyDown={e => {
          if (e.key === 'Escape') { e.preventDefault(); onClose(); }
          if (e.key === 'ArrowDown') { e.preventDefault(); setIndex(i => Math.min(i + 1, results.length - 1)); }
          if (e.key === 'ArrowUp') { e.preventDefault(); setIndex(i => Math.max(i - 1, 0)); }
          if (e.key === 'Enter') { e.preventDefault(); choose(results[index]); }
        }} /><kbd>Esc</kbd></label>
      <ul id="quick-find-results" role="listbox" aria-label="Results" className="quick-find-results">
        {!results.length && <li className="quick-find-empty">No pages or actions match “{query.trim()}”.</li>}
        {results.map((result, i) => <li key={result.id} role="presentation">
          {(i === 0 || results[i - 1].group !== result.group) && <p className="quick-find-group">{result.group}</p>}
          <button type="button" role="option" id={`quick-find-${result.id}`} aria-selected={i === index} tabIndex={-1} onMouseMove={() => setIndex(i)} onClick={() => choose(result)}>
            <result.icon size={16} strokeWidth={1.75} /><span><strong>{result.label}</strong><small>{result.detail}</small></span>{i === index && <CornerDownLeft size={14} />}
          </button>
        </li>)}
      </ul>
    </div>
  </div>;
}
