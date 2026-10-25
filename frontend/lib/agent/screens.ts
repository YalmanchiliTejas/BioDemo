import type { ScopeChip } from './types';

export type ScreenKind = 'analytical' | 'transfer' | 'quality' | 'planning' | 'general';
export type Suggestion = { label: string; templateId: string };

type ScreenAgentContext = { frame: string; kind: ScreenKind; scope: ScopeChip[]; suggestions: Suggestion[] };

const MESA: ScopeChip = { id: 'fac-mesa', kind: 'FACILITY', value: 'Mesa Site · Cleanroom Suite 3B · Skid BR-UP-01' };
const CAMPAIGN: ScopeChip = { id: 'batches-3', kind: 'BATCHES', value: 'CMP-26-10 · MES-26071, MES-26072, MES-26073' };

const S = {
  feed: { label: 'Correlate feed droop with CMMS', templateId: 'feed-cmms' },
  transfer: { label: 'Identify PID constant gaps for Durham', templateId: 'tt-gap' },
  dossier: { label: 'Delegate full investigation dossier', templateId: 'dossier' },
  rca: { label: 'Draft deviation Q-DEV-031 RCA', templateId: 'dossier' },
  hplc: { label: 'Assemble HPLC outlier evidence', templateId: 'dossier' },
  schedule: { label: 'Solve PM-204 sanitization conflict', templateId: 'schedule' },
} satisfies Record<string, Suggestion>;

const ANALYTICAL: Suggestion[] = [S.feed, S.dossier];
const QUALITY: Suggestion[] = [S.rca, S.hplc, S.feed];
const ALL: Suggestion[] = [S.feed, S.dossier, S.transfer, S.schedule];

const CONTEXTS: Record<string, Omit<ScreenAgentContext, 'frame'>> = {
  'HOME-01': { kind: 'general', scope: [MESA, CAMPAIGN], suggestions: [S.dossier, S.feed, S.schedule, S.transfer] },
  'WORK-01': { kind: 'general', scope: [MESA, CAMPAIGN], suggestions: ALL },
  'SOURCES-01': { kind: 'general', scope: [MESA], suggestions: ALL },
  'OPS-01': { kind: 'analytical', scope: [MESA, CAMPAIGN], suggestions: [S.feed, S.schedule] },
  'BATCH-01': { kind: 'analytical', scope: [MESA, { id: 'batch-73', kind: 'BATCHES', value: 'CMP-26-10 · MES-26073' }], suggestions: ANALYTICAL },
  'BATCH-02': { kind: 'analytical', scope: [MESA, { id: 'batch-73', kind: 'BATCHES', value: 'CMP-26-10 · MES-26073' }], suggestions: ANALYTICAL },
  'PROC-01': { kind: 'analytical', scope: [MESA, CAMPAIGN], suggestions: ANALYTICAL },
  'INTEL-01': { kind: 'analytical', scope: [MESA, CAMPAIGN], suggestions: ALL },
  'ANALYSIS-01': { kind: 'analytical', scope: [MESA, CAMPAIGN, { id: 'rec-hist', kind: 'RECORD', value: 'Historian_UP01_Oct.csv §4.2' }], suggestions: ANALYTICAL },
  'INV-01': { kind: 'analytical', scope: [MESA, CAMPAIGN, { id: 'proj-inv', kind: 'PROJECT', value: 'INV-104' }], suggestions: [S.dossier, S.feed] },
  'OPT-01': { kind: 'analytical', scope: [MESA, CAMPAIGN], suggestions: [S.feed, S.transfer] },
  'EQP-01': { kind: 'analytical', scope: [MESA, { id: 'rec-wo', kind: 'RECORD', value: 'CMMS WO-8819' }], suggestions: [S.feed, S.schedule] },
  'QUAL-01': { kind: 'quality', scope: [MESA, CAMPAIGN], suggestions: QUALITY },
  'QUAL-02': { kind: 'quality', scope: [MESA, CAMPAIGN, { id: 'rec-dev', kind: 'RECORD', value: 'Veeva QMS Q-DEV-031' }], suggestions: QUALITY },
  'LAB-01': { kind: 'quality', scope: [MESA, { id: 'rec-qc', kind: 'RECORD', value: 'LabWare QC-948' }], suggestions: [S.hplc, S.rca] },
  'TRANSFER-01': { kind: 'transfer', scope: [{ id: 'proj-tt', kind: 'PROJECT', value: 'TT-006 · Gate 2 (Engineering & CPP dossier)' }], suggestions: [S.transfer] },
  'TRANSFER-02': { kind: 'transfer', scope: [{ id: 'proj-tt', kind: 'PROJECT', value: 'TT-006 · Gate 2 (Engineering & CPP dossier)' }, { id: 'fac-pair', kind: 'FACILITY', value: 'Mesa 500L single-use → Durham 2000L stainless' }], suggestions: [S.transfer] },
  'PLAN-01': { kind: 'planning', scope: [{ id: 'fac-3b', kind: 'FACILITY', value: 'Mesa Site · Cleanroom Suite 3B' }], suggestions: [S.schedule] },
  'DOC-01': { kind: 'general', scope: [MESA, { id: 'rec-doc', kind: 'RECORD', value: 'DOC-UP01-03 v0.2' }], suggestions: [S.transfer, S.rca] },
  'REV-01': { kind: 'general', scope: [MESA], suggestions: ALL },
  'KNOW-01': { kind: 'general', scope: [MESA], suggestions: ALL },
  'AGENT-01': { kind: 'general', scope: [MESA, CAMPAIGN], suggestions: ALL },
  'AGENT-02': { kind: 'general', scope: [MESA, CAMPAIGN], suggestions: ALL },
  'SETTINGS-01': { kind: 'general', scope: [MESA], suggestions: ALL },
};

