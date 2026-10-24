import { lazy, Suspense, useEffect, useState } from "react";
import * as Tooltip from "@radix-ui/react-tooltip";
import "@fontsource-variable/manrope";
import "@fontsource/ibm-plex-mono/400.css";
import "../lab/lab.css";
import "./os.css";
import "./workspace-flow.css";
import { MotionProvider, useAmbientMotion } from "./Atmosphere";
import { ScenarioProvider, useScenario } from "../lab/state";
import { LabUIProvider } from "../lab/chrome";
import { SourceSheet } from "../lab/evidence";
import { ReviewSheet } from "../lab/review";
import { QueueBody } from "../lab/ConceptA";
import type { Evidence } from "../lab/scenario";
import type { Act, Tab } from "../lab/ConceptB";
import type { PenId } from "../lab/familiar";
import { HistorianApp, LimsApp, MesApp, QmsApp, type Tag } from "../lab/hosts";
import { WorkspaceProvider } from "./WorkspaceProvider";
import { WorkspaceShell, viewName, type View } from "./WorkspaceShell";
import { Actions } from "./workbench/Actions";
import { Home } from "./workbench/Home";
import { SavedWork } from "./workbench/SavedWork";
import { Sources } from "./workbench/Sources";
import { workSections, type WorkSection } from "./workbench/WorkDetail";
import { WorkDetail } from "./workbench/WorkDetail";
import "./flow.css";
import "./connected.css";
import { ConnectedProvider, useConnected } from "./api/ConnectedWorkspace";
import {
  ConnectedActions,
  ConnectedHome,
  ConnectedSavedWork,
  ConnectedWorkDetail,
} from "./api/ConnectedViews";

