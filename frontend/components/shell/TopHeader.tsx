'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, LogOut, Menu, PenLine, Search } from 'lucide-react';
import { ROLE_LABELS, ROLE_PEOPLE, SITES, useAppContext, type UserRole } from '@/lib/app-context';
import { BrandMark } from './BrandMark';
import { DemoBoundary, StatusDot } from '../ui';
import { cn } from '@/lib/cn';

function useClickOutside(onOut: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onOut(); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [onOut]);
  return ref;
}

function ContextSwitcher() {
  const { organization, siteId, productId, campaignId, setSite, notify } = useAppContext();
  const [open, setOpen] = useState(false);
  const ref = useClickOutside(() => setOpen(false));
  return (
    <div ref={ref} className="relative min-w-0">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex items-center gap-1.5 h-8 px-2 rounded-control hover:bg-surface-secondary text-[12.5px] min-w-0">
        <span className="font-medium text-text-primary truncate">{organization}</span>
        <span className="text-text-muted">/</span>
        <span className="text-text-secondary truncate hidden sm:inline">{siteId}</span>
        <span className="text-text-muted hidden md:inline">/</span>
        <span className="text-text-secondary hidden md:inline">{productId}</span>
        <span className="text-text-muted hidden lg:inline">/</span>
        <code className="hidden lg:inline text-[11px] font-mono text-text-tertiary">{campaignId}</code>
        <ChevronDown className="h-3.5 w-3.5 text-text-tertiary shrink-0" aria-hidden />
      </button>
      {open && (
        <div className="absolute left-0 top-9 z-50 w-72 bg-surface border border-border-hairline rounded-card shadow-lg py-1">
          <p className="px-3 pt-2 pb-1 text-[10.5px] font-semibold uppercase tracking-wider text-text-muted">Site</p>
          {SITES.map((s) => (
            <button
              key={s}
              onClick={() => {
                setSite(s);
                setOpen(false);
                if (s !== SITES[0]) notify(`${s}: no sample records are loaded in this demo. Showing Mesa data.`, 'warning');
              }}
              className="w-full flex items-center justify-between px-3 py-1.5 text-[13px] text-left hover:bg-surface-secondary"
            >
              <span>{s}{s !== SITES[0] && <span className="ml-1.5 text-[11px] text-text-tertiary">no demo data</span>}</span>
              {s === siteId && <Check className="h-3.5 w-3.5 text-brand-teal" />}
            </button>
          ))}
          <div className="border-t border-border-hairline mt-1 px-3 py-2 text-[11.5px] text-text-tertiary space-y-0.5">
            <p>Product <span className="text-text-secondary">AB-mAb-014 (IgG1)</span></p>
            <p>Process <span className="text-text-secondary">UP-01 upstream</span> · Campaign <span className="font-mono text-text-secondary">CMP-26-10</span></p>
          </div>
        </div>
      )}
    </div>
  );
}

function UserMenu() {
  const { userRole, setRole } = useAppContext();
  const [open, setOpen] = useState(false);
  const ref = useClickOutside(() => setOpen(false));
  const initials = ROLE_PEOPLE[userRole].split(' ').map((p) => p[0]).join('');
  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex items-center gap-2 h-8 pl-1 pr-2 rounded-control hover:bg-surface-secondary">
        <span className="h-6 w-6 rounded-full bg-slate-800 text-white text-[10.5px] font-semibold flex items-center justify-center">{initials}</span>
        <span className="hidden lg:flex flex-col items-start leading-tight">
          <span className="text-[12px] font-medium text-text-primary">{ROLE_PEOPLE[userRole]}</span>
          <span className="text-[10.5px] text-text-tertiary">{ROLE_LABELS[userRole]}</span>
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-text-tertiary" aria-hidden />
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-50 w-64 bg-surface border border-border-hairline rounded-card shadow-lg py-1">
          <p className="px-3 pt-2 pb-1 text-[10.5px] font-semibold uppercase tracking-wider text-text-muted">View as role (demo)</p>
          {(Object.keys(ROLE_LABELS) as UserRole[]).map((r) => (
            <button key={r} onClick={() => { setRole(r); setOpen(false); }} className="w-full flex items-center justify-between px-3 py-1.5 text-[13px] hover:bg-surface-secondary">
              <span>{ROLE_LABELS[r]} <span className="text-text-tertiary text-[11.5px]">· {ROLE_PEOPLE[r]}</span></span>
              {r === userRole && <Check className="h-3.5 w-3.5 text-brand-teal" />}
            </button>
          ))}
          <p className="px-3 py-1.5 text-[11px] text-text-tertiary">In production, roles come from your identity provider and cannot be switched here.</p>
          <div className="border-t border-border-hairline mt-1">
            <Link href="/sign-in" className="flex items-center gap-2 px-3 py-2 text-[13px] text-text-secondary hover:bg-surface-secondary">
              <LogOut className="h-3.5 w-3.5" /> Sign out
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

export function TopHeader({ onOpenPalette, onToggleNav }: { onOpenPalette: () => void; onToggleNav: () => void }) {
  return (
    <header className="h-14 shrink-0 flex items-center gap-2 px-3 bg-surface border-b border-border-hairline">
      <button onClick={onToggleNav} className="lg:hidden p-1.5 rounded text-text-secondary hover:bg-surface-secondary" aria-label="Toggle navigation">
        <Menu className="h-5 w-5" />
      </button>
      <div className="w-[204px] shrink-0 hidden lg:block pl-1"><BrandMark /></div>
      <div className="lg:hidden"><BrandMark label={false} /></div>
      <ContextSwitcher />

      <div className="flex-1 flex justify-center px-2">
        <button
          onClick={onOpenPalette}
          className="w-full max-w-md hidden md:flex items-center gap-2 h-8 px-2.5 rounded-control border border-border-hairline bg-surface-secondary/70 text-[12.5px] text-text-tertiary hover:border-border-strong"
        >
          <Search className="h-3.5 w-3.5" aria-hidden />
          <span className="flex-1 text-left truncate whitespace-nowrap">Search records and screens…</span>
          <kbd className="text-[10px] font-mono border border-border-hairline bg-surface rounded px-1">⌘K</kbd>
        </button>
        <button onClick={onOpenPalette} className="md:hidden p-1.5 rounded text-text-secondary hover:bg-surface-secondary" aria-label="Search">
          <Search className="h-4 w-4" />
        </button>
      </div>

      <div className="flex items-center gap-1.5">
        <DemoBoundary compact className="hidden xl:inline-flex" />
        <Link href="/sources" className="hidden md:flex items-center gap-1.5 h-8 px-2 rounded-control hover:bg-surface-secondary text-[12px] text-text-secondary" title="Source coverage">
          <StatusDot tone="success" /> 5/6 sources
        </Link>
        <Link href="/reviews/REV-01" className={cn('relative flex items-center gap-1.5 h-8 px-2 rounded-control hover:bg-surface-secondary text-[12px] text-text-secondary')} title="Signatures awaiting you">
          <PenLine className="h-4 w-4" aria-hidden />
          <span className="hidden sm:inline">Signatures</span>
          <span className="min-w-[18px] h-[18px] px-1 rounded-pill bg-status-warning text-white text-[10px] font-semibold flex items-center justify-center">2</span>
        </Link>
        <UserMenu />
      </div>
    </header>
  );
}
