import {
  Activity, Bot, Boxes, CalendarRange, ClipboardCheck, Cpu, Database, FileText, FlaskConical, FolderKanban,
  Gauge, GitCompareArrows, Home, Lightbulb, LineChart, Search, Settings, ShieldCheck, Tablet, Truck,
  Wrench, Workflow, type LucideIcon,
} from 'lucide-react';

export type NavItem = { label: string; href: string; icon: LucideIcon; match?: string; badge?: string };
export type NavSection = { title: string; items: NavItem[] };

export const NAV: NavSection[] = [
  {
    title: 'Work',
    items: [
      { label: 'Home', href: '/home', icon: Home },
      { label: 'Workspaces', href: '/workspaces', icon: FolderKanban },
      { label: 'Sources', href: '/sources', icon: Database },
    ],
  },
  {
    title: 'Operate',
    items: [
      { label: 'Operations', href: '/operations', icon: Activity },
      { label: 'Batches', href: '/batches/MES-26073', icon: Boxes, match: '/batches' },
      { label: 'Processes', href: '/processes/UP-01', icon: Workflow, match: '/processes' },
      { label: 'Equipment', href: '/equipment/PM-204', icon: Wrench, match: '/equipment' },
      { label: 'Planning', href: '/planning', icon: CalendarRange },
    ],
  },
  {
    title: 'Improve',
    items: [
      { label: 'Opportunities', href: '/opportunities', icon: Lightbulb },
      { label: 'Workbench', href: '/workbench/AN-104', icon: LineChart, match: '/workbench' },
      { label: 'Investigations', href: '/investigations/INV-104', icon: GitCompareArrows, match: '/investigations' },
      { label: 'Optimization', href: '/optimization/OPT-104', icon: Gauge, match: '/optimization' },
      { label: 'Tech Transfer', href: '/tech-transfer', icon: Truck },
    ],
  },
  {
    title: 'Assure',
    items: [
      { label: 'Quality', href: '/quality', icon: ShieldCheck },
      { label: 'Laboratory', href: '/laboratory/QC-948', icon: FlaskConical, match: '/laboratory' },
      { label: 'Documents', href: '/documents/DOC-UP01-03', icon: FileText, match: '/documents' },
      { label: 'Reviews', href: '/reviews/REV-01', icon: ClipboardCheck, match: '/reviews', badge: '2' },
    ],
  },
  {
    title: 'Platform',
    items: [
      { label: 'Knowledge', href: '/knowledge', icon: Search },
      { label: 'Agents', href: '/agents', icon: Bot },
      { label: 'Runs', href: '/runs/RUN-2026-1042', icon: Cpu, match: '/runs' },
      { label: 'Operator tablet', href: '/operator/shift', icon: Tablet, match: '/operator' },
    ],
  },
];

export const SETTINGS_NAV: NavItem = { label: 'Settings & Governance', href: '/settings/governance', icon: Settings, match: '/settings' };

/** All 32 frames, used by the command palette. */
export const SCREENS: Array<{ id: string; href: string; title: string; keywords?: string }> = [
  { id: 'AUTH-01', href: '/sign-in', title: 'Sign in / workspace access' },
  { id: 'ONB-01', href: '/onboarding/start', title: 'Fast start · choose data source' },
  { id: 'ONB-02', href: '/onboarding/mapping', title: 'Data intake & entity mapping' },
  { id: 'ONB-03', href: '/onboarding/results', title: 'First result & data health' },
  { id: 'HOME-01', href: '/home', title: 'Daily manufacturing briefing' },
  { id: 'WORK-01', href: '/workspaces', title: 'Objective workspaces' },
  { id: 'SOURCES-01', href: '/sources', title: 'Connections & source coverage', keywords: 'DeltaV PI Veeva LabWare Maximo SAP' },
  { id: 'OPS-01', href: '/operations', title: 'Operations control' },
  { id: 'BATCH-01', href: '/batches/MES-26073', title: 'Batch 360 · MES-26073' },
  { id: 'BATCH-02', href: '/batches/MES-26073/timeline', title: 'Batch events & genealogy · MES-26073' },
  { id: 'PROC-01', href: '/processes/UP-01', title: 'Process context · UP-01' },
  { id: 'INTEL-01', href: '/opportunities', title: 'Process intelligence inbox' },
  { id: 'ANALYSIS-01', href: '/workbench/AN-104', title: 'Scientific workbench · AN-104' },
  { id: 'INV-01', href: '/investigations/INV-104', title: 'Causal investigation · INV-104' },
  { id: 'OPT-01', href: '/optimization/OPT-104', title: 'Optimization sandbox · OPT-104' },
  { id: 'EQP-01', href: '/equipment/PM-204', title: 'Equipment · PM-204 feed pump' },
  { id: 'QUAL-01', href: '/quality', title: 'Quality & release overview' },
  { id: 'QUAL-02', href: '/quality/Q-DEV-031', title: 'Deviation · Q-DEV-031' },
  { id: 'LAB-01', href: '/laboratory/QC-948', title: 'Laboratory results · QC-948' },
  { id: 'TRANSFER-01', href: '/tech-transfer', title: 'Tech transfer portfolio' },
  { id: 'TRANSFER-02', href: '/tech-transfer/TT-006', title: 'Tech transfer workspace · TT-006' },
  { id: 'PLAN-01', href: '/planning', title: 'Planning & constraints' },
  { id: 'DOC-01', href: '/documents/DOC-UP01-03', title: 'Controlled draft · DOC-UP01-03' },
  { id: 'REV-01', href: '/reviews/REV-01', title: 'Approval & action center' },
  { id: 'KNOW-01', href: '/knowledge', title: 'Knowledge search', keywords: 'SOP search' },
  { id: 'AGENT-01', href: '/agents', title: 'Agents & runs' },
  { id: 'AGENT-02', href: '/runs/RUN-2026-1042', title: 'Agent run trace · RUN-2026-1042' },
  { id: 'SETTINGS-01', href: '/settings/governance', title: 'Workspace governance' },
  { id: 'OPERATOR-01', href: '/operator/shift', title: 'Operator · shift companion' },
  { id: 'OPERATOR-02', href: '/operator/handoff', title: 'Operator · shift handoff' },
  { id: 'OPERATOR-03', href: '/operator/troubleshooting', title: 'Operator · troubleshooting ALM-UP-204' },
  { id: 'MKT-01', href: '/', title: 'Product landing page' },
];
