import {
  BarChart, Badge, BadgeDelta, Callout, Card, Divider, Flex, Grid, LineChart, List, ListItem,
  Tab, TabGroup, TabList, TabPanel, TabPanels, Table, TableBody, TableCell, TableHead,
  TableHeaderCell, TableRow, Text, Title, Tracker, type Color,
} from "@tremor/react";
import { RiAlertLine, RiShieldCheckLine } from "@remixicon/react";
import raw from "./data/fresenius.json";
import DivergenceTimeline from "./DivergenceTimeline";
import ProjectedSavings from "./ProjectedSavings";
import BenchmarkResults from "./BenchmarkResults";
import FreseniusContext from "./FreseniusContext";
import PilotCTA from "./PilotCTA";
import InvestigationDepth from "./InvestigationDepth";
import { elapsedDays, FDA_RECALL_URL, lotDays, unaddressedCount } from "./presentation.mjs";

type Lot = { batch: string; line: string; excursion: { id: string; time: string; value: number }; released: string; shipped: string; complaint: string | null; projected: string };
type Batch = { id: string; line: string; start: string; released: string; shipped: string; bioburden: number | null; bioburden_status: string; flagged: boolean; projected: string };
type Event = { id: string; time: string; kind: string; title: string; severity: string; detail: string };
type Kpi = { label: string; before: string | number; after: string | number; before_note: string; after_note: string; delta: string; kind: string };

const data = raw as unknown as {
  disclosure: string;
  projection: { hours: { metric: string; Today: number; "With agent": number }[]; assumptions: string };
  plant_view: { escalation: { time: string; batches: string[] }; recognized: { time: string }; recall: { time: string } | null; lead_days: number; lots: Lot[]; kpis: Kpi[]; assumptions: string[] };
  batches: Batch[]; recorded_events: Event[]; agent_events: Event[];
};
const view = data.plant_view;
const fmt = (t: string, year = false) => new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric", ...(year ? { year: "numeric" } : {}), timeZone: "UTC" });
const lotName = (id: string) => `Lot ${id.replace(/^\D+/, "")}`;
const leadDays = Math.round(elapsedDays(view.escalation.time, view.recognized.time));
const unaddressed = (projected: boolean) => lotDays(view.lots, projected ? view.escalation.time : view.recognized.time, projected);

function KpiCards() {
  const cards = [...view.kpis.map(k => k.kind === "date" ? { ...k, delta: `About ${leadDays} days in simulation` } : k), {
    label: "Flagged-lot days in market, unaddressed", before: unaddressed(false), after: unaddressed(true), kind: "count",
    before_note: "until assumed complaint time", after_note: "until assumed escalation time", delta: `${(unaddressed(false) - unaddressed(true)).toFixed(1)} fewer modeled lot-days`,
  }];
  const show = (k: Kpi, v: string | number) => (k.kind === "date" ? fmt(String(v), true) : typeof v === "number" ? k.label.startsWith("Flagged-lot days") ? v.toFixed(1) : Math.round(v).toLocaleString() : v);
  return (
    <Grid numItemsSm={2} numItemsLg={5} className="gap-4">
      {cards.map(k => (
        <Card key={k.label} className="flex flex-col gap-3 p-4">
          <Text className="min-h-[2.5rem] font-medium text-tremor-content-strong">{k.label}</Text>
          <div className="grid grid-cols-2 gap-3">
            <div><p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Baseline</p>
              <p className="text-xl font-semibold text-red-700">{show(k, k.before)}</p></div>
            <div><p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Assumed QA</p>
              <p className="text-xl font-semibold text-emerald-700">{show(k, k.after)}</p></div>
          </div>
          <BadgeDelta deltaType="moderateIncrease" isIncreasePositive size="xs" className="mt-auto self-start">{k.delta}</BadgeDelta>
          <details className="text-xs text-gray-500"><summary className="cursor-pointer">Assumptions</summary><p className="mt-1">Baseline: {k.before_note}. Assumed QA: {k.after_note}.</p></details>
        </Card>
      ))}
      <details className="col-span-full text-xs text-gray-500"><summary className="cursor-pointer">Date-counting methodology · modeled outcomes</summary><p className="mt-1">Elapsed UTC hours ÷ 24; shipment-to-escalation intervals exclude the endpoint, with no inclusive day counting. Sum exact lot-day intervals before rounding totals. The lead time rounds 288.86 elapsed days to about 289; all modeled outcomes depend on assumed event times.</p></details>
    </Grid>
  );
}

