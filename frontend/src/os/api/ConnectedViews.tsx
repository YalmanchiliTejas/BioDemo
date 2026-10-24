import {
  useCallback,
  useEffect,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import {
  RiArrowRightSLine,
  RiRefreshLine,
  RiStackLine,
  RiTaskLine,
  RiTimeLine,
} from "@remixicon/react";
import { Button } from "../../lab/ui";
import { PageHead } from "../workbench/shared";
import type { View } from "../WorkspaceShell";
import { errorMessage, type Proposal } from "./client";
import {
  useAttemptKey,
  useConnected,
  useOpenMission,
} from "./ConnectedWorkspace";
import { ProposalCard } from "./ProposalCard";
import { ProposeSheet } from "./ProposeSheet";
import {
  evidenceTitle,
  missionDisplay,
  proposalStatus,
  type MissionDisplay,
} from "./mapping";

const when = (iso: string) => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
};
const day = (iso: string) => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

export const AI_UNAVAILABLE =
  "AI drafting is unavailable. Calculations, records, approvals and notifications continue.";

function HealthNotice() {
  const { health } = useConnected();
  if (!health || health.models_available) return null;
  return (
    <div className="ws-notice cw-notice" role="status">
      <RiTimeLine size={18} />
      <p>{AI_UNAVAILABLE}</p>
    </div>
  );
}

/** Calm connection states shared by every connected view. */
function Gate({ children }: { children: ReactNode }) {
  const cw = useConnected();
  if (cw.status === "error") {
    return (
      <div className="ws-page ws-empty cw-gate" role="alert">
        <h1>Can’t reach the server</h1>
        <p>{cw.error}</p>
        <div className="ws-detail-tools">
          <Button variant="primary" onClick={cw.retry}>
            Try again
          </Button>
          <Button onClick={cw.disconnect}>Return to sample mode</Button>
        </div>
      </div>
    );
  }
  if (cw.status !== "ready") {
    return (
      <div className="ws-page ws-empty cw-gate" role="status">
        <h1>Connecting to the server…</h1>
      </div>
    );
  }
  return <>{children}</>;
}

function MissionRow({ m, onOpen }: { m: MissionDisplay; onOpen: () => void }) {
  return (
    <button type="button" className="ws-work-row" onClick={onOpen}>
      <span className="ws-work-icon">
        <RiStackLine size={19} />
      </span>
      <span className="ws-work-title">
        <b>{m.goal}</b>
        <span>
          Owner {m.ownerId}
          <i />
          {m.siteLabel}
          {m.pendingDecisionCount > 0 && (
            <>
              <i />
              {m.pendingDecisionCount} pending{" "}
              {m.pendingDecisionCount === 1 ? "decision" : "decisions"}
            </>
          )}
        </span>
      </span>
      <span className="ws-work-state">{m.statusLabel}</span>
      <span className="ws-work-date">{day(m.createdAt)}</span>
      <RiArrowRightSLine size={17} />
    </button>
  );
}

function MissionList({
  openWork,
  query,
}: {
  openWork: (id: string) => void;
  query: string;
}) {
  const cw = useConnected();
  const rows = cw.missions
    .map(missionDisplay)
    .filter((m) => m.goal.toLowerCase().includes(query.toLowerCase()));
  if (cw.missionsState === "error") {
    return (
      <div className="cw-error" role="alert">
        {cw.missionsError}{" "}
        <button type="button" className="link" onClick={() => void cw.refreshMissions()}>
          Try again
        </button>
      </div>
    );
  }
  if (cw.missionsState !== "ready") {
    return (
      <p className="cw-muted" role="status">
        Loading goals from the server…
      </p>
    );
  }
  if (!rows.length) {
    return (
      <div className="studio-empty">
        <h2>{query ? "No matching goals" : "No goals on the server yet"}</h2>
      </div>
    );
  }
  return (
    <div className="studio-work-list">
      {rows.map((m) => (
        <MissionRow key={m.id} m={m} onOpen={() => openWork(m.id)} />
      ))}
    </div>
  );
}

