import { useState } from "react";
import {
  RiAddLine,
  RiCheckLine,
  RiTaskLine,
  RiShieldCheckLine,
} from "@remixicon/react";
import { useWorkspace } from "../WorkspaceProvider";
import {
  actionLabel,
  SAMPLE_ID,
  type WorkAction,
  type ActionStatus,
} from "../workspace-model";
import { action } from "../../lab/scenario";
import { Button, Sheet } from "../../lab/ui";
import { PageHead } from "./shared";

const nextStatus: Partial<Record<ActionStatus, ActionStatus>> = {
  proposed: "reviewed",
  reviewed: "in_progress",
  in_progress: "outcome_recorded",
};
const nextLabel: Partial<Record<ActionStatus, string>> = {
  proposed: "Record local review",
  reviewed: "Record work started",
  in_progress: "Record observed outcome",
};
export function Actions({ workId }: { workId?: string }) {
  const { data, propose, transition } = useWorkspace();
  const [selected, setSelected] = useState<WorkAction | null>(null);
  const [reason, setReason] = useState("");
  const [filter, setFilter] = useState("all");
  const targetId = workId || SAMPLE_ID;
  const hasSample = data.work.some(
    (w) => w.id === targetId && w.context === "sample",
  );
  const scoped = data.actions.filter((a) => !workId || a.workId === workId);
  const actions = scoped.filter((a) => filter === "all" || a.status === filter);
  const addRecommended = () => {
    if (!hasSample) return;
    for (const step of action.steps) {
      if (
        data.actions.some(
          (a) => a.id && a.workId === targetId && a.title === step.text,
        )
      )
        continue;
      propose({
        workId: targetId,
        title: step.text,
        owner: step.owner,
        rationale: action.why,
        expected:
          step.id === "a1"
            ? "An independent DO measurement to compare with the installed probe."
            : step.id === "a2"
              ? "Off-gas observations covering the missing interval, or a documented reason they cannot be recovered."
              : "An administrator decision on read access; access is not granted by this proposal.",
        constraint: `${step.due}. ${action.notProposed}`,
        evidenceIds:
          step.id === "a1" ? ["S1", "S2"] : step.id === "a2" ? ["M1"] : ["M2"],
      });
    }
  };
  return (
    <div className={workId ? "flow-scoped-actions" : "ws-page"}>
      {workId ? (
        <div className="flow-section-head">
          <div>
            <h2>Next steps</h2>
          </div>
          {hasSample && (
            <Button
              onClick={addRecommended}
              disabled={action.steps.every((s) =>
                scoped.some((a) => a.title === s.text),
              )}
            >
              <RiAddLine size={16} />
              Track sample checks
            </Button>
          )}
        </div>
      ) : (
        <PageHead
          eyebrow=""
          title="Actions & follow-up"
          description=""
          action={
            <Button
              variant="primary"
              onClick={addRecommended}
              disabled={
                !hasSample ||
                action.steps.every((s) =>
                  data.actions.some(
                    (a) => a.title === s.text && a.workId === targetId,
                  ),
                )
              }
            >
              <RiAddLine size={16} />
              Track sample checks
            </Button>
          }
        />
      )}
      <div className="ws-notice">
        <RiShieldCheckLine size={18} />
        <p>
          Local tracking only. Review does not grant QA approval or execute an
          action.
        </p>
      </div>
      <div className="ws-filter-bar">
        <span>{scoped.length} tracked actions</span>
        <select
          aria-label="Filter action status"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">All statuses</option>
          {Object.entries(actionLabel).map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </select>
      </div>
      {!actions.length ? (
        <div className="ws-empty ws-surface">
          <RiTaskLine size={30} />
          <h2>
            {scoped.length
              ? "No actions with this status"
              : "No tracked actions"}
          </h2>
          <p>
            {scoped.length
              ? "Choose another status to see your tracked actions."
              : hasSample
                ? "Track verification checks, or propose your own next step for this work."
                : "Use Propose next step to capture an owner, rationale, expected result and required approval."}
          </p>
          {!scoped.length && hasSample && (
            <Button onClick={addRecommended}>Track sample checks</Button>
          )}
        </div>
      ) : (
        <div className="ws-action-list">
          {actions.map((a) => (
            <article className="ws-surface ws-action-card" key={a.id}>
              <header>
                <span className={`ws-tag ws-tag-${a.status}`}>
                  {actionLabel[a.status]}
                </span>
                <span>
                  {data.work.find((w) => w.id === a.workId)?.goal ||
                    "Saved work"}
                </span>
              </header>
              <h2>{a.title}</h2>
              <div className="studio-action-owner">{a.owner}</div>
              <details className="studio-action-details">
                <summary>Rationale & requirements</summary>
                <dl>
                  <div>
                    <dt>Owner</dt>
                    <dd>{a.owner}</dd>
                  </div>
                  <div>
                    <dt>Rationale</dt>
                    <dd>{a.rationale}</dd>
                  </div>
                  <div>
                    <dt>Expected evidence</dt>
                    <dd>{a.expected}</dd>
                  </div>
                  <div>
                    <dt>Constraints</dt>
                    <dd>{a.constraint}</dd>
                  </div>
                </dl>
              </details>
              <div className="ws-action-foot">
                <span>
                  {a.evidenceIds.length
                    ? `Evidence: ${a.evidenceIds.join(", ")}`
                    : "User-authored proposal · no linked source evidence"}
                </span>
                {nextStatus[a.status] && (
                  <Button
                    onClick={() => {
                      setSelected(a);
                      setReason("");
                    }}
                  >
                    {nextLabel[a.status]}
                  </Button>
                )}
              </div>
              <details>
                <summary>
                  Review history · {a.events.length}{" "}
                  {a.events.length === 1 ? "entry" : "entries"}
                </summary>
                <ol>
                  {a.events.map((e, i) => (
                    <li key={i}>
                      <RiCheckLine size={14} />
                      <div>
                        <b>{actionLabel[e.status]}</b>
                        <p>{e.note}</p>
                        <small>
                          {e.actor} · {new Date(e.at).toLocaleString()}
                        </small>
                      </div>
                    </li>
                  ))}
                </ol>
              </details>
            </article>
          ))}
        </div>
      )}
      <Sheet
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        title={selected ? nextLabel[selected.status] : "Action review"}
        description="Record what you reviewed or observed. This does not authorize or execute a manufacturing action."
        footer={
          <>
            <Button onClick={() => setSelected(null)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!reason.trim()}
              onClick={() => {
                if (selected && nextStatus[selected.status]) {
                  transition(selected.id, nextStatus[selected.status]!, reason);
                  setSelected(null);
                }
              }}
            >
              Save record
            </Button>
          </>
        }
      >
        <div className="ws-action-review">
          <h3>{selected?.title}</h3>
          <p>{selected?.expected}</p>
          <label htmlFor="action-reason">
            {selected?.status === "in_progress"
              ? "Observed outcome, evidence and remaining uncertainty"
              : "Review or progress note"}
          </label>
          <textarea
            id="action-reason"
            rows={5}
            maxLength={4000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Describe what was checked, done or observed…"
          />
          <p>
            Recorded as Priya Raman (demo). Real operational approvals remain in
            your authorized system.
          </p>
        </div>
      </Sheet>
    </div>
  );
}
