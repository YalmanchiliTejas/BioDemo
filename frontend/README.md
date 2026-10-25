# Manufacturing OS frontend

Next.js 14 (App Router) + TypeScript + Tailwind CSS + Lucide icons. It implements the
32-frame handoff `MOS-CODEGEN-HANDOFF-v1.1` (“Biomanufacturing OS Enterprise Precision”,
light theme). Every screen runs on **synthetic** data for campaign `CMP-26-10` at the
fictional Aster Biologics Mesa site. Nothing here connects to, or writes to, MES, DCS/PLC,
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
