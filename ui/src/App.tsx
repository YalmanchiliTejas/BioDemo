import {
  AreaChart, Badge, BadgeDelta, Callout, Card, Divider, Flex, Grid, LineChart, List, ListItem,
  Tab, TabGroup, TabList, TabPanel, TabPanels, Table, TableBody, TableCell, TableHead,
  TableHeaderCell, TableRow, Text, Title, Tracker, type Color,
} from "@tremor/react";
import { RiAlertLine, RiShieldCheckLine } from "@remixicon/react";
import raw from "./data/fresenius.json";
import DivergenceTimeline from "./DivergenceTimeline";
import ProjectedSavings from "./ProjectedSavings";
import BenchmarkResults from "./BenchmarkResults";

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
const DAY = 864e5;
const fmt = (t: string, year = false) => new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric", ...(year ? { year: "numeric" } : {}), timeZone: "UTC" });
const lotName = (id: string) => `Lot ${id.replace(/^\D+/, "")}`;
const days = (a: string, b: string) => Math.max(0, Math.round((Date.parse(b) - Date.parse(a)) / DAY));

// Flagged-lot days in the market before anyone acted across batches.
const unaddressed = (projected: boolean) => view.lots.reduce((sum, lot) => {
  const actedAt = projected ? view.escalation.time : view.recognized.time;
  if (projected && lot.projected === "held") return sum;
  return sum + (lot.shipped < actedAt ? days(lot.shipped, actedAt) : 0);
}, 0);

function KpiCards() {
  const cards = [...view.kpis, {
    label: "Flagged-lot days in market, unaddressed", before: unaddressed(false), after: unaddressed(true), kind: "count",
    before_note: "until the complaint", after_note: "until the agent escalates", delta: `${unaddressed(false) - unaddressed(true)} fewer lot-days`,
  }];
  const show = (k: Kpi, v: string | number) => (k.kind === "date" ? fmt(String(v), true) : v.toLocaleString());
  return (
    <Grid numItemsSm={2} numItemsLg={5} className="gap-4">
      {cards.map(k => (
        <Card key={k.label} className="flex flex-col gap-3 p-4">
          <Text className="min-h-[2.5rem] font-medium text-tremor-content-strong">{k.label}</Text>
          <div className="grid grid-cols-2 gap-3">
            <div><p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Without agent</p>
              <p className="text-xl font-semibold text-red-700">{show(k, k.before)}</p><p className="text-xs text-gray-500">{k.before_note}</p></div>
            <div><p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">With agent</p>
              <p className="text-xl font-semibold text-emerald-700">{show(k, k.after)}</p><p className="text-xs text-gray-500">{k.after_note}</p></div>
          </div>
          <BadgeDelta deltaType="moderateIncrease" isIncreasePositive size="xs" className="mt-auto self-start">{k.delta}</BadgeDelta>
        </Card>
      ))}
    </Grid>
  );
}

function BatchTracker() {
  const recent = data.batches.filter(b => b.start >= "2024-10-01");
  const tip = (b: Batch, state: string) => `${b.id} · ${fmt(b.start, true)} · bioburden ${b.bioburden ?? "n/a"} · ${state}`;
  const recorded = recent.map(b => {
    const color: Color = b.bioburden_status === "action" ? "red" : b.bioburden_status === "alert" ? "amber" : "emerald";
    return { key: b.id, color, tooltip: tip(b, b.bioburden_status === "action" ? "action-level failure → released & shipped" : "released") };
  });
  const projected = recent.map(b => {
    const color: Color = b.projected === "held" ? "blue" : b.projected === "flagged_shipped" ? "orange" : b.bioburden_status === "alert" ? "amber" : "emerald";
    const state = b.projected === "held" ? "held for QA decision" : b.projected === "flagged_shipped" ? "already shipped → flagged to QA" : "released";
    return { key: b.id, color, tooltip: tip(b, state) };
  });
  const legend: [Color, string][] = [["emerald", "Normal, released"], ["amber", "Alert level, released"], ["red", "Failed upstream, shipped"], ["orange", "Shipped, flagged to QA"], ["blue", "Held for QA decision"]];
  return (
    <Card>
      <Title>Every batch since October 2024</Title>
      <Text>One bar per batch on the line. Hover a bar for details.</Text>
      <div className="mt-6 space-y-5">
        <div><Flex><Text className="font-medium text-tremor-content-strong">Without the agent</Text><Text>{recorded.filter(r => r.color === "red").length} failed lots shipped</Text></Flex>
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
    batch: `${fmt(b.start)} ’${b.start.slice(2, 4)}`, "Upstream bioburden": b.bioburden, "Action limit": 1, "Alert limit": 0.7,
  }));
  return (
    <Card>
      <Title>Upstream bioburden, all 100 batches</Title>
      <Text>Normalized to the action limit (1.0). The Dec–Mar cluster of three failures is the pattern. A single failure in Feb 2024 had no follow-up failure for nine months.</Text>
      <LineChart className="mt-4 h-72" data={rows} index="batch" categories={["Upstream bioburden", "Action limit", "Alert limit"]}
        colors={["emerald", "red", "amber"]} valueFormatter={v => `${v.toFixed(2)}×`} yAxisWidth={44} curveType="linear" connectNulls />
    </Card>
  );
}