function BatchTracker() {
  const recent = data.batches.filter(b => b.start >= "2024-10-01");
  const tip = (b: Batch, state: string) => `${b.id} · ${fmt(b.start, true)} · bioburden ${b.bioburden ?? "n/a"} · ${state}`;
  const recorded = recent.map(b => {
    const color: Color = b.bioburden == null ? "gray" : b.bioburden_status === "action" ? "red" : b.bioburden_status === "alert" ? "amber" : "emerald";
    return { key: b.id, color, tooltip: tip(b, b.bioburden_status === "action" ? "action-level failure → released & shipped" : "released") };
  });
  const projected = recent.map(b => {
    const color: Color = b.projected === "held" ? "blue" : b.projected === "flagged_shipped" ? "orange" : b.bioburden == null ? "gray" : b.bioburden_status === "alert" ? "amber" : "emerald";
    const state = b.projected === "held" ? "held for QA decision" : b.projected === "flagged_shipped" ? "already shipped → flagged to QA" : "released";
    return { key: b.id, color, tooltip: tip(b, state) };
  });
  const legend: [Color, string][] = [["emerald", "Normal, released"], ["amber", "Alert level, released"], ["gray", "Measurement missing"], ["red", "Failed upstream, shipped"], ["orange", "Shipped, flagged to QA"], ["blue", "Held for QA decision"]];
  return (
    <Card>
      <Title>Synthetic batches since October 2024</Title>
      <Text>{recent.length} simulated batches across all three lines, October 2024–March 2025; this is a subset of the February 2024–March 2025 population plotted below. Dates and dispositions are scenario assumptions. Hover for details.</Text>
      <div className="mt-6 space-y-5">
        <div><Flex><Text className="font-medium text-tremor-content-strong">Scenario baseline</Text><Text>{recorded.filter(r => r.color === "red").length} upstream failures shipped in simulation</Text></Flex>
          <Tracker data={recorded} className="mt-2 h-10" /></div>
        <div><Flex><Text className="font-medium text-tremor-content-strong">With the agent (projected)</Text><Text>{projected.filter(r => r.color === "blue").length} held · {projected.filter(r => r.color === "orange").length} flagged after shipping</Text></Flex>
          <Tracker data={projected} className="mt-2 h-10" /></div>
      </div>
      <Flex justifyContent="start" className="mt-4 flex-wrap gap-4">
        {legend.map(([c, l]) => <span key={l} className="flex items-center gap-2 text-xs text-gray-500"><span className={`h-2.5 w-2.5 rounded-sm bg-${c}-500`} />{l}</span>)}
      </Flex>
    </Card>
  );
}

function BioburdenTrend() {
  const rows = data.batches.filter(b => b.bioburden != null).map(b => ({
    batch: `${b.id} · ${fmt(b.start, true)}`, "Upstream bioburden": b.bioburden, "Action limit": 1, "Alert limit": 0.7,
  }));
  return (
    <Card>
      <Title>Synthetic upstream bioburden · {rows.length}/{data.batches.length} values available</Title>
      <Text>February 2024–March 2025 across all three lines; {data.batches.length - rows.length} missing value omitted. Limits and dates are simulation assumptions. Batches have equal horizontal spacing; this is not an elapsed-time axis.</Text>
      <LineChart className="mt-4 h-72" data={rows} index="batch" categories={["Upstream bioburden", "Action limit", "Alert limit"]}
        colors={["emerald", "red", "amber"]} valueFormatter={v => `${v.toFixed(2)}×`} yAxisWidth={44} curveType="linear" />
    </Card>
  );
}

