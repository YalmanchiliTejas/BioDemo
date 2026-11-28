'use client';

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { LocateFixed, MousePointer2, Volume2, VolumeX, X } from 'lucide-react';

const gutter = 16;
const gap = 22;

function findAnchor(name: string | undefined) {
  if (!name) return null;
  const node = document.querySelector<HTMLElement>(`[data-guide="${name}"]`);
  return node?.getClientRects().length && getComputedStyle(node).visibility === 'visible' ? node : null;
}

function visibleRect(node: HTMLElement | null) {
  if (!node) return null;
  const rect = node.getBoundingClientRect();
  const clip = node.closest('.sidebar-nav, #main')?.getBoundingClientRect();
  const top = Math.max(0, clip?.top ?? 0);
  const bottom = Math.min(window.innerHeight, clip?.bottom ?? window.innerHeight);
  return rect.width && rect.height && rect.top >= top && rect.bottom <= bottom &&
    rect.left >= 0 && rect.right <= window.innerWidth ? rect : null;
}

function placePanel(panel: HTMLElement, target: DOMRect | null) {
  const { width, height } = panel.getBoundingClientRect();
  const right = window.innerWidth - gutter;
  const bottom = window.innerHeight - gutter;
  let x = right - width;
  let y = 72;
  if (target) {
    if (target.right + gap + width <= right) {
      x = target.right + gap;
      y = target.top;
    } else if (target.left - gap - width >= gutter) {
      x = target.left - gap - width;
      y = target.top;
    } else {
      x = target.left;
      const below = bottom - target.bottom;
      const above = target.top - gutter;
      y = above >= height + gap || above > below ? target.top - height - gap : target.bottom + gap;
    }
  }
  const left = Math.max(gutter, Math.min(x, right - width));
  panel.style.left = `${left}px`;
  panel.style.top = `${Math.max(gutter, Math.min(y, bottom - height))}px`;
  return left;
}

function GuideNarration({ text }: { text: string }) {
  const utterance = useRef<SpeechSynthesisUtterance | null>(null);
  const [playing, setPlaying] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => () => {
    if (utterance.current) {
      utterance.current = null;
      window.speechSynthesis.cancel();
    }
  }, []);
  if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) return null;
  const read = () => {
    const speech = window.speechSynthesis;
    if (utterance.current) {
      utterance.current = null;
      speech.cancel();
      setPlaying(false);
      return;
    }
    const next = new SpeechSynthesisUtterance(text);
    const localVoice = speech.getVoices().find(voice => voice.localService && /^en\b/i.test(voice.lang));
    if (localVoice) next.voice = localVoice;
    next.lang = localVoice?.lang ?? 'en-US';
    const finish = (error: boolean) => {
      if (utterance.current !== next) return;
      utterance.current = null;
      setPlaying(false);
      setFailed(error);
    };
    next.onend = () => finish(false);
    next.onerror = () => finish(true);
    utterance.current = next;
    setFailed(false);
    setPlaying(true);
    try { speech.speak(next); } catch { finish(true); }
  };
  return <div className="guide-tool">
    <button type="button" onClick={read}>{playing ? <VolumeX size={15} /> : <Volume2 size={15} />}{playing ? 'Stop reading' : 'Read aloud'}</button>
    {failed && <small role="status">Audio is unavailable in this browser.</small>}
  </div>;
}

export function PointingGuide({ label, anchor, focusKey, narration, locate, reveal, onClose, children }: {
  label: string;
  anchor?: string;
  focusKey?: string;
  narration?: string;
  locate?: boolean;
  reveal?: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLElement>(null);
  const cursorRef = useRef<HTMLDivElement>(null);
  const locateRef = useRef<HTMLButtonElement>(null);

  useLayoutEffect(() => {
    const panel = panelRef.current!;
    const cursor = cursorRef.current!;
    let highlighted: HTMLElement | null = null;
    let observed: HTMLElement | null = null;
    let revealPending = reveal;
    let frame = 0;
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(place);
    };
    const resize = new ResizeObserver(schedule);
    function place() {
      frame = 0;
      const node = findAnchor(anchor);
      let rect = visibleRect(node);
      if (node && revealPending) {
        revealPending = false;
        if (!rect) {
          node.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
          rect = visibleRect(node);
        }
      }
      if (observed !== node) {
        if (observed) resize.unobserve(observed);
        observed = node;
        if (node) resize.observe(node);
      }
      const target = rect ? node : null;
      if (highlighted !== target) {
        highlighted?.classList.remove('guide-target');
        highlighted = target;
        highlighted?.classList.add('guide-target');
      }
      const panelLeft = placePanel(panel, rect);
      cursor.hidden = !rect;
      if (rect) {
        const left = Math.min(rect.right - 8, Math.max(rect.left + 8, panelLeft + 42), window.innerWidth - 33);
        const top = Math.min(rect.bottom - 6, window.innerHeight - 33);
        cursor.style.transform = `translate3d(${left}px, ${top}px, 0)`;
      }
      if (locateRef.current) locateRef.current.hidden = !node;
    }
    place();
    resize.observe(panel);
    const scope = document.querySelector('.workspace-app, .setup-main');
    const mutation = new MutationObserver(schedule);
    if (scope) mutation.observe(scope, { childList: true, subtree: true, attributes: true, attributeFilter: ['open'] });
    window.addEventListener('resize', schedule);
    window.addEventListener('scroll', schedule, { capture: true, passive: true });
    return () => {
      cancelAnimationFrame(frame);
      highlighted?.classList.remove('guide-target');
      resize.disconnect();
      mutation.disconnect();
      window.removeEventListener('resize', schedule);
      window.removeEventListener('scroll', schedule, true);
    };
  }, [anchor, locate, reveal]);

  useEffect(() => {
    panelRef.current?.focus({ preventScroll: true });
  }, [focusKey]);

  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.defaultPrevented) onClose();
    };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [onClose]);

  const showControl = () => {
    const target = findAnchor(anchor);
    target?.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
    target?.focus({ preventScroll: true });
  };

  return createPortal(<>
    <div ref={cursorRef} className="guide-pointer" aria-hidden="true" hidden><MousePointer2 size={25} /></div>
    <aside ref={panelRef} tabIndex={-1} role="dialog" aria-modal="false" aria-label={label} className="workspace-guide">
      <div className="guide-heading">
        <span><MousePointer2 size={15} />{label}</span>
        <button type="button" className="chrome-icon" aria-label="Close guide" onClick={onClose}><X size={17} /></button>
      </div>
      {children}
      {(locate || narration) && <div className="guide-tools">
        {locate && <button ref={locateRef} type="button" onClick={showControl}><LocateFixed size={15} /> Find on page</button>}
        {narration && <GuideNarration key={narration} text={narration} />}
      </div>}
    </aside>
  </>, document.body);
}