/** Route prefix → frame id for screens inside the app shell. Longest prefix wins. */
const ROUTES: Array<[string, string]> = [
  ['/home', 'HOME-01'], ['/workspaces', 'WORK-01'], ['/sources', 'SOURCES-01'], ['/operations', 'OPS-01'],
  ['/batches/MES-26073/timeline', 'BATCH-02'], ['/batches', 'BATCH-01'], ['/processes', 'PROC-01'],
  ['/opportunities', 'INTEL-01'], ['/workbench', 'ANALYSIS-01'], ['/investigations', 'INV-01'], ['/optimization', 'OPT-01'],
  ['/equipment', 'EQP-01'], ['/quality/Q-DEV-031', 'QUAL-02'], ['/quality', 'QUAL-01'], ['/laboratory', 'LAB-01'],
  ['/tech-transfer/TT-006', 'TRANSFER-02'], ['/tech-transfer', 'TRANSFER-01'], ['/planning', 'PLAN-01'],
  ['/documents', 'DOC-01'], ['/reviews', 'REV-01'], ['/knowledge', 'KNOW-01'], ['/agents', 'AGENT-01'], ['/runs', 'AGENT-02'],
  ['/settings', 'SETTINGS-01'],
];

export const FRAME_HREF: Record<string, string> = {
  'ANALYSIS-01': '/workbench/AN-104', 'TRANSFER-02': '/tech-transfer/TT-006', 'QUAL-02': '/quality/Q-DEV-031', 'PLAN-01': '/planning',
  'DOC-01': '/documents/DOC-UP01-03', 'REV-01': '/reviews/REV-01', 'WORK-01': '/workspaces', 'HOME-01': '/home',
};

export function frameForPath(pathname: string): string | null {
  const p = pathname.replace(/\/$/, '');
  const hit = ROUTES.filter(([r]) => p === r || p.startsWith(r + '/')).sort((a, b) => b[0].length - a[0].length)[0];
  return hit?.[1] ?? null;
}

export function screenContext(frame: string | null): ScreenAgentContext {
  const c = (frame && CONTEXTS[frame]) || { kind: 'general' as const, scope: [MESA, CAMPAIGN], suggestions: ALL };
  return { frame: frame ?? 'HOME-01', ...c };
}

export function hasAgentContext(frame?: string) {
  return !!frame && frame in CONTEXTS;
}

export const SCOPE_KIND_LABEL: Record<ScopeChip['kind'], string> = {
  FACILITY: 'Facility / skid', BATCHES: 'Campaign / batches', SPAN: 'Telemetry span', RECORD: 'Record', PROCESS: 'Process', PROJECT: 'Project',
};

/** Extra chips the user can attach from the composer. */
export const ATTACHABLE_SCOPE: ScopeChip[] = [
  MESA,
  CAMPAIGN,
  { id: 'span-260', kind: 'SPAN', value: 'T+260.0h – T+272.0h (12.0h window · feed droop)' },
  { id: 'rec-hist', kind: 'RECORD', value: 'Historian_UP01_Oct.csv §4.2' },
  { id: 'rec-wo', kind: 'RECORD', value: 'CMMS WO-8819' },
  { id: 'rec-dev', kind: 'RECORD', value: 'Veeva QMS Q-DEV-031' },
  { id: 'rec-qc', kind: 'RECORD', value: 'LabWare QC-948' },
];
