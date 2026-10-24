// Pure display mapping for server records. No React, no I/O.
// The rule: recommendation, approval, delivery, outcome and effectiveness are separate
// facts, and no label may imply a later one than the server has recorded.

import type {
  BasisRef,
  EvidenceRecord,
  Mission,
  Proposal,
} from "./types";

export type Tone = "waiting" | "go" | "done" | "warn" | "stop" | "neutral";
export type StatusDisplay = { key: string; label: string; tone: Tone };

export const USER_AUTHORED_BASIS = "User-authored — no source evidence linked";

/** Roles that still have to approve the current content of the proposal. */
export function pendingRoles(p: Proposal): string[] {
  const approved = new Set(
    (p.approvals ?? [])
      .filter(
        (a) =>
          a.decision === "approved" &&
          (!p.content_hash || !a.content_hash || a.content_hash === p.content_hash),
      )
      .map((a) => a.role),
  );
  const left = p.required_roles.filter((r) => !approved.has(r));
  return left.length ? left : [...p.required_roles];
}

const DELIVERY_FACTS = ["delivered", "unknown", "dispatching", "failed"];

export function proposalStatus(p: Proposal): StatusDisplay {
  if ((p.outcomes ?? []).length > 0) {
    return { key: "outcome_recorded", label: "Outcome recorded", tone: "done" };
  }
  if (DELIVERY_FACTS.includes(p.execution_status)) {
    switch (p.execution_status) {
      case "delivered":
        return { key: "delivered", label: `Sent to ${p.target_system}`, tone: "done" };
      case "unknown":
        return {
          key: "unknown",
          label: "Delivery unconfirmed — reconciling",
          tone: "warn",
        };
      case "dispatching":
        return { key: "dispatching", label: `Sending to ${p.target_system}`, tone: "go" };
      default:
        return { key: "failed", label: "Delivery failed", tone: "stop" };
    }
  }
  if (p.status === "rejected") {
    return { key: "rejected", label: "Rejected", tone: "stop" };
  }
  if (p.status === "stale" || p.execution_status === "awaiting_reassessment") {
    return {
      key: "needs_reassessment",
      label: "Evidence changed — needs reassessment",
      tone: "warn",
    };
  }
  if (p.status === "proposed") {
    return {
      key: "proposed",
      label: `Awaiting approval: ${pendingRoles(p).join(", ")}`,
      tone: "waiting",
    };
  }
  if (p.status === "approved") {
    return { key: "approved_queued", label: "Approved — not yet sent", tone: "go" };
  }
  if (p.status === "withdrawn") {
    return { key: "withdrawn", label: "Withdrawn", tone: "neutral" };
  }
  return { key: "other", label: `Status: ${p.status}`, tone: "neutral" };
}

export function effectivenessLabel(value: string | null | undefined): string {
  if (value === "effective") return "Assessed effective";
  if (value === "ineffective") return "Assessed not effective";
  return "Effectiveness not assessed";
}

export type Stage = { name: string; label: string };
/** Decision, delivery, outcome and effectiveness shown side by side, never merged. */
export function proposalStages(p: Proposal): Stage[] {
  const decision =
    p.status === "approved"
      ? "Approved"
      : p.status === "rejected"
        ? "Rejected"
        : p.status === "stale"
          ? "Evidence changed — needs reassessment"
          : p.status === "proposed"
            ? `Awaiting approval: ${pendingRoles(p).join(", ")}`
            : `Status: ${p.status}`;
  const delivery =
    p.execution_status === "delivered"
      ? `Sent to ${p.target_system}`
      : p.execution_status === "unknown"
        ? "Delivery unconfirmed — reconciling"
        : p.execution_status === "dispatching"
          ? `Sending to ${p.target_system}`
          : p.execution_status === "failed"
            ? "Delivery failed"
            : p.execution_status === "awaiting_reassessment"
              ? "Held — needs reassessment"
              : p.execution_status === "queued"
                ? "Approved — not yet sent"
                : "Nothing sent";
  const outcomes = (p.outcomes ?? []).length;
  return [
    { name: "Decision", label: decision },
    { name: "Delivery", label: delivery },
    {
      name: "Outcome",
      label: outcomes ? `Outcome recorded (${outcomes})` : "No outcome recorded",
    },
    { name: "Effectiveness", label: effectivenessLabel(p.effectiveness) },
  ];
}

