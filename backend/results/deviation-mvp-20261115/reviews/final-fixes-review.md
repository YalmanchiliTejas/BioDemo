- **I1 — Native records block scientific and investigation snapshots: ADDRESSED.** `backend/src/lifesci/investigations.py:29` includes the bounded `QualityEvidence.SOURCE_KINDS`; existing revision, site, memory and lineage checks remain in the snapshot path. `backend/tests/lifesci/test_case_science.py:372` combines native collection with mounted catalog/model calls, the actual cooling calculation, ordinary snapshot inclusion, and stale/site/unauthorized rejection.
- **I2 — Saved impact disappears from assessment and QA views: ADDRESSED.** `frontend/components/quality/QualityWorkspace.tsx:121` initializes from `w.impact.summary`, and `:123` preserves `w.impact` on save. The final browser artifact verifies save remount, explicit refresh, reload, unrelated mutation, preserved candidates and QA read-only visibility.
- **I3 — Recurrence concerns are invisible in Quality: ADDRESSED.** `frontend/components/quality/QualityWorkspace.tsx:181` renders each concern under its action, with action identity, human-assessment wording, uncertain timing and exact-revision inspection links; `:229` connects inspection to the source viewer. The final browser artifact verifies adverse/uncertain evidence visibility, exclusion of normal/pre-action events, actual source inspection, and unchanged `not_assessed` effectiveness status.
- **M1 — Follow-up assignee lookup fails silently: ADDRESSED.** `frontend/components/quality/QualityWorkspace.tsx:168` adds loading/error/retry state, effect cleanup and guarded promise completion. `:176` displays status/recovery, and creation controls reject a missing/unavailable selection. Browser checks exercise actual request abortion, retry to authorized data, and late rejection after navigation.
- **M2 — Compact submissions omit actor/time: ADDRESSED.** `frontend/components/quality/QualityWorkspace.tsx:231` uses `submitted_by`/`submitted_at` for submissions and retains `actor_id`/`at` for decisions. The final browser run checks both submitted values against the persisted record.
- **M3 — Legacy-adoption check selects unrelated evidence: ADDRESSED.** `frontend/scripts/check_quality_journey.cjs:207` selects `legacy.source_ref.id`. The fresh 19-check adoption artifact verifies both legacy cases inspect their own preserved revision-1 originals while current revision is 2.
- **M4 — Reopened triage contradicts export status: ADDRESSED.** `backend/src/lifesci/quality_workflow.py:580` and `:590` restore `pending_external_approval` for evidence reopening and external referencing. `backend/tests/lifesci/test_quality_workflow.py:640` checks the full transition sequence through mounted routes and export, retaining a null external receipt.
- **M5 — Scientific catalog remains stale after preparation: ADDRESSED.** `frontend/components/quality/QualityWorkspace.tsx:139` derives the pinned source basis, and `:140` reloads with error cleanup and an obsolete-response guard when that basis changes. The final browser artifact verifies empty basis → supplied configuration and removal of the initial error.

## New Breakage in the Fix Diff

None found. The eight-file fix diff introduces no new Critical, Important or Minor finding. The snapshot expansion remains a bounded kind allowlist; the UI changes preserve server authorization, exact source revisions and advisory scientific/effectiveness labels. Synthetic seed and harness changes retain earlier artifacts and exercise real services rather than fulfilled API responses.

## Checks Reviewed

- Read the supplied `final-fixes.diff`, fix report, changed behavior/tests and exact recorded outputs; no git mutation, server call, test rerun or new broad review.
- `backend/results/deviation-mvp-20261115/logs/final-fixes-backend-green.log`: **86 passed in 6.78s**. The added native and reopened-status tests are present in the diff.
- `backend/results/deviation-mvp-20261115/logs/final-fixes-native-authority-green.log`: **1 passed, 45 deselected in 2.26s**; `final-fixes-snapshot-green.log`: **4 passed, 20 deselected in 1.57s**. These overlap the other evidence and are not summed.
- `backend/results/quality-browser-20261115/final-review-ui-green/result.json`: **passed, 20 checks, 15.806s**, empty failures/page errors/external requests. Checked the per-behavior assertions and their harness implementation, including request abort/delay rather than fabricated responses.
- `backend/results/quality-browser-20261115/final-review-adoption-green/result.json`: **passed, 19 checks, 5.919s**, empty page errors/external requests; both fresh legacy cases retained exact original revisions and context.
- `backend/results/deviation-mvp-20261115/logs/final-fixes-frontend-build.log`: compiled successfully and generated **61/61** static pages. The preexisting experimental type-stripping warning remains nonblocking.

## Out-of-Scope Observations

None. Prior explicitly unverified live integrations, inference qualification and production deployment limits remain unchanged; this scoped fix review does not establish them.

## Verdict

**Fix round: All findings addressed, no new Critical/Important breakage.** **8 addressed, 0 open; 0 new findings.** The final review's three Important and five Minor findings are closed by this fix wave and its recorded focused verification.
