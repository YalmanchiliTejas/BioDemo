import { useEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  RiArrowLeftSLine,
  RiArrowRightUpLine,
  RiCheckLine,
  RiCloseLine,
  RiFolder3Line,
  RiPulseLine,
  RiSubtractLine,
} from "@remixicon/react";
import { action, agentSteps, agitation, antifoam, batch, dissolvedO2, NOW, onlineHours, people, zip, type Evidence } from "./scenario";
import { useScenario } from "./state";
import { TrendChart, type TrendProps } from "./TrendChart";
import { counts, SourceActions, SourceDetail, SourceTitle, useEvidence } from "./evidence";
import { useTiterSeries } from "./charts";
import { Workspace } from "./ConceptB";
import { HistorianApp, QmsApp, tagContext, tags, type Tag } from "./hosts";
import { AgentMark, Balance, Button, Confidence, Kbd, SimNote, StanceMark, cx } from "./ui";

type Host = "historian" | "qms";
type Panel = "summary" | "evidence";

export default function ConceptC() {
  const s = useScenario();
  const [host, setHost] = useState<Host>("historian");
  const [tag, setTag] = useState<Tag>("DO");
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<Panel>("summary");
  const [detail, setDetail] = useState<Evidence | null>(null);
  const [overlay, setOverlay] = useState(false);
  const [workspace, setWorkspace] = useState(false);
  const pillRef = useRef<HTMLButtonElement>(null);
  const list = useEvidence();
  const n = counts(list);
  const { gap } = useTiterSeries();
  const ctx = tagContext[tag];
  const cur = tags.find((t) => t.id === tag)!;

  const expand = () => {
    setOpen(true);
    if (!s.detecting) s.reach("open");
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === ".") {
        e.preventDefault();
        setOpen((v) => !v);
        if (!s.detecting) s.reach("open");
        return;
      }
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement;
      if (t.closest("input,textarea,select,[role=dialog]")) return;
      if (e.key === "Escape" && detail) setDetail(null);
      else if (e.key === "Escape" && open) {
        setOpen(false);
        requestAnimationFrame(() => pillRef.current?.focus());
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const inspect = (e: Evidence) => {
    setDetail(e);
    s.reach("inspect");
  };

  return (
    <div className="c-shell">
      <div className="host-tabs" role="tablist" aria-label="Existing applications (simulated)">
        <span className="host-tabs-label">Existing apps</span>
        <button role="tab" aria-selected={host === "historian"} className={cx("host-tab", host === "historian" && "is-on")} onClick={() => setHost("historian")}>
          PlantView Historian
        </button>
        <button role="tab" aria-selected={host === "qms"} className={cx("host-tab", host === "qms" && "is-on")} onClick={() => { setHost("qms"); s.reach("review"); }}>
          QualityTrack QMS
        </button>
        <SimNote>Simulated host applications</SimNote>
      </div>

      <div className={cx("host-frame", open && "has-companion")}>
        {host === "historian" ? (
          <HistorianApp tag={tag} setTag={setTag} overlay={overlay} setOverlay={setOverlay} linked={open} />
        ) : (
          <QmsApp />
        )}

        {open ? (
          <aside className="companion" aria-label="Assistant">
            <header className="comp-head">
              {detail ? (
                <button type="button" className="comp-back" onClick={() => setDetail(null)}>
                  <RiArrowLeftSLine size={16} /> Back
                </button>
              ) : (
                <span className="comp-brand">
                  <AgentMark size={16} working={s.detecting} /> Assistant
                </span>
              )}
              <span className="comp-head-r">
                <Kbd>⌃.</Kbd>
                <button type="button" className="icon-btn" aria-label="Minimise companion" onClick={() => { setOpen(false); requestAnimationFrame(() => pillRef.current?.focus()); }}>
                  <RiSubtractLine size={16} />
                </button>
              </span>
            </header>

            {s.detecting ? (
              <div className="comp-body">
                <div className="working is-compact" role="status" aria-live="polite">
                  <div>
                    <b>Watching BR-04</b>
                    <ol>
                      {agentSteps.map((t, i) => (
                        <li key={t} className={cx(i < s.step && "done", i === s.step && "now")}>
                          {i < s.step ? <RiCheckLine size={13} /> : <span className="pip" />}
                          {t}
                        </li>
                      ))}
                    </ol>
                  </div>
                </div>
              </div>
            ) : detail ? (
              <>
                <div className="comp-body">
                  <p className="comp-detail-title">
                    <SourceTitle e={detail} />
                  </p>
                  <p className="comp-claim">{detail.claim}</p>
                  <SourceDetail e={detail} />
                </div>
                <footer className="comp-foot">
                  <SourceActions e={detail} />
                </footer>
              </>
            ) : host === "qms" ? (
              <div className="comp-body">
                <p className="comp-ctx">
                  Reading <b>QualityTrack · {action.target.record}</b>
                </p>
                <div className="comp-note">
                  <AgentMark size={14} />
                  <p>I drafted the fields with a teal edge from 8 linked records. Check each one; you save and route it, not me.</p>
                </div>
                <ul className="comp-ev">
                  {list.slice(0, 5).map((e) => (
                    <li key={e.id}>
                      <button type="button" onClick={() => inspect(e)}>
                        <StanceMark stance={e.stance} />
                        <span>{e.claim}</span>
                      </button>
                    </li>
                  ))}
                </ul>
                <Button variant="ghost" onClick={() => setHost("historian")}>
                  Back to the trend
                </Button>
              </div>
            ) : (
              <>
                <div className="comp-body">
                  <p className="comp-ctx">
                    Reading <b className="id">{cur.tag}</b> for {batch.id}
                  </p>
                  <div className={cx("comp-context", ctx.linked ? "is-linked" : "is-unlinked")}>{ctx.text}</div>

                  <section className="comp-finding">
                    <h2>Titer is {gap} % below the R7 reference mean, outside the prior-batch range</h2>
                    <p className="meta">Flagged on this batch at {NOW.label}</p>
                    <p>Likely reduced oxygen transfer after heavy antifoam use. Unconfirmed: off-gas data for 31–44 h is missing.</p>
                    <div className="comp-meta">
                      <Confidence level={2} />
                      <Balance {...n} />
                    </div>
                    {ctx.linked && (
                      <Button variant="secondary" size="sm" onClick={() => setOverlay(!overlay)} icon={overlay ? <RiCheckLine size={14} /> : undefined}>
                        {overlay ? "Overlay shown on trend" : "Show reference on this trend"}
                      </Button>
                    )}
                  </section>

                  <div className="comp-tabs" role="tablist" aria-label="Companion sections">
                    {(["summary", "evidence"] as Panel[]).map((p) => (
                      <button key={p} role="tab" aria-selected={panel === p} className={cx(panel === p && "is-on")} onClick={() => setPanel(p)}>
                        {p === "summary" ? "Next step" : `Evidence · ${list.length}`}
                      </button>
                    ))}
                  </div>

                  {panel === "evidence" ? (
                    <ul className="comp-ev">
                      {list.map((e) => (
                        <li key={e.id}>
                          <button type="button" onClick={() => inspect(e)}>
                            <StanceMark stance={e.stance} />
                            <span>{e.claim}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <section className="comp-action">
                      <h3>{action.title}</h3>
                      <ol>
                        {action.steps.map((st) => (
                          <li key={st.id}>{st.text}</li>
                        ))}
                      </ol>
                      <p className="comp-boundary">No setpoint changes proposed.</p>
                      {s.receipt?.decision === "sent" ? (
                        <p className="comp-done">
                          <RiCheckLine size={14} /> Saved in QualityTrack at {s.receipt.at}. I'll re-assess at 60 h.
                        </p>
                      ) : (
                        <Button variant="primary" onClick={() => { setHost("qms"); s.reach("review"); }}>
                          Draft it in QualityTrack
                        </Button>
                      )}
                    </section>
                  )}
                </div>
                <footer className="comp-foot">
                  <Button variant="ghost" size="sm" onClick={() => setWorkspace(true)} icon={<RiArrowRightUpLine size={14} />}>
                    Open batch record
                  </Button>
                  <span className="foot-note">Read-only on this app</span>
                </footer>
              </>
            )}
          </aside>
        ) : (
          <button ref={pillRef} type="button" className={cx("comp-pill", !s.detecting && "has-finding")} onClick={expand} aria-label={s.detecting ? "Assistant, checking BR-04" : "Assistant, 1 finding on this batch"}>
            <AgentMark size={16} working={s.detecting} />
            <span>{s.detecting ? "Assistant checking BR-04…" : s.receipt ? "Assistant · following up on F-2408" : "Assistant · 1 finding on this batch"}</span>
            <Kbd>⌃.</Kbd>
          </button>
        )}
      </div>

      <Dialog.Root open={workspace} onOpenChange={setWorkspace}>
        <Dialog.Portal>
          <Dialog.Content className="lab ws-overlay" aria-describedby={undefined}>
            <Dialog.Title className="sr-only">Investigation workspace</Dialog.Title>
            <Workspace embedded onClose={() => setWorkspace(false)} />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}

