import { useEffect, useState } from "react";
import { Badge, Card, Text, Title } from "@tremor/react";
import snapshot from "./data/benchmarks.json";
import PublicationReview, { type ReviewedReport } from "./PublicationReview";

type Report = ReviewedReport & {run_id: string};
const example = snapshot.runs.find(run => run.case_id === "FRE-01");

export default function InvestigationDepth() {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!example) return;
    const controller = new AbortController(); let active = true;
    fetch(example.details_url, {signal:controller.signal}).then(async response => {
      if (!response.ok) throw new Error("Recorded investigation example could not be loaded.");
      const data = await response.json();
      if (data.run_id !== example.run_id || data.output_sha256 !== example.output_sha256) throw new Error("Recorded example does not match the exported benchmark snapshot.");
      if (active) setReport(data);
    }).catch(error => {if (active && error.name !== "AbortError") setError(error.message);});
    return () => {active=false;controller.abort();};
  }, []);
  return <Card data-testid="investigation-depth">
    <Badge color="gray">Recorded synthetic benchmark · {example?.case_id ?? "unavailable"}</Badge>
    <Title className="mt-3">Beyond opening a deviation: investigate the broader risk</Title>
    <Text className="mt-2">The original run compared microbiology, environmental and historian records. Its disputed narratives are not featured as validated findings. The review below separates scoped observations, unverified explanations and proposed QA tasks.</Text>
    {!example && <p className="mt-4 text-sm text-gray-500">No recorded example is available in this exported batch.</p>}
    {example && !report && !error && <p role="status" className="mt-4 text-sm text-gray-500">Loading the recorded investigation example…</p>}
    {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
    {example && report && <>
      <p className="mt-4 text-sm text-gray-700">Recorded outcome: final investigation; source review pending; independent scientific review pending. {example.coverage_reviewed}/{example.coverage_total} screened units reviewed, {example.calculation_count} calculations checked and {example.pending_source_reviews} sources awaiting review. These are execution/source/math measurements, not scientific validation.</p>
      <PublicationReview caseId={example.case_id} report={report} />
      <details className="mt-4 text-xs text-gray-500"><summary className="cursor-pointer">Legacy raw artifact · unreviewed original claims</summary>
        <p className="mt-2">The unchanged report retains earlier synthetic deviation-state assumptions and original recommendations. It has not been rerun or scientifically qualified.</p>
        <a className="mt-2 inline-block font-medium text-emerald-700 underline" href={example.details_url} target="_blank" rel="noreferrer">Inspect legacy raw report and unchanged evidence coordinates ↗</a>
      </details>
    </>}
    <p className="mt-4 text-xs text-gray-500">No matched human or conventional-method comparison establishes that this workflow is better, faster or able to prevent the real recall.</p>
  </Card>;
}
