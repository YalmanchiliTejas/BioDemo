'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Check } from 'lucide-react';
import { BrandMark } from './BrandMark';
import { DemoBoundary } from '../ui';
import { cn } from '@/lib/cn';

const STEPS = [
  { href: '/onboarding/start', label: 'Choose data' },
  { href: '/onboarding/mapping', label: 'Confirm mapping' },
  { href: '/onboarding/results', label: 'First result' },
];

export function OnboardingFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || '';
  const current = Math.max(0, STEPS.findIndex((s) => pathname.startsWith(s.href)));
  return (
    <div className="min-h-screen bg-canvas flex flex-col">
      <header className="h-14 shrink-0 flex items-center gap-4 px-4 md:px-6 bg-surface border-b border-border-hairline">
        <BrandMark href="/" />
        <ol className="hidden md:flex items-center gap-1 mx-auto" aria-label="Setup progress">
          {STEPS.map((s, i) => (
            <li key={s.href} className="flex items-center gap-1">
              {i > 0 && <span className="w-8 h-px bg-border-strong mx-1" aria-hidden />}
              <Link href={s.href} aria-current={i === current ? 'step' : undefined} className={cn('flex items-center gap-1.5 h-7 px-2 rounded-pill text-[12px]', i === current ? 'bg-brand-teal-light text-brand-teal-dark font-medium' : 'text-text-tertiary hover:text-text-primary')}>
                <span className={cn('h-4 w-4 rounded-full flex items-center justify-center text-[10px] font-semibold', i < current ? 'bg-brand-teal text-white' : i === current ? 'border border-brand-teal text-brand-teal' : 'border border-border-strong text-text-muted')}>
                  {i < current ? <Check className="h-2.5 w-2.5" /> : i + 1}
                </span>
                {s.label}
              </Link>
            </li>
          ))}
        </ol>
        <div className="ml-auto flex items-center gap-3">
          <DemoBoundary className="hidden sm:inline-flex" />
          <Link href="/home" className="text-[12.5px] text-text-secondary hover:text-text-primary">Skip to briefing</Link>
        </div>
      </header>
      <main className="flex-1 w-full max-w-6xl mx-auto px-4 md:px-6 py-8">{children}</main>
    </div>
  );
}
