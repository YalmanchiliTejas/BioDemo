import { Bell, Building2, Lock, SlidersHorizontal, Database, FlaskConical, FolderKanban, LayoutDashboard, MessageSquare, PackageCheck, Radar, ScrollText, UserRound, type LucideIcon } from 'lucide-react';

/** One entry per destination; the sidebar, page breadcrumbs and quick find all read from this list. */
export type NavItem = { label: string; href: string; icon: LucideIcon; description: string; guide?: string; keywords?: string };
export type NavGroup = { id: string; label: string; items: NavItem[] };

export const NAV_GROUPS: NavGroup[] = [
  {
    id: 'work', label: 'Work', items: [
      { label: 'Overview', href: '/dashboard', icon: LayoutDashboard, guide: 'dashboard', description: 'Status, recent deliveries and what needs attention', keywords: 'dashboard home status' },
      { label: 'Workspaces', href: '/workspaces', icon: FolderKanban, description: 'Saved results, charts, source records and review steps', keywords: 'results investigation deviation schedule data tables actions' },
      { label: 'Signals', href: '/signals', icon: Radar, description: 'Possible deviations detected from your data, triaged by the assistant', keywords: 'deviation alert excursion oos out of spec trend triage' },
      { label: 'Deliveries', href: '/cmo', icon: PackageCheck, guide: 'deliveries', description: 'Check CMO files against their original sources', keywords: 'cmo cdmo upload verify batch coa export' },
      { label: 'Assistant', href: '/home', icon: MessageSquare, guide: 'assistant', description: 'Ask a question with the evidence you choose', keywords: 'chat ask companion question' },
    ],
  },
  {
    id: 'explore', label: 'Explore', items: [
      { label: 'Simulation', href: '/process-simulation', icon: FlaskConical, guide: 'simulation', description: 'Compare process scenarios and predicted outcomes', keywords: 'freeze drying lyophilization transfer physics' },
    ],
  },
  {
    id: 'settings', label: 'Settings', items: [
      { label: 'Data connections', href: '/sources', icon: Database, guide: 'connections', description: 'Connect source systems and manage collection', keywords: 'sources connectors deltav pi veeva labware sap' },
      { label: 'Organization & team', href: '/settings/organization', icon: Building2, guide: 'organization', description: 'Members, roles and site access', keywords: 'members roles access admin' },
      { label: 'Alerts', href: '/settings/alerts', icon: Bell, description: 'Who hears about deviation signals, and where', keywords: 'alerts notifications slack teams email deviation signals routing' },
      { label: 'Specifications', href: '/settings/specifications', icon: SlidersHorizontal, description: 'Approved limits live data is checked against', keywords: 'specification limits spec range oos deviation alarm' },
      { label: 'Memory & sharing', href: '/settings/memory', icon: Lock, description: 'Your private assistant memory and who may read it', keywords: 'memory privacy share access grant conversations corrections' },
      { label: 'Assistant rules', href: '/settings/assistant-rules', icon: ScrollText, description: 'Standing instructions the assistant always follows', keywords: 'rules memory instructions corrections preferences' },
      { label: 'My profile', href: '/settings/profile', icon: UserRound, guide: 'profile', description: 'Your name, sign-in and memberships', keywords: 'account password' },
    ],
  },
];

// Demo visitors have no systems to connect, team to manage or account to edit.
const DEMO_HIDDEN = new Set(['/sources', '/settings/organization', '/settings/alerts', '/settings/memory', '/settings/profile']);
export const navGroups = (demo: boolean): NavGroup[] =>
  demo ? NAV_GROUPS.map(group => ({ ...group, items: group.items.filter(item => !DEMO_HIDDEN.has(item.href)) })) : NAV_GROUPS;

const clean = (path: string) => path.replace(/\/$/, '') || '/';

/** The group and destination that own a path, if it is part of the navigation. */
export function locate(path: string): { group: NavGroup; item: NavItem } | null {
  const target = clean(path);
  for (const group of NAV_GROUPS) {
    const item = group.items.find(entry => target === entry.href || target.startsWith(`${entry.href}/`));
    if (item) return { group, item };
  }
  return null;
}
