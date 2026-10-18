import { useEffect, useState } from "react";
import { Badge, BarChart, Callout, Card, Grid, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow, Text, Title } from "@tremor/react";
import snapshot from "./data/benchmarks.json";
import BenchmarkSummary from "./BenchmarkSummary";

type Run = (typeof snapshot.runs)[number];
type Source = { path?: string; sheet?: string; cell?: string; row?: number; column?: string; page?: number; span?: string };
type Fact = { statement: string; evidence_ids?: string[]; classification?: string };
type Check = { observation_id: string; source_ref: Source; value_matches: boolean | null; source_integrity: boolean };
type Trajectory = { source: string; limitation: string; selection: string; series: { label: string; sheet: string; column: string; points: { time_hours: number; value: number }[] }[] };
type Detail = { assessment: string | null; cross_scope_synthesis: string | null; observed_facts: Fact[]; hypotheses: Fact[]; open_questions: string[]; source_checks: Check[]; diagnostic: string | null; trajectory: Trajectory | null };
const runs = snapshot.runs as Run[];
const final = (run: Run) => run.investigation_status === "complete";
const verified = (run: Run) => ["automatically_verified", "verified_with_human_review"].includes(run.source_verification_status);
const minutes = (seconds: number | null) => seconds == null ? "Not measured" : `${(seconds / 60).toFixed(1)} min`;
const coordinates = (source: Source) => [source.path, source.sheet, source.cell ?? (source.row ? `row ${source.row}, ${source.column ?? ""}` : null), source.page ? `page ${source.page}` : null, source.span].filter(Boolean).join(" · ");

function SourceTrajectoryPlot({ source }: { source: Trajectory }) {
  const points = source.series.flatMap(s => s.points);
  const low = Math.min(...points.map(p => p.time_hours)), high = Math.max(...points.map(p => p.time_hours));
  const x = (time: number) => 55 + (time - low) / (high - low || 1) * 705;
  const y = (value: number) => 210 - value / 100 * 170;
  const colors = ["#059669", "#d97706"];
  return <svg viewBox="0 0 800 255" className="mt-3 w-full" role="img" aria-label="Reactor viability against actual source elapsed hours" data-testid="source-viability-chart">
    {[0, 25, 50, 75, 100].map(value => <g key={value}><line x1="55" x2="760" y1={y(value)} y2={y(value)} stroke="#e5e7eb" /><text x="45" y={y(value) + 4} textAnchor="end" fontSize="11" fill="#6b7280">{value}%</text></g>)}
    {[0, 1, 2, 3, 4].map(i => { const time = low + (high - low) * i / 4; return <text key={i} x={x(time)} y="231" textAnchor="middle" fontSize="11" fill="#6b7280">{Number(time.toFixed(2))} h</text>; })}
    <text x="405" y="252" textAnchor="middle" fontSize="11" fill="#6b7280">Original source elapsed time (hours)</text>
    {source.series.map((series, i) => <g key={series.sheet}>
      <text x={610 + i * 75} y="20" fontSize="12" fill={colors[i % colors.length]}>{series.label}</text>
      <polyline fill="none" stroke={colors[i % colors.length]} strokeWidth="2" points={series.points.map(p => `${x(p.time_hours)},${y(p.value)}`).join(" ")} />
      {series.points.map(point => <circle key={point.time_hours} cx={x(point.time_hours)} cy={y(point.value)} r="2.5" fill={colors[i % colors.length]}><title>{series.sheet} · {point.time_hours} h · {point.value}%</title></circle>)}
    </g>)}
  </svg>;
}

