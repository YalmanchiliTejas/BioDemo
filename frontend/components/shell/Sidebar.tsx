'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BookOpen, FlaskConical, MessageSquare, PackageCheck, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/cn';

type Destination = { label: string; href: string; icon: LucideIcon };

/** The whole navigation. Demo screens remain reachable by URL but are not listed. */
export const DESTINATIONS: Destination[] = [
  { label: 'Deliveries', href: '/cmo', icon: PackageCheck },
  { label: 'Assistant', href: '/home', icon: MessageSquare },
  { label: 'Simulation', href: '/process-simulation', icon: FlaskConical },
  { label: 'Case studies', href: '/case-studies', icon: BookOpen },
];

export function PrimaryNav() {
  const pathname = (usePathname() || '/').replace(/\/$/, '');
  return (
    <nav aria-label="Primary" className="flex min-w-0 items-center gap-2 overflow-x-auto sm:gap-7">
      {DESTINATIONS.map(({ label, href, icon: Icon }) => {
        const active = pathname === href || pathname.startsWith(href + '/');
        return (
          <Link key={href} href={href} aria-current={active ? 'page' : undefined}
            className={cn('flex h-8 shrink-0 items-center gap-1.5 px-2 text-[12.5px] font-medium uppercase tracking-wide transition-colors',
              active ? 'text-brand-teal' : 'text-ink/70 hover:text-brand-teal')}>
            <Icon className="h-4 w-4 sm:hidden" aria-hidden /><span className="hidden sm:inline">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
