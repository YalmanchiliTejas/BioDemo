'use client';

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ArrowLeft, ArrowUpRight, Check, CheckCircle2, X } from 'lucide-react';
import { GUIDE_TOPICS, useTutorial } from '@/lib/tutorial-context';

/** Contextual, non-modal guidance: no backdrop, route gates or automatic actions. */
export function WorkspaceTutorial() {
  const guide = useTutorial();
  const pathname = usePathname();
  const panel = useRef<HTMLElement>(null);
  const focusedTopic = useRef<string | null>(null);
  const [position, setPosition] = useState({ top: 80, left: 80 });
  const current = GUIDE_TOPICS.find(t => t.id === guide.topic);
  useEffect(() => {
    if (!guide.opened) { focusedTopic.current = null; return; }
    let target: HTMLElement | null = null;
    const place = () => {
      target?.classList.remove('guide-target');
      const candidates = Array.from(document.querySelectorAll<HTMLElement>(`[data-guide="${current?.target ?? 'help'}"]`));
      target = candidates.find(node => { const rect = node.getBoundingClientRect(); return rect.width > 0 && rect.left >= 0 && rect.right <= window.innerWidth && getComputedStyle(node).visibility !== 'hidden'; }) ?? document.querySelector('[data-guide="help"]');
      const rect = target?.getBoundingClientRect();
      target?.classList.add('guide-target');
      const width = Math.min(340, window.innerWidth - 32);
      const height = panel.current?.getBoundingClientRect().height ?? 390;
      const left = rect && rect.left < 300 && window.innerWidth >= 900 ? rect.right + 18 : window.innerWidth - width - 24;
      const top = rect && rect.left < 300 && window.innerWidth >= 900 ? rect.top : 78;
      setPosition({ left: Math.max(16, Math.min(left, window.innerWidth - width - 16)), top: Math.max(16, Math.min(top, window.innerHeight - height - 16)) });
    };
    place();
    const focusKey = guide.topic ?? 'all';
    if (focusedTopic.current !== focusKey) { panel.current?.focus({ preventScroll: true }); focusedTopic.current = focusKey; }
    const resize = new ResizeObserver(place);
    if (panel.current) resize.observe(panel.current);
    const navigation = document.getElementById('workspace-navigation');
    const mutation = new MutationObserver(place);
    if (navigation) mutation.observe(navigation, { childList: true, subtree: true });
    window.addEventListener('resize', place); window.addEventListener('scroll', place, true);
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape') { guide.close(); document.querySelector<HTMLButtonElement>('[data-guide="help"]')?.focus({ preventScroll: true }); } };
    window.addEventListener('keydown', escape);
    return () => { target?.classList.remove('guide-target'); resize.disconnect(); mutation.disconnect(); window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true); window.removeEventListener('keydown', escape); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guide.opened, guide.topic, pathname]);
  if (!guide.opened) return null;
  const dismiss = () => { guide.close(); document.querySelector<HTMLButtonElement>('[data-guide="help"]')?.focus(); };
  return createPortal(<aside ref={panel} tabIndex={-1} role="dialog" aria-modal="false" aria-label="Workspace guide" className="workspace-guide" style={position}>
    <div className="guide-heading"><span>YOUR WORKSPACE GUIDE</span><button type="button" className="chrome-icon" aria-label="Close guide" onClick={dismiss}><X size={17} /></button></div>
    {current ? <>
      <button type="button" className="guide-back" onClick={() => guide.open()}><ArrowLeft size={14} /> All topics</button>
      <h2>{current.title}</h2><p>{current.body}</p>
      <Link className="guide-open" href={current.href}>Open {current.id === 'connections' ? 'connections' : current.id} <ArrowUpRight size={15} /></Link>
      <div className="guide-actions"><button type="button" className="chrome-button primary" onClick={() => { guide.markSeen(current.id); guide.open(); }}><Check size={15} /> Got it</button><button type="button" className="chrome-button" onClick={dismiss}>Explore on my own</button></div>
    </> : <><h2>A little help, when you need it.</h2><p>Pick any topic. Keep working while the guide is open.</p><ul className="guide-topics">{GUIDE_TOPICS.map(topic => <li key={topic.id}><button type="button" onClick={() => guide.open(topic.id)}><span className={guide.seen.includes(topic.id) ? 'guide-check seen' : 'guide-check'}><CheckCircle2 size={16} /></span>{topic.label}<ArrowUpRight size={14} /></button></li>)}</ul><small>{guide.seen.length} of {GUIDE_TOPICS.length} topics explored · You choose the order</small></>}
  </aside>, document.body);
}
