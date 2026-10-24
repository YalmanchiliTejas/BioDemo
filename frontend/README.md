# Manufacturing OS frontend

## Current product workspace

`/` opens the landing page and `/app` opens the work surface. Start from a goal,
resume saved work, inspect source evidence and scientific tools, or track a
reviewable next step.

The landing page and workspace share a bone, assay-blue and culture-lime palette.
The landing page uses a dark horizontal top navigation; the workspace keeps a
light top bar with a compact sample/boundary strip beneath it. Home is a
workbench: the goal composer and a contained sample thread sit above a two-column
working surface, with saved work on the left and sources plus the demo boundary
on the right. Saved work opens a vertical numbered thread for Overview, Evidence,
Trends, Next steps and Notes. Work views survive browser history and reload.
Source inspection stays in place, and scientific tools provide an explicit return
to the originating work. On the landing page, the supplied landscape is a
duotoned, full-bleed hero stage behind a glass sample thread. The architecture
section is a dark, normally scrolling map — systems of record, the browser-local
workspace, and human review — with scroll-linked parallax, a highlighted active
layer, handoff packets that move only as the reader scrolls, and an explicit
boundary panel. The workspace keeps the landscape contained in the Home sample
aside. Ambient and scroll motion follow the existing pause and reduced-motion
preferences.

Design decisions and observable checks: [workspace flow](docs/design/workspace-flow.md).
Current visual direction: [paper flow](docs/design/paper-flow.md).
Earlier landing/workspace redesign and applied skills: [clean surface review](docs/design/clean-surface-skill-review.md).

The workspace is a clearly labeled browser-local demonstrator. Goals, notes,
action history and sample review state persist in the current browser. User goals
are drafts; saving one does not run an analysis. No live MES, LIMS, historian or
QMS connection is configured by this UI. Existing backend case and ingestion
features remain separate and unchanged.

An optional connected mode uses the backend `/v1` API instead of browser storage:
choose **Connect to server** in the workspace context strip (development sign-in with
a tenant and person; roles come from the server). Start the API with
`python -m src.lifesci serve --seed-demo --port 8100` from `backend/`; Vite proxies
`/v1` to it. Sample mode remains the default. See [connected mode](docs/design/connected-mode.md).

See [the rebuild decisions](docs/design/ethos-rebuild.md) and the governing
[product principles](../Main_Culture_andETHOS.md).
The [Apprentice-inspired refinement](docs/design/apprentice-reference-refresh.md)
adds shared task entry, workflow discovery and a normally scrolling,
scroll-linked architecture explanation.


Run this project from `frontend/` with `npm install` and `npm run dev`.
The introduction is at `/`, the sample investigation workspace at `/app`, and
the measured benchmark viewer at `/benchmarks`. Existing ingestion and case
views remain at `/benchmarks?tab=ingestion` and `/benchmarks?tab=cases`.

The workspace uses bone surfaces, cobalt actions and a culture-lime signal, with
an overview that prioritizes findings and running batches. The assistant is
optional and can be opened from the top bar. All plant activity in the sample
workspace is simulated; the prototype does not connect to real plant systems.

`npm run build` checks TypeScript and builds `dist/`. The Python export commands
use the shared root `.venv` and read records directly from `../backend/`.
Design studies and visual documentation are under `docs/`.

The browser smoke check is `scripts/check_workspace.cjs`, against a running dev
server. It accepts `PLAYWRIGHT_MODULE` for the Playwright package location,
`WORKSPACE_URL` for the server URL and `SCREENSHOT_DIR` for screenshot output.

## Benchmark result viewer

The default tab displays the latest paired CHO/Fresenius background benchmark
batch, sourced from retained `results/evaluation/*/run.json` records and bound
output hashes. All attempts in the batch are shown, including failures and
partial reports. Final investigations with pending source checks are distinguished
from verified sources and unfinished work. Independent scientific qualification
remains a separate gate. Unknown costs and unavailable results are not zero scores.

