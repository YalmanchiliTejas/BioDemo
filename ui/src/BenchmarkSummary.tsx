import { Card } from "@tremor/react";
import snapshot from "./data/benchmarks.json";

type Run = (typeof snapshot.runs)[number];
const runs = snapshot.runs as Run[];
const final = (r: Run) => r.investigation_status === "complete";
const verified = (r: Run) => ["automatically_verified", "verified_with_human_review"].includes(r.source_verification_status);

function median(values: number[]) {
  const s = [...values].sort((a, b) => a - b), m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

export default function BenchmarkSummary() {
  const cho = runs.filter(r => r.benchmark_id === "cho"), fre = runs.filter(r => r.benchmark_id !== "cho");
  const finals = runs.filter(final);
  const passed = finals.filter(verified);
  const pending = finals.filter(r => r.source_verification_status === "human_review_pending");
  const partial = runs.filter(r => r.execution_status === "completed" && !final(r));
  const failed = runs.filter(r => r.execution_status === "failed");
  const minutes = median(runs.filter(r => r.runtime_seconds != null).map(r => r.runtime_seconds! / 60));
  const budget = Math.round((runs[0]?.budgets?.wall_clock_seconds ?? 1800) / 60);
  const ids = (list: Run[]) => list.map(r => r.case_id).join(", ");

  const legend: [string, string, string][] = [
    ["bg-emerald-500", "Final · source checks passed", "The agent finished, and every number it cited matched the original source cell automatically."],
    ["bg-amber-500", "Final · source review pending", "The agent finished, but some citations point to scanned PDFs, so a person has to look at the page to confirm them."],
    ["bg-orange-500", "Partial report", "The agent returned a report but flagged work it did not finish."],
    ["bg-red-500", "Execution failed", "No report came back, usually because the time budget ran out."],
  ];

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <Card className="lg:col-span-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-emerald-700">Summary</p>
        <p className="mt-3 text-lg leading-relaxed text-gray-800">
          The agent ran <b>{runs.length} investigations</b>: {cho.length} on real CHO bioreactor lab data and {fre.length} on the synthetic Fresenius
          plant scenario, each with a {budget}-minute budget. <b className="text-emerald-700">{finals.length} of {runs.length}</b> ended in a final
          investigation report, with a median run time of <b>{minutes.toFixed(0)} minutes</b>.
        </p>
        <ul className="mt-4 space-y-2 text-sm text-gray-600">
          <li><b className="text-gray-900">{passed.length} reports passed every automatic source check</b> ({ids(passed)}).</li>
          <li><b className="text-gray-900">{pending.length} reports are finished but waiting for a person to check citations in scanned PDFs</b> ({ids(pending)}).</li>
          {partial.length > 0 && <li><b className="text-gray-900">{partial.length} partial</b> ({ids(partial)}): a report came back with open work.</li>}
          {failed.length > 0 && <li><b className="text-gray-900">{failed.length} failed</b> ({ids(failed)}): no report within the time budget.</li>}
        </ul>
      </Card>
      <Card className="lg:col-span-2">
        <p className="text-xs font-semibold uppercase tracking-widest text-emerald-700">How to read this benchmark</p>
        <ul className="mt-3 space-y-3">
          {legend.map(([dot, label, text]) => (
            <li key={label} className="flex gap-3 text-sm">
              <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${dot}`} />
              <span><b className="text-gray-900">{label}.</b> <span className="text-gray-600">{text}</span></span>
            </li>
          ))}
        </ul>
        <div className="mt-4 space-y-1.5 border-t border-gray-100 pt-3 text-xs text-gray-500">
          <p>Each attempt counts once; none are filtered out.</p>
          <p>Times are the agent's machine minutes, not people's working hours.</p>
          <p>Still to come: independent expert review of the findings, and a side-by-side against engineers doing the same task.</p>
        </div>
      </Card>
    </div>
  );
}
