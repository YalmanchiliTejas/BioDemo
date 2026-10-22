import { useEffect, useMemo, useRef, useState } from "react";
import * as Tooltip from "@radix-ui/react-tooltip";
import { AssistantRuntimeProvider, ComposerPrimitive, ThreadPrimitive, useLocalRuntime, type ThreadMessageLike } from "@assistant-ui/react";
import {
  RiArrowRightSLine,
  RiArrowUpLine,
  RiCheckLine,
  RiCloseLine,
  RiFileList3Line,
  RiFlaskLine,
  RiHome5Line,
  RiInboxLine,
  RiLineChartLine,
  RiShieldCheckLine,
  RiStackLine,
} from "@remixicon/react";
import "@fontsource-variable/manrope";
import "@fontsource/ibm-plex-mono/400.css";
import "../lab/lab.css";
import "./os.css";
import { agentSteps, NOW, vessels, workQueue, type Evidence } from "../lab/scenario";
import { ScenarioProvider, useScenario } from "../lab/state";
import { LabUIProvider, Shell, WhatsNew, type NavGroup } from "../lab/chrome";
import { SourceSheet, counts, useEvidence } from "../lab/evidence";
import { ReviewSheet } from "../lab/review";
import { QueueBody } from "../lab/ConceptA";
import { AssistantMessage, RecordBody, UserMessage, makeAdapter, order, replies, type Act, type Tab } from "../lab/ConceptB";
import { HistorianApp, LimsApp, MesApp, QmsApp, tagContext, type Tag } from "../lab/hosts";
import type { PenId } from "../lab/familiar";
import { AgentMark, Balance, Button, cx } from "../lab/ui";

type View = "home" | "queue" | "record" | "historian" | "lims" | "mes" | "qms";

const apps: { id: View; name: string; use: string; icon: JSX.Element }[] = [
  { id: "historian", name: "PlantView Historian", use: "Trends and alarms", icon: <RiLineChartLine size={16} /> },
  { id: "lims", name: "LabWare LIMS", use: "Samples and lab results", icon: <RiFlaskLine size={16} /> },
  { id: "mes", name: "Syncade MES", use: "Executed batch records", icon: <RiFileList3Line size={16} /> },
  { id: "qms", name: "QualityTrack QMS", use: "Deviations and CAPA", icon: <RiShieldCheckLine size={16} /> },
];

const viewName: Record<View, string> = {
  home: "Overview",
  queue: "Work queue",
  record: "Batch F-2408",
  historian: "PlantView Historian",
  lims: "LabWare LIMS",
  mes: "Syncade MES",
  qms: "QualityTrack QMS",
};

const readView = (): View => {
  const v = new URLSearchParams(location.search).get("view");
  return (["home", "queue", "record", "historian", "lims", "mes", "qms"] as View[]).includes(v as View) ? (v as View) : "home";
};

export default function HubApp() {
  return (
    <Tooltip.Provider delayDuration={300}>
      <ScenarioProvider>
        <LabUIProvider>
          <Hub />
        </LabUIProvider>
      </ScenarioProvider>
    </Tooltip.Provider>
  );
}

