import { useEffect, useMemo, useRef, useState } from "react";
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useLocalRuntime,
  type ChatModelAdapter,
  type ThreadMessageLike,
  type ToolCallMessagePartProps,
} from "@assistant-ui/react";
import { RiArrowLeftLine, RiArrowUpLine, RiCheckLine, RiErrorWarningLine, RiFlaskLine, RiInboxLine, RiLineChartLine } from "@remixicon/react";
import { agentSteps, dissolvedO2, agitation, antifoam, events, NOW, type Evidence } from "./scenario";
import { useScenario } from "./state";
import { Shell, type NavId } from "./chrome";
import { TiterChart } from "./charts";
import { SourceSheet } from "./evidence";
import { ReviewSheet } from "./review";
import { BatchHeader, EventsTable, InvestigationForm, LabTable, Tabs, TrendViewer, type PenId } from "./familiar";
import { AgentMark, Button, Kbd, cx } from "./ui";

export type Tab = "summary" | "trends" | "lab" | "events" | "investigation";
export type Act = "trends" | "lab" | "events" | "investigation" | "plan" | "precedent";

const goConcept = (c: string) => window.dispatchEvent(new CustomEvent("lab:go", { detail: c }));
const reduce = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const wait = (ms: number) => new Promise<void>((r) => (reduce() ? r() : setTimeout(r, ms)));
const done = { type: "complete" as const, reason: "stop" as const };

export const replies: Record<Act, { text: string; did: string; prompt: string; chip: string }> = {
  trends: { prompt: "Show DO, agitation and antifoam against the reference", chip: "Compare DO, agitation and antifoam", did: "Opened Trends · 3 pens · reference added", text: "Agitation reaches its 800 rpm limit at 27 h, the same hour DO leaves its 40 % setpoint. Antifoam use climbs after the foam alarm at 22 h. The reference band is from 6 prior R7 batches." },
  lab: { prompt: "When did titer leave the reference range?", chip: "When did titer leave the range?", did: "Opened Lab results", text: "At the 36 h sample: 1.33 g/L against a range of 1.45–1.69 g/L. The 48 h sample is further below. The 60 h sample is due at 20:00." },
  events: { prompt: "Which events line up with the change?", chip: "Which events line up?", did: "Opened Events and alarms", text: "Two: the foam alarm at 22.1 h and the agitation limit alarm at 27 h. Also note the off-gas analyser was offline from 31 to 44 h, so oxygen uptake cannot be checked for that window." },
  investigation: { prompt: "Show me the drafted deviation", chip: "Show the drafted deviation", did: "Opened Investigation", text: "I filled in the deviation form: 3 records support reduced oxygen transfer, 2 contradict it or point elsewhere, 3 are missing. Each section stays a draft until you tick Reviewed." },
  plan: { prompt: "What should we do next?", chip: "What should we do next?", did: "Opened Investigation · proposed actions", text: "Verify before changing anything: a portable DO check at 12:00, the analyser's local logs for 31–44 h, and read access to the airflow tag. No setpoint changes. Press R to review." },
  precedent: { prompt: "Has this happened before?", chip: "Has this happened before?", did: "Opened Investigation · evidence", text: "Once, partly. F-2391 ran at about 30 % DO for 10 h in August and finished with normal titer. Its low-DO period was shorter and shallower, so it weakens the oxygen explanation without ruling it out." },
};
export const order: Act[] = ["trends", "lab", "events", "investigation", "precedent", "plan"];
const intents: [RegExp, Act][] = [
  [/next|what should|plan|action|recommend/i, "plan"],
  [/before|precedent|history|f-?2391|happened/i, "precedent"],
  [/event|alarm|line up|foam/i, "events"],
  [/lab|sample|assay|titer|range|lims/i, "lab"],
  [/deviation|investigat|evidence|cause|why|draft/i, "investigation"],
  [/trend|\bDO\b|oxygen|agitat|antifoam|pen|compare|reference/i, "trends"],
];