function MarketExposure() {
  const months: { month: string; "Without agent": number; "With agent": number }[] = [];
  for (let m = 0; m < 13; m++) {
    const t = new Date(Date.UTC(2024, 11 + m, 15)).toISOString();
    months.push({
      month: new Date(t).toLocaleDateString("en-US", { month: "short", year: "2-digit", timeZone: "UTC" }),
      "Without agent": unaddressedCount(view.lots, t, view.recognized.time, false),
      "With agent": unaddressedCount(view.lots, t, view.escalation.time, true),
    });
  }
  return (
    <Card>
      <Title>Simulated shipped lots awaiting cross-batch escalation</Title>
      <Text>Snapshot on the 15th of each month. A lot stops counting at the assumed escalation time; this does not mean it was recovered or removed from the market. The brief January 2–4 exposure is between snapshots.</Text>
      <BarChart className="mt-4 h-72" data={months} index="month" categories={["Without agent", "With agent"]} colors={["red", "emerald"]}
        allowDecimals={false} yAxisWidth={30} />
    </Card>
  );
}

function LotTable() {
  return (
    <Card>
      <Title>Simulated lot dispositions</Title>
      <Text>Benchmark aliases 075/084/099 are not public lot numbers. Manufacturing, test, release and complaint times are assumed. First-ship calendar dates follow the public recall notice; time of day is assumed.</Text>
      <Table className="mt-4">
        <TableHead><TableRow>
          <TableHeaderCell>Lot</TableHeaderCell><TableHeaderCell>Upstream failure</TableHeaderCell>
          <TableHeaderCell>Scenario baseline</TableHeaderCell><TableHeaderCell>Assumed QA response</TableHeaderCell>
        </TableRow></TableHead>
        <TableBody>{view.lots.map(lot => (
          <TableRow key={lot.batch}>
            <TableCell className="font-medium text-tremor-content-strong">{lotName(lot.batch)}<div className="text-xs text-gray-400">{lot.line}</div></TableCell>
            <TableCell>{lot.excursion.value.toFixed(2)}× limit<div className="text-xs text-gray-400">{fmt(lot.excursion.time, true)}</div></TableCell>
            <TableCell><Badge color="red" icon={RiAlertLine}>Released & shipped</Badge>
              <div className="mt-1 text-xs text-gray-500">Shipped {fmt(lot.shipped)}{lot.complaint ? ` · complaint ${fmt(lot.complaint)}` : ""}</div></TableCell>
            <TableCell>{lot.projected === "held"
              ? <><Badge color="blue" icon={RiShieldCheckLine}>Held before release</Badge><div className="mt-1 text-xs text-gray-500">On hold from {fmt(lot.excursion.time > view.escalation.time ? lot.excursion.time : view.escalation.time)}</div></>
              : <><Badge color="orange">Shipped · flagged to QA</Badge><div className="mt-1 text-xs text-gray-500">Flagged {fmt(view.escalation.time, true)}, about {leadDays} simulated days before the assumed complaint</div></>}
            </TableCell>
          </TableRow>))}
        </TableBody>
      </Table>
    </Card>
  );
}

const sevColor = (s: string): Color => (s === "critical" ? "red" : s === "high" ? "orange" : s === "medium" ? "amber" : "gray");

function EventFeeds() {
  const agent = data.agent_events.filter((e, i, all) => i === 0 || e.title.split(" · ")[0] !== all[i - 1].title.split(" · ")[0] || e.kind !== "assessment");
  return (
    <Card>
      <details>
      <summary className="cursor-pointer text-tremor-title font-medium text-tremor-content-strong">Selected synthetic replay events · assumed timestamps (UTC)</summary>
      <TabGroup className="mt-4">
        <TabList variant="solid"><Tab>Scenario baseline</Tab><Tab>Projected assistance</Tab></TabList>
        <TabPanels>
          {[data.recorded_events, agent].map((events, i) => (
            <TabPanel key={i}><List className="mt-2">{events.map(e => (
              <ListItem key={e.id} className="items-start gap-4 py-3">
                <span className="w-24 shrink-0 text-xs text-gray-400">{fmt(e.time, true)}</span>
                <div className="flex-1"><p className="text-sm font-medium text-tremor-content-strong">{e.title}</p><p className="text-xs text-gray-500">{e.detail.slice(0, 160)}</p></div>
                <Badge color={sevColor(e.severity)} size="xs">{e.severity}</Badge>
              </ListItem>))}</List></TabPanel>
          ))}
        </TabPanels>
      </TabGroup>
      </details>
    </Card>
  );
}