export function ConnectedHome({
  go,
  openWork,
  newWorkRequest,
  onNewWorkOpened,
}: {
  go: (v: View) => void;
  openWork: (id: string) => void;
  newWorkRequest: number;
  onNewWorkOpened: () => void;
}) {
  const cw = useConnected();
  const [goal, setGoal] = useState("");
  const [constraints, setConstraints] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const attempt = useAttemptKey();
  const { status, refreshMissions } = cw;
  useEffect(() => {
    if (status === "ready") void refreshMissions();
  }, [status, refreshMissions]);
  useEffect(() => {
    if (newWorkRequest > 0) {
      document.getElementById("home-goal")?.scrollIntoView({
        block: "center",
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
      });
      document.getElementById("home-goal")?.focus({ preventScroll: true });
      onNewWorkOpened();
    }
  }, [newWorkRequest, onNewWorkOpened]);
  const lines = constraints
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  const ready = goal.trim().length >= 3 && !busy && !!cw.me;
  const submit = async () => {
    if (!ready) return;
    setBusy(true);
    setError("");
    try {
      const mission = await cw.createMission(
        goal,
        lines,
        attempt.keyFor({ goal: goal.trim(), lines }),
      );
      attempt.done();
      setSaved(mission.mission_id);
      setGoal("");
      setConstraints("");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Gate>
      <div className="ws-page cw-home">
        <PageHead
          eyebrow="Server workspace"
          title="What are you working on?"
          description="Save a goal on the server. Records, notes and approvals are kept there under your name."
        />
        <HealthNotice />
        <form
          className="cw-goal"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <label className="sr-only" htmlFor="home-goal">
            Goal
          </label>
          <textarea
            id="home-goal"
            rows={3}
            maxLength={4000}
            value={goal}
            placeholder="Describe the question or goal…"
            onChange={(e) => {
              setGoal(e.target.value);
              setSaved(null);
            }}
          />
          <details>
            <summary>Add constraints (optional)</summary>
            <label className="sr-only" htmlFor="home-constraints">
              Constraints, one per line
            </label>
            <textarea
              id="home-constraints"
              rows={2}
              value={constraints}
              placeholder="One per line, e.g. no recipe change without QA approval"
              onChange={(e) => setConstraints(e.target.value)}
            />
          </details>
          <div className="cw-goal-foot">
            <span>
              Owner {cw.me?.actor_id ?? "…"} · Sites{" "}
              {cw.me?.site_ids.join(", ") || "none"}
            </span>
            <Button type="submit" variant="primary" disabled={!ready}>
              {busy ? "Saving…" : "Save goal"}
            </Button>
          </div>
          {error && (
            <p className="cw-error" role="alert">
              {error}
            </p>
          )}
          {saved && (
            <p className="cw-saved" role="status">
              Goal saved on the server. No analysis has run.{" "}
              <button type="button" className="link" onClick={() => openWork(saved)}>
                Open it
              </button>
            </p>
          )}
        </form>
        <section aria-label="Goals on the server" className="studio-collection">
          <div className="home-section-head">
            <div>
              <h2>Continue your work</h2>
              <p className="home-section-sub">
                Saved on the server · {cw.missions.length}{" "}
                {cw.missions.length === 1 ? "goal" : "goals"}
              </p>
            </div>
            <button type="button" className="link" onClick={() => go("actions")}>
              Next steps and approvals <RiArrowRightSLine size={14} />
            </button>
          </div>
          <div className="studio-collection-toolbar">
            <label className="studio-search">
              <span className="sr-only">Find goals</span>
              <input
                type="search"
                placeholder="Search goals…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
          </div>
          <MissionList openWork={openWork} query={query} />
        </section>
      </div>
    </Gate>
  );
}

export function ConnectedSavedWork({ openWork }: { openWork: (id: string) => void }) {
  const cw = useConnected();
  const [query, setQuery] = useState("");
  const { status, refreshMissions } = cw;
  useEffect(() => {
    if (status === "ready") void refreshMissions();
  }, [status, refreshMissions]);
  return (
    <Gate>
      <div className="ws-page">
        <PageHead eyebrow="" title="Saved work" description="" />
        <HealthNotice />
        <div className="ws-filter-bar saved-filters">
          <label>
            <span className="sr-only">Find saved work</span>
            <input
              aria-label="Find saved work"
              placeholder="Find saved work…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
        </div>
        <MissionList openWork={openWork} query={query} />
      </div>
    </Gate>
  );
}

const connectedSections = ["overview", "evidence", "next", "notes"] as const;
type ConnectedSection = (typeof connectedSections)[number];
const sectionLabels: Record<ConnectedSection, string> = {
  overview: "Overview",
  evidence: "Evidence",
  next: "Next steps",
  notes: "Notes",
};

export function ConnectedWorkDetail({
  id,
  section,
  setSection,
  go,
}: {
  id: string;
  section: string;
  setSection: (section: "overview" | "evidence" | "next" | "notes") => void;
  go: (v: View) => void;
}) {
  return (
    <Gate>
      <Detail id={id} section={section} setSection={setSection} go={go} />
    </Gate>
  );
}

function Detail({
  id,
  section,
  setSection,
  go,
}: {
  id: string;
  section: string;
  setSection: (section: ConnectedSection) => void;
  go: (v: View) => void;
}) {
  const cw = useConnected();
  const open = useOpenMission(id);
  const { mission, proposals } = open;
  const active: ConnectedSection = (connectedSections as readonly string[]).includes(section)
    ? (section as ConnectedSection)
    : "overview";
  const { loadEvidence } = cw;
  useEffect(() => {
    void loadEvidence();
  }, [loadEvidence]);
  const [body, setBody] = useState("");
  const [noteState, setNoteState] = useState<"idle" | "saving" | "saved">("idle");
  const [noteError, setNoteError] = useState("");
  const noteKey = useAttemptKey();
  const tabKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = connectedSections.length - 1;
    let next = index;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = index === last ? 0 : index + 1;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = index === 0 ? last : index - 1;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = last;
    else return;
    event.preventDefault();
    setSection(connectedSections[next]);
    document.getElementById(`work-tab-${connectedSections[next]}`)?.focus();
  };
  if (open.phase !== "ready" || !mission) {
    return (
      <div className="ws-page ws-empty cw-gate" role={open.phase === "error" ? "alert" : "status"}>
        <h1>{open.phase === "error" ? "Can’t open this goal" : "Loading goal…"}</h1>
        {open.phase === "error" && (
          <>
            <p>{open.error}</p>
            <Button onClick={() => go("work")}>Back to saved work</Button>
          </>
        )}
      </div>
    );
  }
  const m = missionDisplay(mission);
  const saveNote = async () => {
    if (!cw.client || !body.trim()) return;
    setNoteState("saving");
    setNoteError("");
    try {
      await cw.client.addNote(id, body.trim(), noteKey.keyFor({ id, body: body.trim() }));
      noteKey.done();
      setBody("");
      setNoteState("saved");
      await open.reload();
    } catch (e) {
      setNoteError(errorMessage(e));
      setNoteState("idle");
    }
  };
  const scope = Object.entries(mission.scope).filter(([k]) => k !== "site_ids");
  return (
    <div className="ws-page ws-detail flow-detail cw-detail">
      <button type="button" className="ws-back" onClick={() => go("work")}>
        ← Saved work
      </button>
      <PageHead
        eyebrow=""
        title={mission.objective}
        description={`${m.statusLabel} · Owner ${m.ownerId} · ${m.siteLabel}`}
        action={
          <div className="ws-header-controls">
            <ProposeSheet mission={mission} onSaved={() => { setSection("next"); void open.reload(); }} />
          </div>
        }
      />
      <HealthNotice />
      <div className="ws-notice">
        <RiTimeLine size={18} />
        <p>
          <b>Saved on the server. No analysis has run.</b> This view shows saved records,
          notes and approvals; it does not start analysis.
        </p>
      </div>
      {open.liveError && (
        <p className="cw-error" role="alert">
          Live updates paused: {open.liveError} Showing the last version loaded.{" "}
          <button type="button" className="link" onClick={() => void open.reload()}>
            Refresh
          </button>
        </p>
      )}
      <div className="work-flow">
        <div role="tablist" aria-label="Work views" className="flow-work-tabs">
          <span className="flow-work-label" aria-hidden="true">
            The thread
          </span>
          {connectedSections.map((tab, index) => (
            <button
              key={tab}
              id={`work-tab-${tab}`}
              type="button"
              role="tab"
              aria-label={sectionLabels[tab]}
              aria-selected={active === tab}
              aria-controls="work-panel"
              tabIndex={active === tab ? 0 : -1}
              onKeyDown={(e) => tabKey(e, index)}
              onClick={() => setSection(tab)}
            >
              <span className="work-flow-index" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="work-flow-name">{sectionLabels[tab]}</span>
              {tab === "next" && proposals.length > 0 && (
                <span className="work-flow-count" aria-hidden="true">
                  {proposals.length}
                </span>
              )}
              {tab === "notes" && m.noteCount > 0 && (
                <span className="work-flow-count" aria-hidden="true">
                  {m.noteCount}
                </span>
              )}
            </button>
          ))}
        </div>
        <div
          id="work-panel"
          role="tabpanel"
          aria-labelledby={`work-tab-${active}`}
          tabIndex={0}
          className="flow-work-panel"
        >
          {active === "overview" && (
            <>
              <section className="ws-surface cw-section">
                <h2>Constraints</h2>
                {mission.constraints.length ? (
                  <ul>
                    {mission.constraints.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="cw-muted">No constraints recorded.</p>
                )}
                {scope.length > 0 && (
                  <dl className="cw-facts">
                    {scope.map(([k, v]) => (
                      <div key={k}>
                        <dt>{k}</dt>
                        <dd>{typeof v === "string" ? v : JSON.stringify(v)}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </section>
              <section className="ws-surface cw-section">
                <h2>Recurring work</h2>
                {mission.obligations.length ? <ul>{mission.obligations.map((o, i) => (
                  <li key={o.obligation_id || i}>
                    <b>{o.description}</b> · {o.runtime_status || o.status}
                    {o.due_at && <span> · Due {new Date(o.due_at).toLocaleString()}</span>}
                    {o.runtime_issues?.map((issue, j) => <p className="cw-error" key={j}>{issue}</p>)}
                  </li>
                ))}</ul> : <p className="cw-muted">No recurring work configured.</p>}
              </section>
              <section className="ws-surface cw-section">
                <h2>Pending decisions</h2>
                {mission.pending_decisions.length ? (
                  <ul>
                    {mission.pending_decisions.map((d) => (
                      <li key={d.decision_id}>
                        <b>{d.question}</b>
                        <span className="cw-muted">
                          {" "}
                          · {d.status === "pending" ? `waiting for ${d.decider_role}` : `answered: ${d.answer ?? "—"}`}
                          {d.options.length ? ` · options: ${d.options.join(", ")}` : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="cw-muted">No decisions are waiting.</p>
                )}
                <p className="cw-muted">Read-only here.</p>
              </section>
              <section className="ws-surface cw-section">
                <h2>Next steps</h2>
                <p>
                  {proposals.length
                    ? `${proposals.length} proposed ${proposals.length === 1 ? "step" : "steps"}.`
                    : "No next steps proposed yet."}
                </p>
                <Button onClick={() => setSection("next")}>
                  Review next steps <RiArrowRightSLine size={14} />
                </Button>
              </section>
            </>
          )}
          {active === "evidence" && (
            <section className="ws-surface cw-section">
              <h2>Source records on the server</h2>
              <p className="cw-muted">
                Records you are allowed to read. Read-only; the originals stay in their systems of
                record.
              </p>
              {cw.evidenceState === "loading" && <p className="cw-muted">Loading…</p>}
              {cw.evidenceState === "error" && (
                <p className="cw-error" role="alert">
                  {cw.evidenceError}
                </p>
              )}
              {cw.evidenceState === "ready" && cw.evidence.length === 0 && (
                <p className="cw-muted">No source records are visible to you yet.</p>
              )}
              <ul className="cw-evidence">
                {cw.evidence.map((r) => (
                  <li key={r.id}>
                    <b>{evidenceTitle(r)}</b>
                    <span>
                      {r.state.source_system} · {r.state.source_record_id}
                      {r.state.site_id ? ` · ${r.state.site_id}` : ""}
                      {r.state.event_time ? ` · ${when(r.state.event_time)}` : ""}
                      {r.state.metadata?.synthetic ? " · synthetic" : ""}
                      {r.state.status && r.state.status !== "current" ? ` · ${r.state.status}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {active === "next" && (
            <div className="flow-scoped-actions">
              <div className="flow-section-head">
                <div>
                  <h2>Next steps</h2>
                </div>
              </div>
              <ProposalList proposals={proposals} onChanged={open.reload} />
            </div>
          )}
          {active === "notes" && (
            <section className="ws-surface ws-notes flow-notes" aria-labelledby="notes-h">
              <div className="ws-section-title">
                <h2 id="notes-h">Notes & corrections</h2>
                <span>{m.noteCount} saved</span>
              </div>
              <p>
                Challenge an interpretation, record a question, or leave context for your next
                session.
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void saveNote();
                }}
              >
                <label className="sr-only" htmlFor="work-note">
                  Note
                </label>
                <textarea
                  id="work-note"
                  value={body}
                  maxLength={4000}
                  onChange={(e) => {
                    setBody(e.target.value);
                    setNoteState("idle");
                  }}
                  rows={4}
                  placeholder="Add a note…"
                />
                <div className="flow-note-submit">
                  <span role="status">
                    {noteState === "saved"
                      ? "Note saved on the server."
                      : "Notes do not change source records."}
                  </span>
                  <Button type="submit" disabled={!body.trim() || noteState === "saving"}>
                    {noteState === "saving" ? "Saving…" : "Save note"}
                  </Button>
                </div>
                {noteError && (
                  <p className="cw-error" role="alert">
                    {noteError}
                  </p>
                )}
              </form>
              <ol className="ws-note-list">
                {[...mission.notes].reverse().map((n) => (
                  <li key={n.note_id}>
                    <p>{n.body}</p>
                    <span>
                      {n.author} · {when(n.at)}
                    </span>
                  </li>
                ))}
              </ol>
              {mission.corrections.length > 0 && (
                <>
                  <h3>Corrections</h3>
                  <ol className="ws-note-list">
                    {mission.corrections.map((c, i) => (
                      <li key={c.correction_id ?? i}>
                        <p>{c.text}</p>
                        <span>
                          {c.by ?? "unknown"}
                          {c.at ? ` · ${when(c.at)}` : ""}
                        </span>
                      </li>
                    ))}
                  </ol>
                </>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function ProposalList({
  proposals,
  onChanged,
  goals,
  empty = "No next steps proposed yet. Use Propose next step to capture an action, its basis and who must approve it.",
}: {
  proposals: Proposal[];
  onChanged: () => Promise<void> | void;
  goals?: Record<string, string>;
  empty?: string;
}) {
  if (!proposals.length) {
    return (
      <div className="ws-empty ws-surface">
        <RiTaskLine size={30} />
        <h2>No tracked actions</h2>
        <p>{empty}</p>
      </div>
    );
  }
  return (
    <div className="ws-action-list">
      {proposals.map((p) => (
        <ProposalCard
          key={p.proposal_id}
          proposal={p}
          missionGoal={p.mission_id ? goals?.[p.mission_id] : undefined}
          onChanged={onChanged}
        />
      ))}
    </div>
  );
}

const FILTERS: [string, string][] = [
  ["all", "All statuses"],
  ["mine", "Needs my decision"],
  ["proposed", "Awaiting approval"],
  ["approved_queued", "Approved — not yet sent"],
  ["needs_reassessment", "Needs reassessment"],
  ["delivered", "Sent"],
  ["unknown", "Delivery unconfirmed"],
  ["rejected", "Rejected"],
  ["outcome_recorded", "Outcome recorded"],
];

export function ConnectedActions() {
  return (
    <Gate>
      <ActionsInner />
    </Gate>
  );
}

function ActionsInner() {
  const cw = useConnected();
  const { client, missions, refreshMissions } = cw;
  const [all, setAll] = useState<Proposal[]>([]);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  useEffect(() => {
    void refreshMissions();
  }, [refreshMissions]);
  const load = useCallback(async () => {
    if (!client) return;
    try {
      const items = await client.listAllProposals();
      setAll(items.sort((a, b) => b.created_at.localeCompare(a.created_at)));
      setPhase("ready");
      setError("");
    } catch (e) {
      setError(errorMessage(e));
      setPhase("error");
    }
  }, [client]);
  useEffect(() => {
    if (cw.missionsState !== "ready") return;
    void load();
    const timer = window.setInterval(() => {
      if (!document.hidden) void load();
    }, 15_000);
    return () => window.clearInterval(timer);
  }, [cw.missionsState, load]);
  useEffect(() => {
    void cw.loadEvidence();
  }, [cw.loadEvidence]);
  const goals: Record<string, string> = {};
  for (const m of missions) goals[m.mission_id] = m.objective;
  const shown = all.filter((p) =>
    filter === "all"
      ? true
      : filter === "mine"
        ? p.status === "proposed" && p.can_decide.length > 0
        : proposalStatus(p).key === filter,
  );
  return (
    <div className="ws-page">
      <PageHead eyebrow="" title="Actions & follow-up" description="" />
      <HealthNotice />
      <div className="ws-notice">
        <RiTimeLine size={18} />
        <p>
          Proposals, approvals and outcomes are kept on the server. Approval and sending are
          shown as separate steps.
        </p>
      </div>
      <div className="ws-filter-bar">
        <span>
          {all.length} tracked {all.length === 1 ? "action" : "actions"}
        </span>
        <select
          aria-label="Filter action status"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          {FILTERS.map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        <Button size="sm" onClick={() => void load()}>
          <RiRefreshLine size={14} /> Refresh
        </Button>
      </div>
      {phase === "error" && (
        <p className="cw-error" role="alert">
          {error}
        </p>
      )}
      {phase === "loading" && cw.missionsState === "ready" && (
        <p className="cw-muted" role="status">
          Loading actions…
        </p>
      )}
      {(phase === "ready" || all.length > 0) && (
        <ProposalList
          proposals={shown}
          goals={goals}
          onChanged={load}
          empty={
            all.length
              ? "Choose another status to see your tracked actions."
              : "Open a goal and use Propose next step to create one."
          }
        />
      )}
    </div>
  );
}
