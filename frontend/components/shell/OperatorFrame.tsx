'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { ArrowLeft, ClipboardList, LifeBuoy, Users, Wifi } from 'lucide-react';
import { cn } from '@/lib/cn';

const TABS = [
  { href: '/operator/shift', label: 'Step checklist', icon: ClipboardList },
  { href: '/operator/troubleshooting', label: 'Troubleshooting', icon: LifeBuoy },
  { href: '/operator/handoff', label: 'Shift handoff', icon: Users },
];

/**
 * Cleanroom tablet companion. Designed for a 1024×768 landscape tablet with gloved touch:
 * 56px minimum targets, high contrast, no hover-dependent controls.
 */
export function OperatorFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || '';
  const [clock, setClock] = useState('');
  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    tick();
    const t = setInterval(tick, 30_000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="min-h-screen bg-slate-200 flex flex-col items-center justify-center p-0 lg:p-6">
      <div className="hidden lg:flex w-[1024px] items-center justify-between mb-2 text-xs text-text-tertiary">
        <Link href="/home" className="inline-flex items-center gap-1 hover:text-text-primary"><ArrowLeft className="h-3.5 w-3.5" /> Back to desktop workspace</Link>
        <span>Tablet preview · 1024 × 768</span>
      </div>
      <div className="w-full lg:w-[1024px] h-screen lg:h-[768px] bg-canvas lg:rounded-[18px] lg:border-[10px] lg:border-slate-900 overflow-hidden flex flex-col shadow-2xl">
        <header className="h-14 shrink-0 flex items-center gap-4 px-5 bg-slate-900 text-white">
          <div className="flex items-center gap-2">
            <span className="h-7 w-7 rounded-md bg-brand-teal flex items-center justify-center text-[11px] font-bold">OS</span>
            <div className="leading-tight">
              <p className="text-[14px] font-semibold">Suite 3B · BR-UP-01</p>
              <p className="text-[11px] text-slate-400">MES-26073 · Shift B · Taylor Reed</p>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-4 text-[13px]">
            <span className="inline-flex items-center gap-1.5 text-amber-300"><span className="h-2 w-2 rounded-full bg-amber-400" />Demo · read-only</span>
            <span className="inline-flex items-center gap-1.5 text-slate-300"><Wifi className="h-4 w-4" />Synced</span>
            <span className="font-mono tabular-nums text-slate-200">{clock}</span>
          </div>
        </header>
        <main className="flex-1 min-h-0 overflow-y-auto">{children}</main>
        <nav className="h-[72px] shrink-0 grid grid-cols-3 border-t border-border-strong bg-surface" aria-label="Operator">
          {TABS.map((t) => {
            const active = pathname.startsWith(t.href);
            const Icon = t.icon;
            return (
              <Link key={t.href} href={t.href} aria-current={active ? 'page' : undefined} className={cn('flex flex-col items-center justify-center gap-1 text-[14px] font-semibold border-t-4', active ? 'border-brand-teal text-brand-teal-dark bg-brand-teal-light' : 'border-transparent text-text-secondary active:bg-surface-secondary')}>
                <Icon className="h-6 w-6" aria-hidden />
                {t.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
