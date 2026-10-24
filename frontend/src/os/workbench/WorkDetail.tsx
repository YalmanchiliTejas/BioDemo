import { useState, type KeyboardEvent } from "react";
import {
  RiArrowRightLine,
  RiDatabase2Line,
  RiDownloadLine,
  RiTimeLine,
} from "@remixicon/react";
import { useWorkspace, downloadWork } from "../WorkspaceProvider";
import { kindLabel, SAMPLE_ID } from "../workspace-model";
import type { View } from "../WorkspaceShell";
import type { Evidence } from "../../lab/scenario";
import { Button, Balance } from "../../lab/ui";
import { counts, useEvidence, EvidenceRow } from "../../lab/evidence";
import { TiterChart } from "../../lab/charts";
import { TrendViewer, type PenId } from "../../lab/familiar";
import { useScenario } from "../../lab/state";
import { PageHead } from "./shared";
import { ProposeNextStep } from "./ProposeNextStep";
import { Actions } from "./Actions";

export const workSections = [
  "overview",
  "evidence",
  "trends",
  "next",
  "notes",
] as const;
export type WorkSection = (typeof workSections)[number];
const sectionLabels: Record<WorkSection, string> = {
  overview: "Overview",
  evidence: "Evidence",
  trends: "Trends",
  next: "Next steps",
  notes: "Notes",
};

