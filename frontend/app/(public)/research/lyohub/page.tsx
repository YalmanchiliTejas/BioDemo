import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import LyoProntoNativeStudy from '@/components/process/LyoProntoNativeStudy';

export const metadata: Metadata = {
  title: { absolute: 'Native LyoPRONTO agent evaluation | Sievance Research' },
  description: 'A fresh evaluation of the workspace agent using native LyoPRONTO calculations, constrained recipe selection, missing characterization and scope limits. Explore every case and reproducible evidence.',
};

export default function LyoHubResearchPage() {
  return <div className="min-h-screen bg-canvas text-text-primary">
    <a href="#research-content" className="sr-only focus:not-sr-only">Skip to research results</a>
    <header className="border-b border-border-hairline bg-surface"><nav aria-label="Research navigation" className="mx-auto flex max-w-6xl items-center justify-between gap-5 px-5 py-5 sm:px-8"><Link href="/" className="flex items-center gap-2 text-sm font-semibold tracking-wider"><img src="/brand/symbol-transparent.png" alt="" width={28} height={28}/>SIEVANCE<span className="ml-2 border-l border-border-strong pl-3 text-[11px] font-normal tracking-normal text-text-secondary">Research</span></Link><Link href="/" className="inline-flex items-center gap-2 text-xs text-text-secondary hover:text-brand-teal"><ArrowLeft size={14}/>Platform</Link></nav></header>
    <main id="research-content" className="mx-auto max-w-6xl px-5 py-10 sm:px-8 sm:py-16"><LyoProntoNativeStudy/></main>
    <footer className="mt-10 border-t border-border-hairline px-5 py-8 text-center text-xs leading-6 text-text-secondary">Sievance Research · Native-model agent evaluation.<br/>No manufacturing equipment was operated. No Purdue affiliation or endorsement is claimed.</footer>
  </div>;
}
