# Browser journey evaluation

**Goal:** Measure Parker's complete local browser workflow with existing public files and actual application services: open data, select fields, read a chart, inspect a known ingestion conflict, and record a supported next step without leaving the application.

**Authority:** User approved the proposed real-browser, isolated-backend evaluation. Governing direction: `Main_Culture_andETHOS.md`; feedback: `docs/feedback,txt`. No new permission or product redesign is needed. Preserve the existing dirty workspace and do not commit or deploy it.

**Approach:** Run the current Next.js UI against `create_app` on isolated SQLite/ingestion stores. Prepare the existing CHO returning, changed and unseen deliveries by real ingestion, with fictional delivery context and labelled artificial defects disclosed. Existing browser contract tests use response fixtures; this new runner must not fulfill or mock any API response. Public-file preparation is a separately measured prerequisite, not user browser time.

**Four pillars:** Start with selectable existing data; verify rendered values and source context; save a decision/next step and verify persistence; count external navigation/downloads and retain the application workflow. These measures show technical behavior, not human discoverability, scientific judgment or customer adoption.

**Alternatives:** Reuse mocked UI tests (cheap but cannot measure actual integration); automate the real local UI (chosen); start a customer pilot (adds real context but is unnecessary for this technical check).

## Tasks

- [x] Backend worker: create `backend/benchmarks/skills/browser_server.py`, isolate databases and artifacts, use real public ingestion and real local authentication, expose the normal API on port 8147, and record preparation/source hashes and reference manifests.
- [x] Browser worker: create `frontend/scripts/check_browser_journey.cjs`, launch the current UI on port 5197, sign in through local development authentication, and exercise controls without API mocks. Record timings, requests, screenshots, console failures, page changes, downloads and persisted results.
- [x] Execute three independently reset sessions. Measure first meaningful chart, selection-to-updated-chart, source-context readiness, decision save/reload, and total scripted journey. Separate first development compilation from subsequent runs. Report all failures; do not erase attempts or tune away product defects.
- [x] Optional explanation: click the real explanation control, use the actual Modal provider with recorded requests and an estimated $2/20-call cap, measure separately, and leave the deterministic journey usable while it runs.
- [x] Review the screenshots and independent answer-key comparisons, audit API traffic for absence of mocks, verify the final saved next step, and write a concise report with limitations. Stop only processes started for this evaluation.

## Scoring and limits

- A useful chart must contain the intended batches/parameter/unit and source-backed points; DOM visibility alone is insufficient.
- The changed-delivery glucose conflict at CHO-007-R02 / 44 h must remain visibly unresolved. Inspect both original rows and a PDF preview internally. Record a next step to obtain clarification; do not manufacture a resolution or authorize manufacturing work.
- Save a traceable review step and outcome, reload, and verify the same evidence references remain. No outbound message or consequential action is sent.
- Time browser actions until visible completion; scripted speed is not human decision time. Record click/selection/input counts and external-app opens. No claim of pilot success or production latency follows.
- All raw results and failed attempts remain. Source hashes identify the code actually exercised; no production fixes are made during a timed sample.

## Execution notes

Runtime isolation preserves the current uncommitted product implementation, which would be lost in a checkout of HEAD. Backend and browser harness work are delegated under the parallel-work skill with distinct files. A real isolated SQLite deployment exercises the current services; it does not model production queueing or authentication.

Completed: three timed journeys and both independent audits passed. See `backend/results/browser-journey-20261115/report.txt` and `summary.json`. Source-loading latency, stale rationale after editing a step, and zero API-reported explanation cost versus nonzero receipt estimates remain documented product findings. Both evaluation servers were stopped and the temporary Next.js tsconfig include removed. Original failed attempts and raw scores are preserved.