export function WorkDetail({
  id,
  section,
  setSection,
  go,
  openRecord,
  onOpen,
  onReview,
}: {
  id: string;
  section: WorkSection;
  setSection: (section: WorkSection) => void;
  go: (v: View) => void;
  openRecord: (tab?: "trends" | "investigation") => void;
  onOpen: (e: Evidence) => void;
  onReview: () => void;
}) {
  const { data, note, attachSample } = useWorkspace();
  const item = data.work.find((w) => w.id === id);
  const evidence = useEvidence();
  const { assayPosted } = useScenario();
  const [body, setBody] = useState("");
  const [saved, setSaved] = useState(false);
  const [pens, setPens] = useState<PenId[]>(["do", "ag"]);
  const [reference, setReference] = useState(true);
  if (!item)
    return (
      <div className="ws-page ws-empty">
        <h1>Work not found</h1>
        <p>This link may refer to work saved in another browser.</p>
        <Button onClick={() => go("work")}>Back to saved work</Button>
      </div>
    );
  const sample = item.id === SAMPLE_ID;
  const hasContext = item.context === "sample";
  const actions = data.actions.filter((a) => a.workId === id);
  const exportItem = () =>
    downloadWork(`work-${item.id}.json`, {
      version: 1,
      mode: "browser-local-demo",
      work: item,
      actions,
      evidence: hasContext ? evidence : [],
    });
  const tabKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next = index;
    if (event.key === "ArrowRight" || event.key === "ArrowDown")
      next = (index + 1) % workSections.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp")
      next = (index + workSections.length - 1) % workSections.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = workSections.length - 1;
    else return;
    event.preventDefault();
    setSection(workSections[next]);
    document.getElementById(`work-tab-${workSections[next]}`)?.focus();
  };
  const emptyContext = (
    <div className="ws-empty ws-surface flow-context-empty">
      <RiDatabase2Line size={28} />
      <h2>Add context when you’re ready.</h2>
      <p>
        Your question is saved. You can keep notes and propose a next step now,
        or explore the existing F-2408 sample records.
      </p>
      <div className="ws-detail-tools">
        <Button onClick={() => attachSample(item.id)}>
          Explore with sample context
        </Button>
        <Button variant="ghost" onClick={() => go("sources")}>
          Inspect source access
        </Button>
      </div>
    </div>
  );
  return (
    <div className="ws-page ws-detail flow-detail">
      <button type="button" className="ws-back" onClick={() => go("work")}>
        ← Saved work
      </button>
      <PageHead
        eyebrow=""
        title={item.goal}
        description={
          hasContext
            ? `F-2408 / BR-04 · ${kindLabel[item.kind]} · Sample`
            : `${kindLabel[item.kind]} · No source context attached`
        }
        action={
          <div className="ws-header-controls">
            <ProposeNextStep work={item} onSaved={() => setSection("next")} />
            <Button onClick={exportItem}>
              <RiDownloadLine size={15} />
              Export work
            </Button>
          </div>
        }
      />
      {!sample && (
        <div className="ws-notice">
          <RiTimeLine size={18} />
          <p>
            <b>Goal saved. No new analysis has run.</b>{" "}
            {hasContext
              ? "These are existing sample records, not an evaluated answer to your question."
              : "Add context, keep notes, or propose the next step."}
          </p>
        </div>
      )}
      <div className="work-flow">
        <div role="tablist" aria-label="Work views" className="flow-work-tabs">
          <span className="flow-work-label" aria-hidden="true">
            The thread
          </span>
          {workSections.map((tab, index) => (
            <button
              key={tab}
              id={`work-tab-${tab}`}
              type="button"
              role="tab"
              aria-label={sectionLabels[tab]}
              aria-selected={section === tab}
              aria-controls="work-panel"
              tabIndex={section === tab ? 0 : -1}
              onKeyDown={(e) => tabKey(e, index)}
              onClick={() => setSection(tab)}
            >
              <span className="work-flow-index" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="work-flow-name">{sectionLabels[tab]}</span>
              {tab === "next" && actions.length > 0 && (
                <span className="work-flow-count" aria-hidden="true">
                  {actions.length}
                </span>
              )}
              {tab === "notes" && item.notes.length > 0 && (
                <span className="work-flow-count" aria-hidden="true">
                  {item.notes.length}
                </span>
              )}
            </button>
          ))}
        </div>
        <div
          id="work-panel"
          role="tabpanel"
          aria-labelledby={`work-tab-${section}`}
          tabIndex={0}
          className="flow-work-panel"
        >
          {section === "overview" &&
            (hasContext ? (
              <>
                <section className="work-result" aria-labelledby="result-h">
                  <div className="work-result-head">
                    <div>
                      <p className="work-kicker">F-2408 · 48 h</p>
                      <h2 id="result-h">Titer comparison</h2>
                      <p className="work-result-line">
                        48 h titer is 18% below the six-batch reference.
                      </p>
                    </div>
                    <span className="studio-status">Unconfirmed cause</span>
                  </div>
                  <div className="studio-metrics">
                    <div>
                      <span>48 h titer</span>
                      <strong>
                        1.74 <small>g/L</small>
                      </strong>
                    </div>
                    <div>
                      <span>vs reference</span>
                      <strong className="studio-negative">
                        −18<small>%</small>
                      </strong>
                    </div>
                    <div>
                      <span>Reference mean</span>
                      <strong>
                        2.12 <small>g/L</small>
                      </strong>
                    </div>
                  </div>
                  <div className="work-chart">
                    <TiterChart height={260} title={false} />
                  </div>
                  <button
                    type="button"
                    className="studio-chart-link"
                    onClick={() => setSection("trends")}
                  >
                    Compare process trends <RiArrowRightLine size={14} />
                  </button>
                </section>
                <section className="work-interpretation">
                  <div className="flow-section-head">
                    <div>
                      <h2>Interpretation</h2>
                      <p>What the evidence supports, and what it does not.</p>
                    </div>
                    <button
                      type="button"
                      className="link"
                      onClick={() => setSection("evidence")}
                    >
                      View evidence <RiArrowRightLine size={14} />
                    </button>
                  </div>
                  <div className="studio-claims">
                    <details>
                      <summary>
                        <span className="studio-claim-type">Hypothesis</span>
                        <span>Reduced oxygen transfer</span>
                      </summary>
                      <p>
                        DO falls as agitation reaches its ceiling. This could
                        contribute to lower titer; it does not establish cause.
                      </p>
                    </details>
                    <details>
                      <summary>
                        <span className="studio-claim-type">
                          Counterevidence
                        </span>
                        <span>F-2391: low DO, normal titer</span>
                      </summary>
                      <p>
                        Low DO alone may not explain the shortfall. The previous
                        batch weakens this explanation.
                      </p>
                    </details>
                    <details>
                      <summary>
                        <span className="studio-claim-type studio-negative">
                          Unknown
                        </span>
                        <span>
                          {assayPosted
                            ? "Off-gas records & aeration access"
                            : "Off-gas, aeration access & 60 h assay"}
                        </span>
                      </summary>
                      <p>
                        Off-gas records are missing for 31–44 h. Aeration-rate
                        read access is denied.{" "}
                        {assayPosted
                          ? "The 60 h assay is available and does not establish cause."
                          : "The 60 h assay is pending."}
                      </p>
                    </details>
                  </div>
                </section>
                <section className="work-context" aria-label="Work context">
                  <div className="work-context-block">
                    <h2>Evidence</h2>
                    <Balance {...counts(evidence)} />
                    <p>
                      Supporting observations, counterevidence, and gaps stay
                      separate from the interpretation.
                    </p>
                    <button
                      type="button"
                      className="link"
                      onClick={() => setSection("evidence")}
                    >
                      Open evidence <RiArrowRightLine size={14} />
                    </button>
                  </div>
                  <div className="work-context-block">
                    <h2>Next step</h2>
                    <p>
                      Verify DO independently and recover the missing off-gas
                      records before changing the process.
                    </p>
                    <Button onClick={() => setSection("next")}>
                      Review next steps <RiArrowRightLine size={14} />
                    </Button>
                  </div>
                </section>
              </>
            ) : (
              emptyContext
            ))}
          {section === "evidence" &&
            (hasContext ? (
              <section className="ws-surface flow-evidence-full">
                <div className="flow-section-head">
                  <div>
                    <h2>Evidence & source records</h2>
                    <p>Queries, input rows and source limits.</p>
                  </div>
                  <Balance {...counts(evidence)} />
                </div>
                {(["supports", "contradicts", "missing"] as const).map(
                  (stance) => (
                    <div className="flow-evidence-group" key={stance}>
                      <h3>
                        {stance === "supports"
                          ? "Supporting observations"
                          : stance === "contradicts"
                            ? "Counterevidence"
                            : "Gaps & access limits"}
                      </h3>
                      {evidence
                        .filter((e) => e.stance === stance)
                        .map((e) => (
                          <EvidenceRow key={e.id} e={e} onOpen={onOpen} detail />
                        ))}
                    </div>
                  ),
                )}
              </section>
            ) : (
              emptyContext
            ))}
          {section === "trends" &&
            (hasContext ? (
              <section className="ws-surface flow-trends">
                <div className="flow-section-head">
                  <div>
                    <h2>Batch trends & comparison</h2>
                    <p>
                      F-2408 against six R7 reference batches. Descriptive
                      sample data; no causal inference.
                    </p>
                  </div>
                </div>
                <TiterChart height={255} />
                <TrendViewer
                  selected={pens}
                  onSelected={setPens}
                  reference={reference}
                  onReference={setReference}
                />
              </section>
            ) : (
              emptyContext
            ))}
          {section === "next" && (
            <>
              <Actions workId={id} />
              {hasContext && (
                <div className="flow-quality-handoff ws-surface">
                  <div>
                    <h3>Review the sample quality draft</h3>
                    <p>
                      Inspect the proposed checks and required authorization in
                      the simulated review.
                    </p>
                  </div>
                  <Button onClick={onReview}>Review proposed plan</Button>
                </div>
              )}
            </>
          )}
          {section === "notes" && (
            <section
              className="ws-surface ws-notes flow-notes"
              aria-labelledby="notes-h"
            >
              <div className="ws-section-title">
                <h2 id="notes-h">Notes & corrections</h2>
                <span>{item.notes.length} saved</span>
              </div>
              <p>
                Challenge an interpretation, record a question, or leave context
                for your next session.
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (body.trim()) {
                    note(item.id, body);
                    setBody("");
                    setSaved(true);
                  }
                }}
              >
                <label className="sr-only" htmlFor="work-note">
                  Note or correction
                </label>
                <textarea
                  id="work-note"
                  value={body}
                  maxLength={4000}
                  onChange={(e) => {
                    setBody(e.target.value);
                    setSaved(false);
                  }}
                  rows={4}
                  placeholder="Add a note or correction…"
                />
                <div className="flow-note-submit">
                  <span role="status">
                    {saved
                      ? "Note saved to this work."
                      : "Notes do not change source records."}
                  </span>
                  <Button type="submit" disabled={!body.trim()}>
                    Save note
                  </Button>
                </div>
              </form>
              <ol className="ws-note-list">
                {[...item.notes].reverse().map((n) => (
                  <li key={n.id}>
                    <p>{n.body}</p>
                    <span>
                      {n.author} · {new Date(n.at).toLocaleString()}
                    </span>
                  </li>
                ))}
              </ol>
            </section>
          )}
        </div>
      </div>
      {hasContext && (
        <footer className="studio-detail-footer">
          <Button variant="ghost" onClick={() => openRecord("investigation")}>
            Open scientific workspace <RiArrowRightLine size={14} />
          </Button>
        </footer>
      )}
    </div>
  );
}
