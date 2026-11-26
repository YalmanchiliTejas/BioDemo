import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import study from '@/data/lyo-study.json';

export function CaseStudies() {
  const followup = study.cohorts.sensitivity;
  const rows = [
    {label:'Agent',results:followup.groups.A.all,color:'#64748b'},
    {label:'Agent + revised model',results:followup.groups.C.all,color:'#0e7490'},
  ];
  return <section id="case-studies" className="scroll-mt-24 border-t border-border-hairline bg-white px-6 py-20 sm:py-24"><div className="mx-auto max-w-6xl">
    <div className="grid items-center gap-10 lg:grid-cols-[.9fr_1.1fr] lg:gap-16">
      <div><p className="lp-eyebrow">Case study</p><h2 className="lp-h2 mt-6">See what changed.<br/>Inspect the evidence.</h2><p className="mt-6 max-w-md text-sm leading-6 text-text-secondary">A freeze-drying comparison with actual agent runs, side-by-side results, and the failures that remain.</p><Link href="/case-studies/freeze-drying/" className="lp-btn lp-btn-primary mt-8">Explore the study <ArrowRight className="h-4 w-4"/></Link></div>
      <article className="rounded-xl border border-border-hairline bg-canvas p-6 sm:p-8"><div className="flex flex-wrap items-center justify-between gap-3 text-[11px]"><span className="font-medium text-brand-teal">Freeze-drying · {study.date}</span><span className="rounded-full border border-border-strong px-2.5 py-1 text-text-secondary">{study.classification}</span></div><h3 className="mt-5 text-lg font-semibold tracking-tight">Does a physical model make the agent more useful?</h3><p className="mt-2 text-xs text-text-secondary">Feasible choices · follow-up protocol</p><div className="mt-6 space-y-4" role="img" aria-label={rows.map(r=>`${r.label}: ${r.results.feasible_selections} of ${r.results.planned} feasible choices`).join('; ')}>{rows.map(row=><div key={row.label}><div className="mb-2 flex justify-between gap-3 text-xs"><span>{row.label}</span><strong className="tabular-nums">{row.results.feasible_selections}/{row.results.planned}</strong></div><div className="h-4 overflow-hidden rounded-sm bg-white"><div className="h-full" style={{width:`${row.results.feasible_selections/row.results.planned*100}%`,background:row.color}}/></div></div>)}</div><p className="mt-5 border-t border-border-hairline pt-4 text-[11px] leading-5 text-text-secondary">Six reused synthetic cases, two tasks each. Budget, wall time and submission policy changed together. One unsafe choice in each arm; real manufacturing benefit remains unproven.</p><Link href="/case-studies/freeze-drying/#evidence" className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-brand-teal">View results, limits & evidence <ArrowRight size={14}/></Link></article>
    </div>
  </div></section>;
}
