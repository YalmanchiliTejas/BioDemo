// Wire types for the /v1 HTTP API (backend/src/lifesci/api.py). Pure types, no runtime code.

export type Me = {
  tenant_id: string;
  actor_id: string;
  actor_kind?: string;
  roles: string[];
  site_ids: string[];
  auth_mode: string;
};

export type Health = {
  status?: string;
  api_version?: string;
  backend?: string;
  models_available: boolean;
  continuing: string[];
  blocked_task_kinds: string[];
  outbox_pending?: number;
};

export type MissionNote = { note_id: string; body: string; author: string; at: string };
export type Correction = {
  correction_id?: string;
  text: string;
  by?: string;
  at?: string;
  source_ref?: unknown;
  claim_ref?: unknown;
};
export type PendingDecision = {
  decision_id: string;
  question: string;
  options: string[];
  decider_role: string;
  status: string;
  answer?: string | null;
  requested_at?: string;
};
export type Obligation = {
  obligation_id?: string;
  description: string;
  status: string;
  due_at?: string | null;
  runtime_status?: string;
  runtime_issues?: string[];
};

export type Mission = {
  mission_id: string;
  objective: string;
  owner_id: string;
  scope: { site_ids?: string[]; [key: string]: unknown };
  constraints: string[];
  notes: MissionNote[];
  corrections: Correction[];
  pending_decisions: PendingDecision[];
  obligations: Obligation[];
  status: string;
  created_at: string;
  revision: number;
};

export type BasisRef = {
  kind: string;
  id: string;
  revision?: number;
  site_id?: string | null;
};

export type Approval = {
  approval_id: string;
  proposal_id: string;
  proposal_revision?: number;
  content_hash?: string;
  actor_id: string;
  role: string;
  decision: "approved" | "rejected" | string;
  comment?: string | null;
  decided_at: string;
  authentication?: { method?: string };
};

export type Outcome = {
  outcome_id: string;
  proposal_id: string;
  observation: string;
  measure: string;
  observed_value: unknown;
  evidence: BasisRef[];
  attribution_limits: string;
  expected_result?: string;
  recorded_by: string;
  recorded_at: string;
};

export type ProposalStatus = "proposed" | "approved" | "rejected" | "stale" | string;
export type ExecutionStatus =
  | "not_started"
  | "queued"
  | "awaiting_reassessment"
  | "dispatching"
  | "delivered"
  | "unknown"
  | "failed"
  | string;

export type Proposal = {
  proposal_id: string;
  operation: string;
  target_system: string;
  target_id: string;
  payload?: Record<string, unknown>;
  rationale: string;
  expected_result: string;
  owner_id: string;
  follow_up_measure?: string | null;
  constraints?: string[];
  risk: string;
  required_roles: string[];
  status: ProposalStatus;
  execution_status: ExecutionStatus;
  effectiveness: string;
  effectiveness_rationale?: string;
  basis: BasisRef[];
  stale_reasons: (string | { reason?: string; source?: string })[];
  content_hash?: string;
  mission_id?: string | null;
  site_id?: string | null;
  revision: number;
  requested_by: string;
  created_at: string;
  approvals: Approval[];
  outcomes: Outcome[];
  can_decide: string[];
};

export type EvidenceRecord = {
  id: string;
  revision: number;
  state: {
    source_system: string;
    source_record_id: string;
    media_type?: string;
    site_id?: string | null;
    event_time?: string | null;
    recorded_at?: string;
    metadata?: { title?: string; synthetic?: boolean; [key: string]: unknown };
    status?: string;
  };
};

export type StreamEvent = {
  seq: number;
  type: string;
  aggregate_kind?: string;
  aggregate_id?: string;
  occurred_at?: string;
  payload?: Record<string, unknown>;
};
export type StreamResult = { snapshot: Mission; events: StreamEvent[]; cursor: number };

export type MissionInput = {
  objective: string;
  owner_id: string;
  scope: { site_ids: string[] };
  constraints?: string[];
};
export type ProposalInput = {
  target_system: string;
  operation: string;
  target_id: string;
  payload: Record<string, unknown>;
  basis: BasisRef[];
  rationale: string;
  expected_result: string;
  owner_id: string;
  follow_up_measure?: string;
  constraints?: string[];
  site_id?: string;
  mission_id?: string;
};
export type DecisionInput = {
  expected_revision: number;
  decision: "approved" | "rejected";
  role: string;
  comment?: string;
  authentication?: { method: string };
};
export type OutcomeInput = {
  observation: string;
  measure: string;
  observed_value: string;
  evidence: BasisRef[];
  attribution_limits: string;
};

export type ConnectorConfig = {
  connector_id: string;
  family: string;
  transport: string;
  site_id: string;
  owner: string;
  options: Record<string, unknown>;
  mapping?: Record<string, unknown>;
  enabled?: boolean;
};
export type ConnectorRecord = ConnectorConfig & {
  revision: number;
  qualification: string;
  last_sync: string | null;
  last_error: string | null;
  last_result?: { ingested: number; duplicates: number; corrections: number; mapping_issues: number };
};
export type ConnectorCatalog = {
  families: { system: string; record_type: string; template: Record<string, unknown> }[];
  transports: { transport: string; available: boolean }[];
  vendor_qualification: string;
};
