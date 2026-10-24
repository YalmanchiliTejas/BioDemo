import { useState } from "react";
import { RiCheckLine, RiShieldCheckLine } from "@remixicon/react";
import { Button, Sheet } from "../../lab/ui";
import { ApiError, errorMessage, type Proposal } from "./client";
import { useConnected } from "./ConnectedWorkspace";
import {
  basisLabel,
  canRecordOutcome,
  isUserAuthoredOnly,
  needsReauthentication,
  operationLabel,
  proposalStages,
  proposalStatus,
  riskLabel,
} from "./mapping";

const when = (iso: string) => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
};

function CommandDetails({ proposal: p }: { proposal: Proposal }) {
  return (
    <section aria-label="Exact command for review" className="cw-command">
      <h3>Command for approval</h3>
      <p><b>{p.operation}</b> · {p.target_system} · {p.target_id} · Site {p.site_id || "tenant-wide"}</p>
      <pre>{JSON.stringify(p.payload ?? {}, null, 2)}</pre>
      <small>Revision {p.revision} · Content hash {p.content_hash || "unavailable"}</small>
    </section>
  );
}

export function ProposalCard({
  proposal: p,
  missionGoal,
  onChanged,
}: {
  proposal: Proposal;
  missionGoal?: string;
  onChanged: () => Promise<void> | void;
}) {
  const { evidenceTitles } = useConnected();
  const [deciding, setDeciding] = useState(false);
  const [recording, setRecording] = useState(false);
  const [flash, setFlash] = useState("");
  const status = proposalStatus(p);
  const mayDecide = p.status === "proposed" && p.can_decide.length > 0;
  return (
    <article className="ws-surface ws-action-card cw-proposal">
      <header>
        <span className={`ws-tag cw-tag cw-tone-${status.tone}`}>{status.label}</span>
        {missionGoal && <span title={missionGoal}>{missionGoal}</span>}
      </header>
      <h2>
        {operationLabel(p.operation)} · {p.target_id}
      </h2>
      <div className="studio-action-owner">
        Target system {p.target_system} · Owner {p.owner_id} · Proposed by{" "}
        {p.requested_by} · {when(p.created_at)}
      </div>
      <div className="cw-chips">
        <span className={`cw-risk cw-risk-${p.risk}`}>{riskLabel(p.risk)}</span>
        <span>Required approval: {p.required_roles.join(", ") || "none listed"}</span>
      </div>
      <ol className="cw-stages" aria-label="Lifecycle, shown separately">
        {proposalStages(p).map((stage) => (
          <li key={stage.name}>
            <span>{stage.name}</span>
            <b>{stage.label}</b>
          </li>
        ))}
      </ol>
      {p.stale_reasons.length > 0 && (
        <div className="cw-stale" role="status">
          <b>Why this needs reassessment</b>
          <ul>
            {p.stale_reasons.map((reason, i) => (
              <li key={i}>{typeof reason === "string" ? reason : `${reason.source ? `${reason.source}: ` : ""}${reason.reason || "Source changed"}`}</li>
            ))}
          </ul>
        </div>
      )}
      {flash && (
        <p className="cw-error" role="alert">
          {flash}
        </p>
      )}
      <dl className="cw-facts">
        <div>
          <dt>Rationale</dt>
          <dd>{p.rationale}</dd>
        </div>
        <div>
          <dt>Expected result</dt>
          <dd>{p.expected_result}</dd>
        </div>
        {p.follow_up_measure && (
          <div>
            <dt>Follow-up measure</dt>
            <dd>{p.follow_up_measure}</dd>
          </div>
        )}
        {p.constraints && p.constraints.length > 0 && (
          <div>
            <dt>Constraints</dt>
            <dd>{p.constraints.join("; ")}</dd>
          </div>
        )}
      </dl>
      <details>
        <summary>Inspect command and parameters</summary>
        <CommandDetails proposal={p} />
      </details>
      <div className="cw-basis">
        <h3>Basis</h3>
        <ul>
          {p.basis.map((ref, i) => (
            <li
              key={`${ref.kind}-${ref.id}-${i}`}
              className={ref.kind === "mission" ? "cw-basis-user" : undefined}
            >
              {basisLabel(ref, evidenceTitles)}
            </li>
          ))}
        </ul>
        {isUserAuthoredOnly(p.basis) && (
          <p>This proposal has not been checked against source records.</p>
        )}
      </div>
      <details>
        <summary>
          Approval history · {p.approvals.length}{" "}
          {p.approvals.length === 1 ? "entry" : "entries"}
        </summary>
        {p.approvals.length ? (
          <ol>
            {[...p.approvals]
              .sort((a, b) => a.decided_at.localeCompare(b.decided_at))
              .map((a) => (
                <li key={a.approval_id}>
                  <RiCheckLine size={14} />
                  <div>
                    <b>
                      {a.decision === "approved" ? "Approved" : "Rejected"} as {a.role}
                    </b>
                    {a.comment && <p>{a.comment}</p>}
                    <small>
                      {a.actor_id} · {when(a.decided_at)} · sign-in:{" "}
                      {a.authentication?.method ?? "session"}
                    </small>
                  </div>
                </li>
              ))}
          </ol>
        ) : (
          <p className="cw-muted">No decisions recorded.</p>
        )}
      </details>
      {p.outcomes.length > 0 && (
        <details>
          <summary>
            Recorded outcomes · {p.outcomes.length}
          </summary>
          <ol>
            {p.outcomes.map((o) => (
              <li key={o.outcome_id}>
                <RiCheckLine size={14} />
                <div>
                  <b>
                    {o.measure}: {String(o.observed_value ?? "—")}
                  </b>
                  <p>{o.observation}</p>
                  <p className="cw-muted">Limits on attribution: {o.attribution_limits}</p>
                  <small>
                    {o.recorded_by} · {when(o.recorded_at)} ·{" "}
                    {o.evidence.map((e) => basisLabel(e, evidenceTitles)).join("; ")}
                  </small>
                </div>
              </li>
            ))}
          </ol>
        </details>
      )}
      <div className="ws-action-foot cw-foot">
        {mayDecide ? (
          <span>You can decide as: {p.can_decide.join(", ")}</span>
        ) : p.status === "proposed" ? (
          <span>
            Needs {p.required_roles.join(", ")}. Requesters cannot approve their own
            proposals.
          </span>
        ) : (
          <span />
        )}
        <div className="cw-foot-actions">
          {mayDecide && (
            <Button
              variant="primary"
              onClick={() => {
                setFlash("");
                setDeciding(true);
              }}
            >
              Review decision
            </Button>
          )}
          {canRecordOutcome(p) && (
            <Button onClick={() => setRecording(true)}>Record outcome</Button>
          )}
        </div>
      </div>
      {deciding && (
        <DecisionSheet
          proposal={p}
          onClose={() => setDeciding(false)}
          onConflict={(message) => {
            setDeciding(false);
            setFlash(message);
            void onChanged();
          }}
          onDone={() => {
            setDeciding(false);
            void onChanged();
          }}
        />
      )}
      {recording && (
        <OutcomeSheet
          proposal={p}
          onClose={() => setRecording(false)}
          onDone={() => {
            setRecording(false);
            void onChanged();
          }}
        />
      )}
    </article>
  );
}