function MarketExposure() {
  const months: { month: string; "Without agent": number; "With agent": number }[] = [];
  for (let m = 0; m < 13; m++) {
    const t = new Date(Date.UTC(2024, 11 + m, 15)).toISOString();
    months.push({
      month: new Date(t).toLocaleDateString("en-US", { month: "short", year: "2-digit", timeZone: "UTC" }),
      "Without agent": view.lots.filter(l => l.shipped <= t).length,
      "With agent": view.lots.filter(l => l.projected !== "held" && l.shipped <= t && t < view.escalation.time).length,
    });
  }
  return (
    <Card>
      <Title>Failed lots sitting in the market, unaddressed</Title>
      <Text>Count of flagged lots shipped with no cross-batch action yet, by month.</Text>
      <AreaChart className="mt-4 h-72" data={months} index="month" categories={["Without agent", "With agent"]} colors={["red", "emerald"]}
        allowDecimals={false} yAxisWidth={30} />
    </Card>
  );
}

function LotTable() {
  return (
    <Card>
      <Title>Lot by lot</Title>
      <Table className="mt-4">
        <TableHead><TableRow>
          <TableHeaderCell>Lot</TableHeaderCell><TableHeaderCell>Upstream failure</TableHeaderCell>
          <TableHeaderCell>Without agent</TableHeaderCell><TableHeaderCell>With agent (projected)</TableHeaderCell>
        </TableRow></TableHead>
        <TableBody>{view.lots.map(lot => (
          <TableRow key={lot.batch}>
            <TableCell className="font-medium text-tremor-content-strong">{lotName(lot.batch)}<div className="text-xs text-gray-400">{lot.line}</div></TableCell>
            <TableCell>{lot.excursion.value.toFixed(2)}× limit<div className="text-xs text-gray-400">{fmt(lot.excursion.time, true)}</div></TableCell>
            <TableCell><Badge color="red" icon={RiAlertLine}>Released & shipped</Badge>
              <div className="mt-1 text-xs text-gray-500">Shipped {fmt(lot.shipped)}{lot.complaint ? ` · complaint ${fmt(lot.complaint)}` : ""}</div></TableCell>
            <TableCell>{lot.projected === "held"
              ? <><Badge color="blue" icon={RiShieldCheckLine}>Held before release</Badge><div className="mt-1 text-xs text-gray-500">On hold from {fmt(lot.excursion.time > view.escalation.time ? lot.excursion.time : view.escalation.time)}</div></>
              : <><Badge color="orange">Shipped · flagged to QA</Badge><div className="mt-1 text-xs text-gray-500">Flagged {fmt(view.escalation.time)}, {view.lead_days} days before the complaint</div></>}
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
      <summary className="cursor-pointer text-tremor-title font-medium text-tremor-content-strong">Full event log, step by step</summary>
      <TabGroup className="mt-4">
        <TabList variant="solid"><Tab>Without agent (recorded)</Tab><Tab>With agent (replay)</Tab></TabList>
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
        <p className="text-xs font-semibold uppercase tracking-widest text-emerald-700">Synthetic workflow projection · Famotidine injection · Line A</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-gray-900">A synthetic batch-quality scenario, replayed</h1>
        <Callout title="Projected workflow, not measured benchmark performance" color="amber" className="mt-4">{data.disclosure} No recall prevention, manufacturing intervention or human-effort reduction was measured.</Callout>
        <p className="mt-2 max-w-3xl text-gray-500">Within this simulation, three lots failed an upstream bioburden check. Each passed its final tests and shipped, and the pattern only surfaced
          with a customer complaint on {fmt(view.recognized.time, true)}. With the agent, the second failure on {fmt(view.escalation.time, true)} links the lots
          and escalates to QA — <span className="font-semibold text-emerald-700">{view.lead_days} days earlier</span>.</p>
      </header>
      <KpiCards />
      <ProjectedSavings projection={data.projection} />
      <BatchTracker />
      <Grid numItemsLg={2} className="gap-6"><BioburdenTrend /><MarketExposure /></Grid>
      <DivergenceTimeline recorded={data.recorded_events} agent={data.agent_events} lots={view.lots} forkId="AI-EVT-006" />
      <LotTable />
      <EventFeeds />
      <Divider />
      <Callout title="How to read this projection" color="amber">
        <ul className="list-disc space-y-1 pl-4">{view.assumptions.map(a => <li key={a}>{a}</li>)}</ul>
      </Callout>
    </main>
  );
}

export default function App() {
  return <main className="mx-auto max-w-7xl px-6 py-8">
    <p className="mb-4 text-sm font-semibold tracking-tight text-emerald-800">lotic · Manufacturing AI OS</p>
    <TabGroup defaultIndex={new URLSearchParams(window.location.search).get("tab") === "benchmark" ? 1 : 0}><TabList variant="solid"><Tab>Workflow impact</Tab><Tab>Engineering benchmark runs</Tab></TabList>
      <TabPanels><TabPanel><SyntheticReplay /></TabPanel><TabPanel className="mt-8"><BenchmarkResults /></TabPanel></TabPanels>
    </TabGroup>
  </main>;
}
