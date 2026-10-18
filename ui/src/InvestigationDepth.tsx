import { useEffect, useState } from "react";
import { Badge, Card, Grid, Text, Title } from "@tremor/react";
import snapshot from "./data/benchmarks.json";

type Fact = { statement: string; evidence_ids: string[] };
type Hypothesis = { statement: string; supporting_evidence_ids: string[]; contradicting_evidence_ids: string[]; tests_or_observations_that_would_discriminate: string[] };
type Check = { observation_id: string; source_integrity: boolean; value_matches: boolean | null; source_ref: {path?: string; sheet?: string; row?: number; column?: string; cell?: string; page?: number; span?: string} };
type Report = { run_id: string; output_sha256: string; observed_facts: Fact[]; hypotheses: Hypothesis[]; next_actions: {action: string; owner: string; requires_human_approval: boolean}[]; source_checks: Check[] };
// An identified example of a recorded run, not a simulated performance score.
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
  const facts = (report?.observed_facts ?? []).filter(fact =>
    /Environmental monitoring sample EM-0100|BATCH-084 had action-level|All four historian events for BATCH-099/.test(fact.statement));
  const hypotheses = (report?.hypotheses ?? []).filter(hypothesis =>
    /recurring upstream microbiological control problem|sampling or analytical error/.test(hypothesis.statement));
  const actions = (report?.next_actions ?? []).filter(action =>
    /independent confirmation|environmental controls and cleaning/i.test(action.action));
  const sourceList = (ids: string[]) => <ul className="mt-2 space-y-1 text-xs text-gray-500">{ids.map(id => {
    const check = report?.source_checks.find(check => check.observation_id === id);
    const ref = check?.source_ref;
    return <li key={id} className="break-words">{ref ? [ref.path, ref.sheet, ref.cell ?? (ref.row ? `row ${ref.row}, ${ref.column ?? ""}` : null), ref.page ? `page ${ref.page}` : null, ref.span].filter(Boolean).join(" · ") : id} · {check?.source_integrity && check.value_matches === true ? "automatic location/value check passed" : "not automatically verified"}</li>;
  })}</ul>;
  return <Card data-testid="investigation-depth">
    <Badge color="gray">Recorded synthetic benchmark · {example?.case_id ?? "unavailable"}</Badge>
    <Title className="mt-3">Beyond opening a deviation: investigate the broader risk</Title>
    <Text className="mt-2">The scripted replay illustrates escalation. The separate recorded investigation below shows actual agent work on synthetic evidence: cross-batch comparison, counterevidence, competing explanations and proposed checks.</Text>
    <div className="mt-4 grid gap-3 text-sm md:grid-cols-3">
      <div className="rounded-lg bg-gray-50 p-3"><b>Assess scope</b><p className="mt-1 text-gray-600">Compare microbiology across batches and environmental samples, rather than treating passing final tests as the whole risk assessment.</p></div>
      <div className="rounded-lg bg-gray-50 p-3"><b>Challenge explanations</b><p className="mt-1 text-gray-600">Consider analytical error and normal historian readings alongside microbial-control hypotheses. Matching signals do not prove a common cause.</p></div>
      <div className="rounded-lg bg-gray-50 p-3"><b>Ask for decisive evidence</b><p className="mt-1 text-gray-600">Request independent confirmation and environmental-control review. QA decides disposition; the agent proposes review tasks.</p></div>
    </div>
    {!example && <p className="mt-4 text-sm text-gray-500">No recorded example is available in this exported batch.</p>}
    {example && !report && !error && <p role="status" className="mt-4 text-sm text-gray-500">Loading the recorded investigation example…</p>}
    {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
    {example && report && <>
      <p className="mt-4 text-sm text-gray-700">Recorded outcome: final investigation; source review pending; independent scientific review pending. {example.coverage_reviewed}/{example.coverage_total} screened units reviewed, {example.calculation_count} calculations verified and {example.pending_source_reviews} source checks awaiting review. These counts are not a scientific-quality score.</p>
      <Grid numItemsLg={2} className="mt-4 gap-5">
        <section><h3 className="text-sm font-semibold">Source-linked observations and counterevidence</h3>
          <p className="mt-1 text-xs text-gray-500">Selected original agent excerpts. All batch identities, values and operating events below belong to the synthetic dataset.</p>
          {facts.map((fact,index) => <details key={index} className="mt-3 rounded-lg bg-gray-50 p-3"><summary className="cursor-pointer text-sm">{fact.statement}</summary>{sourceList(fact.evidence_ids)}</details>)}
        </section>
        <section><h3 className="text-sm font-semibold">Competing explanations · not verified causes</h3>
          {hypotheses.map((hypothesis,index) => <details key={index} className="mt-3 rounded-lg bg-amber-50 p-3"><summary className="cursor-pointer text-sm">{hypothesis.statement}</summary>
            <p className="mt-2 text-xs font-semibold">Supporting source references</p>{sourceList(hypothesis.supporting_evidence_ids)}
            <p className="mt-2 text-xs font-semibold">Contradicting source references</p>{hypothesis.contradicting_evidence_ids.length ? sourceList(hypothesis.contradicting_evidence_ids) : <p className="text-xs text-gray-500">None linked for this hypothesis; absence of contradiction does not verify it.</p>}
            <p className="mt-2 text-xs font-semibold">Checks that could distinguish the explanations</p><ul className="mt-1 list-disc pl-4 text-xs text-gray-600">{hypothesis.tests_or_observations_that_would_discriminate.map(test => <li key={test}>{test}</li>)}</ul>
          </details>)}
          <h3 className="mt-4 text-sm font-semibold">Proposed human-review tasks</h3>
          <ul className="mt-2 list-disc space-y-2 pl-4 text-sm text-gray-600">{actions.map(action => <li key={action.action}>{action.action} · owner: {action.owner} · proposed, not performed.</li>)}</ul>
        </section>
      </Grid>
      <a className="mt-4 inline-block text-sm font-medium text-emerald-700 underline" href={example.details_url} target="_blank" rel="noreferrer">Inspect the original report, all evidence coordinates and output hash ↗</a>
    </>}
    <p className="mt-4 text-xs text-gray-500">Legacy snapshot disclosure: this recorded run used the original synthetic dataset, including open-deviation assumptions. Its contents have not been rewritten or reevaluated for the revised public narrative. No matched human or conventional-method comparison establishes that our investigation is better, faster or able to prevent the real recall.</p>
  </Card>;
}