```sh
cd /Users/tejas/Desktop/BioDemo/frontend
npm run export-benchmarks
npm run dev
```

Open http://127.0.0.1:5180/benchmarks. After another benchmark batch finishes, run
`npm run export-benchmarks` again. `npm run build` creates `dist/` with the exported
summary and detailed case data. Runtime stores can be offloaded: this view reads
retained reports and, optionally, checksum-matching original CHO workbooks.

The viewer includes outcome and runtime bar charts, an example selector, source
coordinates, competing hypotheses, unresolved questions, numerical-review flags,
and a table of every attempt. Source viability trajectories are optional: they
are read from a frozen-hash-matching CHO workbook and shown only when the selected
paired cited measurements share the same original source time. Lines connect
sampled means, without inventing replicate statistics or establishing event onset
or causation. The example selection method is disclosed beside the chart.

Case exports are under `public/benchmarks/`; the summary is also stored at
`src/data/benchmarks.json`. These are presentation snapshots, not modifications to
the recorded benchmark outputs. Inspect full case JSON to see all findings and
the source/run/output hashes. Case examples on the page are explicitly selected
excerpts rather than the complete report.

The second tab is a separately labeled synthetic workflow replay. Its projected
holds, earlier escalation and market-exposure changes are deterministic simulation
outputs, not measured agent performance or actual manufacturing interventions.
Fresenius is a synthetic reconstruction informed by public FDA-related materials;
no internal company data, participation, endorsement or validation is implied.

The public recall announcement (November 6, 2025) and FDA posting (November 7,
2025) are linked separately from the assigned 2024–2025 simulation events. First
shipment calendar dates match the public notice; timestamps within those days
are assumptions. Simulated early escalation and QA holds are scripted, not RLM
performance measurements. The planning sandbox defaults to zero assumed labor
reduction and reports gross modeled labor value, with excluded costs listed.

Publication labeling audit: [docs/UI_PUBLICATION_AUDIT.md](../docs/UI_PUBLICATION_AUDIT.md).
Run `node --test frontend/scripts/test_presentation.mjs` from the repository root to
check exposure cutoff, elapsed-day rounding and the missing-measurement scope.
Exports redact workstation paths; original result records remain unchanged.

Shadow-pilot CTAs use the approved Google Calendar booking URL. They request a
discussion of a de-identified deviation, not uploads of confidential records.
Case details are displayed only after their run ID matches the selected case;
CHO report excerpts can be explored by experiment without mixing chart and
hypothesis scopes. Partial-report self-descriptions stay in the technical
artifact; evaluated status is shown in the interface.

The public release narrative is versioned `v2-investigation-adequacy`: release
after inadequate broader-risk assessment is distinguished from administrative
deviation closure (unknown in the public record). The investigation-depth panel
uses original FRE-01 excerpts with source coordinates, counterevidence,
alternative explanations and proposed checks. It explicitly discloses that the
recorded run retains earlier synthetic open-deviation assumptions. This does not
change frozen data or establish superior performance on a revised scenario.

Visual hierarchy: the measured page leads with compact status cards and outcome/
runtime charts. The replay leads with a short synthetic-data label, model figures
and the animated workflow. Detailed context, original report excerpts, methodology
and the illustrative calculator are expandable below the visuals. Material
provenance and scientific-review qualifications stay visible near the figures.

Launch credibility corrections are documented in
[LAUNCH_SCIENTIFIC_CREDIBILITY_PASS.md](../docs/LAUNCH_SCIENTIFIC_CREDIBILITY_PASS.md).
Public narratives now use explicitly editorial, output-hash-bound publication
reviews; original unreviewed reports are linked as legacy artifacts. Do not
replace raw report text with these notes or promote old runs' scientific status.
The replay cost model, held-lot strip and exposure plot are removed. Run
`node --test frontend/scripts/test_public_reviews.mjs` from the repository root and
use `frontend/scripts/check_publication.cjs` with Playwright for the all-case phrase scan.
