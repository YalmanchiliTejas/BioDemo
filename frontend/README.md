# Manufacturing OS frontend

Next.js 14 (App Router) + TypeScript + Tailwind CSS + Lucide icons. It implements the
32-frame handoff `MOS-CODEGEN-HANDOFF-v1.1` (“Biomanufacturing OS Enterprise Precision”,
light theme). Most screens run on **synthetic** data for campaign `CMP-26-10` at the
fictional Aster Biologics Mesa site. `/home/` hosts the persistent engineering conversation: the existing gateway can assemble versioned scientific workflows from a problem description, with questions, charts, 3D review and proposals in the thread. The current live planning route is unavailable and the interface discloses that failure without synthetic results. `/process-simulation/` provides the numerical simulation workbench; `/process-simulation/advanced/` remains a compatible entry to it. See the [conversation report](../docs/process-simulation/conversation.md) for the execution boundary, verification and API launch commands.
The global agent dock remains template-driven. No screen writes to MES, DCS/PLC,
LIMS, QMS, CMMS or ERP systems.

```sh
cd frontend
npm install
npm run dev      # http://127.0.0.1:5180
npm run build    # static export to dist/ (served by backend/deploy/cmo-ingestion nginx)
npm run lint     # tsc --noEmit
```

Governing principles: [../Main_Culture_andETHOS.md](../Main_Culture_andETHOS.md).
Design decisions and trade-offs: [docs/design/mos-32-screen-implementation.md](docs/design/mos-32-screen-implementation.md).

## Layout

| Path | Purpose |
|---|---|
| `app/(marketing)/page.tsx` | `/` public landing page (MKT-01) |
| `app/(auth)/sign-in` | AUTH-01 |
| `app/(onboarding)/onboarding/*` | ONB-01…03 with a stepper frame |
| `app/(app)/*` | All desktop screens inside the app shell (header, 228px sidebar, 360px inspector, run strip) |
| `app/(operator)/operator/*` | 1024×768 cleanroom tablet companion (OPERATOR-01…03) |
| `components/ui.tsx` | Design-system primitives (Card, Pill, ClaimTag, EvidenceChip, PageHeader, Modal…) |
| `components/EvidenceDrawer.tsx` · `ScientificPlot.tsx` · `ReviewDossier.tsx` | The three core component contracts from the handoff |
| `components/shell/*` | App shell, command palette (⌘K), inspector, run strip, toasts, onboarding/operator frames |
| `components/agent/*` · `lib/agent/*` | Agent interaction layer: composer (Find/Ask/Delegate), dock, run strip, artifacts, review gate, task state machine ([decisions](docs/design/agent-interaction-layer.md)) |
| `lib/app-context.tsx` | `useAppContext()` global state (site, role, inspector entity, agent run state, toasts) |
| `fixtures/` | `MOCK_DATASET`, citation registry, deterministic time series |

## Conventions that carry the product principles

- **Claim types are always labelled** with `ClaimTag`: observation, calculated, hypothesis,
  proposal, unknown, imputed, contradicted, approved.
- **Every sourced claim has an `EvidenceChip`** that opens the raw excerpt, transformation,
  record timestamp and content hash in the inspector. Match scores are labelled as string
  match, never as probability of correctness. Hashes are synthetic demo values.
- **Gaps are shown, not hidden**: the 42-minute historian gap is hatched on plots, imputed
  values are dashed and excluded from statistics.
- **Proposals are never actions**: signatures in `ReviewDossier` are simulated, stored only
  in the browser, and do not push changes to any system. Compliance language is limited to
  “designed to support”; nothing claims validation or qualification.

## Retired

The previous Vite application (`/app` workspace, `/concepts`, `/benchmarks` viewer and their
Playwright check scripts) was replaced by this app and remains in git history (before this
change). `scripts/export_benchmarks.py` and `scripts/export_data.py` are kept because backend
tests import them; they still write snapshots to `public/benchmarks/` and `src/data/`, which
this UI does not currently render. Design documents in `docs/design/` other than the one
linked above describe that earlier implementation.

### Workspace companion

`/home/` centers the persistent companion. `/process-simulation/` opens the scientific simulation workbench, with the same companion available alongside it. The older `/process-simulation/advanced/` URL remains supported. Open it elsewhere in the desktop workspace with the Companion button or **⌘/Ctrl+J**. Drafts survive client navigation; sent conversations and attachments are saved by the existing engineering API and restored after reload. **⌘/Ctrl+K** still searches. The full tool catalog is under **Explore tools**.

Highlight text, then choose **Ask about this**. On scientific plots, drag to select a range and choose **Ask about range**, or attach the current chart directly. Inspect or remove the snapshot before sending. Chart snapshots carry values, units, series IDs, imputation flags, page origin and capture time. They are unverified display context; the API preserves them with the instruction evidence and keeps them separate from authorized source records. Existing source inspection and human review remain available. Reasoning and scientific execution use the existing engineering gateway and registered operations; a missing model route is disclosed, and the interface does not imply desktop automation or new manufacturing execution capabilities.

To review beside an existing build, run `NEXT_DIST_DIR=artifacts/companion-dev npm run dev -- --port 5181` and set `NEXT_PUBLIC_LIFESCI_API_URL` to the test API. Allow that frontend origin in `LIFESCI_CORS_ORIGINS` on the API. `NEXT_DIST_DIR` keeps temporary development/build output separate from `dist/`.

Browser contract (requires Playwright, a running API and an unavailable model route for the failure-path assertion): `PLAYWRIGHT_MODULE=/path/to/playwright node scripts/check_companion.cjs http://127.0.0.1:5181`. The check uses actual API requests and writes screenshots/check results to `/private/tmp/biodemo-companion-artifacts` by default; set `COMPANION_ARTIFACTS` to change this.

## Physics benchmark case study

`/case-studies/` now opens the completed PenSimPy/SMPL AI comparison. The page contains an introduction, results and reading guide, with16 chart panels: paired arm comparisons and uncertainty intervals, forecast horizons, decision outcomes and case-by-case prediction errors. Process filters and exact chart-value tables support inspection. Earlier case studies and the prior oxygen/freeze-drying pilot remain accessible.

Regenerate the reviewed presentation assets with `npm run export-physics-benchmark`. Their source is `docs/case_studies/model-repair-continuous-20261028/analysis.json`; no new experiment is run. The compact chart data and downloadable report/CSVs are retained under `public/case-study-results/physics-benchmark/` with the analysis hash. The view preserves the partial-support conclusion, retained timeout, simulation boundaries and unresolved230h viscosity failure.

Browser verification: `PLAYWRIGHT_MODULE=/path/to/playwright node frontend/scripts/check_physics_benchmark.cjs http://127.0.0.1:5180` from the repository root. It verifies numerical agreement with the recorded analysis,16 figures, process filtering, downloads, hash navigation and mobile overflow. Build using `npm run build` from `frontend/`; the exported app is in `dist/`.
