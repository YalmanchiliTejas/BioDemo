'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { ArrowUpRight, BookOpen, Building2, ChevronLeft, ChevronRight, Compass, Database, FlaskConical, HelpCircle, LayoutDashboard, MessageSquare, PackageCheck, Search, Settings, UserRound, Users, X, type LucideIcon } from 'lucide-react';
import { useWorkspace } from '@/lib/workspace-context';
import { useTutorial } from '@/lib/tutorial-context';
import { BrandMark } from './BrandMark';

type Destination = { label: string; href: string; icon: LucideIcon; guide?: string };
export const DESTINATIONS: Destination[] = [
  { label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard, guide: 'dashboard' },
  { label: 'Deliveries', href: '/cmo', icon: PackageCheck, guide: 'deliveries' },
  { label: 'Assistant', href: '/home', icon: MessageSquare, guide: 'assistant' },
  { label: 'Simulation', href: '/process-simulation', icon: FlaskConical, guide: 'simulation' },
  { label: 'Case studies', href: '/case-studies', icon: BookOpen },
];
export const NAV_SECTIONS = [
  { id: 'work', label: 'Workspace', short: 'Work', icon: LayoutDashboard, groups: [{ label: 'Your work', items: DESTINATIONS.slice(0, 3) }] },
  { id: 'data', label: 'Data & sources', short: 'Data', icon: Database, groups: [{ label: 'Bring your context', items: [{ label: 'Connections', href: '/sources', icon: Database, guide: 'connections' }, DESTINATIONS[1]] }] },
  { id: 'explore', label: 'Explore', short: 'Explore', icon: Compass, groups: [{ label: 'Tools & examples', items: DESTINATIONS.slice(3) }] },
  { id: 'organization', label: 'Organization', short: 'Org', icon: Building2, groups: [{ label: 'Workspace settings', items: [{ label: 'Organization & team', href: '/settings/organization', icon: Users, guide: 'organization' }] }, { label: 'Personal', items: [{ label: 'My profile', href: '/settings/profile', icon: UserRound, guide: 'profile' }] }] },
] as const;
const sectionOf = (path: string) => NAV_SECTIONS.find(section => section.groups.some(group => group.items.some(item => item.href === path)))?.id ?? 'work';

export function Sidebar() {
  const path = usePathname().replace(/\/$/, '');
  const { collapsed, setCollapsed, mobileOpen, setMobileOpen, organization, mode } = useWorkspace();
  const guide = useTutorial();
  const [selection, setSelection] = useState<{ path: string; id: string }>({ path, id: sectionOf(path) });
  const [query, setQuery] = useState('');
  const filter = useRef<HTMLInputElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  const selectedSection = NAV_SECTIONS.find(section => section.id === selection.id);
  const staysInSection = selectedSection?.groups.some(group => group.items.some(item => item.href === path));
  const id = selection.path === path || staysInSection ? selection.id : sectionOf(path);
  const current = NAV_SECTIONS.find(section => section.id === id)!;
  const q = query.trim().toLowerCase();
  const matches = (item: Destination, group: string, section: string) => `${item.label} ${group} ${section}`.toLowerCase().includes(q);
  useEffect(() => { setMobileOpen(false); setQuery(''); }, [path, setMobileOpen]);
  useEffect(() => {
    if (!guide.opened || !guide.topic) return;
    const section = NAV_SECTIONS.find(s => s.groups.some(g => g.items.some(item => item.guide === guide.topic)));
    if (section) { setSelection({ path, id: section.id }); setQuery(''); setCollapsed(false); }
    // A topic reveals its navigation group; the user can still browse freely afterwards.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guide.topic, guide.opened]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === '/' && !e.metaKey && !e.ctrlKey && !(e.target as HTMLElement).closest('input,textarea,select,[contenteditable="true"]')) {
        e.preventDefault(); setCollapsed(false);
        if (window.innerWidth < 900) setMobileOpen(true);
        requestAnimationFrame(() => filter.current?.focus());
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    sidebar.current?.querySelector<HTMLButtonElement>('button')?.focus();
    const trap = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setMobileOpen(false); previous?.focus(); }
      if (e.key !== 'Tab') return;
      const focusable = Array.from(sidebar.current?.querySelectorAll<HTMLElement>('button,a,input') ?? []).filter(node => node.getClientRects().length && !node.hasAttribute('disabled'));
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
      <div className="sidebar-brand"><BrandMark href="/dashboard/" /><button type="button" className="chrome-icon mobile-only" aria-label="Close navigation" onClick={dismiss}><X size={18} /></button></div>
      <div className="sidebar-body"><div className="section-rail" aria-label="Navigation sections">{NAV_SECTIONS.map(section => <button type="button" key={section.id} aria-pressed={id === section.id} title={section.label} onClick={() => { setSelection({ path, id: section.id }); setQuery(''); setCollapsed(false); }}><section.icon size={19} /><span>{section.short}</span></button>)}<div className="rail-bottom"><Link href="/settings/profile/" aria-label="My profile" title="My profile"><Settings size={18} /></Link><button type="button" aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'} className="desktop-only" onClick={() => setCollapsed(!collapsed)}>{collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}</button></div></div>
      <div className="navigation-panel"><div className="navigation-title">{q ? 'Search views' : current.label}</div><label className="navigation-filter"><Search size={14} /><input ref={filter} value={query} onChange={e => setQuery(e.target.value)} placeholder="Find a view…" aria-label="Filter navigation" /><kbd>/</kbd></label>
        <nav aria-label="Primary" className="navigation-links">{NAV_SECTIONS.filter(section => q || section.id === id).map(section => <div key={section.id}>{section.groups.map(group => <div className="navigation-group" key={group.label}>{group.items.some(item => matches(item, group.label, section.label)) && <h2>{group.label}</h2>}{group.items.filter(item => matches(item, group.label, section.label)).map(item => <Link key={item.href} href={`${item.href}/`} data-guide={item.guide} aria-current={path === item.href ? 'page' : undefined}><item.icon size={16} /><span>{item.label}</span>{path === item.href && <span className="active-indicator" />}</Link>)}</div>)}</div>)}{q && !NAV_SECTIONS.some(section => section.groups.some(group => group.items.some(item => matches(item, group.label, section.label)))) && <p className="navigation-empty">No views match “{query}”.</p>}</nav>
        <button type="button" className="sidebar-guide" onClick={() => { dismiss(); guide.open(); }}><HelpCircle size={17} /><span>Get started<small>{guide.seen.length} of 6 topics explored</small></span><ArrowUpRight size={14} /></button>
        <div className="sidebar-scope"><Building2 size={13} /><span>{organization?.name ?? (mode === 'development' ? 'Development workspace' : 'Your organization')}</span></div>
      </div></div>
    </aside>
  </>;
}

/** Retained for existing consumers; the shell uses the sectioned Sidebar. */
export function PrimaryNav() { return <nav aria-label="Primary">{DESTINATIONS.map(item => <Link key={item.href} href={item.href}>{item.label}</Link>)}</nav>; }
