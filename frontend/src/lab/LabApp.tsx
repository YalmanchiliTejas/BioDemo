import { lazy, Suspense, useEffect, useState } from "react";
import * as Tooltip from "@radix-ui/react-tooltip";
import { RiArrowLeftLine, RiKeyboardLine, RiReplay5Line } from "@remixicon/react";
import "@fontsource-variable/manrope";
import "@fontsource/ibm-plex-mono/400.css";
import "./lab.css";
import { ScenarioProvider, stages, useScenario } from "./state";
import { LabUIProvider } from "./chrome";
import { Kbd, Sheet, cx } from "./ui";

const ConceptA = lazy(() => import("./ConceptA"));
const ConceptB = lazy(() => import("./ConceptB"));
const ConceptC = lazy(() => import("./ConceptC"));
const Compare = lazy(() => import("./Compare"));

type View = "a" | "b" | "c" | "compare";
const views: { id: View; key: string; label: string; short: string }[] = [
  { id: "a", key: "1", label: "Work queue", short: "A" },
  { id: "b", key: "2", label: "Batch record", short: "B" },
  { id: "c", key: "3", label: "Inside your apps", short: "C" },
  { id: "compare", key: "4", label: "Comparison", short: "" },
];
const titles: Record<View, string> = { a: "A · Work queue", b: "B · Batch record", c: "C · Inside your apps", compare: "Comparison" };

const readView = (): View => {
  const v = new URLSearchParams(location.search).get("concept");
  return v === "b" || v === "c" || v === "compare" ? v : "a";
};

export default function LabApp() {
  return (
    <Tooltip.Provider delayDuration={300}>
      <ScenarioProvider>
        <LabUIProvider>
          <Lab />
        </LabUIProvider>
      </ScenarioProvider>
    </Tooltip.Provider>
  );
}

function Lab() {
  const [view, setView] = useState<View>(readView);
  const [help, setHelp] = useState(false);
  const s = useScenario();

  const go = (v: View) => {
    if (v === view) return;
    setView(v);
    history.replaceState(null, "", `/concepts?concept=${v}${new URLSearchParams(location.search).has("instant") ? "&instant" : ""}`);
    s.replay();
  };

  useEffect(() => {
    document.title = `${titles[view]} · Manufacturing OS interaction study`;
  }, [view]);

  useEffect(() => {
    const onGo = (e: Event) => go((e as CustomEvent<View>).detail);
    window.addEventListener("lab:go", onGo);
    return () => window.removeEventListener("lab:go", onGo);
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement;
      if (t.closest("input,textarea,select,[role=dialog],[cmdk-root]")) return;
      const v = views.find((x) => x.key === e.key);
      if (v) {
        e.preventDefault();
        go(v.id);
      } else if (e.key === "?") {
        e.preventDefault();
        setHelp(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div className={cx("lab lab-root", (view === "a" || view === "b") && "is-fixed")}>
      <a href="#lab-stage" className="skip">
        Skip to prototype
      </a>
      <div className="labbar" role="region" aria-label="Interaction study controls">
        <a className="labbar-back" href="/">
          <RiArrowLeftLine size={14} /> App
        </a>
        <nav className="labbar-tabs" aria-label="Interface concepts">
          {views.map((v) => (
            <button key={v.id} type="button" className={cx("labtab", view === v.id && "is-on")} aria-current={view === v.id ? "page" : undefined} onClick={() => go(v.id)}>
              {v.short && <span className="labtab-letter">{v.short}</span>}
              {v.label}
              <Kbd>{v.key}</Kbd>
            </button>
          ))}
        </nav>
        {view !== "compare" && (
          <>
            <ol className="journey" aria-label="Scenario progress">
              {stages.map((st) => (
                <li key={st.id} className={cx(s.reached.includes(st.id) && "is-done")}>
                  {st.label}
                </li>
              ))}
            </ol>
            <div className="labbar-ctl">
              <label className="switch">
                <input type="checkbox" checked={s.assayPosted} onChange={(e) => s.setAssay(e.target.checked)} />
                <span className="switch-track" aria-hidden="true" />
                60 h assay arrives
              </label>
              <button type="button" className="labbar-btn" onClick={s.replay}>
                <RiReplay5Line size={14} /> Replay
              </button>
            </div>
          </>
        )}
        <button type="button" className="labbar-btn" onClick={() => setHelp(true)} aria-label="Keyboard shortcuts">
          <RiKeyboardLine size={15} />
          <Kbd>?</Kbd>
        </button>
      </div>
      <p className="sim-banner">Illustrative prototype. Plant data, connectors, people and agent activity are simulated; nothing is read from or written to a real system.</p>
      <div id="lab-stage" className="stage" key={view}>
        <Suspense fallback={<p className="loading">Loading…</p>}>
          {view === "a" && <ConceptA />}
          {view === "b" && <ConceptB />}
          {view === "c" && <ConceptC />}
          {view === "compare" && <Compare />}
        </Suspense>
      </div>
      <Sheet open={help} onOpenChange={setHelp} title="Keyboard shortcuts" width={440}>
        <dl className="shortcuts">
          {[
            ["1 2 3 4", "Switch concept / comparison"],
            ["?", "This list"],
            ["Esc", "Close the top layer"],
            ["⌘K", "Search batches, tags and samples"],
            ["A · ↑ ↓", "Move through the work queue"],
            ["A, B · R", "Review the proposed plan"],
            ["C · ⌃ .", "Show or hide the companion"],
            ["Charts · ← →", "Step through data points"],
            ["Review · ⌘ ↵", "Send or decline"],
          ].map(([k, d]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{d}</dd>
            </div>
          ))}
        </dl>
      </Sheet>
    </div>
  );
}