export function makeAdapter(onAct: (a: Act) => void): ChatModelAdapter {
  return {
    async *run({ messages }) {
      const text = messages[messages.length - 1].content.map((c) => (c.type === "text" ? c.text : "")).join(" ").trim();
      const act = (Object.keys(replies) as Act[]).find((k) => replies[k].prompt === text) ?? intents.find(([re]) => re.test(text))?.[1];
      if (!act) {
        await wait(250);
        yield { content: [{ type: "text", text: "Only this batch's record is scripted in the prototype. Ask about its trends, lab results, events, the drafted deviation or the next step." }], status: done };
        return;
      }
      const r = replies[act];
      const words = r.text.split(" ");
      for (let i = 5; i < words.length; i += 5) {
        await wait(35);
        yield { content: [{ type: "text", text: words.slice(0, i).join(" ") }] };
      }
      onAct(act);
      yield {
        content: [
          { type: "text", text: r.text },
          { type: "tool-call", toolCallId: `${act}-${Date.now()}`, toolName: "did", args: { label: r.did }, argsText: JSON.stringify({ label: r.did }), result: { ok: true } },
        ],
        status: done,
      };
    },
  };
}

const initial = (embedded: boolean): ThreadMessageLike[] => [
  {
    role: "assistant",
    content: embedded
      ? "You came from the historian trend for BR04.DO.PV. The full batch record is here; ask me to show you anything on it."
      : `I flagged this batch at ${NOW.label}: titer is 18 % below the R7 reference at 48 h. I drafted a deviation under Investigation. Ask me to show you anything on this record.`,
  },
];

const Did = ({ args }: ToolCallMessagePartProps<{ label: string }>) => (
  <p className="did">
    <RiCheckLine size={13} /> {args.label}
  </p>
);

export function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="msg msg-assistant">
      <MessagePrimitive.Parts components={{ Text: ({ text }) => <p>{text}</p>, tools: { by_name: { did: Did } } }} />
    </MessagePrimitive.Root>
  );
}
export function UserMessage() {
  return (
    <MessagePrimitive.Root className="msg msg-user">
      <MessagePrimitive.Parts components={{ Text: ({ text }) => <p>{text}</p> }} />
    </MessagePrimitive.Root>
  );
}

function AssistantPanel({ tab, onAct, embedded }: { tab: Tab; onAct: (a: Act) => void; embedded: boolean }) {
  const s = useScenario();
  const [used, setUsed] = useState<Act[]>([]);
  const actRef = useRef(onAct);
  actRef.current = (a) => {
    setUsed((u) => (u.includes(a) ? u : [...u, a]));
    onAct(a);
  };
  const adapter = useMemo(() => makeAdapter((a) => actRef.current(a)), []);
  const runtime = useLocalRuntime(adapter, { initialMessages: initial(embedded), maxSteps: 1 });
  const next = order.filter((a) => !used.includes(a)).slice(0, 3);
  const tabName = { summary: "Summary", trends: "Trends", lab: "Lab results", events: "Events and alarms", investigation: "Investigation" }[tab];

  return (
    <div className="assistant-inner">
      <header className="assistant-head">
        <AgentMark size={16} working={s.detecting} />
        <div>
          <h2>Assistant</h2>
          <p>Reads Historian, LIMS, MES and QMS. Cannot change records.</p>
        </div>
      </header>
      <p className="assistant-ctx">
        Looking at <b>Batch F-2408 · {tabName}</b>
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
              <p className="assistant-note">Scripted in this prototype. Answers cite the tab they open.</p>
            </div>
          </ThreadPrimitive.Root>
        </AssistantRuntimeProvider>
      )}
    </div>
  );
}