export default function BenchmarkResults() {
  const [selected, setSelected] = useState(runs.find(r => r.case_id === "CHO-04")?.run_id ?? runs[0]?.run_id ?? "");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const run = runs.find(r => r.run_id === selected);
  useEffect(() => {
    if (!run) return;
    const controller = new AbortController(); setDetail(null); setError("");
    fetch(run.details_url, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error("Recorded case details could not be loaded.");
      return response.json();
    }).then(setDetail).catch(error => { if (error.name !== "AbortError") setError(error.message); });
    return () => controller.abort();
  }, [selected]);

  const outcomes = ["cho", "fresenius"].map(dataset => {
    const cohort = runs.filter(r => r.benchmark_id === dataset);
    return { dataset: dataset === "cho" ? "CHO · laboratory" : "Fresenius · synthetic",
      "Final · source checks passed": cohort.filter(r => final(r) && verified(r)).length,
      "Final · source review pending": cohort.filter(r => final(r) && r.source_verification_status === "human_review_pending").length,
      "Partial report": cohort.filter(r => r.execution_status === "completed" && !final(r)).length,
      "Execution failed": cohort.filter(r => r.execution_status === "failed").length };
  });
  const runtime = runs.map(r => ({ case: r.case_id,
    "Execution returned": r.execution_status === "completed" && r.runtime_seconds != null ? r.runtime_seconds / 60 : 0,
    "Execution failed": r.execution_status === "failed" && r.runtime_seconds != null ? r.runtime_seconds / 60 : 0 }));
  const totals = [
    { value: `${runs.filter(final).length}/${runs.length}`, title: "Final investigations", note: "Includes reports awaiting source review" },
    { value: runs.filter(r => final(r) && verified(r)).length, title: "Source checks passed", note: "Independent scientific review pending" },
    { value: runs.filter(r => final(r) && r.source_verification_status === "human_review_pending").length, title: "Final · source review pending", note: "Scanned-PDF citations need visual review" },
    { value: runs.filter(r => !final(r)).length, title: "Cases needing follow-up", note: "Failures and partial reports included" },
  ];

  const illustrativeFacts = [...(detail?.observed_facts ?? [])].sort((a, b) => {
    const priority = (fact: Fact) => /viability|\bVCD\b|cell density|bioburden|endotoxin/i.test(fact.statement) ? 2 : /growth|lactate|glucose|divergence/i.test(fact.statement) ? 1 : 0;
    return priority(b) - priority(a);
  }).slice(0, 3);
  const sourceLine = detail?.trajectory;

  return <div className="space-y-6" data-testid="measured-benchmarks">
    <header>
      <p className="text-xs font-semibold uppercase tracking-widest text-emerald-700">Recorded benchmark batch · {snapshot.batch}</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight text-gray-900">Manufacturing data → reviewable investigations</h1>
      <p className="mt-2 max-w-3xl text-gray-500">Actual CHO and Fresenius benchmark runs. Every attempt in this batch is shown, including failures and pending checks.</p>
      <p className="mt-3 text-sm text-gray-600">CHO: authentic laboratory measurements. Fresenius: synthetic FDA-informed reconstruction; no internal company data or endorsement.</p>
    </header>
    <BenchmarkSummary />
    {snapshot.unavailable_records.length > 0 && <Callout title="Some batch records are unavailable" color="red">See the exported summary for missing run records; they have not been counted as successes.</Callout>}
    <Grid numItemsSm={2} numItemsLg={4} className="gap-4">{totals.map(k => <Card key={k.title} className="p-5">
      <Text>{k.title}</Text><p className="mt-2 text-4xl font-semibold text-gray-900">{k.value}</p><Text className="mt-2 text-xs">{k.note}</Text>
    </Card>)}</Grid>
    <Grid numItemsLg={2} className="gap-6">
      <Card><Title>Investigation outcomes</Title><Text>Completion and source verification are separate. No scientific qualification is claimed.</Text>
        <BarChart className="mt-5 h-72" data={outcomes} index="dataset" categories={["Final · source checks passed", "Final · source review pending", "Partial report", "Execution failed"]} colors={["emerald", "amber", "orange", "red"]} stack allowDecimals={false} yAxisWidth={28} />
      </Card>
      <Card><Title>Time per attempt</Title><Text>Machine wall time in minutes. The case deadline was 30 minutes; human effort was not measured.</Text>
        <BarChart className="mt-5 h-72" data={runtime} index="case" categories={["Execution returned", "Execution failed"]} colors={["emerald", "red"]} valueFormatter={v => `${v.toFixed(1)} min`} yAxisWidth={55} />
      </Card>
    </Grid>
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><Title>Inspect a recorded investigation</Title><Text>Observations and hypotheses remain distinct. Select any attempt, including the failed case.</Text></div>
        <label className="flex w-full min-w-0 flex-col gap-2 text-sm text-gray-600 sm:w-auto sm:max-w-[28rem] sm:flex-row sm:items-center">Case <select aria-label="Recorded benchmark case" value={selected} onChange={event => setSelected(event.target.value)} className="min-w-0 w-full rounded-lg border-gray-300 text-sm sm:w-auto">
          {runs.map(r => <option key={r.run_id} value={r.run_id}>{r.case_id} · {r.label}</option>)}
        </select></label>
      </div>
      {run && <>
        <div className="mt-5 flex flex-wrap gap-2"><Badge color={final(run) ? verified(run) ? "emerald" : "amber" : "red"}>{run.label}</Badge><Badge color="gray">Independent review pending</Badge><Badge color="gray">{minutes(run.runtime_seconds)}</Badge></div>
        <p className="mt-3 text-sm text-gray-600">{run.disclosure}</p>
        <div className="mt-4 grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
          <div><p className="text-gray-400">Source/entity coverage</p><p className="font-semibold">{run.coverage_reviewed ?? "—"}/{run.coverage_total ?? "—"}</p></div>
          <div><p className="text-gray-400">Automatic source checks</p><p className="font-semibold">{run.source_check_count ? `${run.automatically_verified_sources}/${run.source_check_count}` : "Unavailable"}</p></div>
          <div><p className="text-gray-400">Verified calculations</p><p className="font-semibold">{run.calculation_count ?? "Unavailable"}</p></div>
          <div><p className="text-gray-400">Pending visual checks</p><p className="font-semibold">{run.pending_source_reviews ?? "Unavailable"}</p></div>
        </div>
        {error && <p role="alert" className="mt-4 text-red-700">{error}</p>}
        {detail && <div className="mt-5 space-y-4">
          {sourceLine && <section className="rounded-lg border border-gray-200 p-4"><h3 className="text-sm font-semibold">Reactor divergence · source viability measurements</h3>
            <SourceTrajectoryPlot source={sourceLine} />
            <p className="mt-2 break-words text-xs text-gray-500">{sourceLine.source} · {sourceLine.series.map(s => `${s.sheet} / ${s.column}`).join(" · ")}</p>
            <p className="mt-1 text-xs text-gray-500">{sourceLine.limitation}</p><details className="mt-1 text-xs text-gray-400"><summary className="cursor-pointer">Example selection</summary>{sourceLine.selection}</details>
          </section>}
          {detail.assessment && <details><summary className="cursor-pointer text-sm font-semibold">Investigation assessment</summary><p className="mt-2 whitespace-pre-wrap text-sm text-gray-600">{detail.assessment}</p></details>}
          {detail.diagnostic && !final(run) && <details open><summary className="cursor-pointer text-sm font-semibold text-red-700">Recorded diagnostic</summary><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words text-xs text-gray-600">{detail.diagnostic}</pre></details>}
          {run.numeric_review_items.length > 0 && <Callout color="amber" title="Numerical review remains open">Unlinked assessment literals: {run.numeric_review_items.map(item => item.literal).join(", ")}. These are not certified numerical claims.</Callout>}
          <Grid numItemsLg={2} className="gap-5">
            <section><h3 className="text-sm font-semibold">Recorded observations</h3><p className="mt-1 text-xs text-gray-400">{illustrativeFacts.length} selected examples; complete findings are in the case data.</p><div className="mt-3 space-y-3">{illustrativeFacts.map((fact, i) => <div key={i} className="rounded-lg bg-gray-50 p-3">
              <p className="text-sm text-gray-700">{fact.statement}</p>
              <div className="mt-2 space-y-1">{(fact.evidence_ids ?? []).slice(0, 3).map(id => {
                const check = detail.source_checks.find(c => c.observation_id === id);
                return <p key={id} className="break-words text-xs text-gray-500">{check ? coordinates(check.source_ref) : id}{check?.value_matches === null ? " · review pending" : ""}</p>;
              })}</div>
            </div>)}</div></section>
            <section><h3 className="text-sm font-semibold">Competing explanations · not verified causes</h3><div className="mt-3 space-y-3">{detail.hypotheses.slice(0, 3).map((hypothesis, i) => <p key={i} className="rounded-lg bg-amber-50 p-3 text-sm text-gray-700">{hypothesis.statement}</p>)}</div>
              {detail.hypotheses.some(h => /\bfeed\b/i.test(h.statement)) && <p className="mt-3 text-xs text-gray-500">Feed-log termination alone does not establish physical feed interruption. Delivery records and operating strategy still require review.</p>}
              {detail.open_questions.length > 0 && <details className="mt-3"><summary className="cursor-pointer text-sm font-semibold">Unresolved questions</summary><ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-gray-600">{detail.open_questions.map((q, i) => <li key={i}>{q}</li>)}</ul></details>}
            </section>
          </Grid>
        </div>}
        <a className="mt-5 inline-block text-sm font-medium text-emerald-700 underline" href={run.details_url} target="_blank" rel="noreferrer">Open complete recorded case data and source coordinates ↗</a>
      </>}
    </Card>
    <Card><Title>All {runs.length} attempts in this batch</Title><Text>Top-level “incomplete” can mean a final investigation is awaiting source review. The dimensions below show the distinction.</Text>
      <Table className="mt-4"><TableHead><TableRow>{["Case", "Investigation", "Source verification", "Time", "Calculations", "Pending checks"].map(h => <TableHeaderCell key={h}>{h}</TableHeaderCell>)}</TableRow></TableHead>
        <TableBody>{runs.map(r => <TableRow key={r.run_id}>
          <TableCell><button onClick={() => setSelected(r.run_id)} className="font-semibold text-emerald-700 underline">{r.case_id}</button><p className="text-xs text-gray-400">{r.benchmark_id === "cho" ? "Laboratory data" : "Synthetic scenario"}</p></TableCell>
          <TableCell><Badge color={final(r) ? "emerald" : "red"}>{r.execution_status === "failed" ? "Execution failed" : final(r) ? "Final report" : "Partial report"}</Badge></TableCell>
          <TableCell>{verified(r) ? "Checks passed" : r.source_verification_status === "human_review_pending" ? "Visual review pending" : "Unavailable"}</TableCell>
          <TableCell>{minutes(r.runtime_seconds)}</TableCell><TableCell>{r.calculation_count ?? "—"}</TableCell><TableCell>{r.pending_source_reviews ?? "—"}</TableCell>
        </TableRow>)}</TableBody>
      </Table>
    </Card>
    <Callout color="amber" title="What these results establish">
      <p>Recorded investigation execution and automated source/arithmetic checks. Independent scientific qualification, human-effort savings and production improvements have not been demonstrated.</p>
      <details className="mt-2"><summary className="cursor-pointer">Data provenance and measurement limits</summary><ul className="mt-2 list-disc space-y-1 pl-4">{snapshot.disclosures.map(d => <li key={d}>{d}</li>)}</ul></details>
    </Callout>
    <p className="text-xs text-gray-400">Snapshot exported {new Date(snapshot.exported_at).toLocaleString()} · <a className="underline" href="/benchmarks/summary.json">Download measured summary</a>. Source run and output hashes are retained in each case artifact.</p>
  </div>;
}
