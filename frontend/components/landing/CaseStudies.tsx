import Link from 'next/link';
import { ArrowRight } from 'lucide-react';

const studies = [
  { id: 'physics-value', type: 'Recorded paired experiment', title: 'Do physical models improve agent decisions?', body: 'Compare agents with and without executable models. Inspect results, failed runs and the limits of the comparison.' },
  { id: 'sulfolobus', type: 'Published experiment', title: 'Can a 2 L process travel to 200 L?', body: 'Explore oxygen transfer across scales, source measurements and what still needs characterization.' },
  { id: 'pichia', type: 'Published experiment + modeled costs', title: 'Can pressure replace supplemental oxygen?', body: 'Review oxygen delivery, production confounders and the assumptions behind operating costs.' },
];
export function CaseStudies() {
  return <section id="case-studies" className="scroll-mt-24 border-t border-border-hairline bg-white px-6 py-24"><div className="mx-auto max-w-6xl">
    <p className="lp-eyebrow">Case studies</p><h2 className="lp-h2 mt-6 max-w-3xl">Explore the work.<br/>Inspect the evidence.</h2>
    <p className="mt-6 max-w-2xl text-text-secondary">Published experiments and recorded evaluations, with sources, assumptions and limitations. These are research examples, not validated customer outcomes.</p>
    <div className="mt-12 grid gap-8 md:grid-cols-3">{studies.map(s => <article key={s.id} className="border-t border-border-strong pt-6"><p className="text-xs text-brand-teal">{s.type}</p><h3 className="mt-4 text-2xl font-medium tracking-tight">{s.title}</h3><p className="mt-4 text-sm leading-6 text-text-secondary">{s.body}</p><Link href={`/studies/#${s.id}`} className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-brand-teal">Read case study <ArrowRight className="h-4 w-4"/></Link></article>)}</div>
    <Link href="/studies/" className="lp-btn lp-btn-outline mt-10">Browse all case studies <ArrowRight className="h-4 w-4"/></Link>
  </div></section>;
}
