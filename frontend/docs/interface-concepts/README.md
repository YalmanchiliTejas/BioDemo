# Pharmaceutical manufacturing interaction study

> **Superseded by [v3](v3/README.md)**, which now serves `/concepts`. This first version remains available at `/concepts/v1`; the links below have been updated accordingly.

Three isolated React prototypes are available at:

- [A — Ambient AI Teammate](http://127.0.0.1:5180/concepts/v1?concept=a)
- [B — Adaptive Scientific Workspace](http://127.0.0.1:5180/concepts/v1?concept=b)
- [C — Embedded Agent Experience](http://127.0.0.1:5180/concepts/v1?concept=c)

Start with `cd ui && npm run dev`. The existing application remains at `/`, including its case and ingestion routes. No FastAPI or Prime runtime changes were made.

## Walkthrough

1. Read the F-2408 fermentation update. In A, open the investigation; in C, select **Inspect linked evidence**. B starts in the investigation.
2. Inspect a supporting source, then switch to **Counterevidence**. Open the temperature/pH record or the calibration record.
3. Open **Missing**. The 72 h assay is not posted; actual airflow is outside the authorized connector scope. Drafting an evidence request changes only local prototype state.
4. In B, compare product concentration and dissolved oxygen, inspect the batch table, and explore alternative hypotheses.
5. Select **Review next action**, enter a reviewer and rationale, then accept the draft or request changes. Download the evidence packet from the local receipt.
6. In C, close the workspace to return to the host, dismiss/reopen the companion, and inspect batch records or shift notes. In A, inspect remembered responsibilities, source scope, or the simulated next-shift reminder.

Keyboard: **1 / 2 / 3** switch concepts, **E** opens the investigation, **R** opens review when an investigation is visible, and **Escape** dismisses dialogs. Inputs retain normal typing behavior. Dialogs trap focus and restore it to the invoking control; reduced-motion preferences are respected. Narrow-screen layouts stack content and keep tables horizontally scrollable.

## Comparison

These are design judgments and manual-path counts, not engineer-study results. Measured time to understand what needs attention remains **unmeasured** for all three.

| Criterion | A — Ambient teammate | B — Scientific workspace | C — Embedded companion |
| --- | --- | --- | --- |
| Expected attention effort | Lowest on a daily return: one development and a short summary | Higher: finding, analysis and reasoning visible together | Low when already in the host: contextual alert, but attention competes with host content |
| Interactions to an original supporting source | 2: open investigation, select source | 1: select source | 2: inspect linked evidence, select source |
| Findings and uncertainty | Concise hypothesis first; counterevidence and missing-data controls in the investigation | Strongest overview: persistent interpretation, gaps and competing hypotheses | Brief caveat in companion; full source and uncertainty inspection on demand |
| Next action | Review after opening the investigation | Persistent decision panel | Review in the focused workspace over the host |
| Visual distinctiveness | Highest: a daily brief organized around delegated responsibilities | Moderate: familiar scientific structure with progressive tools | Companion is distinctive; host deliberately remains conventional |
| Engineer familiarity | Familiar reading pattern; responsibility model needs introduction | Highest analytical familiarity: chart, batch table, source records | Highest workflow continuity: existing app stays available |
| Main cost | Another step before detailed evidence; prioritize feed noise carefully | More information up front and greater screen-space demand | Requires host context/access integration; companion can compete for space |

The counts start at each concept's initial view and refer to a supporting source. Opening a contradictory source adds a category selection. The initial views show the same scenario, not identical tool density.

**Recommendation:** use A as the home for ongoing responsibilities and meaningful developments, with B as the deeper scientific workspace. Offer C as an optional entry point within existing applications where integration permits. A handles attention; B handles scientific scrutiny; C reduces context switching. Do not combine all three layouts into a single permanent screen.

Before expanding the product, run a counterbalanced study with pharmaceutical engineers: identify what needs attention, locate a contradictory source, explain the two missing inputs, review the verification task, and return to their prior work. Measure completion time, clicks, uncertainty comprehension, mistaken causal conclusions, and review errors. Test each standalone concept before testing the recommended combination.

## Architecture and scope

The existing frontend is React 18 / Vite with Tremor and Remix Icon components. The case workspace already supports source review, descriptive analysis and handoff; its current flow emphasizes intake and preparation. The backend uses FastAPI with the existing Prime TypeScript SDK host, scoped evidence bridge and review workflow. The prototypes are lazily loaded from `frontend/src/main.tsx` at `/concepts`; styles are scoped to the concept lab. `fixtures.ts` supplies invented connector responses. Radix Dialog (the primitive used by shadcn/ui dialogs) provides accessible modal behavior; existing Remix icons are reused. Assistant-ui and 21st.dev components were not added because none of these concepts requires a conversation transcript or a borrowed presentation component.

All connectors, activity, records, measurements and people are **illustrative**. No live detection, model invocation, background monitoring, production write or QMS integration occurs. Session state is in React memory and resets on reload. Exported packets are explicit user-triggered local downloads. A receipt is not a GMP signature. Recipe changes, batch disposition and release remain outside the prototype.

The six-batch comparison is descriptive. Product concentration is 1.74 versus 2.12 g/L at 48 h (17.9% lower, rounded to 18%). This is not final yield. Dissolved oxygen is 25% versus 40% air saturation. Time-aligned association does not establish causation. Temperature/pH and prior calibration are counterpoints, not proof against oxygen limitation. The missing assay and unauthorized airflow are never filled with zero or inferred values.

## Screenshots and verification

Each concept has overview, evidence, review and mobile captures in [screenshots](screenshots). The mobile captures document the state reached by the walkthrough, not always the initial view.

| Concept | Overview | Evidence | Review | Mobile |
| --- | --- | --- | --- | --- |
| A | [Brief](screenshots/a-overview.png) | [Investigation](screenshots/a-evidence.png) | [Review](screenshots/a-review.png) | [Mobile](screenshots/a-mobile.png) |
| B | [Workbench](screenshots/b-overview.png) | [Evidence](screenshots/b-evidence.png) | [Review](screenshots/b-review.png) | [Mobile](screenshots/b-mobile.png) |
| C | [Companion](screenshots/c-overview.png) | [Workspace](screenshots/c-evidence.png) | [Review](screenshots/c-review.png) | [Mobile](screenshots/c-mobile.png) |

Run `npm run build` in `frontend`. Browser verification: `node frontend/scripts/check_interface_concepts.cjs` from the repository root with Vite on port 5180. Set `PLAYWRIGHT_MODULE` to a local Playwright module if the default workstation module is unavailable. Chrome is required. The script verifies the complete investigation/review path, exports review packets, checks keyboard navigation and mobile overflow, collects runtime errors and confirms zero backend API calls. Results are saved in `verification.json`.

## Design review

The first visual pass confirmed distinct reading patterns: A's narrative brief, B's analysis workbench and C's companion in a muted host. An Escape-key conflict discovered in walkthrough testing was corrected so source dismissal preserves the underlying investigation. The companion replaces the workspace dialog with source or review dialogs rather than stacking competing focus scopes. Secondary text contrast was strengthened, and mobile charts scroll horizontally to preserve readable axes. Focus trapping/restoration and the request-changes branch passed browser checks. Shared evidence, a common action gate and restrained motion preserve comparison validity.

`frontend-design` was found and read in the installed Claude plugin skill cache. The requested `impeccable`, `distill`, `critique`, and `web-design-guidelines` skill files were not found in installed Codex/Claude/agent skill directories. Their simplification and critique intent was applied manually; this is not claimed as execution of unavailable skills. The Sites local-only workflow guidance was consulted; these are local prototypes in the existing Vite checkout and are not published.
