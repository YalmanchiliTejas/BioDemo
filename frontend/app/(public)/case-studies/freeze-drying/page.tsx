import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import FreezeDryingStudy from '@/components/process/FreezeDryingStudy';

export const metadata: Metadata = {
  title: {absolute:'Freeze-drying: agent vs. agent + mechanistic model | Sievance'},
  description:'Explore a controlled synthetic comparison of an agent with and without a revised freeze-drying model. Results, interactive graphs, heat and mass balances, and reproducible evidence.',
};

export default function FreezeDryingCaseStudyPage() {
  return <div className="min-h-screen bg-canvas text-text-primary">
    <a href="#freeze-drying-content" className="sr-only focus:not-sr-only">Skip to study results</a>
    <header className="border-b border-border-hairline bg-surface"><nav aria-label="Public navigation" className="mx-auto flex max-w-[1440px] items-center justify-between gap-4 px-5 py-4 sm:px-8"><Link href="/" className="flex items-center gap-2 text-sm font-semibold tracking-wider"><img src="/brand/symbol-transparent.png" alt="" width={28} height={28}/>SIEVANCE</Link><Link href="/case-studies/" className="inline-flex items-center gap-2 text-xs font-medium text-text-secondary hover:text-brand-teal"><ArrowLeft size={15}/>All case studies</Link></nav></header>
    <main id="freeze-drying-content" className="mx-auto max-w-[1200px] px-5 py-9 sm:px-8 sm:py-12"><FreezeDryingStudy/></main>
    <footer className="mt-10 px-5 py-6 text-center text-xs leading-5 text-text-secondary">Synthetic research comparison. No equipment was operated. These proposals are not approved manufacturing actions.</footer>
  </div>;
}
