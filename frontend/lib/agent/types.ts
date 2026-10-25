import type { ClaimKind } from '@/components/ui';
import type { UserRole } from '@/lib/app-context';

/** Finite state machine for agent execution (MOS-AGENT-DELTA §3). */
export type AgentTaskState =
  | 'READY'
  | 'SCOPING_PLAN_PREVIEW'
  | 'QUEUED'
  | 'RUNNING'
  | 'NEEDS_USER_INPUT'
  | 'WAITING_ON_PERMISSION'
  | 'PROPOSAL_NEEDS_REVIEW'
  | 'APPROVED_FOR_HANDOFF'
  | 'SENT_TO_EXTERNAL_SYSTEM'
  | 'MONITORING_ACTIVE'
  | 'FAILED'
  | 'CANCELLED';

export type ComposerMode = 'FIND' | 'ASK' | 'DELEGATE';

export type ScopeKind = 'FACILITY' | 'BATCHES' | 'SPAN' | 'RECORD' | 'PROCESS' | 'PROJECT';
export type ScopeChip = { id: string; kind: ScopeKind; value: string };

export type Output = { text: string; kind: ClaimKind; citations?: string[] };
export type Answers = Record<string, string>;

export type Checkpoint = {
  id: string;
  title: string;
  /** Short label used in the run strip, e.g. "CMMS cross-ref". */
  short: string;
  subtask?: string;
  tool: string;
  durationSec: number;
  /** Source system that becomes resolved when this checkpoint completes. */
  resolvesSource?: string;
  outputs: Output[] | ((answers: Answers) => Output[]);
};

export type GateOption = { label: string; value: string; recommended?: boolean; note?: string; /** Keeps the task blocked (e.g. "Pause until…"). */ holds?: boolean };
export type Gate = {
  id: string;
  kind: 'INPUT' | 'PERMISSION';
  /** Index of the checkpoint that cannot start until this gate is resolved. */
  beforeStep: number;
  question: string;
  context?: string;
  citations?: string[];
  options: GateOption[];
};

export type ParameterDiff = { parameter: string; current: string; proposed: string; kind: ClaimKind; citation?: string; note?: string };

export type ArtifactData =
  | { type: 'CHART_DIFF'; xLabel: string; unit: string; window: [number, number]; observed: Array<[number, number]>; reference: Array<[number, number]>; compensated: Array<[number, number]>; note: string; citations: string[] }
  | { type: 'HYPOTHESIS_MATRIX'; rows: Array<{ hypothesis: string; statistic: string; for: string; against: string; kind: ClaimKind; citations: string[] }>; note: string }
  | { type: 'TABLE_DIFF'; columns: [string, string, string]; rows: ParameterDiff[]; note: string }
  | { type: 'DOC_DRAFT'; docId: string; version: string; sections: Array<{ heading: string; body: string; kind: ClaimKind; citations: string[] }> }
  | { type: 'SCHEDULE_DIFF'; options: Array<{ key: string; title: string; recommended?: boolean; rows: Array<[string, string]>; risks: string[]; citations: string[] }> }
  | { type: 'REVIEW_GATE' };

export type ArtifactDef = {
  id: string;
  title: string;
  kind: ClaimKind;
  summary: string;
  /** Becomes visible once this many checkpoints are complete (intermediate results). */
  availableAfter: number;
  /** Frame whose canvas can receive the artifact. */
  insertTarget?: string;
  build: (answers: Answers, selections: Record<string, string>) => ArtifactData;
};

export type ReviewDef = {
  proposalId: string;
  title: string;
  signOffRoles: UserRole[];
  riskTier: 'Low' | 'Medium' | 'High';
  systemOfRecord: string;
  rationale: string;
  expectedResult: string;
  constraints: string;
  owner: string;
  changeMind: string[];
  monitor: string;
  diff: (answers: Answers, selections: Record<string, string>) => ParameterDiff[];
};

export type TaskTemplate = {
  id: string;
  taskId: string;
  title: string;
  agent: string;
  originFrame: string;
  summary: string;
  keywords: string[];
  defaultScope: ScopeChip[];
  sources: string[];
  /** Systems in scope that are not connected; shown up front in the plan preview. */
  unavailableSources?: string[];
  subtasks?: string[];
  checkpoints: Checkpoint[];
  gates?: Gate[];
  artifacts: ArtifactDef[];
  review?: ReviewDef;
  runTraceHref?: string;
};

export type ArtifactState = { insertedInto: string[]; pinned: boolean; revisionNote?: string };

export type AgentMessage = {
  id: string;
  at: number;
  from: 'user' | 'agent' | 'system';
  text: string;
  outputs?: Output[];
  artifactId?: string;
};

export type ReviewRecord = {
  routedAt?: number;
  signedBy?: { name: string; role: UserRole; at: number; meaning: string };
  dispatchedAt?: number;
  monitoringSince?: number;
  revisionNote?: string;
};

export type AgentTask = {
  uid: string;
  templateId: string;
  taskId: string;
  title: string;
  agent: string;
  mode: ComposerMode;
  prompt: string;
  scope: ScopeChip[];
  originFrame: string;
  originHref: string;
  requesterRole: UserRole;
  state: AgentTaskState;
  /** Number of completed checkpoints. */
  stepIndex: number;
  stepElapsed: number;
  startedAt: number;
  endedAt?: number;
  answers: Answers;
  selections: Record<string, string>;
  messages: AgentMessage[];
  artifacts: Record<string, ArtifactState>;
  review: ReviewRecord;
};

export const ACTIVE_STATES: AgentTaskState[] = ['QUEUED', 'RUNNING', 'NEEDS_USER_INPUT', 'WAITING_ON_PERMISSION'];
export const BLOCKED_STATES: AgentTaskState[] = ['NEEDS_USER_INPUT', 'WAITING_ON_PERMISSION'];