function SummaryTab({ go }: { go: (t: Tab) => void }) {
  const latest = [
    { tag: "BR04.DO.PV", label: "Dissolved oxygen", value: `${dissolvedO2.current[dissolvedO2.current.length - 1]} %`, sp: "SP 40 %", flag: true },
    { tag: "BR04.SIC-110.OUT", label: "Agitation", value: `${agitation.current[agitation.current.length - 1]} rpm`, sp: "HI 800 rpm", flag: true },
    { tag: "BR04.AF.TOT", label: "Antifoam total", value: `${antifoam.current[antifoam.current.length - 1]} mL`, sp: "ref. 120 mL", flag: true },
    { tag: "BR04.TEMP.PV", label: "Temperature", value: "30.0 °C", sp: "SP 30.0 °C" },
    { tag: "BR04.PH.PV", label: "pH", value: "6.80", sp: "SP 6.80" },
  ];
  return (
    <div className="grid">
      <section className="card span-8" aria-labelledby="sum-titer">
        <header className="card-head">
          <h2 id="sum-titer">Titer against the R7 reference</h2>
          <button type="button" className="link" onClick={() => go("lab")}>
            Lab results
          </button>
        </header>
        <TiterChart height={300} title={false} />
      </section>
      <section className="card span-4" aria-labelledby="sum-latest">
        <header className="card-head">
          <h2 id="sum-latest">Current values</h2>
          <span className="meta num">{NOW.label}</span>
        </header>
        <table className="kv">
          <tbody>
            {latest.map((l) => (
              <tr key={l.tag}>
                <th scope="row">
                  {l.label}
                  <small className="cell-sub id">{l.tag}</small>
                </th>
                <td className={cx("n num", l.flag && "is-flag")}>
                  {l.value}
                  <small className="cell-sub">{l.sp}</small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button type="button" className="link" onClick={() => go("trends")}>
          Open in Trends
        </button>
      </section>
      <section className="card span-12" aria-labelledby="sum-events">
        <header className="card-head">
          <h2 id="sum-events">Recent events and alarms</h2>
          <button type="button" className="link" onClick={() => go("events")}>
            View all {events.length}
          </button>
        </header>
        <ul className="rows">
          {events
            .slice(-4)
            .reverse()
            .map((e) => (
              <li key={e.age + e.text} className="row ev-mini">
                <span className="num">{e.age.toFixed(1)} h</span>
                <span className={cx("pill", e.kind === "Alarm" ? "pill-warn" : "pill-plain")}>{e.kind}</span>
                <span>{e.text}</span>
              </li>
            ))}
        </ul>
      </section>
    </div>
  );
}

export function Workspace({ embedded = false, onClose }: { embedded?: boolean; onClose?: () => void }) {
  const s = useScenario();
  const [tab, setTab] = useState<Tab>(embedded ? "trends" : "summary");
  const [penSel, setPenSel] = useState<PenId[]>(embedded ? ["do", "ag", "af"] : ["do"]);
  const [reference, setReference] = useState(embedded);
  const [assistant, setAssistant] = useState(true);
  const [review, setReview] = useState(false);
  const [source, setSource] = useState<Evidence | null>(null);

  useEffect(() => {
    if (!s.detecting) s.reach("open");
  }, [s.detecting, s.reach]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement;
      if (t.closest("input,textarea,select,[role=dialog],[cmdk-root]")) return;
      if (e.key.toLowerCase() === "r" && !s.detecting) setReview(true);
      else if (e.key === "Escape" && embedded) onClose?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const scrollTo = (sel: string) =>
    setTimeout(() => document.querySelector(sel)?.scrollIntoView({ behavior: reduce() ? "auto" : "smooth", block: "start" }), 80);

  const onAct = (a: Act) => {
    if (a === "trends") {
      setPenSel(["do", "ag", "af"]);
      setReference(true);
      setTab("trends");
    } else if (a === "lab") setTab("lab");
    else if (a === "events") setTab("events");
    else {
      setTab("investigation");
      if (a === "plan") scrollTo("#action-h");
      if (a === "precedent") scrollTo("#f-ev");
    }
  };

  const navigate = (id: NavId) => {
    if (id === "queue") return embedded ? onClose?.() : goConcept("a");
    if (id === "trends") setTab("trends");
    else if (id === "lab") setTab("lab");
    else if (id === "events") setTab("events");
    else if (id === "deviations") setTab("investigation");
    else setTab("summary");
  };
  const navCurrent: NavId = tab === "trends" ? "trends" : tab === "lab" ? "lab" : tab === "events" ? "events" : tab === "investigation" ? "deviations" : "batches";

  const open = (e: Evidence) => {
    setSource(e);
    s.reach("inspect");
  };

  return (
    <Shell
      current={navCurrent}
      title="Batch F-2408"
      onNavigate={navigate}
      assistantOpen={assistant}
      onAssistant={() => setAssistant((v) => !v)}
      assistant={<AssistantPanel tab={tab} onAct={onAct} embedded={embedded} />}
      commands={[
        { id: "queue", group: "Work queue", label: "Work queue", icon: <RiInboxLine size={16} />, run: () => navigate("queue") },
        { id: "trends", group: "Batch F-2408", label: "Trends · DO, agitation, antifoam", icon: <RiLineChartLine size={16} />, run: () => onAct("trends") },
        { id: "lab", group: "Batch F-2408", label: "Lab results", icon: <RiFlaskLine size={16} />, run: () => setTab("lab") },
        { id: "events", group: "Batch F-2408", label: "Events and alarms", icon: <RiErrorWarningLine size={16} />, run: () => setTab("events") },
      ]}
    >
      <div className="record-page">
        {embedded && (
          <button type="button" className="crumb" onClick={onClose}>
            <RiArrowLeftLine size={14} /> Back to the historian <Kbd>Esc</Kbd>
          </button>
        )}
        <RecordBody tab={tab} setTab={setTab} penSel={penSel} setPenSel={setPenSel} reference={reference} setReference={setReference} onReview={() => setReview(true)} onOpen={open} />
      </div>
      <ReviewSheet open={review} onOpenChange={setReview} />
      <SourceSheet e={source} onClose={() => setSource(null)} />
    </Shell>
  );
}

export function RecordBody({
  tab,
  setTab,
  penSel,
  setPenSel,
  reference,
  setReference,
  onReview,
  onOpen,
}: {
  tab: Tab;
  setTab: (t: Tab) => void;
  penSel: PenId[];
  setPenSel: (p: PenId[]) => void;
  reference: boolean;
  setReference: (v: boolean) => void;
  onReview: () => void;
  onOpen: (e: Evidence) => void;
}) {
  const s = useScenario();
  const setReview = (v: boolean) => {
    if (v) onReview();
  };
  const open = onOpen;
  return (
    <>
        <BatchHeader
          actions={
            <Button variant="primary" onClick={() => setReview(true)} kbd="R" disabled={s.detecting}>
              {s.receipt ? "View receipt" : "Review plan"}
            </Button>
          }
        />
        <Tabs<Tab>
          value={tab}
          onChange={setTab}
          tabs={[
            { id: "summary", label: "Summary" },
            { id: "trends", label: "Trends" },
            { id: "lab", label: "Lab results" },
            { id: "events", label: "Events and alarms" },
            { id: "investigation", label: "Investigation", badge: s.detecting ? undefined : <span className="tab-badge"><AgentMark size={11} /> Draft</span> },
          ]}
        />
        <div className="tab-panel" role="tabpanel">
          {tab === "summary" && <SummaryTab go={setTab} />}
          {tab === "trends" && <TrendViewer selected={penSel} onSelected={setPenSel} reference={reference} onReference={setReference} />}
          {tab === "lab" && <LabTable />}
          {tab === "events" && <EventsTable />}
          {tab === "investigation" &&
            (s.detecting ? <p className="empty">The Assistant is still reading the batch data.</p> : <InvestigationForm onOpen={open} onReview={() => setReview(true)} />)}
        </div>
    </>
  );
}

export default function ConceptB() {
  return <Workspace />;
}
