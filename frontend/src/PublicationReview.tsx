import { reviewedCase, supportingIds } from "./publicReviews.mjs";
import snapshot from "./data/benchmarks.json";

type SourceCheck = {observation_id: string; source_integrity: boolean; value_matches: boolean | null; source_ref: {path?: string; sheet?: string; cell?: string; row?: number; column?: string; page?: number; span?: string}};
export type ReviewedReport = {output_sha256: string | null; observed_facts: {statement: string; evidence_ids?: string[]}[]; hypotheses: {statement: string; supporting_evidence_ids?: string[]}[]; source_checks: SourceCheck[]};

export default function PublicationReview({caseId, report, experiment = "", compact = false}: {caseId: string; report: ReviewedReport; experiment?: string; compact?: boolean}) {
  const review = reviewedCase(caseId, report.output_sha256);
  if (!review) return <p role="alert" className="mt-4 text-sm text-amber-800">No publication review is bound to this output hash. Unreviewed narrative is available only in the legacy artifact.</p>;
  const sections = review.sections.filter(section => !experiment || !section.experiment || section.experiment === experiment);
  return <section data-testid="publication-review" className="mt-4 space-y-4">
    <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
      <h3 className="text-sm font-semibold text-emerald-900">Publication review · editorial interpretation</h3>
      <p className="mt-1 text-xs text-gray-600">Not a revised agent quotation, rerun, or scientific approval. Original outputs, evidence IDs and coordinates remain unchanged.</p>
      <p className="mt-3 text-sm text-gray-800">{review.summary}</p>
    </div>
    {!sections.length && experiment && <p className="text-sm text-gray-500">No reviewed narrative excerpt for {experiment}. The graph, when available, shows source samples only. Other original findings remain in the unreviewed legacy artifact.</p>}
    {sections.map((section, index) => <div key={index} className={`grid gap-5 ${compact ? "" : "lg:grid-cols-2"}`}>
      <div><h4 className="text-sm font-semibold">Observation · scoped records{section.experiment ? ` · ${section.experiment}` : ""}</h4>
        <div className="mt-3 space-y-3">{section.observations.map((observation, index) => {
          const ids = supportingIds(report, observation);
          return <div key={index} className="rounded-lg bg-gray-50 p-3"><p className="text-sm text-gray-700">{observation.text}</p>
            <details className="mt-2 text-xs text-gray-500"><summary className="cursor-pointer">Original source references · {ids.length} links</summary><ul className="mt-2 space-y-1">{ids.map(id => {
              const check = report.source_checks.find(check => check.observation_id === id), ref = check?.source_ref;
              return <li key={id} className="break-words">{ref ? [ref.path, ref.sheet, ref.cell ?? (ref.row ? `row ${ref.row}, ${ref.column ?? ""}` : null), ref.page ? `page ${ref.page}` : null, ref.span].filter(Boolean).join(" · ") : id} · {check?.source_integrity && check.value_matches === true ? "recorded location/value check passed; interpretation unqualified" : "source review unresolved"}</li>;
            })}</ul></details>
          </div>;
        })}</div>
        {section.notes?.map(note => <p key={note} className="mt-3 text-sm text-gray-600">{note}</p>)}
        {section.supplementalCase && <a className="mt-2 inline-block text-xs text-emerald-700 underline" href={snapshot.runs.find(run => run.case_id === section.supplementalCase)?.details_url} target="_blank" rel="noreferrer">Supplemental source check: {section.supplementalCase} legacy artifact (separate run) ↗</a>}
      </div>
      <div>
        {!review.quarantine && section.hypotheses.length > 0 && <><h4 className="text-sm font-semibold">Hypothesis · unverified</h4><ul className="mt-3 list-disc space-y-2 pl-4 text-sm text-gray-700">{section.hypotheses.map(hypothesis => <li key={hypothesis}>{hypothesis}</li>)}</ul></>}
        <h4 className="mt-4 text-sm font-semibold">Proposed next checks · not performed</h4><ul className="mt-2 list-disc space-y-2 pl-4 text-sm text-gray-700">{section.tasks.map(task => <li key={task}>{task}</li>)}</ul>
      </div>
    </div>)}
    <details className="text-xs text-gray-500"><summary className="cursor-pointer">What still requires a rerun or adjudication?</summary><p className="mt-2">{review.rerun}</p></details>
  </section>;
}
