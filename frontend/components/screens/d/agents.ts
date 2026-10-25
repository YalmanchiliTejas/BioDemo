// Synthetic configuration for the background agent fabric (AGENT-01). Agents are read-only; outputs are proposals.

export type AgentStatus = 'idle' | 'running' | 'awaiting_review' | 'paused';

export type AgentRole = {
  id: string;
  name: string;
  purpose: string;
  trigger: string;
  scope: string[];
  produces: string;
  gate: string;
  owner: string;
  status: AgentStatus;
  detail: string;
  reviewCount?: number;
  href?: string;
};

export const AGENT_ROLES: AgentRole[] = [
  {
    id: 'data-intake', name: 'Data Intake', purpose: 'Pull, align and quality-check records from connected systems for a workspace.',
    trigger: 'New batch phase, connector sync, or a user request', scope: ['OSIsoft PI', 'DeltaV eBR', 'LabWare LIMS'],
    produces: 'Aligned dataset drafts with gap and unit reports', gate: 'MSAT Lead confirms mappings', owner: 'Alex Rivera',
    status: 'running', detail: 'Resolving 3 of 8 sources for MES-26073 Phase 05 refresh',
  },
  {
    id: 'yield-sentry', name: 'MSAT Yield Sentry', purpose: 'Watch campaign yield and CPP trends; open an investigation draft when a batch falls outside its envelope.',
    trigger: 'Yield index < target − 3 pts or CPP alarm on a campaign batch', scope: ['OSIsoft PI', 'DeltaV eBR', 'Maximo CMMS', 'LabWare LIMS'],
    produces: 'Investigation trace and recipe patch proposal', gate: 'MSAT Lead + QA Reviewer sign in REV-01', owner: 'Alex Rivera',
    status: 'awaiting_review', detail: 'RUN-2026-1042 stopped at human checkpoint', reviewCount: 1, href: '/runs/RUN-2026-1042',
  },
  {
    id: 'tt-link', name: 'Tech Transfer Link', purpose: 'Compare donor and recipient process parameters and flag unmapped items.',
    trigger: 'Tech transfer gate review scheduled', scope: ['Documentum', 'DeltaV eBR'],
    produces: 'Parameter gap list for TT-006', gate: 'Transfer lead reviews gap list', owner: 'Alex Rivera',
    status: 'idle', detail: 'Last run 2 days ago · TT-006 Gate 2 gap list', href: '/tech-transfer/TT-006',
  },
  {
    id: 'deviation-drafter', name: 'Deviation Narrative Drafter', purpose: 'Draft deviation descriptions and timelines from cited records.',
    trigger: 'Deviation opened in Veeva Vault QMS', scope: ['Veeva Vault QMS', 'DeltaV eBR', 'OSIsoft PI'],
    produces: 'Narrative and timeline drafts (never filed automatically)', gate: 'QA Reviewer edits and files in QMS', owner: 'Priya Natarajan',
    status: 'awaiting_review', detail: '2 narrative drafts for Q-DEV-031', reviewCount: 2, href: '/quality/Q-DEV-031',
  },
  {
    id: 'lab-watcher', name: 'Lab Result Watcher', purpose: 'Flag out-of-trend LIMS results against campaign history.',
    trigger: 'New LIMS result on an active batch', scope: ['LabWare LIMS'],
    produces: 'OOT notifications with trend context', gate: 'Analyst and QA review in LIMS', owner: 'Priya Natarajan',
    status: 'idle', detail: 'Last event QC-948 OOT at 11:40 UTC', href: '/laboratory/QC-948',
  },
  {
    id: 'maint-correlator', name: 'Maintenance Correlator', purpose: 'Link equipment alarms to recent work orders and calibration records.',
    trigger: 'Equipment alarm or work order closed on a GMP asset', scope: ['Maximo CMMS', 'OSIsoft PI'],
    produces: 'Correlation notes on equipment records', gate: 'Maintenance planner reviews', owner: 'Marcus Bell',
    status: 'running', detail: 'Correlating ALM-UP-204 with PM-204 history', href: '/equipment/PM-204',
  },
  {
    id: 'schedule-checker', name: 'Schedule Conflict Checker', purpose: 'Detect equipment and resource overlaps in the MES schedule.',
    trigger: 'MES schedule export changes', scope: ['DeltaV eBR', 'Maximo CMMS'],
    produces: 'Conflict reports and resolution scenarios', gate: 'Cleanroom Supervisor chooses a scenario', owner: 'Marcus Bell',
    status: 'awaiting_review', detail: 'CIP-UP01-118 overlaps MES-26074 by 4.5 h', reviewCount: 1, href: '/planning',
  },
  {
    id: 'knowledge-indexer', name: 'Knowledge Indexer', purpose: 'Keep the search index current with effective document versions and permissions.',
    trigger: 'Nightly, or on document effective-date change', scope: ['Documentum', 'Veeva Vault QMS', 'Maximo CMMS', 'DeltaV eBR', 'LabWare LIMS'],
    produces: 'Search index entries (no document edits)', gate: 'None needed — index only; permissions inherited', owner: 'IT · R. Osei',
    status: 'idle', detail: 'Index refreshed 08:40 UTC · 41,208 records', href: '/knowledge',
  },
  {
    id: 'audit-packager', name: 'Audit Packager', purpose: 'Assemble evidence and audit-trail packages for a decision or record.',
    trigger: 'Review approved or on request', scope: ['Platform audit log'],
    produces: 'Audit package drafts with hash manifest', gate: 'QA Reviewer releases package', owner: 'Priya Natarajan',
    status: 'paused', detail: 'Paused by P. Natarajan pending template update', href: '/settings/governance',
  },
];