function DecisionSheet({
  proposal: p,
  onClose,
  onDone,
  onConflict,
}: {
  proposal: Proposal;
  onClose: () => void;
  onDone: () => void;
  onConflict: (message: string) => void;
}) {
  const { client } = useConnected();
  const [role, setRole] = useState(p.can_decide[0] ?? "");
  const [comment, setComment] = useState("");
  const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const strong = needsReauthentication(p.risk);
  const ready = !!role && (!strong || attested) && !busy;
  const decide = async (decision: "approved" | "rejected") => {
    if (!client || !ready) return;
    setBusy(true);
    setError("");
    try {
      await client.decide(p.proposal_id, {
        expected_revision: p.revision,
        decision,
        role,
        ...(comment.trim() ? { comment: comment.trim() } : {}),
        ...(strong ? { authentication: { method: "development_attestation" } } : {}),
      });
      onDone();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) onConflict(e.message);
      else {
        setError(errorMessage(e));
        setBusy(false);
      }
    }
  };
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
      title={`Decide: ${operationLabel(p.operation)} · ${p.target_id}`}
      description="Your decision is recorded with your name, role and the version you reviewed."
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button disabled={!ready} onClick={() => void decide("rejected")}>
            Reject
          </Button>
          <Button variant="primary" disabled={!ready} onClick={() => void decide("approved")}>
            Approve
          </Button>
        </>
      }
    >
      <div className="cw-form">
        <CommandDetails proposal={p} />
        <p>
          <b>{riskLabel(p.risk)}</b> · target system {p.target_system} · revision {p.revision}
        </p>
        <p>{p.rationale}</p>
        <p className="cw-muted">Expected: {p.expected_result}</p>
        {p.can_decide.length > 1 ? (
          <label>
            <span>Decide as role</span>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {p.can_decide.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p>
            Deciding as role: <b>{role}</b>
          </p>
        )}
        <label>
          <span>Comment (optional)</span>
          <textarea
            rows={3}
            maxLength={2000}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What did you check?"
          />
        </label>
        {strong && (
          <label className="cw-check">
            <input
              type="checkbox"
              checked={attested}
              onChange={(e) => setAttested(e.target.checked)}
            />
            <span>
              I re-authenticated for this decision (development sign-in)
              <small>
                Development-only attestation, not a verified re-authentication. A real
                deployment must require sign-in again through your organization’s identity
                provider.
              </small>
            </span>
          </label>
        )}
        <p className="cw-muted">
          <RiShieldCheckLine size={14} aria-hidden="true" /> Approving records a decision. Sending
          to {p.target_system} is a separate step performed by the server, not by this screen.
        </p>
        {error && (
          <p className="cw-error" role="alert">
            {error}
          </p>
        )}
      </div>
    </Sheet>
  );
}

