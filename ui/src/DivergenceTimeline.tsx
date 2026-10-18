import { useEffect, useMemo, useRef, useState } from "react";
import { Badge, Card, ProgressBar, Text, Title } from "@tremor/react";
import { RiCheckboxCircleFill, RiCloseCircleLine, RiPauseFill, RiPlayFill, RiRefreshLine, RiTimeLine } from "@remixicon/react";

type Event = { id: string; time: string };
type Lot = { batch: string; released: string; shipped: string };
type Props = { recorded: Event[]; agent: Event[]; lots: Lot[]; forkId: string };
type Lane = "trunk" | "recorded" | "agent";
type Tone = "red" | "gray" | "green" | "amber";
type NodeDef = { lane: Lane; time: string; title: string; sub: string; tone: Tone; pos: "up" | "down"; start?: boolean };

const W = 1200, LEFT = 40, RIGHT = 1160, Y = { trunk: 175, recorded: 100, agent: 260 }, AXIS = 345, H = 372;
const CURVE = 40, DURATION = 16000;
// Piecewise time scale: the quiet months between April and October are compressed.
const SEGMENTS: [string, number][] = [["2024-11-22", 0], ["2025-04-22", 0.62], ["2025-10-12", 0.7], ["2025-11-14", 1]];
const toFrac = (t: string) => {
  const v = Date.parse(t);
  for (let i = 1; i < SEGMENTS.length; i++) {
    const [a, fa] = SEGMENTS[i - 1], [b, fb] = SEGMENTS[i];
    if (v <= Date.parse(b)) return fa + (fb - fa) * Math.max(0, (v - Date.parse(a)) / (Date.parse(b) - Date.parse(a)));
  }
  return 1;
};
const fromFrac = (f: number) => {
  for (let i = 1; i < SEGMENTS.length; i++) {
    const [a, fa] = SEGMENTS[i - 1], [b, fb] = SEGMENTS[i];
    if (f <= fb) return new Date(Date.parse(a) + (Date.parse(b) - Date.parse(a)) * (f - fa) / (fb - fa));
  }
  return new Date(SEGMENTS[SEGMENTS.length - 1][0]);
};
const X = (t: string) => LEFT + toFrac(t) * (RIGHT - LEFT);
const fmt = (t: string | Date, year = false) => new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric", ...(year ? { year: "numeric" } : {}), timeZone: "UTC" });
const TONE: Record<Tone, string> = { red: "#dc2626", gray: "#9ca3af", green: "#059669", amber: "#d97706" };

