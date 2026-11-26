'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { ChevronRight, Ellipsis, PanelLeftClose, PanelLeftOpen, X } from 'lucide-react';
import { useWorkspace } from '@/lib/workspace-context';
import { navFor, locate, type NavItem } from '@/lib/navigation';
import { useView } from '@/lib/use-view';
import { useDemo } from '@/lib/demo-api';
import { LANDING } from '@/lib/auth';
import { BrandMark } from './BrandMark';

export function Sidebar() {
  const { demo } = useDemo();
  const path = usePathname();
  const { collapsed, setCollapsed, mobileOpen, setMobileOpen } = useWorkspace();
  const sidebar = useRef<HTMLElement>(null);
  const active = locate(path)?.item.href;
  const { icp } = useView(demo?.persona);
  const groups = navFor(icp, !!demo);
  // More starts closed and opens by itself when the page a person is on lives inside it.
  const [moreOpen, setMoreOpen] = useState(false);
  const inMore = groups.some(group => group.folded && group.items.some(item => item.href === active));
  useEffect(() => { if (inMore) setMoreOpen(true); }, [inMore, active]);
  const link = (item: NavItem) => <Link key={item.href} href={`${item.href}/`} data-guide={item.guide} title={collapsed ? item.label : undefined} aria-current={active === item.href ? 'page' : undefined}><item.icon size={16} strokeWidth={1.75} /><span>{item.label}</span></Link>;
  useEffect(() => { setMobileOpen(false); }, [path, setMobileOpen]);
  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    sidebar.current?.querySelector<HTMLButtonElement>('button')?.focus();
    const trap = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setMobileOpen(false); previous?.focus(); }
      if (e.key !== 'Tab') return;
      const focusable = Array.from(sidebar.current?.querySelectorAll<HTMLElement>('button,a,summary') ?? []).filter(node => node.getClientRects().length && !node.hasAttribute('disabled'));
      const first = focusable[0]; const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', trap);
    return () => document.removeEventListener('keydown', trap);
  }, [mobileOpen, setMobileOpen]);
  const dismiss = () => { setMobileOpen(false); document.querySelector<HTMLButtonElement>('[aria-label="Open navigation"]')?.focus(); };
  return <>
    {mobileOpen && <button type="button" tabIndex={-1} className="navigation-scrim" aria-label="Close navigation overlay" onClick={dismiss} />}
    <aside ref={sidebar} id="workspace-navigation" className={`workspace-sidebar ${collapsed ? 'is-collapsed' : ''} ${mobileOpen ? 'is-open' : ''}`} role={mobileOpen ? 'dialog' : undefined} aria-modal={mobileOpen || undefined} aria-label="Workspace navigation">
      <div className="sidebar-brand"><BrandMark href={LANDING} label={!collapsed || mobileOpen} /><button type="button" className="chrome-icon mobile-only" aria-label="Close navigation" onClick={dismiss}><X size={18} /></button></div>
      <nav aria-label="Primary" className="sidebar-nav">
        {groups.map(group => group.folded
          ? <details className="sidebar-group sidebar-more" key={group.id} open={moreOpen} onToggle={e => setMoreOpen(e.currentTarget.open)}>
            <summary title={collapsed ? group.label : undefined}><Ellipsis size={16} strokeWidth={1.75} /><span>{group.label}</span><ChevronRight size={14} className="sidebar-more-chevron" aria-hidden /></summary>
            <div className="sidebar-more-items">{group.items.map(link)}</div>
          </details>
          : <div className={`sidebar-group ${group.id === 'settings' ? 'sidebar-group-end' : ''}`} key={group.id}>
            <h2>{group.label}</h2>
            {group.items.map(link)}
          </div>)}
      </nav>
      <div className="sidebar-foot desktop-only"><button type="button" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'} title={collapsed ? 'Expand navigation' : undefined}>{collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}<span>Collapse</span></button></div>
    </aside>
  </>;
}
