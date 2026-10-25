'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { NAV, SETTINGS_NAV, type NavItem } from '@/lib/routes';
import { cn } from '@/lib/cn';

function isActive(pathname: string, item: NavItem) {
  const base = item.match ?? item.href;
  return pathname === item.href || pathname.startsWith(base + '/') || pathname === base;
}

function NavLink({ item, pathname, onNavigate }: { item: NavItem; pathname: string; onNavigate?: () => void }) {
  const active = isActive(pathname, item);
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'group flex items-center gap-2.5 h-8 px-2.5 rounded-control text-[13px] transition-colors',
        active ? 'bg-brand-teal-light text-brand-teal-dark font-medium' : 'text-text-secondary hover:bg-surface-secondary hover:text-text-primary',
      )}
    >
      <Icon className={cn('h-4 w-4 shrink-0', active ? 'text-brand-teal' : 'text-text-tertiary group-hover:text-text-secondary')} aria-hidden />
      <span className="truncate flex-1">{item.label}</span>
      {item.badge && <span className="min-w-[18px] h-[18px] px-1 rounded-pill bg-status-warning-bg text-amber-700 text-[10px] font-semibold flex items-center justify-center tabular-nums">{item.badge}</span>}
    </Link>
  );
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname() || '/';
  return (
    <nav aria-label="Primary" className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
        {NAV.map((section) => (
          <div key={section.title}>
            <p className="px-2.5 mb-1 text-[10.5px] font-semibold uppercase tracking-wider text-text-muted">{section.title}</p>
            <div className="space-y-0.5">
              {section.items.map((item) => <NavLink key={item.href} item={item} pathname={pathname} onNavigate={onNavigate} />)}
            </div>
          </div>
        ))}
      </div>
      <div className="px-3 py-3 border-t border-border-hairline space-y-2">
        <NavLink item={SETTINGS_NAV} pathname={pathname} onNavigate={onNavigate} />
        <p className="px-2.5 text-[10.5px] leading-snug text-text-muted">
          Read-only to MES, DCS, LIMS, QMS &amp; ERP. Consequential actions need a named human signature.
        </p>
      </div>
    </nav>
  );
}
