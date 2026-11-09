'use client';

import Link from 'next/link';
import { FlaskConical } from 'lucide-react';
import { CONTACT_URL, hoursLeft, PERSONA_LABEL, useDemo } from '@/lib/demo-api';

/** A thin strip in demo workspaces: synthetic data, time and messages left, and a way to talk to us. */
export function DemoBanner() {
  const { demo, expired } = useDemo();
  if (expired) return <DemoExpired />;
  if (!demo) return null;
  const hours = hoursLeft(demo.expires_at);
  const limit = demo.message_limit ?? 20;
  const left = demo.messages_left ?? Math.max(0, limit - (demo.messages_used ?? 0));
  return <div role="note" className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-brand-teal/20 bg-brand-teal-light/60 px-4 py-1.5 text-[12px] text-text-secondary">
    <span className="inline-flex items-center gap-1.5 font-medium text-brand-teal"><FlaskConical size={13} />Demo workspace{demo.persona ? ` · ${PERSONA_LABEL[demo.persona] ?? demo.persona}` : ''}</span>
    <span>Sample data + optional uploads</span>
    <Link href="/cmo/" className="font-medium text-brand-teal underline">Try your own delivery</Link>
    <Link href="/process-simulation/" className="font-medium text-brand-teal underline">Try the model library</Link>
    {hours != null && <span>Access expires in {hours} h</span>}
    <span className={left <= 3 ? 'font-medium text-status-warning' : ''}>{left} of {limit} messages left</span>
    {CONTACT_URL && <a href={CONTACT_URL} target="_blank" rel="noreferrer" className="font-medium text-brand-teal underline-offset-2 hover:underline">Talk to us</a>}
  </div>;
}

function DemoExpired() {
  return <div role="alert" className="fixed inset-0 z-[95] flex items-center justify-center bg-canvas p-6">
    <div className="max-w-md text-center">
      <h1 className="text-2xl font-medium text-ink">This demo workspace has expired</h1>
      <p className="mt-3 text-sm leading-6 text-text-secondary">Demo workspace access expires after 24 hours. You can start a fresh one in a click.</p>
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <Link href="/demo/" className="rounded-control bg-brand-teal px-4 py-2 text-sm font-medium text-white hover:bg-brand-teal-dark">Start a new demo</Link>
        {CONTACT_URL && <a href={CONTACT_URL} className="rounded-control border border-border-hairline px-4 py-2 text-sm text-text-primary hover:border-brand-teal">Talk to us</a>}
      </div>
    </div>
  </div>;
}
