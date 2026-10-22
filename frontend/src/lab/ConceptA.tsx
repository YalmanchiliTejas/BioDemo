import { useEffect, useState } from "react";
import { RiArrowLeftLine, RiArrowRightUpLine, RiFlaskLine, RiInboxLine, RiLineChartLine, RiTimeLine } from "@remixicon/react";
import { action, NOW, workQueue, type Evidence, type QueueItem } from "./scenario";
import { useScenario } from "./state";
import { Shell, WhatsNew, useLabUI, type NavId } from "./chrome";
import { TiterChart, useTiterSeries } from "./charts";
import { SourceSheet, counts, useEvidence } from "./evidence";
import { ReviewSheet } from "./review";
import { OpenInSource } from "./familiar";
import { AgentMark, Balance, Button, SourceRef, StanceMark, cx } from "./ui";

type Filter = "all" | "assistant";
const goConcept = (c: string) => window.dispatchEvent(new CustomEvent("lab:go", { detail: c }));

export default function ConceptA() {
  const s = useScenario();
  const [review, setReview] = useState(false);
  const [source, setSource] = useState<Evidence | null>(null);
  const navigate = (id: NavId) => {
    if (id === "queue") return;
    goConcept("b");
  };
  return (
    <Shell
      current="queue"
      title="Work queue"
      onNavigate={navigate}
      commands={[
        { id: "f2408", group: "Batches", label: "Batch F-2408 · BR-04", icon: <RiFlaskLine size={16} />, run: () => goConcept("b") },
        { id: "q1", group: "Work queue", label: "Titer below reference range · F-2408", icon: <RiInboxLine size={16} />, run: () => undefined },
        { id: "do", group: "Trends", label: "BR04.DO.PV · Dissolved oxygen", icon: <RiLineChartLine size={16} />, run: () => goConcept("b") },
      ]}
    >
      <QueueBody
        onReview={() => setReview(true)}
        onOpen={(e) => {
          setSource(e);
          s.reach("inspect");
        }}
        onOpenRecord={() => goConcept("b")}
      />
      <ReviewSheet open={review} onOpenChange={setReview} />
      <SourceSheet e={source} onClose={() => setSource(null)} />
    </Shell>
  );
}

export function QueueBody({ onReview, onOpen, onOpenRecord, intro = true }: { onReview: () => void; onOpen: (e: Evidence) => void; onOpenRecord: () => void; intro?: boolean }) {
  const s = useScenario();
  const { toast } = useLabUI();
  const [selected, setSelected] = useState<string>("q1");
  const [filter, setFilter] = useState<Filter>("all");
  const [phoneDetail, setPhoneDetail] = useState(false);

  const items = workQueue.filter((q) => !(q.id === "q1" && s.detecting)).filter((q) => filter === "all" || q.assistant);
  const current = items.find((q) => q.id === selected) ?? items[0];

  useEffect(() => {
    if (current?.id === "q1" && !s.detecting) s.reach("open");
  }, [current?.id, s.detecting, s.reach]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement;
      if (t.closest("input,textarea,select,[role=dialog],[cmdk-root]")) return;
      const i = items.findIndex((q) => q.id === current?.id);
      if (e.key === "ArrowDown" || e.key === "j") {
        e.preventDefault();
        setSelected(items[Math.min(items.length - 1, i + 1)].id);
      } else if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        setSelected(items[Math.max(0, i - 1)].id);
      } else if (e.key.toLowerCase() === "r" && current?.id === "q1") onReview();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const pick = (id: string) => {
    setSelected(id);
    setPhoneDetail(true);
  };

  return (
      <div className={cx("queue-page", phoneDetail && "show-detail")}>
        <header className="page-head">
          <div>
            <h1>Work queue</h1>
            <p className="sub">
              {items.length} open · day shift, {NOW.day}
            </p>
          </div>
          <div className="segmented" role="group" aria-label="Filter">
            <button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>
              All items
            </button>
            <button type="button" aria-pressed={filter === "assistant"} onClick={() => setFilter("assistant")}>
              From the Assistant
            </button>
          </div>
        </header>

        {intro && (
          <WhatsNew id="queue">
            New: the Assistant now adds findings to this queue and prepares routine records. They are marked with its symbol and stay drafts until you act.
          </WhatsNew>
        )}

        <div className="split">
          <div className="list-pane">
            <table className="queue">
              <thead>
                <tr>
                  <th scope="col">Priority</th>
                  <th scope="col">Item</th>
                  <th scope="col">From</th>
                  <th scope="col">Due</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {s.detecting && filter === "all" && (
                  <tr className="is-pending">
                    <td />
                    <td colSpan={4}>
                      <span className="checking">
                        <AgentMark size={14} working /> Assistant is checking the latest BR-04 data
                      </span>
                    </td>
                  </tr>
                )}
                {items.map((q) => (
                  <QueueRow key={q.id} q={q} selected={q.id === current?.id} onSelect={() => pick(q.id)} />
                ))}
              </tbody>
            </table>
            <p className="table-foot">Use ↑ ↓ to move through the queue.</p>
          </div>

          <section className="detail-pane" aria-label="Selected item">
            <button type="button" className="crumb phone-only" onClick={() => setPhoneDetail(false)}>
              <RiArrowLeftLine size={14} /> Work queue
            </button>
            {current?.id === "q1" ? (
              <FindingDetail onReview={onReview} onOpen={onOpen} onOpenRecord={onOpenRecord} onSnooze={() => toast("Snoozed until 13:00. The Assistant brings it back sooner if the gap widens.")} />
            ) : current ? (
              <RoutineDetail q={current} />
            ) : null}
          </section>
        </div>
      </div>
  );
}

