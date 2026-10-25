'use client';

import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { ArrowRight, Check, Database, FileSearch, Fingerprint, Minus, PlugZap, ShieldCheck, Signature, Workflow, Zap } from 'lucide-react';
import { BrandMark } from '@/components/shell/BrandMark';
import { Button, Modal, Pill, buttonClass, useDisclosure } from '@/components/ui';
import { StandaloneEvidence } from '@/components/screens/a/StandaloneEvidence';
import { WorkbenchPreview } from '@/components/screens/a/WorkbenchPreview';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

const NAV = [
  { href: '#architecture', label: 'Architecture' },
  { href: '#principles', label: 'Principles' },
  { href: '#connectors', label: 'Connectors' },
  { href: '#validation', label: 'Validation' },
];

const ARCH = [
  {
    icon: Database,
    title: 'Works with your systems of record',
    body: 'Reads from MES, historians, LIMS, QMS and CMMS through scoped service accounts. Nothing is migrated; your existing systems stay authoritative.',
    points: ['No data migration', 'Reusable connectors, independent of any screen', 'Mappings confirmed once, reused after'],
  },
  {
    icon: FileSearch,
    title: 'Evidence you can verify',
    body: 'Every finding links to the raw source excerpt with its system, timestamp, transformation and SHA-256 content hash.',
    points: ['Observation, calculation, hypothesis and proposal labelled separately', 'Gaps and stale data shown, not smoothed over', 'Reproducible intake manifests'],
  },
  {
    icon: ShieldCheck,
    title: 'Read-only by default, humans approve',
    body: 'No write path to DCS/PLC or MES. Proposals stay proposals until a named, authorized person signs them in your existing workflow.',
    points: ['Read-only scopes as the default boundary', 'Air-gapped deployment option', 'Agent proposals are never approved actions'],
  },
];

const PROMISES = [
  { icon: Zap, title: 'Easy to start', body: 'Begin with a question, an event or the data you already have. The product asks only what it cannot work out itself, when it needs to know.' },
  { icon: Fingerprint, title: 'Easy to trust', body: 'See where each claim came from, what supports or contradicts it, and what is still unknown — without wading through it by default.' },
  { icon: Signature, title: 'Easy to act', body: 'Findings arrive with specific next steps: rationale, owner, required approval, and the evidence that would change the recommendation.' },
  { icon: Workflow, title: 'Easy to adopt', body: 'Fits around current systems, roles and approval paths. Simple by default, with deeper tools for those who need them.' },
];

const CONNECTORS: Array<{ vendor: string; product: string; kind: string; demo: 'SIMULATED' | 'NOT_IN_DEMO' }> = [
  { vendor: 'Emerson', product: 'DeltaV eBR', kind: 'MES / batch record', demo: 'SIMULATED' },
  { vendor: 'AVEVA OSIsoft', product: 'PI System', kind: 'Historian', demo: 'SIMULATED' },
  { vendor: 'Rockwell', product: 'FactoryTalk', kind: 'MES / historian', demo: 'NOT_IN_DEMO' },
  { vendor: 'LabWare', product: 'LIMS', kind: 'Laboratory', demo: 'SIMULATED' },
  { vendor: 'Veeva', product: 'Vault QMS', kind: 'Quality', demo: 'SIMULATED' },
  { vendor: 'SAP', product: 'S/4HANA', kind: 'ERP', demo: 'NOT_IN_DEMO' },
  { vendor: 'IBM', product: 'Maximo', kind: 'Maintenance', demo: 'SIMULATED' },
];

const VALIDATION: Array<{ item: string; state: 'yes' | 'partial' | 'no'; note: string }> = [
  { item: 'Audit trail of actions, model/tool versions and reviews', state: 'yes', note: 'Designed to support 21 CFR Part 11 workflows' },
  { item: 'Named electronic signatures for consequential actions', state: 'yes', note: 'Signature meaning recorded with each approval' },
  { item: 'Supplier documentation for GAMP 5 Category 4 validation', state: 'partial', note: 'In preparation' },
  { item: 'Issued validation package (IQ/OQ templates, trace matrix)', state: 'no', note: 'Not yet issued' },
];

