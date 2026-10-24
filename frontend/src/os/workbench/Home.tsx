import { useEffect, useState } from "react";
import {
  RiArrowRightLine,
  RiSearchLine,
} from "@remixicon/react";
import { useWorkspace } from "../WorkspaceProvider";
import { GoalComposer } from "../GoalComposer";
import { WorkflowGallery } from "../WorkflowGallery";
import { initialEntry, clearEntry } from "../work-entry";
import { SAMPLE_ID } from "../workspace-model";
import type { View } from "../WorkspaceShell";
import { Atmosphere, MotionControl } from "../Atmosphere";
import { WorkRow } from "./shared";
import { sourceApps } from "./catalog";

export function Home({
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
  const { data, create } = useWorkspace();
  const [incoming] = useState(() => {
    const entry = initialEntry();
    return {
      entry,
      missing: new URLSearchParams(location.search).has("draft") && !entry.goal,
    };
  });
  const [entry, setEntry] = useState(incoming.entry);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const work = data.work.filter(
    (w) =>
      w.goal.toLowerCase().includes(query.toLowerCase()) &&
      (filter === "all" ||
        (filter === "drafts"
          ? w.id !== SAMPLE_ID
          : data.actions.some(
              (a) => a.workId === w.id && a.status !== "outcome_recorded",
            ))),
  );
  const openFollowUp = data.actions.filter(
    (a) => a.status !== "outcome_recorded",
  ).length;

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

  const submit = () => {
    if (!entry.goal.trim()) return;
    const id = create(entry.goal, entry.kind, entry.context);
    clearEntry();
    openWork(id);
  };

  return (
    <div className="ws-page studio-home">
      <header className="home-hero">
        <div className="home-intro">
          <p className="home-kicker">Workbench · ask</p>
          <h1>What are you working on?</h1>
          <p className="home-lede">
            Start with a question. Add context when it helps.
          </p>
          {incoming.missing && (
            <p className="studio-recovery" role="alert">
              Your draft could not be restored in this tab. Start here, or
              return to the previous page to copy your question.
            </p>
          )}
          <GoalComposer
            id="home-goal"
            value={entry}
            onChange={setEntry}
            onSubmit={submit}
          />
          <p className="home-form-hint">
            Saved as a draft. New analysis is unavailable in this demo.
          </p>
          <details className="studio-starting-points">
            <summary>Find a starting point for your work</summary>
            <WorkflowGallery
              compact
              onChoose={(draft) => {
                setEntry(draft);
                document.getElementById("home-goal")?.focus();
              }}
            />
          </details>
        </div>

        <aside className="home-current" aria-label="Sample investigation">
          <Atmosphere />
          <div className="home-current-veil" aria-hidden="true" />
          <div className="home-current-top">
            <span>Sample thread</span>
            <span>F-2408 · BR-04</span>
          </div>
          <div className="home-current-body">
            <div className="home-current-copy">
              <span>48 h titer</span>
              <strong>
                1.74 <small>g/L</small>
              </strong>
              <em>−18% vs reference</em>
            </div>
            <ol className="home-current-thread">
              <li>
                <span>27 h</span>
                <p>DO leaves setpoint</p>
              </li>
              <li>
                <span>48 h</span>
                <p>Titer below reference</p>
              </li>
              <li>
                <span>Next</span>
                <p>Verify DO; recover off-gas</p>
              </li>
            </ol>
            <div className="home-current-sources" aria-hidden="true">
              <span>Historian</span>
              <span>LIMS</span>
              <span>MES</span>
              <span>Read-only</span>
            </div>
          </div>
          <div className="home-current-foot">
            <button
              type="button"
              className="home-current-link"
              aria-label="Continue investigation"
              onClick={() => openWork(SAMPLE_ID)}
            >
              Continue investigation{" "}
              <RiArrowRightLine size={15} aria-hidden="true" />
            </button>
            <MotionControl />
          </div>
        </aside>
      </header>

      <div className="home-lower">
        <section aria-label="Recent work" className="studio-collection home-work">
          <div className="home-section-head">
            <div>
              <h2>Continue your work</h2>
              <p className="home-section-sub">
                Saved in this browser · {data.work.length}{" "}
                {data.work.length === 1 ? "thread" : "threads"}
                {openFollowUp > 0
                  ? ` · ${openFollowUp} open follow-up`
                  : ""}
              </p>
            </div>
            <button type="button" className="link" onClick={() => go("work")}>
              All saved work <RiArrowRightLine size={14} />
            </button>
          </div>
          <div className="studio-collection-toolbar">
            <div
              className="studio-filter-tabs"
              role="group"
              aria-label="Filter recent work"
            >
              {[
                ["all", "All work"],
                ["drafts", "Drafts"],
                ["followup", "Needs follow-up"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  aria-pressed={filter === id}
                  onClick={() => setFilter(id)}
                >
                  {label}
                  {id === "all" && <span>{data.work.length}</span>}
                </button>
              ))}
            </div>
            <label className="studio-search">
              <RiSearchLine size={15} />
              <span className="sr-only">Find recent work</span>
              <input
                type="search"
                placeholder="Search work…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
          </div>
          <div className="studio-work-list">
            {work.map((w) => (
              <WorkRow key={w.id} work={w} onOpen={() => openWork(w.id)} />
            ))}
          </div>
          {!work.length && (
            <div className="studio-empty">
              <h2>
                {query
                  ? "No matching work"
                  : filter === "followup"
                    ? "No pending follow-up"
                    : "No drafts yet"}
              </h2>
              <button
                type="button"
                className="link"
                onClick={() => {
                  setQuery("");
                  setFilter("all");
                }}
              >
                Show all work
              </button>
            </div>
          )}
        </section>

        <aside className="home-rail" aria-label="Sources and boundaries">
          <section
            className="home-rail-card home-sources"
            aria-labelledby="source-short-h"
          >
            <div className="home-section-head">
              <h2 id="source-short-h">
                Sources{" "}
                <span className="studio-source-context">
                  Sample snapshots
                </span>
              </h2>
              <button
                type="button"
                className="link"
                onClick={() => go("sources")}
              >
                Manage access <RiArrowRightLine size={14} />
              </button>
            </div>
            <div className="studio-source-grid">
              {sourceApps.map((a) => (
                <button
                  key={a.view}
                  type="button"
                  className="studio-source"
                  onClick={() => go(a.view)}
                >
                  <span className="studio-source-icon">
                    <a.icon size={18} />
                  </span>
                  <span>
                    <b>{a.name}</b>
                    <small>{a.system}</small>
                  </span>
                </button>
              ))}
            </div>
          </section>

          <section
            className="home-rail-card home-boundary"
            aria-labelledby="home-boundary-h"
          >
            <p className="home-boundary-kicker">
              <i /> Boundary
            </p>
            <h2 id="home-boundary-h">What is real here?</h2>
            <p>
              Sample records and browser-local drafts. No live MES, LIMS,
              historian or QMS connection is configured.
            </p>
            <dl className="home-boundary-list">
              <div>
                <dt>In this demo</dt>
                <dd>Sample records · browser-local drafts</dd>
              </div>
              <div>
                <dt>In a real deployment</dt>
                <dd>Scoped connectors · approved write paths</dd>
              </div>
            </dl>
            <button type="button" onClick={() => go("sources")}>
              Inspect source boundary
              <RiArrowRightLine size={14} aria-hidden="true" />
            </button>
          </section>
        </aside>
      </div>
    </div>
  );
}
