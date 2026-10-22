import { useEffect, useState } from "react";
import { Badge, BarChart, Callout, Card, Grid, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow, Text, Title } from "@tremor/react";
import snapshot from "./data/benchmarks.json";
import BenchmarkSummary from "./BenchmarkSummary";
import PilotCTA from "./PilotCTA";
import PublicationReview from "./PublicationReview";

type Run = (typeof snapshot.runs)[number];
type Source = { path?: string; sheet?: string; cell?: string; row?: number; column?: string; page?: number; span?: string };
type Fact = { statement: string; evidence_ids?: string[]; classification?: string };
type Check = { observation_id: string; source_ref: Source; value_matches: boolean | null; source_integrity: boolean };
type Trajectory = { source: string; limitation: string; selection: string; series: { label: string; sheet: string; column: string; points: { time_hours: number; value: number }[] }[] };
type Detail = { run_id: string; output_sha256: string | null; assessment: string | null; cross_scope_synthesis: string | null; observed_facts: Fact[]; hypotheses: Fact[]; open_questions: string[]; source_checks: Check[]; diagnostic: string | null; trajectory: Trajectory | null; coverage: {entity_id: string | null}[] };
const runs = snapshot.runs as Run[];
const executionDates = [...new Set(runs.flatMap(run => [run.started_at, run.ended_at].filter(Boolean).map(time => new Date(time!).toISOString().slice(0, 10))))].sort();
const final = (run: Run) => run.investigation_status === "complete";
const verified = (run: Run) => ["automatically_verified", "verified_with_human_review"].includes(run.source_verification_status);
const caseLabel = (run: Run) => run.execution_status === "failed" ? "Execution failed" : !final(run) ? "Partial result — scientific and source review pending" : run.label;
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
  const [loaded, setLoaded] = useState<Detail | null>(null);
  const [loadError, setLoadError] = useState<{id: string; message: string} | null>(null);
  const [experimentChoice, setExperimentChoice] = useState<{run: string; experiment: string} | null>(null);
  // Mask synchronously on selection, before effects run; stale responses cannot
  // be rendered under a new case's metrics or artifact link.
  const detail = loaded?.run_id === selected ? loaded : null;
  const error = loadError?.id === selected ? loadError.message : "";
  const run = runs.find(r => r.run_id === selected);
  useEffect(() => {
    if (!run) return;
    const controller = new AbortController(); let active = true;
    setLoaded(null); setLoadError(null);
    fetch(run.details_url, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error("Recorded case details could not be loaded.");
      const result = await response.json();
      if (result.run_id !== run.run_id || result.output_sha256 !== run.output_sha256) throw new Error("Case data does not match the requested run and output hash.");
      return result;
    }).then(result => { if (active) setLoaded(result); }).catch(error => { if (active && error.name !== "AbortError") setLoadError({id:run.run_id, message:error.message}); });
    return () => { active = false; controller.abort(); };
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

  const experiments = [...new Set((detail?.coverage ?? []).map(unit => unit.entity_id?.match(/EXP\d+/)?.[0]).filter((id): id is string => Boolean(id)))].sort();
  const chartExperiment = detail?.trajectory?.source.match(/EXP\d+/)?.[0];
  const experiment = experimentChoice?.run === selected ? experimentChoice.experiment : chartExperiment ?? experiments[0] ?? "";
  const sourceLine = chartExperiment === experiment ? detail?.trajectory : null;
  const partialStatus = run && !final(run) && run.execution_status !== "failed" ? `Partial report; ${run.numeric_review_items.length} assessment numbers lack source links and ${run.pending_source_reviews ?? "unknown"} source check(s) remain pending.` : null;

  return <div className="space-y-6" data-testid="measured-benchmarks">
    <header>
      <p className="text-xs font-semibold uppercase tracking-widest text-emerald-700">Recorded benchmark batch ID · {snapshot.batch}</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight text-gray-900">Manufacturing data → reviewable investigations</h1>
      <p className="mt-2 text-sm text-gray-600">CHO: authentic lab data · Fresenius: synthetic reconstruction · Independent scientific review pending.</p>
    </header>
    <PilotCTA compact />
    {snapshot.unavailable_records.length > 0 && <Callout title="Some batch records are unavailable" color="red">See the exported summary for missing run records; they have not been counted as successes.</Callout>}
    <Grid numItemsSm={2} numItemsLg={4} className="gap-4">{totals.map(k => <Card key={k.title} className="p-5">
      <Text>{k.title}</Text><p className="mt-2 text-4xl font-semibold text-gray-900">{k.value}</p><Text className="mt-2 text-xs">{k.note}</Text>
    </Card>)}</Grid>
    <Grid numItemsLg={2} className="gap-6">
      <Card><Title>Investigation outcomes</Title><Text>All {runs.length} attempts. Final reports ≠ scientific qualification.</Text>
        <BarChart className="mt-5 h-72" data={outcomes} index="dataset" categories={["Final · source checks passed", "Final · source review pending", "Partial report", "Execution failed"]} colors={["emerald", "amber", "orange", "red"]} stack allowDecimals={false} yAxisWidth={28} />
      </Card>
      <Card><Title>Time per attempt</Title><Text>Recorded machine minutes · 30-minute case deadline.</Text>
        <BarChart className="mt-5 h-72" data={runtime} index="case" categories={["Execution returned", "Execution failed"]} colors={["emerald", "red"]} valueFormatter={v => `${v.toFixed(1)} min`} yAxisWidth={55} />
      </Card>
    </Grid>
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><Title>Inspect a recorded investigation</Title><Text>Observations and hypotheses remain distinct. Select any attempt, including the failed case.</Text></div>
        <label className="flex w-full min-w-0 flex-col gap-2 text-sm text-gray-600 sm:w-auto sm:max-w-[28rem] sm:flex-row sm:items-center">Case <select aria-label="Recorded benchmark case" value={selected} onChange={event => setSelected(event.target.value)} className="min-w-0 w-full rounded-lg border-gray-300 text-sm sm:w-auto">
          {runs.map(r => <option key={r.run_id} value={r.run_id}>{r.case_id} · {caseLabel(r)}</option>)}
        </select></label>
      </div>
      {!detail && !error && <p role="status" className="mt-5 text-sm text-gray-500">Loading {run?.case_id} report and evidence…</p>}
      {error && <p role="alert" className="mt-4 text-red-700">{error}</p>}
      {run && detail && <div data-testid="case-panel" data-run-id={run.run_id}>
        <div className="mt-5 flex flex-wrap gap-2"><Badge color={final(run) ? verified(run) ? "emerald" : "amber" : "red"}>{caseLabel(run)}</Badge><Badge color="gray">Independent review pending</Badge><Badge color="gray">{minutes(run.runtime_seconds)}</Badge></div>
        <p className="mt-3 text-sm text-gray-600">{partialStatus ?? run.disclosure}</p>
        {run.benchmark_id === "fresenius" && <p className="mt-2 text-xs text-gray-500">Legacy synthetic benchmark: the earlier synthetic deviation-state assumptions are not verified Fresenius history and have not been rerun. The revised public narrative leaves real deviation closure dates unknown.</p>}
        <div className="mt-4 grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
          <div><p className="text-gray-400">Reviewed/screened units</p><p className="font-semibold">{run.coverage_reviewed ?? "—"}/{run.coverage_total ?? "—"}</p></div>
          <div><p className="text-gray-400">Automatic source checks</p><p className="font-semibold">{run.source_check_count ? `${run.automatically_verified_sources}/${run.source_check_count}` : "Unavailable"}</p></div>
          <div><p className="text-gray-400">Verified calculations</p><p className="font-semibold">{run.calculation_count ?? "Unavailable"}</p></div>
          <div><p className="text-gray-400">Pending visual checks</p><p className="font-semibold">{run.pending_source_reviews ?? "Unavailable"}</p></div>
        </div>
        <p className="mt-2 text-xs text-gray-500">Coverage units are case-specific and are not comparable across datasets. Counts do not establish critical-signal recall or scientific correctness.</p>
        {experiments.length > 0 && <div className="mt-4 rounded-lg bg-emerald-50 p-4 text-sm text-gray-700">
          <p><b>Investigation scope: {experiments.length} experiments, {new Set(detail.coverage.map(unit => unit.entity_id).filter(Boolean)).size} reactor entities.</b> Explore one experiment below.</p>
          <label className="mt-3 block">Experiment <select aria-label="Investigation experiment" className="ml-2 rounded border-gray-300 text-sm" value={experiment} onChange={event => setExperimentChoice({run:selected, experiment:event.target.value})}>{experiments.map(id => <option key={id}>{id}</option>)}</select></label>
        </div>}
        {detail && <div className="mt-5 space-y-4">
          {sourceLine && <section className="rounded-lg border border-gray-200 p-4"><h3 className="text-sm font-semibold">Reactor divergence · source viability measurements</h3>
            <SourceTrajectoryPlot source={sourceLine} />
            <p className="mt-2 break-words text-xs text-gray-500">{sourceLine.source} · {sourceLine.series.map(s => `${s.sheet} / ${s.column}`).join(" · ")}</p>
            <p className="mt-1 text-xs text-gray-500">{sourceLine.limitation}</p><details className="mt-1 text-xs text-gray-400"><summary className="cursor-pointer">Example selection</summary>{sourceLine.selection}</details>
          </section>}
          {partialStatus && <p className="text-xs text-gray-500">The raw agent assessment is retained in the technical artifact and may describe itself as complete. The evaluated status above takes precedence.</p>}
          {run.execution_status === "failed" && <Callout color="red" title="Runtime failure">Execution ended without a retained final report after {minutes(run.runtime_seconds)}. The recorded runtime exited with an error; wall-clock exhaustion is not established. Diagnostics are retained in the downloadable technical artifact.</Callout>}
          {run.numeric_review_items.length > 0 && <Callout color="amber" title="Numerical review remains open">Unlinked assessment literals: {run.numeric_review_items.map(item => item.literal).join(", ")}. These are not certified numerical claims.</Callout>}
          <PublicationReview caseId={run.case_id} report={detail} experiment={experiment} />
        </div>}
        <details className="mt-5 text-xs text-gray-500"><summary className="cursor-pointer">Legacy raw artifact · contains unreviewed original claims</summary>
          <p className="mt-2">Original agent assertions, including disputed causal/routing wording, are preserved for audit. They are not validated public findings. Publication notes above are separate editorial corrections, not new agent output.</p>
          <a className="mt-2 inline-block font-medium text-emerald-700 underline" href={run.details_url} target="_blank" rel="noreferrer">Download legacy raw case data and unchanged source coordinates ↗</a>
        </details>
      </div>}
    </Card>
    <details className="rounded-lg border border-gray-200 p-4"><summary className="cursor-pointer text-sm font-semibold">How to read the results · methodology, dates and provenance</summary>
      <div className="mt-4 space-y-4"><BenchmarkSummary />
        <p className="text-xs text-gray-500">Execution dates: {executionDates.join(" / ")} (UTC). The batch ID is a local launch label, not an event date. Source-event and simulation dates differ from execution dates. This batch uses the full RLM method only; no matched method comparison is shown. Runtime uses the recorded investigation timer; timestamp differences also include orchestration overhead. No human effort was measured.</p>
        <a className="inline-block text-sm text-emerald-700 underline" href="/?tab=replay">Fresenius public facts and simulation assumptions ↗</a>
      </div>
    </details>
    <Card><Title>All {runs.length} attempts in this batch</Title><Text>Top-level “incomplete” can mean a final investigation is awaiting source review. The dimensions below show the distinction.</Text>
      <Table className="mt-4"><TableHead><TableRow>{["Case", "Investigation", "Source verification", "Time", "Calculations", "Pending visual checks", "Numerical review items"].map(h => <TableHeaderCell key={h}>{h}</TableHeaderCell>)}</TableRow></TableHead>
        <TableBody>{runs.map(r => <TableRow key={r.run_id}>
          <TableCell><button onClick={() => setSelected(r.run_id)} className="font-semibold text-emerald-700 underline">{r.case_id}</button><p className="text-xs text-gray-400">{r.benchmark_id === "cho" ? "Laboratory data" : "Synthetic scenario"}</p></TableCell>
          <TableCell><Badge color={final(r) ? "emerald" : "red"}>{r.execution_status === "failed" ? "Execution failed" : final(r) ? "Final report" : "Partial result"}</Badge></TableCell>
          <TableCell>{verified(r) ? "Checks passed" : r.source_verification_status === "human_review_pending" ? "Visual review pending" : "Unavailable"}</TableCell>
          <TableCell>{minutes(r.runtime_seconds)}</TableCell><TableCell>{r.calculation_count ?? "—"}</TableCell><TableCell>{r.pending_source_reviews ?? "—"}</TableCell><TableCell>{r.execution_status === "failed" ? "Unavailable" : r.numeric_review_items.length}</TableCell>
        </TableRow>)}</TableBody>
      </Table>
    </Card>
    <Callout color="amber" title="What these results establish">
      <p>Recorded investigation execution and automated source/arithmetic checks. Independent scientific qualification, human-effort savings and production improvements have not been demonstrated.</p>
      <details className="mt-2"><summary className="cursor-pointer">Data provenance and measurement limits</summary><ul className="mt-2 list-disc space-y-1 pl-4">{snapshot.disclosures.map(d => <li key={d}>{d}</li>)}</ul></details>
    </Callout>
    <PilotCTA />
    <p className="text-xs text-gray-400">Snapshot exported {new Date(snapshot.exported_at).toISOString().replace("T", " ")} (UTC) · <a className="underline" href="/benchmarks/summary.json">Download measured summary</a>. Source run and output hashes are retained in each case artifact.</p>
  </div>;
}