function OutcomeSheet({
  proposal: p,
  onClose,
  onDone,
}: {
  proposal: Proposal;
  onClose: () => void;
  onDone: () => void;
}) {
  const { client, evidenceTitles } = useConnected();
  const [observation, setObservation] = useState("");
  const [measure, setMeasure] = useState(p.follow_up_measure ?? "");
  const [value, setValue] = useState("");
  const [limits, setLimits] = useState("");
  const [chosen, setChosen] = useState<number[]>(p.basis.map((_, i) => i));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ready =
    !busy &&
    observation.trim() &&
    measure.trim() &&
    value.trim() &&
    limits.trim() &&
    chosen.length > 0;
  const submit = async () => {
    if (!client || !ready) return;
    setBusy(true);
    setError("");
    try {
      await client.recordOutcome(p.proposal_id, {
        observation: observation.trim(),
        measure: measure.trim(),
        observed_value: value.trim(),
        evidence: chosen.map((i) => p.basis[i]),
        attribution_limits: limits.trim(),
      });
      onDone();
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  };
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
      title="Record an observed outcome"
      description="What happened after the action, compared with what was expected."
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!ready} onClick={() => void submit()}>
            Save outcome
          </Button>
        </>
      }
    >
      <div className="cw-form">
        <p className="cw-muted">Expected: {p.expected_result}</p>
        {p.execution_status !== "delivered" && (
          <p className="cw-warn" role="status">
            The server has not confirmed this action as sent. Record only what you actually
            observed.
          </p>
        )}
        <label>
          <span>Observation</span>
          <textarea
            rows={3}
            maxLength={4000}
            value={observation}
            onChange={(e) => setObservation(e.target.value)}
          />
        </label>
        <label>
          <span>Measure</span>
          <input value={measure} maxLength={500} onChange={(e) => setMeasure(e.target.value)} />
        </label>
        <label>
          <span>Observed value</span>
          <input value={value} maxLength={500} onChange={(e) => setValue(e.target.value)} />
        </label>
        <fieldset>
          <legend>Evidence for this outcome</legend>
          {p.basis.map((ref, i) => (
            <label className="cw-check" key={`${ref.kind}-${ref.id}-${i}`}>
              <input
                type="checkbox"
                checked={chosen.includes(i)}
                onChange={(e) =>
                  setChosen((c) => (e.target.checked ? [...c, i] : c.filter((x) => x !== i)))
                }
              />
              <span>{basisLabel(ref, evidenceTitles)}</span>
            </label>
          ))}
        </fieldset>
        <label>
          <span>Limits on attributing this to the action</span>
          <textarea
            rows={3}
            maxLength={2000}
            value={limits}
            onChange={(e) => setLimits(e.target.value)}
            placeholder="What else could explain the result?"
          />
        </label>
        {error && (
          <p className="cw-error" role="alert">
            {error}
          </p>
        )}
      </div>
    </Sheet>
  );
}
