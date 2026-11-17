import { viewPages, type Icp } from './overview-views';
import { Bell, Building2, ChartLine, ClipboardList, Download, Lock, SlidersHorizontal, Database, FlaskConical, FolderKanban, FolderOpen, LayoutDashboard, MessageSquare, PackageCheck, Radar, ScrollText, UserRound, type LucideIcon } from 'lucide-react';

/** One entry per destination; the sidebar, page breadcrumbs and quick find all read from this list. */
export type NavItem = { label: string; href: string; icon: LucideIcon; description: string; guide?: string; keywords?: string };
/** `folded` groups start closed in the sidebar; their pages stay one click away. */
export type NavGroup = { id: string; label: string; items: NavItem[]; folded?: boolean };

export const NAV_GROUPS: NavGroup[] = [
  // Grouped by what a person is doing, in the order work usually flows: see where things stand, review what arrived,
  // analyze it, then keep or hand off the result.
  {
    id: 'start', label: 'Start', items: [
      { label: 'Overview', href: '/dashboard', icon: LayoutDashboard, guide: 'dashboard', description: 'What needs you and where things stand, with one click to each place', keywords: 'dashboard home status overview summary' },
      { label: 'Assistant', href: '/home', icon: MessageSquare, guide: 'assistant', description: 'Ask a question with the evidence you choose', keywords: 'chat ask companion question' },
    ],
  },
  {
    id: 'review', label: 'Review', items: [
      { label: 'Deliveries', href: '/cmo', icon: PackageCheck, guide: 'deliveries', description: 'Check CDMO files against their original sources', keywords: 'cmo cdmo upload verify batch coa export' },
      { label: 'Signals', href: '/signals', icon: Radar, description: 'Possible deviations detected from your data, triaged by the assistant', keywords: 'deviation alert excursion oos out of spec trend triage' },
      { label: 'Quality', href: '/quality', icon: FolderKanban, description: 'Prepare quality events, inspect evidence and complete local review', keywords: 'quality deviation investigation qa msat review impact sources' },
    ],
  },
  {
    id: 'analyze', label: 'Analyze', items: [
      { label: 'Trends', href: '/trends', icon: ChartLine, description: 'Any accepted value across batches and over process time, with export', keywords: 'trend chart graph plot batches parameter compare export csv excel control' },
      { label: 'Workbench', href: '/workbench', icon: ClipboardList, description: 'Put deliveries side by side, see what the data shows, and plan the next steps', keywords: 'workbench work plan compare batches gaps findings next steps action proposal evidence request consolidate' },
      { label: 'Simulation', href: '/process-simulation', icon: FlaskConical, guide: 'simulation', description: 'Compare process scenarios and predicted outcomes', keywords: 'freeze drying lyophilization transfer physics' },
    ],
  },
  {
    id: 'results', label: 'Results', items: [
      { label: 'Saved work', href: '/workspaces', icon: FolderOpen, description: 'Saved results, charts, source records and review steps', keywords: 'workspaces results investigation deviation schedule data tables actions' },
      { label: 'Export', href: '/export', icon: Download, description: 'Take batch values or signals to another tool, in the shape it needs', keywords: 'export download csv excel xlsx json file columns units preset' },
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
const DEMO_HIDDEN = new Set(['/sources', '/settings/organization', '/settings/alerts', '/settings/profile']);  // memory is worth showing
export const navGroups = (demo: boolean): NavGroup[] =>
  demo ? NAV_GROUPS.map(group => ({ ...group, items: group.items.filter(item => !DEMO_HIDDEN.has(item.href)) })) : NAV_GROUPS;

/**
 * The sidebar for one view. The pages that view's overview leads to come first, in the same order, and the rest fold
 * under More, so every page stays reachable whatever a person's role. "Everything" keeps the full grouping.
 */
export function navFor(icp: Icp, demo: boolean): NavGroup[] {
  const groups = navGroups(demo);
  if (icp === 'everyone') return groups;
  const start = groups[0], settings = groups[groups.length - 1];
  const pages = groups.slice(1, -1).flatMap(group => group.items);
  const yours = viewPages(icp, demo).flatMap(href => pages.filter(item => item.href === href));
  const more = pages.filter(item => !yours.includes(item));
  return [start, { id: 'yours', label: 'Your work', items: yours }, ...(more.length ? [{ id: 'more', label: 'More', items: more, folded: true }] : []), settings];
}

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
