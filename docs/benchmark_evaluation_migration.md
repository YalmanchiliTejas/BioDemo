# Evaluation migration audit

## Preserved architecture and assets

The existing `ManufacturingStore`, ten scoped tools, Prime SDK host, native
recursive workers, Blackboard and investigation workflow remain the runtime.
The existing conventional parser, single-pass baseline, source renderer,
field-aware temporal store, source maps and reference datasets are reused.

Before implementation, 150 files totaling 606,762,533 bytes were copied read-only
to `benchmarks/snapshots/pre-evaluation-v2/assets`. The snapshot manifest SHA-256
is `787737e0887fcb44b9bc9137bf8d76c5b04c71e2ca5166a10d87214c1cd5fca3`.
Original workbooks, the CHO archive, aligned references, synthetic canonical
records, validated scores and old evaluation code remain inspectable there.
No original measurement or causal label was rewritten to match an agent output.

## Prior implementation

Existing support included fixed-format CHO reconstruction, original workbook
inventory, synthetic time-filtered source generation, source-to-record maps,
macOS reference denial, a parser and single-pass baseline, retrospective replay,
and unscored Prime pilots. The runner explicitly rejected `full_rlm`. Its
engineering-work ledger had five stages and one accepted-work/hour endpoint.

Gaps were a common case manifest, the actual SDK benchmark adapter, original
citation-location checks, blinded qualification policy, seven-stage human time,
setup allocation/first-case accounting, separate A–E groups, condition cohorts,
updated SDK trial reuse and end-to-end traces. Existing source-ID validity was
not claim support; synthetic RCA labels were not independently established truth.

## Migrations

- Default `--action run` now uses v2 investigation cases. `--legacy-tasks`
  preserves the old task diagnostics and output paths.
- New runs use UUID directories under `results/evaluation/`; legacy JSON scores
  are left untouched. The dashboard leads with v2 audited case checks and the
  qualified-rate/effort endpoints; earlier task diagnostics are expandable.
- `InvestigationInput` dispatches `full_rlm` to raw ingestion plus the existing
  `PrimeManufacturingHarness`. Optional trace and budget hooks were added to
  that harness/bridge; its model loop and tools were not replaced.
- Persistent SDK benchmark workspaces are owned, isolated, version-checked
  copies under `benchmarks/runtime/`. Updates must identify a completed earlier
  trial at an earlier cutoff in the same dataset, tenant and scope.
- Historical raw documents are independently rebuilt byte-for-byte, including
  PDF/scanned bytes, filenames and document metadata. Staged filesystem mtimes
  use the validated synthetic cutoff rather than current packaging time.
- Case workers deny reference/label/public-outcome roots, other trial data and a
  permission canary. Sources are checked again after execution. Scores are
  withheld on audit failures; infrastructure failures remain in artifacts.
- The legacy five-stage human ledger is not automatically translated to seven
  stages. New observed logs and exact-output blinded reviews are required.
- Displayed root-cause accuracy from synthetic campaign labels is withheld.
  Hypothesis evidence handling is distinct from verified causal truth.

## What remains external or untested

Independent reviewers must approve the draft quality threshold, noninferiority
margin and project triage rubric, and supply defensible scope/triage/relevance
labels where needed. No human study, qualified labor-savings result, hands-on
incumbent comparison or confidential manufacturing validation is created by this
migration. No untouched CHO source-data generalization is possible with the
already-inspected workbooks. Filename challenges are narrower format tests.

CHO clean/updated condition packages need appropriate additional frozen
manifests. Actual repeated model trials, update behavior, and scientific review
remain experiments to execute; a wired interface or mocked SDK test is not a
quality measurement. Token/cost accounting from the existing SDK is root-session
only; missing child/OCR/tool cost is explicitly unknown.

The pre-existing `test_recorded_prime_pilot_is_wired` depends on the absent
`runs/cho-comparison` artifact. Missing that historical pilot is not repaired by
inventing one or relabeling another run.