export default function LandingPage() {
  const briefing = useDisclosure();
  const { notify } = useAppContext();
  const [form, setForm] = useState({ name: '', email: '', company: '', role: '' });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    notify('Thanks — this is a demo, so nothing was sent and no data was stored.', 'info');
    setForm({ name: '', email: '', company: '', role: '' });
    briefing.onClose();
  };

  const inputCls = 'mt-1 w-full h-9 px-3 rounded-control border border-slate-300 bg-white text-[13px] text-slate-900 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700';

  return (
    <>
      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur border-b border-slate-200">
        <div className="max-w-[1200px] mx-auto h-14 px-4 md:px-6 flex items-center gap-6">
          <BrandMark href="/" />
          <nav aria-label="Page sections" className="hidden md:flex items-center gap-5 text-[13px] text-slate-600">
            {NAV.map((n) => <a key={n.href} href={n.href} className="hover:text-slate-900">{n.label}</a>)}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <Link href="/sign-in" className="hidden sm:inline-flex h-8 items-center px-3 text-[13px] font-medium text-slate-700 hover:text-slate-900">Sign in</Link>
            <Link href="/sign-in" className={buttonClass('primary', 'md')}>Explore interactive demo</Link>
          </div>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="max-w-[1200px] mx-auto px-4 md:px-6 pt-14 md:pt-20 pb-14 grid grid-cols-1 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] gap-10 items-center">
          <div>
            <Pill tone="brand">For biologics MSAT, QA and manufacturing teams</Pill>
            <h1 className="mt-4 text-[34px] md:text-[42px] leading-[1.1] font-semibold tracking-tight text-slate-900">
              Manufacturing intelligence that shows its evidence.
            </h1>
            <p className="mt-4 text-[15px] leading-relaxed text-slate-600 max-w-[520px]">
              Connect the historian, batch records, LIMS and quality systems you already run. Get findings you can trace to the source record, with clear next steps that a named person approves.
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              <Link href="/sign-in" className={buttonClass('primary', 'lg')}>Explore Interactive Demo <ArrowRight className="h-4 w-4" aria-hidden /></Link>
              <Button variant="secondary" size="lg" onClick={briefing.onOpen}>Request Technical Briefing</Button>
            </div>
            <ul className="mt-6 space-y-1.5 text-[12.5px] text-slate-600">
              {['Read-only by default — no writes to MES, DCS/PLC, LIMS or QMS', 'Every claim links to a hashed source excerpt', 'Proposals are never actions until a human signs'].map((t) => (
                <li key={t} className="flex gap-2"><Check className="h-4 w-4 text-cyan-700 shrink-0" aria-hidden />{t}</li>
              ))}
            </ul>
          </div>
          <div>
            <WorkbenchPreview />
            <p className="mt-2 text-[11px] text-slate-500 text-center">Live preview with synthetic data. Hover the plots; click the evidence chip to open its source.</p>
          </div>
        </section>

        {/* Architecture */}
        <section id="architecture" className="border-t border-slate-200 bg-slate-50/70 scroll-mt-14">
          <div className="max-w-[1200px] mx-auto px-4 md:px-6 py-16">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-cyan-700">Architecture</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 max-w-2xl">Built to sit beside the systems you validated, not replace them.</h2>
            <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-4">
              {ARCH.map((a) => (
                <article key={a.title} className="rounded-card border border-slate-200 bg-white p-5">
                  <span className="h-9 w-9 rounded-control bg-cyan-50 text-cyan-700 flex items-center justify-center"><a.icon className="h-[18px] w-[18px]" aria-hidden /></span>
                  <h3 className="mt-3 text-[15px] font-semibold text-slate-900">{a.title}</h3>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-slate-600">{a.body}</p>
                  <ul className="mt-3 space-y-1 text-[12.5px] text-slate-700">
                    {a.points.map((p) => <li key={p} className="flex gap-2"><span className="mt-[7px] h-1 w-1 rounded-full bg-cyan-700 shrink-0" aria-hidden />{p}</li>)}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* Four pillars */}
        <section id="principles" className="border-t border-slate-200 scroll-mt-14">
          <div className="max-w-[1200px] mx-auto px-4 md:px-6 py-16">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-cyan-700">What we promise</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 max-w-2xl">Four principles every feature is held to.</h2>
            <p className="mt-2 text-[14px] text-slate-600 max-w-2xl">They are joint constraints: faster output that is hard to audit, or a clever agent that needs weeks of configuration, does not count as progress.</p>
            <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-px bg-slate-200 rounded-card overflow-hidden border border-slate-200">
              {PROMISES.map((p, i) => (
                <article key={p.title} className="bg-white p-5">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono text-slate-400">0{i + 1}</span>
                    <p.icon className="h-4 w-4 text-cyan-700" aria-hidden />
                  </div>
                  <h3 className="mt-3 text-[15px] font-semibold text-slate-900">{p.title}</h3>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-slate-600">{p.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* Connectors */}
        <section id="connectors" className="border-t border-slate-200 bg-slate-50/70 scroll-mt-14">
          <div className="max-w-[1200px] mx-auto px-4 md:px-6 py-16">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-cyan-700">Connectors</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">Read-only connectors for common plant systems.</h2>
                <p className="mt-2 text-[14px] text-slate-600 max-w-2xl">Status below describes this public demo. Simulated connectors behave like live ones against synthetic records; no real system is contacted.</p>
              </div>
              <div className="flex gap-2 text-[11px]">
                <Pill tone="brand" dot>Simulated in demo</Pill>
                <Pill tone="muted">Not shown in demo</Pill>
              </div>
            </div>
            <ul className="mt-8 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3">
              {CONNECTORS.map((c) => (
                <li key={c.vendor} className={cn('rounded-card border bg-white p-3.5', c.demo === 'SIMULATED' ? 'border-slate-200' : 'border-dashed border-slate-300')}>
                  <PlugZap className={cn('h-4 w-4', c.demo === 'SIMULATED' ? 'text-cyan-700' : 'text-slate-400')} aria-hidden />
                  <p className="mt-2 text-[13px] font-semibold text-slate-900">{c.vendor}</p>
                  <p className="text-[12px] text-slate-600">{c.product}</p>
                  <p className="text-[11px] text-slate-400">{c.kind}</p>
                  <p className={cn('mt-2 text-[10.5px] font-medium', c.demo === 'SIMULATED' ? 'text-cyan-700' : 'text-slate-400')}>
                    {c.demo === 'SIMULATED' ? 'Simulated in demo' : 'Not shown in demo'}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Validation */}
        <section id="validation" className="border-t border-slate-200 scroll-mt-14">
          <div className="max-w-[1200px] mx-auto px-4 md:px-6 py-16 grid grid-cols-1 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] gap-10">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-cyan-700">Validation readiness</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">Built to support GAMP 5 Category 4 validation.</h2>
              <p className="mt-3 text-[14px] leading-relaxed text-slate-600">
                The validation package has <span className="font-semibold text-slate-900">not yet been issued</span>. We will not describe the product as qualified or compliant; compliance depends on how your organization validates and operates it.
              </p>
            </div>
            <div className="rounded-card border border-slate-200 overflow-hidden">
              <table className="w-full text-[13px]">
                <caption className="sr-only">Validation readiness status</caption>
                <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                  <tr><th className="text-left font-semibold px-4 py-2.5">Capability</th><th className="text-left font-semibold px-4 py-2.5">Status</th></tr>
                </thead>
                <tbody>
                  {VALIDATION.map((v) => (
                    <tr key={v.item} className="border-t border-slate-200">
                      <td className="px-4 py-3 text-slate-800">{v.item}</td>
                      <td className="px-4 py-3">
                        <span className={cn('inline-flex items-center gap-1.5 text-[12px] font-medium whitespace-nowrap', v.state === 'yes' ? 'text-emerald-700' : v.state === 'partial' ? 'text-amber-700' : 'text-slate-500')}>
                          {v.state === 'yes' ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Minus className="h-3.5 w-3.5" aria-hidden />}
                          {v.note}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* Closing CTA */}
        <section className="border-t border-slate-200 bg-slate-900">
          <div className="max-w-[1200px] mx-auto px-4 md:px-6 py-14 flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div>
              <h2 className="text-xl font-semibold text-white">See it on a synthetic fed-batch campaign.</h2>
              <p className="mt-1 text-[14px] text-slate-300">Three batches, a yield decline, a historian gap and an open deviation. No account needed.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link href="/sign-in" className={buttonClass('primary', 'lg', 'bg-cyan-600 hover:bg-cyan-500')}>Explore Interactive Demo <ArrowRight className="h-4 w-4" aria-hidden /></Link>
              <button type="button" onClick={briefing.onOpen} className="inline-flex items-center h-10 px-4 rounded-control border border-slate-600 text-sm font-medium text-white hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400">
                Request Technical Briefing
              </button>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-slate-200">
        <div className="max-w-[1200px] mx-auto px-4 md:px-6 py-8 flex flex-col md:flex-row gap-4 md:items-start justify-between text-[12px] text-slate-500">
          <div className="space-y-2 max-w-2xl">
            <BrandMark href="/" />
            <p>
              Demo disclaimer: all companies, batches, equipment, results and documents shown are synthetic. The demo does not connect to or write to any MES, DCS/PLC, LIMS, QMS or ERP system, and signatures in the demo have no regulatory effect. No claims of validated accuracy, time savings or regulatory compliance are made.
            </p>
          </div>
          <nav aria-label="Footer" className="flex gap-4">
            <Link href="/sign-in" className="hover:text-slate-900">Sign in</Link>
            <a href="#validation" className="hover:text-slate-900">Validation</a>
            <a href="#connectors" className="hover:text-slate-900">Connectors</a>
          </nav>
        </div>
      </footer>

      <Modal
        open={briefing.open}
        onClose={briefing.onClose}
        title="Request a technical briefing"
        footer={
          <>
            <Button variant="ghost" onClick={briefing.onClose}>Cancel</Button>
            <Button variant="primary" type="submit" form="briefing-form">Submit request</Button>
          </>
        }
      >
        <form id="briefing-form" onSubmit={submit} className="space-y-3">
          <p className="text-[12.5px] text-slate-600">A 45-minute session with an engineer covering architecture, connector scopes and validation approach.</p>
          {([
            ['name', 'Full name', 'text', 'Jordan Lee'],
            ['email', 'Work email', 'email', 'jordan.lee@company.com'],
            ['company', 'Company', 'text', 'Company name'],
          ] as const).map(([k, label, type, ph]) => (
            <label key={k} className="block text-[12.5px] font-medium text-slate-800">
              {label}
              <input required type={type} value={form[k]} onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))} placeholder={ph} className={inputCls} />
            </label>
          ))}
          <label className="block text-[12.5px] font-medium text-slate-800">
            Role
            <select required value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))} className={inputCls}>
              <option value="" disabled>Select a role</option>
              <option>MSAT / process engineering</option>
              <option>Quality assurance</option>
              <option>Manufacturing operations</option>
              <option>IT / OT architecture</option>
              <option>Other</option>
            </select>
          </label>
          <p className="text-[11px] text-slate-500">Demo form: submissions are not sent or stored.</p>
        </form>
      </Modal>
      <StandaloneEvidence />
    </>
  );
}