function QueueRow({ q, selected, onSelect }: { q: QueueItem; selected: boolean; onSelect: () => void }) {
  const s = useScenario();
  const sent = q.id === "q1" && s.receipt?.decision === "sent";
  const status = sent ? "Sent to QA" : q.status;
  return (
    <tr aria-selected={selected} className={cx("clickable", q.assistant === "finding" && "is-finding")} onClick={onSelect}>
      <td>
        <span className={cx("prio", `is-${q.priority.toLowerCase()}`)}>{q.priority}</span>
      </td>
      <td>
        <button type="button" className="row-link" onClick={(e) => { e.stopPropagation(); onSelect(); }} aria-current={selected || undefined}>
          {q.title}
        </button>
        <small className="cell-sub">{[q.unit, q.batch].filter(Boolean).join(" · ") || "Site"}</small>
      </td>
      <td>
        {q.source === "Assistant" ? (
          <span className="from-assistant">
            <AgentMark size={13} /> Assistant
          </span>
        ) : (
          <span className="from">
            <SourceRef system={q.source} />
            {q.assistant === "prepared" && (
              <span className="prepared" title="Prepared by the Assistant">
                <AgentMark size={11} />
                <span className="sr-only">Prepared by the Assistant</span>
              </span>
            )}
          </span>
        )}
      </td>
      <td className="num">{q.due}</td>
      <td>
        <span className={cx("pill", sent ? "pill-pos" : status === "New" ? "pill-warn" : status === "Ready" ? "pill-neutral" : "pill-plain")}>{status}</span>
      </td>
    </tr>
  );
}

function FindingDetail({ onReview, onOpen, onOpenRecord, onSnooze }: { onReview: () => void; onOpen: (e: Evidence) => void; onOpenRecord: () => void; onSnooze: () => void }) {
  const s = useScenario();
  const { at, value, mean, gap, assayPosted } = useTiterSeries();
  const list = useEvidence();
  const n = counts(list);
  const sent = s.receipt?.decision === "sent";
  return (
    <>
      <header className="detail-head">
        <h2>Titer below reference range</h2>
        <p className="sub">
          BR-04 · Batch F-2408 · found by the Assistant at {NOW.label}
        </p>
      </header>
      {assayPosted && <p className="notice-line">The 60 h result posted at 20:14. The gap is holding at {gap} %, not widening.</p>}
      <p className="detail-text">
        Titer is {gap} % below the mean of 6 prior R7 batches at {at} h. Dissolved oxygen fell when agitation reached its limit, after heavy antifoam use. Likely reduced oxygen transfer, <b>not confirmed</b>: off-gas data for 31–44 h is missing.
      </p>
      <dl className="detail-figs">
        <div>
          <dt>Titer at {at} h</dt>
          <dd className="num">
            {value.toFixed(2)} <small>g/L</small>
          </dd>
        </div>
        <div>
          <dt>Reference mean</dt>
          <dd className="num">
            {mean.toFixed(2)} <small>g/L</small>
          </dd>
        </div>
        <div>
          <dt>Difference</dt>
          <dd className="num">
            {"\u2212"}
            {gap} <small>%</small>
          </dd>
        </div>
      </dl>
      <div className="detail-chart">
        <TiterChart height={200} />
      </div>

      <h3 className="detail-h">
        Evidence <Balance {...n} />
      </h3>
      <ul className="rows detail-ev">
        {list.slice(0, 6).map((e) => (
          <li key={e.id}>
            <button type="button" className="row ev-line" onClick={() => onOpen(e)}>
              <StanceMark stance={e.stance} />
              <span>{e.claim}</span>
              <SourceRef system={e.system} />
            </button>
          </li>
        ))}
      </ul>

      <h3 className="detail-h">Proposed next step</h3>
      <div className="detail-plan">
        <p>
          <b>{action.title}.</b> {action.steps.length} tasks, drafted as a QMS deviation. No setpoint changes.
        </p>
        <div className="detail-actions">
          <Button variant="primary" onClick={onReview} kbd="R">
            {s.receipt ? "View receipt" : "Review plan"}
          </Button>
          <Button variant="secondary" onClick={onOpenRecord} icon={<RiArrowRightUpLine size={15} />}>
            Open batch record
          </Button>
          {!sent && (
            <Button variant="ghost" onClick={onSnooze} icon={<RiTimeLine size={15} />}>
              Snooze
            </Button>
          )}
        </div>
      </div>
    </>
  );
}

const routine: Record<string, { text: string; system: string }> = {
  q2: { text: "The Assistant filled the harvest record from the executed batch steps and the historian. 2 fields need your entry: harvest volume and operator verification.", system: "MES" },
  q3: { text: "Three samples are in testing. Results are expected at 11:30. Nothing to do until then.", system: "LIMS" },
  q4: { text: "The Assistant checked 3 cleaning records against the procedure. No discrepancies found. Ready for your signature in MES.", system: "MES" },
  q5: { text: "Checklist for the 14:00 seed transfer into BR-06. Not started.", system: "MES" },
  q6: { text: "Effectiveness check for the media hold-time change. No relevant batches since 14 Oct.", system: "QMS" },
};

function RoutineDetail({ q }: { q: QueueItem }) {
  const r = routine[q.id];
  return (
    <>
      <header className="detail-head">
        <h2>{q.title}</h2>
        <p className="sub">
          {[q.unit, q.batch].filter(Boolean).join(" · ") || "Site"} · due {q.due}
        </p>
      </header>
      {q.assistant === "prepared" && (
        <p className="prepared-line">
          <AgentMark size={13} /> Prepared by the Assistant. Check it in {r.system} as usual.
        </p>
      )}
      <p className="detail-text">{r.text}</p>
      <div className="detail-actions">
        <OpenInSource system={r.system} />
      </div>
    </>
  );
}
