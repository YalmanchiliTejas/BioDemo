'use client';

import { useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { usePathname } from 'next/navigation';
import { ArrowUpRight, Loader2, Maximize2, Minimize2, X } from 'lucide-react';
import { useCompanion, type DisplayContext } from '@/lib/companion-context';
import { useAppContext } from '@/lib/app-context';
import { SCREENS } from '@/lib/routes';

const EngineeringChat = dynamic(() => import('../process/EngineeringChat').then(m => m.EngineeringChat), {
  loading: () => <p className="p-8 text-sm text-text-tertiary">Opening your companion…</p>,
});

export function Companion({ home }: { home: boolean }) {
  const { open, expanded, busy, show, close, setExpanded } = useCompanion();
  const { isInspectorOpen, closeInspector } = useAppContext();
  const [activated, setActivated] = useState(home || open);
  const panel = useRef<HTMLElement>(null);
  const launcher = useRef<HTMLButtonElement>(null);
  const visible = home || (open && !isInspectorOpen);
  useEffect(() => { if (home || open) setActivated(true); }, [home, open]);
  useEffect(() => {
    if (visible && !home) panel.current?.querySelector<HTMLTextAreaElement>('textarea')?.focus();
  }, [visible, home]);
  function dismiss() { close(); launcher.current?.focus(); }

  return <>
    <section ref={panel} hidden={!visible} aria-label="Work companion" data-testid="work-companion"
      onKeyDown={e => { if (e.key === 'Escape' && !home) { e.stopPropagation(); dismiss(); } }}
      className={home ? 'companion-home' : `companion-panel ${expanded ? 'companion-panel-expanded' : ''}`}>
      {!home && <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border-hairline px-5 py-3">
        <div className="flex items-center gap-2.5"><span className="companion-mark" aria-hidden /><div><h2 className="text-sm font-medium">Your companion</h2><p className="text-[11px] text-text-tertiary">Here with you in Sievance</p></div></div>
        <div className="flex gap-1"><button type="button" onClick={() => setExpanded(!expanded)} className="companion-icon-button" aria-label={expanded ? 'Reduce companion' : 'Expand companion'}>{expanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}</button><button type="button" onClick={dismiss} className="companion-icon-button" aria-label="Minimize companion"><X size={17} /></button></div>
      </div>}
      <div className={home ? '' : 'min-h-0 flex-1 overflow-y-auto'}>
        {activated && <EngineeringChat companion compact={!home} />}
      </div>
    </section>
    {!home && <button ref={launcher} type="button" onClick={() => { if (visible) dismiss(); else { closeInspector(); show(); } }}
      className="companion-launcher" aria-label={visible ? 'Minimize companion' : 'Open companion'} aria-expanded={visible}>
      {busy ? <Loader2 size={18} className="motion-safe:animate-spin" /> : <span className="companion-mark" aria-hidden />}
      <span>{busy ? 'Working with you' : 'Companion'}</span><kbd className="hidden sm:inline text-[10px] opacity-60">⌘J</kbd>
    </button>}
    <SelectionAction />
  </>;
}

function SelectionAction() {
  const pathname = usePathname();
  const { show } = useCompanion();
  const { closeInspector } = useAppContext();
  const [candidate, setCandidate] = useState<{ context: DisplayContext; x: number; y: number } | null>(null);
  useEffect(() => {
    setCandidate(null);
    const read = () => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || !selection.rangeCount) { setCandidate(null); return; }
      const range = selection.getRangeAt(0);
      const node = range.commonAncestorContainer;
      const element = node.nodeType === Node.ELEMENT_NODE ? node as Element : node.parentElement;
      if (!element?.closest('#main') || element.closest('input, textarea, [contenteditable="true"], [data-testid="work-companion"]')) {
        setCandidate(null); return;
      }
      const text = selection.toString().trim();
      if (text.length < 3) { setCandidate(null); return; }
      const rect = range.getBoundingClientRect();
      setCandidate({
        context: { kind: 'text', label: SCREENS.find(s => s.href === pathname.replace(/\/$/, ''))?.title ?? document.title,
          page_path: pathname, captured_at: new Date().toISOString(), content: text.length > 120000
            ? text.slice(0, 119900) + '\n[Selection truncated. Highlight a smaller passage to share it in full.]' : text },
        x: Math.max(12, Math.min(window.innerWidth - 174, rect.left + rect.width / 2 - 78)),
        y: Math.max(12, Math.min(window.innerHeight - 52, rect.bottom + 8)),
      });
    };
    const key = (e: KeyboardEvent) => { if (e.key === 'Shift' || e.key.startsWith('Arrow')) read(); if (e.key === 'Escape') setCandidate(null); };
    const clear = () => setCandidate(null);
    const selectionChanged = () => { if (window.getSelection()?.isCollapsed) clear(); };
    document.addEventListener('mouseup', read);
    document.addEventListener('keyup', key);
    document.addEventListener('selectionchange', selectionChanged);
    // Scroll changes selection geometry; dismiss instead of leaving a detached action.
    window.addEventListener('scroll', clear, true);
    return () => { document.removeEventListener('mouseup', read); document.removeEventListener('keyup', key); document.removeEventListener('selectionchange', selectionChanged); window.removeEventListener('scroll', clear, true); };
  }, [pathname]);
  if (!candidate) return null;
  return <button type="button" className="selection-action" style={{ left: candidate.x, top: candidate.y }}
    onMouseDown={e => e.preventDefault()} onClick={() => { closeInspector(); show(candidate.context); setCandidate(null); window.getSelection()?.removeAllRanges(); }}>
    <span className="companion-mark" aria-hidden />Ask about this<ArrowUpRight size={14} />
  </button>;
}
