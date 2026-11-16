# Final-review fix wave — complete, awaiting scoped re-review

Scope: I1–I3 and M1–M5 from `final-review.md`; existing uncommitted implementation retained. Job: allow owners and QA to continue ordinary preparation, scientific inspection and follow-up without losing native source access or human reasoning. The narrow existing-contract fixes reduce re-entry/setup (Start), retain exact revisions and uncertainty (Trust), expose human follow-up (Act), and preserve the current APIs/system-of-record boundaries (Adopt). A broader state/UI rewrite would add migration and review risk without resolving these defects more directly. Measures are actual saved-field retention, exact-source inspection, successful registered model execution and recoverable failed lookups; synthetic elapsed times are not human effort savings.

## Source and harness files changed in this wave

- `backend/src/lifesci/investigations.py`: snapshot kinds include the bounded quality source kinds; current revision, site, permission, memory and lineage checks remain.
- `backend/src/lifesci/quality_workflow.py`: reopening evidence review and referencing an external record normalize pending external status without inventing a receipt.
- `frontend/components/quality/QualityWorkspace.tsx`: impact uses workspace impact; action concerns show prior action, exact evidence revisions, uncertain clocks and a human-assessment next step; assignees have guarded loading/error/retry; compact submissions use submitted actor/time; catalog follows pinned source basis with error cleanup/obsolete-response guard.
- `backend/tests/lifesci/test_case_science.py`: actual native lab/result/instrument/material collection plus work-order/raw-signal records through mounted catalog/model API and ordinary snapshot; registered cooling solver output, manifest inclusion, revision/site/authority rejection.
- `backend/tests/lifesci/test_quality_workflow.py`: mounted no-deviation → evidence → external-reference status consistency with export.
- `backend/scripts/deviation_acceptance_seed.py`: separate synthetic recurrence fixture with normal, known pre-action, adverse post-action and unknown-clock originals.
- `backend/scripts/quality_browser_server.py`: unique legacy adoption fixtures under explicit acceptance names; existing DB and history retained.
- `frontend/scripts/check_quality_journey.cjs`: correct legacy evidence ID; final-review behavior probes with real local APIs, request abort/delay only, no response fulfillment.

## Verification to date

Backend RED: `.venv/bin/python -I backend/results/deviation-mvp-20261115/run_isolated_regression.py backend/tests/lifesci/test_case_science.py backend/tests/lifesci/test_quality_workflow.py -k 'native_quality_sources or reopened_no_deviation' -q --tb=short` → **2 expected failures** (native catalog HTTP400; external status disagreement). Two fixture setup mistakes were corrected before this final RED; neither was treated as a product failure.

Backend GREEN, same runner with both files and no `-k`: **86 passed in 6.78s**. Follow-up native authority assertion: **1 passed in 2.26s**; existing ordinary snapshot/privacy regressions: **4 passed in 1.57s**. Counts overlap and are not added to prior broad runs. Logs: `backend/results/deviation-mvp-20261115/logs/final-fixes-*.log`.

Browser RED: `node frontend/scripts/check_quality_journey.cjs <fresh-output> backend/results/quality-browser-20261115/final-review-red1-manifest.json --final-review` demonstrated stale catalog after preparation, missing saved impact, missing recurrence, missing compact submission identity/time and unhandled lookup rejection. Per-finding failures retained in `final-review-ui-red-diagnostics2/result.json`; the separate `--probe=submission` run checks the actual existing summary text. Legacy `--regress-adoption` failed on the exact unrelated-source click. One diagnostic launch was sandbox-blocked before assertions; the approved browser command was rerun outside that sandbox. All browser output directories retained.

Browser GREEN preflight: `node frontend/scripts/check_quality_journey.cjs backend/results/quality-browser-20261115/final-review-ui-green-preflight2 backend/results/quality-browser-20261115/final-review-red1-manifest.json --final-review` → **20 checks passed in 14.443s**, zero page exceptions or external requests. Covers impact save/refresh/browser reload/unrelated mutation/QA read-only view and preserved candidates; empty-basis catalog → prepared supplied configuration/error cleared; compact submission actor/time; exact recurrence source inspection, uncertain timing and exclusions; assignee failure/retry and late rejected requests after navigation. First GREEN preflight exposed three harness assumptions, corrected without production changes: scope the scientific error rather than Next's global alert region; enter actual QA review before expecting read-only fields; specify the new case site before awaiting owner options. Prior attempt retained.

Build: `env NEXT_TELEMETRY_DISABLED=1 NEXT_DIST_DIR=.next-quality-final-review npm run build` (frontend) → **exit 0, TypeScript validation and 61 static pages**. Log `logs/final-fixes-frontend-build.log`. Existing Node experimental type-stripping warning only; no config-file change.

Final browser runs used the definite GREEN API restart (root-owned PID 73474, `--acceptance-name final-review-green1`, same preserved SQLite DB):

```sh
node frontend/scripts/check_quality_journey.cjs backend/results/quality-browser-20261115/final-review-ui-green backend/results/quality-browser-20261115/final-review-green1-manifest.json --final-review
node frontend/scripts/check_quality_journey.cjs backend/results/quality-browser-20261115/final-review-adoption-green backend/results/quality-browser-20261115/manifest.json --regress-adoption
```

Both **exit 0**: final UI **20 checks in 15.806s**, fresh legacy adoption **19 checks in 5.919s**. The latter exercises actual OOS and note-case manifests, retained revision-1 originals despite current revision 2, exact deadline/people/context and their own evidence IDs. No page exceptions or outside requests. These focused checks overlap the prior acceptance evidence; no aggregate inflated count is claimed.

Exact browser RED commands used the same script with outputs `final-review-ui-red-diagnostics2` and `final-review-submission-red`, manifest `final-review-red1-manifest.json`, flags `--final-review` and `--final-review --probe=submission` respectively. Legacy RED used output `final-review-adoption-red`, actual `manifest.json`, flag `--regress-adoption`. Each result/trace/screenshot is preserved in its output directory.

Additional updated evidence files: `backend/results/deviation-mvp-20261115/report.md`, `metrics.json`, `logs/final-fixes-backend-red.log`, `logs/final-fixes-backend-green.log`, `logs/final-fixes-native-authority-green.log`, `logs/final-fixes-snapshot-green.log`, `logs/final-fixes-frontend-build.log`, and this report. Browser output directories are under `backend/results/quality-browser-20261115/final-review-*`; runtime-generated manifests, executor packages and SQLite history remain there. The eight source/harness paths above were verified by byte comparison with `final-reviewed`; no other copied source file changed.

## Boundaries

No live inference, provider transport, customer database, manufacturing action, external approval, deployment, commit, push or outside message. Existing reviewed submissions, originals and approval authority remain intact. The seed’s deterministic registered-model runner is not evidence of live LLM accuracy. Parent owns server cleanup and the scoped re-review.
