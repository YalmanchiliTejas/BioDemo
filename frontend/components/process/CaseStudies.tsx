'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { ArrowDown, ArrowRight, ChevronDown, FileText } from 'lucide-react';
import { DecisionStudy } from './DecisionStudy';

const ArchivedStudies = dynamic(() => import('./ArchivedCaseStudies'), {
  loading: () => <p role="status" className="py-6 text-sm text-text-secondary">Loading earlier study records…</p>,
});
const olderHashes = new Set(['workflows', 'live-app', 'sulfolobus', 'pichia', 'sanofi', 'indpensim', 'earlier-physics']);

export default function CaseStudies() {
  const [archiveOpen, setArchiveOpen] = useState(false);
  useEffect(() => {
    const sync = () => {
      if (olderHashes.has(window.location.hash.slice(1))) {
        setArchiveOpen(true);
        requestAnimationFrame(() => document.getElementById('earlier-studies')?.scrollIntoView({ block: 'start' }));
      }
    };
    sync();
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, []);
  return <div data-testid="case-study-story">
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4 border-b border-border-strong pb-6">
      <div><p className="text-[11px] font-medium uppercase tracking-[.18em] text-brand-teal">Evidence & evaluations</p><h1 className="mt-2 font-display text-3xl font-medium tracking-[-.04em] sm:text-4xl">Case studies</h1><p className="mt-2 max-w-xl text-sm leading-6 text-text-secondary">See the results, the decisions, and where the models fell short.</p></div>
      <a href="#earlier-studies" className="inline-flex items-center gap-2 text-sm font-medium text-text-secondary hover:text-brand-teal">Earlier studies <ArrowDown size={15}/></a>
    </div>
    <Link href="/case-studies/freeze-drying/" className="group mb-10 grid gap-5 rounded-xl border border-brand-teal/25 bg-surface p-6 sm:p-8 md:grid-cols-[1.5fr_1fr] md:items-center">
      <div><p className="text-[11px] font-semibold uppercase tracking-[.14em] text-brand-teal">New case study · Freeze-drying</p><h2 className="mt-3 font-display text-2xl font-medium tracking-tight">Does a physical model make the agent more useful?</h2><p className="mt-3 max-w-xl text-sm leading-6 text-text-secondary">Agent vs. agent + revised model. Explore the results, the budget sensitivity, and the heat and mass balances behind the predictions.</p><span className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-brand-teal">Explore the comparison <ArrowRight size={15}/></span></div>
      <div className="border-l-2 border-brand-teal/30 pl-5"><p className="text-xs text-text-secondary">Feasible choices · follow-up protocol</p><p className="mt-2 flex items-center gap-3 font-display text-3xl tabular-nums"><span className="text-text-tertiary">6/12</span><ArrowRight size={20} className="text-text-tertiary"/><strong className="font-medium text-brand-teal">11/12</strong></p><p className="mt-2 text-xs leading-5 text-text-secondary">Six reused synthetic cases, two tasks each.<br/>One unsafe choice in each arm.</p></div>
    </Link>
    <DecisionStudy/>
    <section className="mt-16 border-t border-border-strong pt-9" aria-labelledby="more-studies-heading">
      <div className="flex flex-wrap items-baseline justify-between gap-3"><h2 id="more-studies-heading" className="font-display text-2xl font-medium tracking-tight">Explore the other evidence</h2><span className="text-xs text-text-tertiary">Different questions. Separate study designs.</span></div>
      <div className="mt-6 grid gap-6 sm:grid-cols-3">{[
        { hash:'workflows', label:'Actual agent runs', title:'Manufacturing workflow accuracy', text:'Precision, recall and task correctness across investigations, deviations, ingestion and scheduling.' },
        { hash:'sulfolobus', label:'Published experiment', title:'Oxygen transfer across scales', text:'A source-only prediction compared with published measurements at larger reactor scales.' },
        { hash:'pichia', label:'Published data + modeled costs', title:'Pressure and oxygen delivery', text:'Production outcomes, utility assumptions and what a pressure-only explanation misses.' },
      ].map(study => <a key={study.hash} href={`#${study.hash}`} className="group border-t border-border-hairline py-5"><p className="text-[11px] font-medium text-brand-teal">{study.label}</p><h3 className="mt-3 flex items-start justify-between gap-3 text-base font-semibold">{study.title}<ArrowRight size={17} className="mt-1 shrink-0 text-text-tertiary group-hover:text-brand-teal"/></h3><p className="mt-2 text-xs leading-5 text-text-secondary">{study.text}</p></a>)}</div>
      <details id="earlier-studies" open={archiveOpen} onToggle={event => setArchiveOpen(event.currentTarget.open)} className="group mt-5 scroll-mt-6 rounded-xl border border-border-hairline bg-surface">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-5 text-sm font-semibold [&::-webkit-details-marker]:hidden"><span className="flex items-center gap-3"><FileText size={18} className="text-brand-teal"/>All earlier evaluations & published examples</span><ChevronDown size={18} className="shrink-0 transition-transform group-open:rotate-180"/></summary>
        {archiveOpen ? <div className="border-t border-border-hairline p-4 sm:p-6"><ArchivedStudies/></div> : null}
      </details>
    </section>
  </div>;
}
