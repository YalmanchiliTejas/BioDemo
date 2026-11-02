import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import study from '@/data/decision-study.json';

export function CaseStudies() {
  const rows = [
    {label:'GLM agent',correct:study.summaries.A.correct,color:'#64748b'},
    {label:'GLM + mechanistic model',correct:study.summaries.B.correct,color:'#0e7490'},
    {label:'Model-only selector',correct:study.summaries.model_only.correct,color:'#8a6d3b'},
  ];
  return <section id="case-studies" className="scroll-mt-24 border-t border-border-hairline bg-white px-6 py-20 sm:py-24"><div className="mx-auto max-w-6xl">
    <div className="grid items-center gap-10 lg:grid-cols-[.9fr_1.1fr] lg:gap-16">
      <div><p className="lp-eyebrow">Case studies</p><h2 className="lp-h2 mt-6">See what changed.<br/>Inspect the evidence.</h2><p className="mt-6 max-w-md text-sm leading-6 text-text-secondary">Actual GLM runs, side-by-side comparisons, and the failures that remain.</p><Link href="/case-studies/" className="lp-btn lp-btn-primary mt-8">Explore the results <ArrowRight className="h-4 w-4"/></Link></div>
      <article className="rounded-xl border border-border-hairline bg-canvas p-6 sm:p-8"><div className="flex flex-wrap items-center justify-between gap-3 text-[11px]"><span className="font-medium text-brand-teal">Latest evaluation · {study.date}</span><span className="rounded-full border border-border-strong px-2.5 py-1 text-text-secondary">Exploratory simulation</span></div><h3 className="mt-5 text-lg font-semibold tracking-tight">Does model access improve agent decisions?</h3><p className="mt-2 text-xs text-text-secondary">Correct constrained decisions across {study.scenarios} scenarios</p><div className="mt-6 space-y-4" role="img" aria-label={rows.map(r=>`${r.label}: ${r.correct} of ${study.scenarios} correct constrained decisions`).join('; ')}>{rows.map(row=><div key={row.label}><div className="mb-2 flex justify-between gap-3 text-xs"><span>{row.label}</span><strong className="tabular-nums">{row.correct}/{study.scenarios}</strong></div><div className="h-4 overflow-hidden rounded-sm bg-white"><div className="h-full" style={{width:`${row.correct/study.scenarios*100}%`,background:row.color}}/></div></div>)}</div><p className="mt-5 border-t border-border-hairline pt-4 text-[11px] leading-5 text-text-secondary">Model-only matched the assisted agent. Real manufacturing benefit is not established by this simulation.</p><Link href="/case-studies/#physics-value" className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-brand-teal">View decisions, limits & methods <ArrowRight size={14}/></Link></article>
    </div>
    <div className="mt-10 flex flex-wrap gap-x-8 gap-y-3 border-t border-border-hairline pt-5 text-xs text-text-secondary"><span className="font-medium">Also explore</span><Link href="/case-studies/#workflows" className="hover:text-brand-teal hover:underline">Manufacturing workflow accuracy ↗</Link><Link href="/case-studies/#sulfolobus" className="hover:text-brand-teal hover:underline">Oxygen transfer across scales ↗</Link><Link href="/case-studies/#pichia" className="hover:text-brand-teal hover:underline">Pressure & oxygen delivery ↗</Link></div>
  </div></section>;
}
