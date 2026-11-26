import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import study from '@/data/lyo-study.json';

export default function CaseStudies() {
  const results = study.cohorts.sensitivity;
  return <div data-testid="case-study-story">
    <header className="mb-7 border-b border-border-strong pb-6">
      <p className="text-[11px] font-medium uppercase tracking-[.18em] text-brand-teal">Evidence & evaluations</p>
      <h1 className="mt-2 font-display text-3xl font-medium tracking-[-.04em] sm:text-4xl">Case studies</h1>
      <p className="mt-2 max-w-xl text-sm leading-6 text-text-secondary">Explore the freeze-drying comparison, its results, and the evidence behind them.</p>
    </header>
    <Link href="/case-studies/freeze-drying/" className="group grid gap-5 rounded-xl border border-brand-teal/25 bg-surface p-6 sm:p-8 md:grid-cols-[1.5fr_1fr] md:items-center">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[.14em] text-brand-teal">Freeze-drying · {study.date}</p>
        <h2 className="mt-3 font-display text-2xl font-medium tracking-tight">Does a physical model make the agent more useful?</h2>
        <p className="mt-3 max-w-xl text-sm leading-6 text-text-secondary">Agent vs. agent + revised model. Explore the results, the budget sensitivity, and the heat and mass balances behind the predictions.</p>
        <span className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-brand-teal">Explore the comparison <ArrowRight size={15}/></span>
      </div>
      <div className="border-l-2 border-brand-teal/30 pl-5">
        <p className="text-xs text-text-secondary">Feasible choices · follow-up protocol</p>
        <p className="mt-2 flex items-center gap-3 font-display text-3xl tabular-nums"><span className="text-text-tertiary">{results.groups.A.all.feasible_selections}/{results.groups.A.all.planned}</span><ArrowRight size={20} className="text-text-tertiary"/><strong className="font-medium text-brand-teal">{results.groups.C.all.feasible_selections}/{results.groups.C.all.planned}</strong></p>
        <p className="mt-2 text-xs leading-5 text-text-secondary">Six reused synthetic cases, two tasks each.<br/>One unsafe choice in each arm.</p>
      </div>
    </Link>
  </div>;
}
