'use client';

import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';

/** Cloudflare Turnstile site key (public). Unset: no CAPTCHA, and Supabase must not require one. */
export const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? '';

type TurnstileApi = {
  render: (el: HTMLElement, options: Record<string, unknown>) => string;
  reset: (id?: string) => void;
  remove: (id?: string) => void;
};
declare global { interface Window { turnstile?: TurnstileApi } }

const SCRIPT = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
let loading: Promise<void> | null = null;
function load(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  loading ??= new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = SCRIPT; s.async = true; s.onload = () => resolve(); s.onerror = () => { loading = null; reject(new Error('CAPTCHA could not load')); };
    document.head.appendChild(s);
  });
  return loading;
}

export type TurnstileHandle = { reset: () => void };

/** Bot check before an anonymous demo sign-in. Usually invisible to people; tokens are single-use, so reset after a try. */
export const Turnstile = forwardRef<TurnstileHandle, { onToken: (token: string) => void; onError?: (message: string) => void }>(
  function Turnstile({ onToken, onError }, ref) {
    const box = useRef<HTMLDivElement>(null);
    const id = useRef<string | undefined>(undefined);
    const callbacks = useRef({ onToken, onError });
    callbacks.current = { onToken, onError };
    useImperativeHandle(ref, () => ({ reset: () => { callbacks.current.onToken(''); if (id.current) window.turnstile?.reset(id.current); } }), []);
    useEffect(() => {
      if (!TURNSTILE_SITE_KEY) return;
      let cancelled = false;
      load().then(() => {
        if (cancelled || !box.current || !window.turnstile) return;
        id.current = window.turnstile.render(box.current, {
          sitekey: TURNSTILE_SITE_KEY, appearance: 'interaction-only', action: 'demo-start',
          callback: (token: string) => callbacks.current.onToken(token),
          'expired-callback': () => callbacks.current.onToken(''),
          'error-callback': () => { callbacks.current.onToken(''); callbacks.current.onError?.('The bot check failed. Reload the page and try again.'); },
        });
      }).catch(e => callbacks.current.onError?.((e as Error).message));
      return () => { cancelled = true; if (id.current) window.turnstile?.remove(id.current); };
    }, []);
    return TURNSTILE_SITE_KEY ? <div ref={box} className="mt-4" /> : null;
  });