export const LEDGER = [
  { run: 'RUN-2026-1042', agent: 'MSAT Yield Sentry', trigger: 'ALM-UP-204 + yield < target', duration: '6m 41s', scope: 'PI, eBR, CMMS, LIMS', outcome: 'Awaiting human authorization', tone: 'warning' as const, reviewer: 'A. Rivera, P. Natarajan', href: '/runs/RUN-2026-1042' },
  { run: 'RUN-2026-1041', agent: 'Lab Result Watcher', trigger: 'QC-948 result posted', duration: '0m 38s', scope: 'LIMS', outcome: 'Notification sent', tone: 'success' as const, reviewer: 'M. Okafor' },
  { run: 'RUN-2026-1040', agent: 'Deviation Narrative Drafter', trigger: 'Q-DEV-031 opened', duration: '2m 12s', scope: 'QMS, eBR, PI', outcome: 'Draft awaiting review', tone: 'warning' as const, reviewer: 'P. Natarajan' },
  { run: 'RUN-2026-1039', agent: 'Schedule Conflict Checker', trigger: 'MES schedule export', duration: '1m 05s', scope: 'eBR, CMMS', outcome: 'Draft awaiting review', tone: 'warning' as const, reviewer: 'M. Bell' },
  { run: 'RUN-2026-1038', agent: 'Data Intake', trigger: 'PI connector resync', duration: '4m 50s', scope: 'PI', outcome: 'Completed with gap (42 min)', tone: 'neutral' as const, reviewer: 'A. Rivera' },
  { run: 'RUN-2026-1037', agent: 'Audit Packager', trigger: 'Manual request', duration: '0m 21s', scope: 'Audit log', outcome: 'Failed: template v3 missing', tone: 'critical' as const, reviewer: '—' },
  { run: 'RUN-2026-1036', agent: 'Knowledge Indexer', trigger: 'Nightly 02:00', duration: '18m 02s', scope: '5 systems', outcome: 'Completed', tone: 'success' as const, reviewer: 'Not required' },
];

export const STREAM_TEMPLATES = [
  { topic: 'historian.sample', text: 'PM204.FLOW_PV 14.4x mL/min · quality GOOD' },
  { topic: 'historian.sample', text: 'PM204.HEAD_P 1.4x bar · quality GOOD' },
  { topic: 'ebr.step', text: 'MES-26073 step 05.4 RUNNING · ack T.Reed' },
  { topic: 'agent.checkpoint', text: 'data-intake resolved source 4/8 (LabWare LIMS)' },
  { topic: 'cmms.read', text: 'maint-correlator read WO-8819, CAL-3310' },
  { topic: 'historian.sample', text: 'BR-UP-01.DO_A 39.x % · quality GOOD' },
  { topic: 'lims.poll', text: 'LabWare poll · 0 new results' },
  { topic: 'agent.heartbeat', text: '9 roles registered · 2 in flight · writeback LOCKED' },
];