export default function DivergenceTimeline({ recorded, agent, lots, forkId }: Props) {
  const at = (id: string) => [...recorded, ...agent].find(e => e.id === id)?.time ?? "";
  const lot = (id: string) => lots.find(l => l.batch === id)!;
  const fork = at(forkId), xf = X(fork);

  const nodes: NodeDef[] = useMemo(() => [
    { lane: "trunk", time: at("TRAD-EVT-002"), title: "Lot 075 fails upstream", sub: "deviation opened", tone: "red", pos: "up" },
    { lane: "trunk", time: lot("BATCH-075").released, title: "Lot 075 released", sub: `ships ${fmt(lot("BATCH-075").shipped)}`, tone: "gray", pos: "down" },
    { lane: "recorded", time: at("TRAD-EVT-007"), title: "Batch-local assessment", sub: "Lot 084 · broader risk missed", tone: "gray", pos: "up", start: true },
    { lane: "recorded", time: lot("BATCH-084").released, title: "Lot 084 released", sub: `ships ${fmt(lot("BATCH-084").shipped)}`, tone: "red", pos: "down", start: true },
    { lane: "recorded", time: at("TRAD-EVT-009"), title: "Lot 099 fails upstream", sub: "3rd separate deviation", tone: "red", pos: "up" },
    { lane: "recorded", time: lot("BATCH-099").released, title: "Lot 099 released", sub: `ships ${fmt(lot("BATCH-099").shipped)}`, tone: "red", pos: "down" },
    { lane: "recorded", time: at("TRAD-EVT-011"), title: "Customer complaint", sub: "pattern finally surfaces", tone: "amber", pos: "up" },
    { lane: "recorded", time: at("TRAD-EVT-012"), title: "Reserve sample fails", sub: "endotoxin out of spec", tone: "red", pos: "down" },
    { lane: "recorded", time: at("TRAD-EVT-013"), title: "Public recall notice", sub: "FDA posting · Nov 7, 2025", tone: "red", pos: "up" },
    { lane: "agent", time: at("AI-EVT-006"), title: "Lots 075 + 084 linked", sub: "to QA · 084 held, 075 flagged", tone: "green", pos: "up", start: true },
    { lane: "agent", time: at("AI-EVT-009"), title: "Lot 099 held", sub: "linked for cross-batch QA review", tone: "green", pos: "down" },
    { lane: "agent", time: at("AI-EVT-010"), title: "Organism ID added", sub: "reviewed with all 3 lots", tone: "green", pos: "up" },
    { lane: "agent", time: at("AI-EVT-011"), title: "Complaint matches case", sub: "already under review", tone: "green", pos: "down" },
    { lane: "agent", time: at("AI-EVT-012"), title: "Critical escalation", sub: "urgent QA decision", tone: "amber", pos: "up" },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [recorded, agent, lots]);

  const work = [
    { label: "Record the first failure signal", rec: at("TRAD-EVT-002"), ai: at("AI-EVT-002") },
    { label: "Link repeat failures into one case", rec: at("TRAD-EVT-011"), ai: at("AI-EVT-006") },
    { label: "Flag shipped lots for market-action review", rec: at("TRAD-EVT-013"), ai: at("AI-EVT-006") },
    { label: "Hold affected lots before release", rec: null, ai: at("AI-EVT-009") },
    { label: "Escalate for an urgent QA decision", rec: at("TRAD-EVT-012"), ai: at("AI-EVT-012") },
  ];

  const reduced = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // ?p=0.4 opens the timeline at a fixed position (useful for screenshots and links).
  const fixed = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("p") : null;
  const [p, setP] = useState(fixed != null ? Math.min(1, Math.max(0, Number(fixed) || 0)) : reduced ? 1 : 0);
  const [playing, setPlaying] = useState(fixed == null && !reduced);
  const last = useRef<number | null>(null);
  useEffect(() => {
    if (!playing) { last.current = null; return; }
    let frame = 0;
    const tick = (now: number) => {
      const dt = last.current == null ? 0 : now - last.current;
      last.current = now;
      setP(prev => {
        const next = Math.min(1, prev + dt / DURATION);
        if (next >= 1) setPlaying(false);
        return next;
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing]);

  const px = LEFT + p * (RIGHT - LEFT);
  const now = fromFrac(p);
  const nowIso = now.toISOString();
  const placed = nodes.map(n => ({ ...n, x: n.lane === "trunk" ? X(n.time) : Math.max(X(n.time), xf + CURVE), y: Y[n.lane] }));
  const done = (t: string | null) => t != null && t <= nowIso;
  const recDone = work.filter(w => done(w.rec)).length, aiDone = work.filter(w => done(w.ai)).length;
  const latest = (lane: Lane) => [...placed].reverse().find(n => (n.lane === lane || n.lane === "trunk") && n.x <= px + 0.5);

  const branch = (lane: "recorded" | "agent") => `M${xf},${Y.trunk} C${xf + CURVE / 2},${Y.trunk} ${xf + CURVE / 2},${Y[lane]} ${xf + CURVE},${Y[lane]} H${RIGHT}`;
  const months = ["2024-12-01", "2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01", "2025-10-15", "2025-11-01"];
  const play = () => { if (p >= 1) setP(0); setPlaying(v => !v || p >= 1); };

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Title>Assumed workflow divergence · synthetic replay</Title>
          <Text>Scripted baseline vs proposed QA workflow · assumed dates · April–October compressed.</Text>
          <details className="mt-2 text-xs text-gray-500"><summary className="cursor-pointer">Timeline assumptions</summary>The paths show an assumed cross-batch escalation after the second simulated failure on {fmt(fork, true)}. These are scripted tasks, not measured agent completions. Dates are assumed except the public FDA posting date; horizontal distance is not proportional to elapsed time.</details>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={play} className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700">
            {playing ? <RiPauseFill className="h-4 w-4" /> : <RiPlayFill className="h-4 w-4" />}{playing ? "Pause" : p >= 1 ? "Replay" : "Play"}
          </button>
          <button onClick={() => { setP(0); setPlaying(true); }} aria-label="Restart" className="rounded-md border border-gray-200 p-1.5 text-gray-500 hover:bg-gray-50"><RiRefreshLine className="h-4 w-4" /></button>
        </div>
      </div>

      <div data-testid="timeline-frame-summary" className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
        <b>{fmt(now, true)}</b> · projected path <b>{aiDone} of {work.length}</b> scripted tasks · baseline <b>{recDone}</b>. Simulated, not measured productivity.
      </div>

      <div className="mt-4 overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="block w-full min-w-[900px]" role="img" aria-label="Animated timeline of the regular process diverging from the agent-assisted process">
          <defs><clipPath id="progress"><rect x={0} y={0} width={px} height={H} /></clipPath></defs>
          {/* quiet-period band */}
          <rect x={X("2025-04-22")} y={40} width={X("2025-10-12") - X("2025-04-22")} height={AXIS - 40} fill="#f9fafb" />
          <text x={(X("2025-04-22") + X("2025-10-12")) / 2} y={AXIS - 8} textAnchor="middle" className="fill-gray-400 text-[10px]">Compressed time</text>
          {months.map(m => (
            <g key={m}><line x1={X(m)} x2={X(m)} y1={44} y2={AXIS} stroke="#f1f5f9" />
              <text x={X(m) + 3} y={AXIS + 16} className="fill-gray-400 text-[10px]">{new Date(m).toLocaleDateString("en-US", { month: "short", year: m.endsWith("-01-01") || m === months[0] ? "2-digit" : undefined, timeZone: "UTC" })}</text></g>
          ))}
          {/* divergence marker */}
          <line x1={xf} x2={xf} y1={34} y2={AXIS} stroke="#059669" strokeDasharray="4 4" />
          <text x={xf + 6} y={30} className="fill-emerald-700 text-[11px] font-semibold">{fmt(fork, true)} · Lot 084 fails · the paths split</text>
          {/* lane names */}
          <text x={RIGHT} y={Y.recorded - 44} textAnchor="end" className="fill-red-700 text-[12px] font-semibold">Scenario baseline (assumed)</text>
          <text x={RIGHT} y={Y.agent + 58} textAnchor="end" className="fill-emerald-700 text-[12px] font-semibold">With the agent (projected)</text>
          {/* faint full paths */}
          <g fill="none" strokeWidth={3} opacity={0.18}>
            <line x1={LEFT} x2={xf} y1={Y.trunk} y2={Y.trunk} stroke="#6b7280" />
            <path d={branch("recorded")} stroke="#dc2626" />
            <path d={branch("agent")} stroke="#059669" />
          </g>
          {/* progressed paths */}
          <g fill="none" strokeWidth={4} strokeLinecap="round" clipPath="url(#progress)">
            <line x1={LEFT} x2={xf} y1={Y.trunk} y2={Y.trunk} stroke="#6b7280" />
            <path d={branch("recorded")} stroke="#dc2626" />
            <path d={branch("agent")} stroke="#059669" />
          </g>
          {/* nodes */}
          {placed.map(n => {
            const shown = n.x <= px + 0.5, up = n.pos === "up";
            return (
              <g key={n.title} className="transition-all duration-500 ease-out" style={{ opacity: shown ? 1 : 0, transform: `translateY(${shown ? 0 : 6}px)` }}>
                <circle cx={n.x} cy={n.y} r={7} fill="white" stroke={TONE[n.tone]} strokeWidth={3} />
                <circle cx={n.x} cy={n.y} r={3} fill={TONE[n.tone]} />
                <text x={n.start ? n.x - 6 : n.x} y={up ? n.y - 27 : n.y + 25} textAnchor={n.start ? "start" : "middle"} className="fill-gray-900 text-[11px] font-semibold">{n.title}</text>
                <text x={n.start ? n.x - 6 : n.x} y={up ? n.y - 14 : n.y + 38} textAnchor={n.start ? "start" : "middle"} className="fill-gray-500 text-[10px]">{fmt(n.time)} · {n.sub}</text>
              </g>
            );
          })}
          {/* playhead */}
          {p < 1 && <g>
            <line x1={px} x2={px} y1={40} y2={AXIS} stroke="#f59e0b" strokeWidth={2} />
            <rect x={px - 44} y={AXIS + 2} width={88} height={20} rx={10} fill="#f59e0b" />
            <text x={px} y={AXIS + 16} textAnchor="middle" className="fill-white text-[11px] font-semibold">{fmt(now, true)}</text>
          </g>}
        </svg>
      </div>

      <input type="range" min={0} max={1000} value={Math.round(p * 1000)} aria-label="Scrub timeline"
        onChange={e => { setPlaying(false); setP(Number(e.target.value) / 1000); }} className="mt-2 w-full accent-emerald-600" />

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {([["Scenario baseline", "rec", recDone, "red", "recorded"], ["Projected assistance", "ai", aiDone, "emerald", "agent"]] as const).map(([name, key, count, color, lane]) => {
          const current = latest(lane);
          return (
            <div key={key} className={`rounded-lg border p-4 ${key === "ai" ? "border-emerald-200 bg-emerald-50/40" : "border-red-100 bg-red-50/30"}`}>
              <div className="flex items-center justify-between"><p className="text-sm font-semibold text-gray-900">{name}</p>
                <Badge color={color} size="xs">{count}/{work.length} scripted tasks</Badge></div>
              <ProgressBar value={(count / work.length) * 100} color={color} className="mt-3" />
              <p className="mt-3 min-h-[2.5rem] text-xs text-gray-500">{current ? <>Latest: <b className="text-gray-800">{current.title}</b> · {fmt(current.time, true)}</> : "Waiting for the first event…"}</p>
              <ul className="mt-2 space-y-2">{work.map(w => {
                const t = key === "rec" ? w.rec : w.ai, ok = done(t);
                return (
                  <li key={w.label} className="flex items-center gap-2 text-sm">
                    {ok ? <RiCheckboxCircleFill className={`h-4 w-4 shrink-0 ${key === "ai" ? "text-emerald-600" : "text-red-500"}`} />
                      : t ? <RiTimeLine className="h-4 w-4 shrink-0 text-gray-300" /> : <RiCloseCircleLine className="h-4 w-4 shrink-0 text-gray-300" />}
                    <span className={ok ? "text-gray-900" : "text-gray-400"}>{w.label}</span>
                    <span className="ml-auto whitespace-nowrap text-xs text-gray-400">{t ? (ok ? fmt(t, true) : "later in replay") : "not modeled"}</span>
                  </li>);
              })}</ul>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
