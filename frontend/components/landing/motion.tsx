'use client';

import { useEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react';
import { cn } from '@/lib/cn';

export const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

export function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);
  return reduced;
}

/**
 * Calls `onFrame` at most once per animation frame while the page scrolls.
 * `pinned`: progress through a tall section whose child is sticky (0 when its top reaches the viewport top,
 * 1 when its bottom reaches the viewport bottom). Otherwise: progress while the element crosses the viewport.
 * The callback writes styles directly, so scrolling never re-renders React.
 */
export function useScrollFrame(ref: RefObject<HTMLElement>, onFrame: (p: number) => void, { pinned = false, enabled = true } = {}) {
  const cb = useRef(onFrame);
  cb.current = onFrame;
  useEffect(() => {
    const el = ref.current;
    if (!el || !enabled) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const r = el.getBoundingClientRect();
      const vh = window.innerHeight;
      const p = pinned ? (r.height - vh > 0 ? -r.top / (r.height - vh) : 0) : (vh - r.top) / (vh + r.height);
      cb.current(clamp(p));
    };
    const request = () => { if (!frame) frame = requestAnimationFrame(update); };
    update();
    window.addEventListener('scroll', request, { passive: true });
    window.addEventListener('resize', request);
    return () => {
      window.removeEventListener('scroll', request);
      window.removeEventListener('resize', request);
      cancelAnimationFrame(frame);
    };
  }, [ref, pinned, enabled]);
}

/** Fades and lifts children into place once, the first time they enter the viewport. */
export function Reveal({ children, className, delay = 0, as: Tag = 'div' }: { children: ReactNode; className?: string; delay?: number; as?: 'div' | 'li' | 'section' }) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) { setShown(true); io.disconnect(); } }, { rootMargin: '0px 0px -12% 0px' });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <Tag ref={ref as never} data-shown={shown || undefined} className={cn('lp-reveal', className)} style={{ '--d': `${delay}ms` } as CSSProperties}>
      {children}
    </Tag>
  );
}

/** Returns true once the element has entered the viewport. */
export function useInView<T extends HTMLElement>(margin = '0px 0px -15% 0px') {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) { setSeen(true); io.disconnect(); } }, { rootMargin: margin });
    io.observe(el);
    return () => io.disconnect();
  }, [margin]);
  return [ref, seen] as const;
}

/** Counts up to a recorded figure once visible. The final text is always the exact value. */
export function CountUp({ value, from = 0, decimals = 0, suffix = '', duration = 1400 }: { value: number; from?: number; decimals?: number; suffix?: string; duration?: number }) {
  const [ref, seen] = useInView<HTMLSpanElement>();
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(from);
  useEffect(() => {
    if (!seen) return;
    if (reduced) { setShown(value); return; }
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = clamp((now - start) / duration);
      setShown(from + (value - from) * (1 - Math.pow(1 - t, 3)));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [seen, reduced, value, from, duration]);
  const text = shown.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return (
    <span ref={ref} className="tabular-nums">
      <span aria-hidden>{text}{suffix}</span>
      <span className="sr-only">{value.toLocaleString('en-US', { minimumFractionDigits: decimals })}{suffix}</span>
    </span>
  );
}
