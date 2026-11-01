# Structured workspaces — local implementation

The existing /workspaces route now presents saved account results as domain views.
The sidebar links to it; the Assistant points to the corresponding saved turn and
collapses its long explanation. No new model call, backend endpoint or database
migration is required. Deploy the frontend before claiming this exists in the live
account.

## Decision

Job: help a technician inspect a saved result, identify affected rows, see what ran, and hand the next question to the assistant without reconstructing a report.
Start: use existing authenticated account conversations and source inputs; no new model calls or setup.
Trust: separate source measurements, agent proposals, deterministic comparisons and unresolved questions. Display blocked work and original CSV rows. Never promote user text to verified evidence.
Act: row inspection, a traceable review queue, CSV export and a scoped assistant handoff. Execution and approval stay separate.
Adopt: reuse the app shell, navigation and account authorization. Keep original conversations and existing MES/LIMS/QMS records unchanged.
Alternatives: a read-only projection of existing saved results requires only a frontend deployment; introducing a new durable task/approval engine would require backend lifecycle and permission work. Choose the projection for this correction; do not simulate action completion.
Measures: no report reading before first useful table/chart; one click from a finding to its original row; no wrong-organizational results; actual execution statuses visible; no paid requests on page load.
Trade-off: supports known structured answer contracts; prose-only results remain unavailable rather than inventing a chart. Existing conversation API exposes only recent conversations, so label the scope.

## Behavior and boundaries

- Hold-time comparisons: measured source values, inclusive procedure threshold,
  calculated comparison and separate agent flags. Disagreement remains visible.
- Assays: source-labeled current specification band, assay table and source rows.
  Historical effective-time reconstruction is not claimed.
- Reconciliation: original values and units, normalized proposals, duplicate rows
  and review routing. None of these are labeled approved or verified.
- Scheduling: proposed Gantt bars, maintenance, source constraints and deterministic
  overlap/precedence/duration checks. No scheduling execution or optimality claim.
- Work status distinguishes supplied sources, model response, calculations,
  unrecorded review decisions and manufacturing actions not performed. It shows
  actual saved workflow steps when present. Suggested review has no assigned owner.
- Original replies remain in an expandable record. A row click opens its source,
  and the assistant receives a bounded selected screen snapshot, not source authority.
- Existing owner/organization authorization applies to every account API read. No
  public sample or reference answer is substituted on errors; scope changes remount
  and clear client result state. Only recent conversations exposed by the existing
  API are shown. Prose-only or ambiguous results do not become invented charts.

This first implementation supports the four existing structured answer contracts,
not arbitrary narrative-to-chart extraction. New result kinds need explicit typed
projections. Actual source rows and structured answers are used; hidden benchmark
keys never enter the production projection.

## Verification and preview

Six pure logic tests cover quoted CSV and physical row references, ambiguous
answers, inclusive limits and missed flags, duplicate source records, scheduling
violations and safe CSV export. Eleven browser checks over saved account receipts
cover all four views, source inspection, filtering/export, blocked work, URL reload,
assistant context, collapsed replies, mobile layout and explicit API errors. The
browser check intercepts API calls and asserts no mutations or inference requests.
TypeScript passes. These UI checks are not new manufacturing accuracy evidence.

Run logic tests from frontend/:

```sh
node --experimental-strip-types --test tests/work-results.test.mjs
npm run lint
```

The browser contract is frontend/scripts/check_work_results.cjs; its explicit local
fixture reconstructs the inputs from the source CSVs and reads replies from retained
account receipts. The fixture excludes reference keys and is not shipped as a
production fallback.

Local review artifacts: Sievance-workspace-preview.mp4 and
Sievance-workspace-preview.png in the repository root. The video is permanently
labeled LOCAL PREVIEW and frontend deployment pending. It is not footage of an
already-deployed account update. The earlier text-report video remains historical.
