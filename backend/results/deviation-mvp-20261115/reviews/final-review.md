# Final whole-change review — deviation/investigation MVP

Reviewed the supplied 43-file uncommitted diff against HEAD `d542b80da480c5bb6d68128a1d5defcb10b5d866`, current implementation files, governing `Main_Culture_andETHOS.md`, the approved design/plan, relevant domain/mission contracts, and the implementation handoff. This is the consolidated broad review, performed in service/authority, science/monitoring, and UI/acceptance passes. No checkout, index, server, provider, customer database, or branch mutations were performed. This report is the only file written.

## Strengths

- The implementation extends existing case identity, versioned evidence, current authorization, transactional receipts, missions, runtime fencing, and analytical services. It preserves Workbench and investigation entry points and offers useful direct controls.
- Historical review snapshots, source revisions and originals remain inspectable. Current source authority is rechecked through case, signal, generic-record and export paths; local QA review binds to a content fingerprint and rejects changed evidence. Generic case closure cannot bypass managed review.
- Scientific output distinguishes explicit source-backed calculations from hypotheses and qualification. Missing inputs and incompatible units are withheld. The ordinary executor advertises registered tools, and the citation endpoint retrieves actual pinned originals rather than fixture data.
- Monitoring retains source clocks, conversion provenance, distinct batch summaries and duration evidence. Original OOS records survive laboratory assessment; the final OOT correction preserves advisory status while allowing independent numerical limit evaluation.
- External quality status is explicitly local/pending with no fabricated receipt. Test reporting distinguishes synthetic service/browser evidence, deterministic execution, unavailable full-suite artifacts, and unperformed inference/qualification.

## Issues

### Critical (must fix)

None found.

### Important (should fix)

**I1 — Native records collected into a case break its scientific and investigation paths.**

- References: `backend/src/lifesci/investigations.py:28`, `:320`, `:327`; `backend/src/lifesci/case_science.py:19`; `backend/src/lifesci/quality_evidence.py:7`.
- Quality preparation collects `result`, `instrument`, `work_order`, `signal`, and `material_lot`, but the snapshot allowlist rejects all five. Case science sends the entire prepared source list to this snapshot function, and ordinary case-based investigation now automatically appends that same list. One authorized native lab result therefore prevents catalog retrieval, scientific analysis and the investigation snapshot, even if the other sources contain a valid model configuration.
- Narrow reproduction used only a new in-memory `RecordStore`, empty providers, cleared database/executor environment, synthetic native batch/lab ownership, a batch, a sample and a result. After case preparation, source kinds were `['batch', 'sample', 'result']`. Both `case_science.catalog(ctx, 'C')` and `investigations.snapshot(ctx, site_id='S', case_ids=['C'])` raised `ValueError: investigations can include only case, batch, sample, procedure_instance, claim, proposal, evidence, physical_analysis_context, physical_analysis_result, deviation_signal records`.
- Fix: align the bounded snapshot contract with supported quality evidence kinds, retaining the existing site, revision, memory and lineage checks. Do not silently discard native evidence. Add a regression combining native evidence collection with actual model/catalog and investigation snapshot use; the existing native-publisher test verifies collection alone.

**I2 — Saved human impact assessments disappear from the editable and QA views.**

- References: `frontend/components/quality/QualityWorkspace.tsx:121`, `:123`, `:215`; `backend/src/lifesci/quality_workflow.py:443`.
- The backend deliberately removes `impact` from `assessment` and stores it in `workflow.impact`, exposed as `w.impact`. The form initializes from `a.impact?.summary` and spreads `a.impact` on save. Because Assessment is keyed by case revision, a successful save immediately remounts it with an empty impact field. QA's disabled assessment view is also empty despite a saved impact assessment and passing completeness check. This forces re-entry on later edits and hides required human reasoning in the normal review view.
- A narrow in-memory service check confirmed `w.impact.summary == 'Synthetic batch B impact assessment'` while `w.assessment.get('impact') is None`; the rendering path is explicit in the referenced component.
- Fix: initialize and preserve impact from `w.impact`. Verify the entered summary survives save, refresh, another unrelated mutation, and the QA read-only view.

**I3 — Recurrence/effectiveness concerns never reach the connected Quality UI.**

- References: `backend/src/lifesci/quality_workflow.py:385`; `frontend/components/quality/QualityWorkspace.tsx:161`, `:169`, `:217`.
- Background preparation persists a linked concern with action ID, source refs, timing uncertainty and `requires_human_assessment`. No Quality component reads `workflow.effectiveness_concerns`. FollowUp displays only the unchanged action `effectiveness_status` (normally `not_assessed`), while activity shows a generic preparation update. Even after a workspace refresh, the user cannot see that adverse post-action evidence needs assessment without exporting/reading raw API data. Scenario F proves persistence, but its practical user-facing follow-up is missing.
- Fix: surface these concerns in the action/follow-up view, linked to the prior action and exact evidence revisions, including uncertain timing and an explicit human-assessment next step. Keep the wording advisory; do not infer CAPA failure/success. Add a real UI check that an adverse event is visible after refresh and that a normal or known pre-action event is not presented as recurrence.

### Minor (nice to have)

**M1 — Follow-up assignee loading fails silently.**