export const needsReauthentication = (risk: string) =>
  risk === "high" || risk === "critical";

/** Outcomes may be recorded once the action is approved or confirmed sent. */
export const canRecordOutcome = (p: Proposal) =>
  p.execution_status === "delivered" || p.status === "approved";

export const evidenceTitle = (record: EvidenceRecord): string =>
  record.state.metadata?.title?.trim() ||
  `${record.state.source_system} ${record.state.source_record_id}`;

export function evidenceTitles(records: EvidenceRecord[]): Record<string, string> {
  const titles: Record<string, string> = {};
  for (const r of records) titles[r.id] = evidenceTitle(r);
  return titles;
}

export function basisLabel(ref: BasisRef, titles: Record<string, string> = {}): string {
  if (ref.kind === "mission") return USER_AUTHORED_BASIS;
  const name = ref.kind === "evidence" ? titles[ref.id] : undefined;
  const base = name ?? `${ref.kind === "evidence" ? "Evidence" : ref.kind} ${ref.id}`;
  return ref.revision !== undefined ? `${base} · revision ${ref.revision}` : base;
}

export const isUserAuthoredOnly = (basis: BasisRef[]) =>
  basis.length > 0 && basis.every((b) => b.kind === "mission");

export const missionBasis = (missionId: string): BasisRef[] => [
  { kind: "mission", id: missionId },
];

export const evidenceBasis = (record: EvidenceRecord): BasisRef => ({
  kind: "evidence",
  id: record.id,
  revision: record.revision,
  ...(record.state.site_id ? { site_id: record.state.site_id } : {}),
});

export const PROPOSAL_OPERATIONS: {
  id: string;
  label: string;
  system: string;
}[] = [
  { id: "place_hold", label: "Place hold", system: "MES" },
  { id: "request_retest", label: "Request retest", system: "LIMS" },
  { id: "submit_deviation", label: "Submit deviation", system: "QMS" },
  { id: "reschedule_batch", label: "Reschedule batch", system: "" },
  { id: "create_work_order", label: "Create work order", system: "" },
  { id: "send_notification", label: "Send notification", system: "" },
];

export const operationLabel = (id: string) =>
  PROPOSAL_OPERATIONS.find((o) => o.id === id)?.label ??
  id.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

export const riskLabel = (risk: string) =>
  `${risk.charAt(0).toUpperCase()}${risk.slice(1)} risk`;

const MISSION_STATUS: Record<string, string> = {
  active: "Open",
  paused_budget: "Paused — budget",
  blocked: "Blocked",
  cancelled: "Cancelled",
  archived: "Archived",
};

export type MissionDisplay = {
  id: string;
  goal: string;
  statusLabel: string;
  ownerId: string;
  siteLabel: string;
  createdAt: string;
  noteCount: number;
  correctionCount: number;
  pendingDecisionCount: number;
  constraintCount: number;
};

export function missionDisplay(m: Mission): MissionDisplay {
  const sites = m.scope?.site_ids ?? [];
  return {
    id: m.mission_id,
    goal: m.objective,
    statusLabel: MISSION_STATUS[m.status] ?? m.status,
    ownerId: m.owner_id,
    siteLabel: sites.length ? sites.join(", ") : "No site scope",
    createdAt: m.created_at,
    noteCount: (m.notes ?? []).length,
    correctionCount: (m.corrections ?? []).length,
    pendingDecisionCount: (m.pending_decisions ?? []).filter(
      (d) => d.status === "pending",
    ).length,
    constraintCount: (m.constraints ?? []).length,
  };
}

export const initials = (actor: string) =>
  actor
    .split(/[^A-Za-z0-9]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("") || "?";

export const authLabel = (mode: string) =>
  mode === "development_headers"
    ? "Development sign-in"
    : mode === "oidc"
      ? "SSO"
      : mode;
