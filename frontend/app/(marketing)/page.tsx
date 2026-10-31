'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Menu, X } from 'lucide-react';
import { BrandMark } from '@/components/shell/BrandMark';
import { HeroTour } from '@/components/landing/HeroTour';
import { Closing, Footer, How, Physics, Platform, Problem, RealData, Systems, UsesRoll } from '@/components/landing/Sections';
import { CaseStudies } from '@/components/landing/CaseStudies';
import { cn } from '@/lib/cn';

const NAV = [
  { href: '#platform', label: 'Platform' },
  { href: '#physics', label: 'Physics models' },
  { href: '#case-studies', label: 'Case studies' },
  { href: '#how', label: 'How it works' },
];

function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);
  return (
    <header className="fixed inset-x-0 top-0 z-50 px-3 pt-3">
      <div className={cn('lp-nav mx-auto', (scrolled || open) && 'lp-nav-floating')}>
        <div className="flex h-14 items-center justify-between px-5">
          <BrandMark href="/" />
          <nav className="hidden items-center gap-9 lg:flex" aria-label="Primary">
            {NAV.map(item => <a key={item.href} href={item.href} className="lp-nav-link">{item.label}</a>)}
          </nav>
          <div className="flex items-center gap-4">
            <Link href="/demo/" className="lp-nav-link hidden sm:inline">Live demo</Link>
            <Link href="/demo/" className="lp-btn lp-btn-primary h-9 px-4 text-[14px]">Explore the platform</Link>
            <button type="button" className="-mr-1 flex h-9 w-9 items-center justify-center rounded-[4px] text-ink lg:hidden" aria-expanded={open} aria-controls="lp-mobile-nav" aria-label={open ? 'Close menu' : 'Open menu'} onClick={() => setOpen(o => !o)}>
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
        <nav id="lp-mobile-nav" hidden={!open} className="border-t border-border-hairline px-5 pb-4 pt-2 lg:hidden" aria-label="Sections">
          {NAV.map(item => <a key={item.href} href={item.href} onClick={() => setOpen(false)} className="block py-2.5 text-[15px] text-ink">{item.label}</a>)}
          <Link href="/demo/" className="block py-2.5 text-[15px] text-ink sm:hidden">Live demo</Link>
        </nav>
      </div>
    </header>
  );
}

export default function LandingPage() {
  return (
    <div className="lp font-sans text-ink">
      <Nav />
      <main className="relative z-10 bg-canvas">
        <HeroTour />
        <UsesRoll />
        <Problem />
        <Platform />
        <Physics />
        <RealData />
        <CaseStudies />
        <How />
        <Systems />
        <Closing />
      </main>
      <Footer />
    </div>
  );
}