function SyntheticReplay() {
  return (
    <main className="mx-auto max-w-7xl space-y-6 px-6 py-10">
      <header>
        <p className="text-xs font-semibold uppercase tracking-widest text-emerald-700">Synthetic workflow projection · three-line dataset · Line A incident example</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-gray-900">A synthetic batch-quality scenario, replayed</h1>
        <Callout title="Synthetic replay · hypothetical outcomes" color="amber" className="mt-4">Assumed 2024–2025 operating dates and QA actions. No measured recall prevention or Fresenius endorsement. <a href={FDA_RECALL_URL} target="_blank" rel="noreferrer" className="underline">Real recall: November 2025 ↗</a></Callout>
      </header>
      <PilotCTA compact />
      <KpiCards />
      <DivergenceTimeline recorded={data.recorded_events} agent={data.agent_events} lots={view.lots} forkId="AI-EVT-006" />
      <Grid numItemsLg={2} className="gap-6"><BioburdenTrend /><MarketExposure /></Grid>
      <BatchTracker />
      <details className="rounded-lg border border-gray-200 p-4"><summary className="cursor-pointer text-sm font-semibold">Public FDA facts, simulation assumptions and date methodology</summary>
      <div className="mt-4 space-y-5">
        <FreseniusContext />
        <Callout title="Public dates versus assumed simulation dates" color="gray">
          The company recall announcement was November 6, 2025; FDA published it November 7, 2025. <a className="underline" href={FDA_RECALL_URL} target="_blank" rel="noreferrer">Read the public notice</a>.
          The 2024 background batches, December 2024 production event, and January–October 2025 investigation events are assigned simulation dates, not a verified Fresenius operating history. All replay dates use UTC. The modeled lead time depends on these assumptions.
        </Callout>
        <p className="mt-2 max-w-3xl text-gray-500">Within this simulation, three lots failed an upstream bioburden check. Each passed its final tests and shipped, and the pattern only surfaced
          with a customer complaint on {fmt(view.recognized.time, true)}. With the agent, the second failure on {fmt(view.escalation.time, true)} links the lots
          and escalates to QA — <span className="font-semibold text-emerald-700">about {leadDays} days earlier within this assumed scenario</span>. This is a scripted replay, not a measured prediction by the benchmark agent.</p>
      <Card>
        <Title>Release pathway · investigation adequacy, not closure status</Title>
        <p className="mt-3 text-sm text-gray-700">Upstream excursion recorded → batch-local assessment did not adequately assess the broader risk → QA released the batch after passing finished-product tests.</p>
        <p className="mt-2 text-sm font-medium text-gray-700">The public record does not establish the deviation’s closure date. This replay does not assert release before closure.</p>
        <p className="mt-2 text-xs text-gray-500">Public narrative v2. Frozen benchmark inputs and their original reports retain the earlier synthetic open-deviation assumptions. Those are simulation records, not Fresenius history, and have not been rerun against this revised presentation.</p>
      </Card>
      <p className="text-xs text-gray-500">{data.disclosure}</p>
      </div></details>
      <details className="rounded-lg border border-gray-200 p-4"><summary className="cursor-pointer text-sm font-semibold">Inside the recorded investigation · evidence, alternatives and review tasks</summary><div className="mt-4"><InvestigationDepth /></div></details>
      <LotTable />
      <EventFeeds />
      <Divider />
      <Callout title="How to read this projection" color="amber">
        <ul className="list-disc space-y-1 pl-4">{view.assumptions.map(a => <li key={a}>{a}</li>)}</ul>
      </Callout>
      <details className="rounded-lg border border-gray-200 p-4"><summary className="cursor-pointer text-sm font-semibold">Explore an illustrative planning model · savings unmeasured</summary><div className="mt-4"><ProjectedSavings projection={data.projection} /></div></details>
      <PilotCTA />
    </main>
  );
}

export default function App() {
  return <main className="mx-auto max-w-7xl px-6 py-8">
    <p className="mb-4 text-sm font-semibold tracking-tight text-emerald-800">lotic · Manufacturing AI OS</p>
    <TabGroup defaultIndex={new URLSearchParams(window.location.search).get("tab") === "replay" ? 0 : 1}><TabList variant="solid"><Tab>Synthetic workflow replay</Tab><Tab>Measured benchmarks</Tab></TabList>
      <TabPanels><TabPanel><SyntheticReplay /></TabPanel><TabPanel className="mt-8"><BenchmarkResults /></TabPanel></TabPanels>
    </TabGroup>
  </main>;
}
