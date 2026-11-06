'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowRight, ClipboardCheck, FlaskConical, Gauge, Loader2, Workflow } from 'lucide-react';
import { BrandMark } from '@/components/shell/BrandMark';
import { adoptLocalDemoTenant, selectOrganization, signInAvailable, signInForDemo } from '@/lib/auth';
import { CONTACT_URL, startDemo, type Persona } from '@/lib/demo-api';
import { ProcessApiError } from '@/lib/process-api';

const PERSONAS: { id: Persona; title: string; value: string; icon: typeof Gauge }[] = [
  { id: 'process_engineer', title: 'Process Engineer', value: 'Find why a batch drifted, forecast growth and glucose, compare runs.', icon: FlaskConical },
  { id: 'msat', title: 'MSAT', value: 'Judge whether CMO data is trustworthy and what a transfer still needs.', icon: Workflow },
  { id: 'qa', title: 'Quality (QA)', value: 'Triage an overnight deviation, find precedents, prepare the review.', icon: ClipboardCheck },
  { id: 'executive', title: 'Executive', value: 'See what needs attention this week, and who owns it.', icon: Gauge },
];
const DEMO_NOTICE = 'This is a demo with synthetic data. We keep demo conversations and feedback to improve the product. Don’t enter confidential information.';

/** One click into a private demo workspace with sample data and scenarios for the chosen role. */
export default function DemoStartPage() {
  const [persona, setPersona] = useState<Persona | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [capacity, setCapacity] = useState(false);

  async function start() {
    if (!persona || !accepted) return;
    setBusy(true); setError(''); setCapacity(false);
    try {
      await signInForDemo();
      const workspace = await startDemo(persona);
      const tenant = workspace.tenant_id ?? workspace.organization_id;
      if (tenant) adoptLocalDemoTenant(tenant);
      await selectOrganization(workspace.organization_id ?? tenant ?? '');
      window.location.assign('/home/?scenarios=1');
    } catch (e) {
      if (e instanceof ProcessApiError && (e.status === 429 || e.status === 503)) setCapacity(true);
      setError((e as Error).message || 'The demo could not start. Try again in a moment.');
      setBusy(false);
    }
  }

  return <main className="min-h-screen bg-canvas px-5 py-6 sm:px-10">
    <header className="mx-auto flex max-w-5xl items-center justify-between gap-4"><BrandMark href="/" /><Link href="/" className="text-sm text-text-secondary">Back to home</Link></header>
    <div className="mx-auto max-w-5xl py-12">
      <p className="lp-eyebrow">Try it yourself · no sign-up</p>
      <h1 className="mt-4 text-3xl font-medium tracking-tight sm:text-5xl">Work a real manufacturing problem in a minute.</h1>
      <p className="mt-5 max-w-3xl text-text-secondary">Pick your role. You get a private workspace with sample batch, lab and deviation data and a few realistic scenarios to try with the assistant. Nothing from your systems is needed.</p>

      <fieldset className="mt-10">
        <legend className="mb-3 text-sm font-medium text-text-secondary">Your role</legend>
        <div className="grid gap-3 sm:grid-cols-2">{PERSONAS.map(p => <label key={p.id}
          className={`flex cursor-pointer gap-3 rounded-xl border bg-white p-5 transition-colors ${persona === p.id ? 'border-brand-teal ring-2 ring-brand-teal/20' : 'border-border-hairline hover:border-brand-teal/60'}`}>
          <input type="radio" name="persona" value={p.id} checked={persona === p.id} onChange={() => setPersona(p.id)} className="sr-only" />
          <p.icon className="mt-0.5 h-5 w-5 shrink-0 text-brand-teal" />
          <span><span className="block text-[15px] font-medium text-ink">{p.title}</span><span className="mt-1 block text-sm leading-6 text-text-secondary">{p.value}</span></span>
        </label>)}</div>
      </fieldset>

      <label className="mt-8 flex max-w-3xl items-start gap-3 rounded-lg border border-border-hairline bg-white p-4 text-sm leading-6">
        <input type="checkbox" checked={accepted} onChange={e => setAccepted(e.target.checked)} className="mt-1 h-4 w-4 shrink-0" />
        <span>{DEMO_NOTICE} <span className="text-text-tertiary">Your workspace is deleted after 24 hours.</span></span>
      </label>

      {error && <div role="alert" className="mt-5 max-w-3xl rounded-lg bg-status-critical-bg px-4 py-3 text-sm text-text-primary">{error}
        {capacity && CONTACT_URL && <> <a href={CONTACT_URL} className="font-medium text-brand-teal underline">Talk to us</a> and we’ll set one up for you.</>}</div>}
      {!signInAvailable() && <p className="mt-5 text-sm text-text-secondary">Demo workspaces aren’t available on this deployment.</p>}

      <div className="mt-6 flex flex-wrap items-center gap-4">
        <button type="button" onClick={() => void start()} disabled={!persona || !accepted || busy || !signInAvailable()} className="lp-btn lp-btn-primary disabled:opacity-40">
          {busy ? <><Loader2 className="h-4 w-4 animate-spin" />Preparing your workspace…</> : <>Start the demo<ArrowRight className="h-4 w-4" /></>}</button>
        <Link href="/demo/tour/" className="text-sm text-text-secondary underline-offset-2 hover:underline">Prefer a guided tour without the assistant?</Link>
      </div>
    </div>
  </main>;
}