function Hub() {
  const s = useScenario();
  const [view, setView] = useState<View>(readView);
  const [tag, setTag] = useState<Tag>("DO");
  const [overlay, setOverlay] = useState(false);
  const [tab, setTab] = useState<Tab>("summary");
  const [penSel, setPenSel] = useState<PenId[]>(["do"]);
  const [reference, setReference] = useState(false);
  const [assistant, setAssistant] = useState(false);
  const [review, setReview] = useState(false);
  const [source, setSource] = useState<Evidence | null>(null);

  useEffect(() => {
    const restoreView = () => setView(readView());
    window.addEventListener("popstate", restoreView);
    return () => window.removeEventListener("popstate", restoreView);
  }, []);

  useEffect(() => {
    document.title = `${viewName[view]} · Manufacturing OS`;
    const url = new URL(location.href);
    if (view === "home") url.searchParams.delete("view");
    else url.searchParams.set("view", view);
    history.replaceState(null, "", url);
    if (view === "qms") s.reach("review");
    else if (view !== "home" && !s.detecting) s.reach("open");
  }, [view]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement;
      if (t.closest("input,textarea,select,[role=dialog],[cmdk-root]")) return;
      if (e.key.toLowerCase() === "r" && !s.detecting && (view === "record" || view === "home")) setReview(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const go = (v: View) => {
    if (v !== view) {
      const url = new URL(location.href);
      if (v === "home") url.searchParams.delete("view");
      else url.searchParams.set("view", v);
      history.pushState(null, "", url);
    }
    setView(v);
    document.querySelector(".sheet-page")?.scrollTo({ top: 0 });
  };
  const openRecord = (t: Tab = "summary") => {
    setTab(t);
    go("record");
  };
  const inspect = (e: Evidence) => {
    setSource(e);
    s.reach("inspect");
  };

  const onAct = (a: Act) => {
    if (a === "trends") {
      if (view === "historian") {
        setTag("DO");
        setOverlay(true);
      } else {
        setPenSel(["do", "ag", "af"]);
        setReference(true);
        openRecord("trends");
      }
    } else if (a === "lab") go("lims");
    else if (a === "events") openRecord("events");
    else openRecord("investigation");
    if (a === "plan" || a === "precedent")
      setTimeout(() => document.querySelector(a === "plan" ? "#action-h" : "#f-ev")?.scrollIntoView({ block: "start" }), 120);
  };

  const queueCount = workQueue.length - (s.receipt ? 1 : 0) - (s.detecting ? 1 : 0);
  const nav: NavGroup[] = [
    {
      group: "Workspace",
      items: [
        { id: "home", label: "Overview", icon: <RiHome5Line size={16} /> },
        { id: "queue", label: "Work queue", icon: <RiInboxLine size={16} />, count: queueCount },
        { id: "record", label: "Batch F-2408", note: "BR-04 · fed-batch", icon: <RiStackLine size={16} /> },
      ],
    },
    { group: "Source workspaces", items: apps.map((a) => ({ id: a.id, label: a.use, note: a.name, icon: a.icon })) },
  ];

  return (
    <div className="lab os-app">
      <a href="#work" className="skip">
        Skip to content
      </a>
      <p className="sim-banner"><span>Demo workspace</span> Sample plant data and simulated activity. No changes reach a real system.</p>
      <Shell
        current={view}
        title={viewName[view]}
        nav={nav}
        onNavigate={(id) => go(id as View)}
        assistantOpen={assistant}
        onAssistant={() => setAssistant((v) => !v)}
        assistant={<HubAssistant view={view} tag={tag} overlay={overlay} setOverlay={setOverlay} onAct={onAct} onOpen={inspect} onDraft={() => go("qms")} onClose={() => setAssistant(false)} />}
        commands={[
          ...apps.map((a) => ({ id: a.id, group: "Your applications", label: a.name, icon: a.icon, run: () => go(a.id) })),
          { id: "queue", group: "Workspace", label: "Work queue", icon: <RiInboxLine size={16} />, run: () => go("queue") },
          { id: "record", group: "Workspace", label: "Batch F-2408 · BR-04", icon: <RiStackLine size={16} />, run: () => openRecord() },
        ]}
      >
        {view === "home" && <Home go={go} openRecord={openRecord} onReview={() => setReview(true)} />}
        {view === "queue" && <QueueBody intro={false} onReview={() => setReview(true)} onOpen={inspect} onOpenRecord={() => openRecord()} />}
        {view === "record" && (
          <div className="record-page">
            <RecordBody tab={tab} setTab={setTab} penSel={penSel} setPenSel={setPenSel} reference={reference} setReference={setReference} onReview={() => setReview(true)} onOpen={inspect} />
          </div>
        )}
        {view === "historian" && <HistorianApp tag={tag} setTag={setTag} overlay={overlay} setOverlay={setOverlay} linked={assistant} />}
        {view === "lims" && <LimsApp />}
        {view === "mes" && <MesApp />}
        {view === "qms" && <QmsApp />}
      </Shell>
      <ReviewSheet open={review} onOpenChange={setReview} />
      <SourceSheet e={source} onClose={() => setSource(null)} />
    </div>
  );
}

/* ───────── Home: the applications they already use, and what the Assistant found ───────── */

function Home({ go, openRecord, onReview }: { go: (v: View) => void; openRecord: (t?: Tab) => void; onReview: () => void }) {
  const s = useScenario();
  const n = counts(useEvidence());
  const sent = s.receipt?.decision === "sent";
  const latest: Record<string, string> = {
    historian: s.detecting ? "Reading BR-04 trends" : "BR-04 agitation at its limit since 27 h",
    lims: "F-2408: 2 titer results below range",
    mes: "BR-03 harvest record ready to approve",
    qms: sent ? "EV-2026-0418 routed to QA" : s.detecting ? "No drafts" : "1 deviation drafted for you to check",
  };
  const running = vessels.filter((v) => v.batch && v.age != null);
  return (
    <div className="queue-page home">
      <header className="page-head">
        <div>
          <p className="page-eyebrow">Your workspace</p>
          <h1>Overview</h1>
          <p className="sub">Northfield · Upstream · day shift, {NOW.day}</p>
        </div>
        <Button onClick={() => go("queue")} icon={<RiInboxLine size={15} />}>View work queue</Button>
      </header>
      <WhatsNew id="hub-refresh">Start with the finding below. Inspect its evidence, review the proposed actions, then save a draft when you are ready.</WhatsNew>

      <div className="grid home-grid">
        <section className="card span-8 assistant-card" aria-labelledby="found-h">
          <header className="card-head">
            <h2 id="found-h">
              <AgentMark size={14} working={s.detecting} /> {sent ? "Review in progress" : "Needs your attention"}
            </h2>
            <span className="finding-label">{s.detecting ? "Checking sources" : "F-2408 · BR-04"}</span>
          </header>
          {s.detecting ? (
            <ol className="steps" role="status" aria-live="polite">
              {agentSteps.map((t, i) => (
                <li key={t} className={cx(i < s.step && "done", i === s.step && "now")}>
                  {i < s.step ? <RiCheckLine size={14} /> : <span className="pip" />}
                  {t}
                </li>
              ))}
            </ol>
          ) : (
            <>
              <p className="found-title">A lower titer needs a closer look.</p>
              <p className="found-text">Batch F-2408 is 18% below the R7 reference at 48 h. Reduced oxygen transfer is a possible explanation; missing off-gas data means it is not confirmed.</p>
              <Balance {...n} />
              <div className="found-actions">
                <Button variant="primary" onClick={sent ? () => go("qms") : () => openRecord("investigation")}>
                  {sent ? "Open quality draft" : "Investigate batch"} <RiArrowRightSLine size={16} />
                </Button>
                <Button variant="secondary" onClick={onReview}>
                  Review proposed plan
                </Button>
              </div>
              <button type="button" className="link found-more" onClick={() => go("queue")}>
                See all items in your work queue <RiArrowRightSLine size={14} />
              </button>
            </>
          )}
        </section>

        <section className="card span-4 shift-card" aria-labelledby="shift-h">
          <header className="card-head"><h2 id="shift-h">Shift at a glance</h2><span className="meta">{NOW.label}</span></header>
          <dl className="shift-metrics">
            <div><dt>Running batches</dt><dd>{running.length}</dd></div>
            <div><dt>Work queue</dt><dd>{workQueue.length - (s.receipt ? 1 : 0) - (s.detecting ? 1 : 0)}</dd></div>
            <div><dt>Source workspaces</dt><dd>{apps.length}</dd></div>
          </dl>
          <p className="shift-note">Sources are read only. Proposed quality actions stay in draft until reviewed.</p>
        </section>

        <section className="card span-12" aria-labelledby="run-h">
          <header className="card-head">
            <h2 id="run-h">Batches running</h2>
            <span className="meta num">Updated {NOW.label}</span>
          </header>
          <p className="table-scroll-note">Scroll across to see all batch details.</p>
          <div className="table-wrap" role="region" aria-labelledby="run-h" tabIndex={0}>
            <table aria-label="Running batches">
              <thead>
                <tr>
                  <th scope="col">Unit</th>
                  <th scope="col">Batch</th>
                  <th scope="col">Recipe</th>
                  <th scope="col" className="n">
                    Age
                  </th>
                  <th scope="col">Status</th>
                  <th scope="col" />
                </tr>
              </thead>
              <tbody>
                {running.map((v) => (
                  <tr key={v.id} className={cx(v.flagged && "clickable")} onClick={v.flagged ? () => openRecord() : undefined}>
                    <th scope="row">{v.id}</th>
                    <td className="id">{v.batch}</td>
                    <td>{v.recipe}</td>
                    <td className="n num">{v.age!.toFixed(1)} h</td>
                    <td>{v.flagged ? <span className={cx("pill", sent ? "pill-pos" : "pill-warn")}>{sent ? "Verification with QA" : v.state}</span> : <span className="muted-cell">{v.state}</span>}</td>
                    <td className="n">
                      {v.flagged && (
                        <button type="button" className="link" onClick={(e) => { e.stopPropagation(); openRecord(); }}>
                          Open record
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card span-12 sources-card" aria-labelledby="apps-h">
          <header className="card-head"><div><h2 id="apps-h">Explore the source records</h2><p className="meta">Open the context behind a finding.</p></div><span className="meta">Simulated workspaces</span></header>
          <ul className="source-app-grid">
            {apps.map((a) => <li key={a.id}><button type="button" className="source-app" onClick={() => go(a.id)}>
              <span className="source-app-top"><span className="app-icon">{a.icon}</span><RiArrowRightSLine size={16} /></span>
              <b>{a.use}</b><span className="meta">{a.name}</span><span className="source-app-note">{latest[a.id]}</span>
            </button></li>)}
          </ul>
        </section>
      </div>
    </div>
  );
}

/* ───────── One Assistant, beside whichever application is open ───────── */

const contextNote = (view: View, tag: Tag): { text: string; linked?: boolean } | null => {
  switch (view) {
    case "historian":
      return { text: tagContext[tag].text, linked: tagContext[tag].linked };
    case "lims":
      return { text: "The 36 h and 48 h titer results are below the reference range of 6 prior R7 batches. The 60 h sample is due at 20:00." };
    case "mes":
      return { text: "Step 4.3 records the foam alarm at 22 h. Antifoam use rose after it, which is part of the leading explanation." };
    case "qms":
      return { text: "I drafted the fields with a teal edge from 8 linked records. Check each one; you save and route it with QMS's own button." };
    default:
      return null;
  }
};

function HubAssistant({
  view,
  tag,
  overlay,
  setOverlay,
  onAct,
  onOpen,
  onDraft,
  onClose,
}: {
  view: View;
  tag: Tag;
  overlay: boolean;
  setOverlay: (v: boolean) => void;
  onAct: (a: Act) => void;
  onOpen: (e: Evidence) => void;
  onDraft: () => void;
  onClose: () => void;
}) {
  const s = useScenario();
  const list = useEvidence();
  const [used, setUsed] = useState<Act[]>([]);
  const actRef = useRef(onAct);
  actRef.current = (a) => {
    setUsed((u) => (u.includes(a) ? u : [...u, a]));
    onAct(a);
  };
  const adapter = useMemo(() => makeAdapter((a) => actRef.current(a)), []);
  const initial: ThreadMessageLike[] = [
    {
      role: "assistant",
      content: `I flagged batch F-2408 at ${NOW.label}: titer is 18 % below the R7 reference at 48 h. Open any of your applications as usual and I will explain what you are looking at.`,
    },
  ];
  const runtime = useLocalRuntime(adapter, { initialMessages: initial, maxSteps: 1 });
  const next = order.filter((a) => !used.includes(a)).slice(0, 3);
  const note = s.detecting ? null : contextNote(view, tag);
  const missing = list.filter((e) => e.stance === "missing");

  return (
    <div className="assistant-inner">
      <header className="assistant-head">
        <AgentMark size={16} working={s.detecting} />
        <div>
          <h2>Assistant</h2>
          <p>Reads Historian, LIMS, MES and QMS. Cannot change records.</p>
        </div>
        <button type="button" className="icon-btn assistant-close" aria-label="Close assistant panel" onClick={onClose}><RiCloseLine size={17} /></button>
      </header>
      <p className="assistant-ctx">
        Looking at <b>{viewName[view]}</b>
        {view === "historian" && <> · {tag === "DO" ? "BR04.DO.PV" : tag === "AG" ? "BR04.SIC-110.OUT" : tag === "AF" ? "BR04.AF.TOT" : tag === "TEMP" ? "BR04.TEMP.PV" : "BR04.PH.PV"}</>}
      </p>
      {s.detecting ? (
        <div className="assistant-body">
          <ol className="steps" role="status" aria-live="polite">
            {agentSteps.map((t, i) => (
              <li key={t} className={cx(i < s.step && "done", i === s.step && "now")}>
                {i < s.step ? <RiCheckLine size={14} /> : <span className="pip" />}
                {t}
              </li>
            ))}
          </ol>
        </div>
      ) : (
        <AssistantRuntimeProvider runtime={runtime}>
          <ThreadPrimitive.Root className="assistant-thread">
            <ThreadPrimitive.Viewport className="assistant-body">
              {note && (
                <div className={cx("assistant-note-card", note.linked === false && "is-quiet")}>
                  <p>{note.text}</p>
                  {view === "historian" && note.linked && (
                    <Button size="sm" variant="secondary" onClick={() => setOverlay(!overlay)} icon={overlay ? <RiCheckLine size={14} /> : undefined}>
                      {overlay ? "Reference shown on this trend" : "Show reference on this trend"}
                    </Button>
                  )}
                  {view === "lims" && (
                    <button type="button" className="link" onClick={() => onOpen(missing[2] ?? missing[0])}>
                      What the 60 h result will tell us
                    </button>
                  )}
                </div>
              )}
              {view !== "qms" && !s.receipt && !s.detecting && (
                <button type="button" className="assistant-draft" onClick={onDraft}>
                  <RiShieldCheckLine size={15} />
                  <span>
                    <b>Deviation drafted in QualityTrack</b>
                    <small>3 tasks · no setpoint changes · waiting for your check</small>
                  </span>
                  <RiArrowRightSLine size={16} />
                </button>
              )}
              <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
            </ThreadPrimitive.Viewport>
            <div className="assistant-foot">
              {next.length > 0 && (
                <div className="suggest" aria-label="Suggested questions">
                  {next.map((a) => (
                    <ThreadPrimitive.Suggestion key={a} prompt={replies[a].prompt} send className="chip">
                      {replies[a].chip}
                    </ThreadPrimitive.Suggestion>
                  ))}
                </div>
              )}
              <ComposerPrimitive.Root className="composer">
                <ComposerPrimitive.Input className="composer-input" placeholder="Ask about this batch" rows={1} aria-label="Ask the Assistant" />
                <ComposerPrimitive.Send className="composer-send" aria-label="Send">
                  <RiArrowUpLine size={15} />
                </ComposerPrimitive.Send>
              </ComposerPrimitive.Root>
              <p className="assistant-note">Scripted in this prototype. Answers open the record they come from.</p>
            </div>
          </ThreadPrimitive.Root>
        </AssistantRuntimeProvider>
      )}
    </div>
  );
}