- Reference: `frontend/components/quality/QualityWorkspace.tsx:163`.
- The promise has neither rejection handling nor an obsolete-response guard. A failed lookup leaves an empty selector and an unhandled rejection with no recovery message. Route keying already reduces stale cross-case exposure, so this is not classified as an authority failure.
- Fix: use loading/error state, a current-effect guard, and an understandable retry path, as the new-workspace assignee loader already partly does.

**M2 — Compact submission rows omit the submitting person and time.**

- Reference: `frontend/components/quality/QualityWorkspace.tsx:219`; submission shape: `backend/src/lifesci/quality_workflow.py:594`.
- Rows read `actor_id`/`at`, while submitted records contain `submitted_by`/`submitted_at`. The preserved expanded JSON is correct, so this is a presentation defect rather than audit loss.
- Fix: select the appropriate fields for submitted versus decision records.

**M3 — Legacy-adoption browser mode selects the wrong evidence ID.**

- Reference: `frontend/scripts/check_quality_journey.cjs:127`.
- Inside the `legacy` loop, the inspector button uses `manifest.source_ref.id` instead of `legacy.source_ref.id`. The preceding assertion correctly checks the legacy source; the subsequent click targets the unrelated general acceptance source and can time out.
- Fix: use the loop's legacy reference and exercise that specific mode against its actual manifest. This does not invalidate the separately reported fresh 25-check browser journey.

**M4 — Reopened external-reference triage retains contradictory external status.**

- References: `backend/src/lifesci/quality_workflow.py:578`, `:581`, `:587`, `:661`.
- The supported sequence `no_formal_deviation → request_evidence → reference_external` changes triage but leaves `workflow.external_status = not_requested`. Export derives `pending_external_approval` from the new triage. An isolated in-memory reproduction confirmed these different values for the same case, so the page header and package disagree.
- Fix: normalize external status for transitions out of the no-formal-deviation outcome, without asserting any actual receipt or approval. Cover the sequence through workspace and export responses.

**M5 — Scientific configuration availability stays stale after preparation/refresh.**

- Reference: `frontend/components/quality/QualityWorkspace.tsx:139`.
- Catalog fetching depends only on case ID. Preparing a manual case or receiving a newly supplied configuration changes source refs but does not rerun this effect; an initial empty-basis error/“None found” remains even when analysis can now run. Errors are also never cleared on a later successful fetch. This is misleading guidance, although the Run button still calls the current backend.
- Fix: refresh catalog when the pinned source basis changes, clear previous errors, and ignore obsolete responses. Verify initial empty sources followed by preparation with a supplied configuration.

## Specification assessment

The architecture follows the approved extension approach and all four pillars together: existing-data starts, traceable evidence, durable review/action state, and integration with established records. Local-only export is a justified implementation of the unavailable external-writer boundary, not fake handoff. The Important findings are concrete integration gaps: native evidence breaks scientific access (I1), human impact is hidden in review (I2), and proactive recurrence is not presented for action (I3). Those must be corrected before describing the full connected MVP as complete.

## Quality and verification assessment

Authority, idempotency, frozen review content, deterministic scientific withholding and truthful external boundaries are generally strong. The remaining issues occur where independently tested contracts meet. The broad use of `Fields`/`any` makes the assessment/impact shape mismatch easy to miss; the necessary remedy is the focused field fix and behavior check, not a broad rewrite.

Existing evidence considered: the reported scoped OS-enabled 1187 passing tests plus 48 subtests; subsequent OOT fix's 97 passing tests; production frontend build with 61 pages; fresh 25-check browser run and supplemental source/citation/retry checks. These overlapping runs were not added together or rerun. The failed full attempt and missing legacy scientific artifacts remain disclosed limitations. This review ran only the two narrowly targeted, provider-free, in-memory reproductions described above; it did not start or call servers. I3 and M1–M3/M5 are source-level findings, not newly executed browser results.

## Recommendations

Apply one bounded fix pass for I1–I3 and the five small actionable defects above. Verify native source-to-science integration, saved impact in QA, and visible recurrence follow-up through the real contracts. Retain current authority checks, immutable historical submissions, honest scientific labels, and uncommitted reviewability.

## Declined to judge

- Live MES/LIMS/eQMS transport, deployment/runtime operations and external handoff receipts: explicitly outside this local synthetic acceptance; no live connection or real receipt was provided or claimed.
- Live model reasoning quality, calibrated causal accuracy and GMP qualification: deterministic tools and host-contract tests cannot establish these; the report correctly marks them unverified.
- Missing CHO/Lyo upstream benchmark artifacts from the full-suite attempt: no artifacts or authorization to reconstruct them were supplied, and the unrelated preexisting benchmark paths are excluded from this review.
- Preexisting Node experimental type-stripping warning: a toolchain warning rather than a demonstrated MVP defect; no new finding or change requested.

## Assessment

**Ready to merge? With fixes.**

The core implementation preserves the right data and authority boundaries, but three reproducible or directly evidenced integration gaps prevent the full connected workflow from being complete. Resolve I1–I3 and verify the focused behaviors; the five minor items are small, actionable fixes suitable for the same pass. Counts: **0 Critical, 3 Important, 5 Minor**.
