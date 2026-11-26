import type { Metadata } from 'next';
import Link from 'next/link';
import CaseStudies from '@/components/process/CaseStudies';

export const metadata: Metadata = {
  title: { absolute: 'Case studies | Sievance' },
  description: 'Explore the freeze-drying comparison of an agent with and without a revised physical model, with interactive results, methods and reproducible evidence. No account required.',
};

export default function PublicCaseStudies() {
  return <div className="min-h-screen bg-canvas text-text-primary">
    <a href="#case-study-content" className="sr-only focus:not-sr-only">Skip to case studies</a>
    <header className="border-b border-border-hairline bg-surface">
      <nav aria-label="Public navigation" className="mx-auto flex max-w-[1440px] items-center justify-between gap-4 px-5 py-4 sm:px-8">
        <Link href="/" className="flex items-center gap-2 text-sm font-semibold tracking-wider"><img src="/brand/symbol-transparent.png" alt="" width={28} height={28}/>SIEVANCE</Link>
        <div className="flex items-center gap-5 text-sm"><Link href="/" className="hidden text-text-secondary hover:underline sm:inline">Product</Link><Link href="/sign-in/" className="whitespace-nowrap rounded-lg bg-brand-teal px-4 py-2 font-medium text-white">Open workspace</Link></div>
      </nav>
    </header>
    <main id="case-study-content" className="mx-auto max-w-[1200px] px-5 py-8 sm:px-8 sm:py-10"><CaseStudies/></main>
    <footer className="border-t border-border-hairline px-5 py-6 text-center text-xs leading-5 text-text-secondary">Published evidence, simulated outcomes and live product runs are labeled separately. No production changes are authorized by these examples.</footer>
  </div>;
}