const ScientificRecord = lazy(() =>
  import("../lab/ConceptB").then((m) => ({ default: m.RecordBody })),
);
const WorkspaceAssistant = lazy(() => import("./WorkspaceAssistant"));
const views = Object.keys(viewName);
const panels: Tab[] = ["summary", "trends", "lab", "events", "investigation"];
function readRoute() {
  const params = new URLSearchParams(location.search);
  return {
    view: (views.includes(params.get("view") || "")
      ? params.get("view")
      : "home") as View,
    item: params.get("work") || "",
    section: (workSections.includes(params.get("section") as WorkSection)
      ? params.get("section")
      : "overview") as WorkSection,
    panel: (panels.includes(params.get("panel") as Tab)
      ? params.get("panel")
      : "summary") as Tab,
  };
}
export default function HubApp() {
  return (
    <MotionProvider>
      <Tooltip.Provider delayDuration={300}>
        <ScenarioProvider persistKey="manufacturing-os:sample:v1">
          <WorkspaceProvider>
            <ConnectedProvider>
              <LabUIProvider>
                <Hub />
              </LabUIProvider>
            </ConnectedProvider>
          </WorkspaceProvider>
        </ScenarioProvider>
      </Tooltip.Provider>
    </MotionProvider>
  );
}
function Hub() {
  const { paused, reduced } = useAmbientMotion();
  const s = useScenario();
  const connected = useConnected().active;
  const [route, setRoute] = useState(readRoute);
  const { view, item, panel, section } = route;
  const [newWorkRequest, setNewWorkRequest] = useState(0);
  const [tag, setTag] = useState<Tag>("DO");
  const [overlay, setOverlay] = useState(false);
  const [pens, setPens] = useState<PenId[]>(["do"]);
  const [reference, setReference] = useState(false);
  const [assistant, setAssistant] = useState(false);
  const [review, setReview] = useState(false);
  const [source, setSource] = useState<Evidence | null>(null);
  useEffect(() => {
    const back = () => setRoute(readRoute());
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, []);
  useEffect(() => {
    document.title = `${viewName[view]} · Manufacturing OS`;
  }, [view]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (
        e.defaultPrevented ||
        e.metaKey ||
        e.ctrlKey ||
        e.altKey ||
        (e.target as HTMLElement).closest(
          "input,textarea,select,[role=dialog],[cmdk-root]",
        )
      )
        return;
      if (e.key.toLowerCase() === "r" && !s.detecting && view === "record")
        setReview(true);
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [s.detecting, view]);
  const navigate = (
    next: View,
    id = "",
    tab: Tab = "summary",
    replace = false,
  ) => {
    const url = new URL(location.href);
    url.searchParams.delete("draft");
    url.searchParams.delete("intent");
    if (next === "home") url.searchParams.delete("view");
    else url.searchParams.set("view", next);
    if (id) url.searchParams.set("work", id);
    else url.searchParams.delete("work");
    url.searchParams.delete("section");
    if (next === "record") url.searchParams.set("panel", tab);
    else url.searchParams.delete("panel");
    if (replace) history.replaceState(null, "", url);
    else history.pushState(null, "", url);
    setRoute({ view: next, item: id, panel: tab, section: "overview" });
    document.querySelector(".sheet-page")?.scrollTo({ top: 0 });
    s.reach("open");
  };
  const go = (next: View) => navigate(next);
  const newWork = () => {
    go("home");
    setNewWorkRequest((v) => v + 1);
  };
  const setSection = (next: WorkSection) => {
    const url = new URL(location.href);
    url.searchParams.set("section", next);
    history.pushState(null, "", url);
    setRoute((r) => ({ ...r, section: next }));
  };
  const openWork = (id: string) => navigate("item", id);
  const openRecord = (tab: Tab = "summary") => navigate("record", "", tab);
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
        setPens(["do", "ag", "af"]);
        setReference(true);
        openRecord("trends");
      }
    } else if (a === "lab") go("lims");
    else if (a === "events") openRecord("events");
    else openRecord("investigation");
  };
  return (
    <div
      className="lab os-app"
      data-motion={paused || reduced ? "still" : "full"}
      data-view={view}
    >
      <a href="#work" className="skip">
        Skip to content
      </a>
      <WorkspaceShell
        view={view}
        go={go}
        openWork={openWork}
        onNewWork={newWork}
        assistantOpen={assistant}
        onAssistant={() => setAssistant((v) => !v)}
        assistant={
          <Suspense
            fallback={
              <div className="ws-loading" role="status">
                Opening sample guide…
              </div>
            }
          >
            <WorkspaceAssistant
              view={view}
              tag={tag}
              overlay={overlay}
              setOverlay={setOverlay}
              onAct={onAct}
              onOpen={inspect}
              onDraft={() => go("qms")}
              onClose={() => setAssistant(false)}
            />
          </Suspense>
        }
      >
        <div key={`${view}-${item}`} className="workspace-view">
          {["historian", "lims", "mes", "qms", "queue"].includes(view) && (
            <p className="ws-source-boundary">
              Simulated workspace · Snapshot records · No live connection or
              background monitoring
            </p>
          )}
          {view === "home" && connected && (
            <ConnectedHome
              go={go}
              openWork={openWork}
              newWorkRequest={newWorkRequest}
              onNewWorkOpened={() => setNewWorkRequest(0)}
            />
          )}
          {view === "home" && !connected && (
            <Home
              go={go}
              openWork={openWork}
              newWorkRequest={newWorkRequest}
              onNewWorkOpened={() => setNewWorkRequest(0)}
            />
          )}
          {view === "work" && connected && (
            <ConnectedSavedWork openWork={openWork} />
          )}
          {view === "work" && !connected && (
            <SavedWork openWork={openWork} />
          )}
          {view === "item" && connected && (
            <ConnectedWorkDetail
              id={item}
              section={section}
              setSection={setSection}
              go={go}
            />
          )}
          {view === "item" && !connected && (
            <WorkDetail
              id={item}
              section={section}
              setSection={setSection}
              onReview={() => setReview(true)}
              go={go}
              openRecord={(tab) => navigate("record", item, tab)}
              onOpen={inspect}
            />
          )}
          {view === "actions" && connected && <ConnectedActions />}
          {view === "actions" && !connected && <Actions />}
          {view === "sources" && <Sources go={go} />}
          {view === "queue" && (
            <QueueBody
              intro={false}
              onReview={() => setReview(true)}
              onOpen={inspect}
              onOpenRecord={() => openRecord()}
            />
          )}
          {view === "record" && (
            <div className="record-page">
              <div className="ws-record-context">
                {item ? (
                  <button type="button" onClick={() => openWork(item)}>
                    ← Back to this work
                  </button>
                ) : (
                  <span>Scientific workspace / Sample F-2408</span>
                )}
                <button type="button" onClick={() => go("actions")}>
                  Actions & follow-up →
                </button>
              </div>
              <Suspense
                fallback={
                  <div className="ws-loading" role="status">
                    Opening scientific tools…
                  </div>
                }
              >
                <ScientificRecord
                  tab={panel}
                  setTab={(tab) => navigate("record", item, tab, true)}
                  penSel={pens}
                  setPenSel={setPens}
                  reference={reference}
                  setReference={setReference}
                  onReview={() => setReview(true)}
                  onOpen={inspect}
                />
              </Suspense>
            </div>
          )}
          {view === "historian" && (
            <HistorianApp
              tag={tag}
              setTag={setTag}
              overlay={overlay}
              setOverlay={setOverlay}
              linked={assistant}
            />
          )}
          {view === "lims" && <LimsApp />}
          {view === "mes" && <MesApp />}
          {view === "qms" && <QmsApp />}
        </div>
      </WorkspaceShell>
      <ReviewSheet open={review} onOpenChange={setReview} localOnly />
      <SourceSheet e={source} onClose={() => setSource(null)} />
    </div>
  );
}
