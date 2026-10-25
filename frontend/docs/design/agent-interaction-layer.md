# Agent interaction layer — decisions

Source: `MOS-AGENT-DELTA-v1.0` (written delta spec). The referenced Stitch screen
(`projects/6692134241538759647/screens/fdf32c87…`) requires sign-in and was not available, so
the layer was built from the text spec on top of the existing 32-frame app.

## Job to be done

Let someone who is already looking at a plot, a transfer gap, a deviation or a schedule
conflict hand the surrounding legwork to an agent **without leaving that screen**, watch it
progress, answer only the questions the agent cannot settle, and get back reviewable drafts
that fit into the existing screens and the existing approval center (REV-01).

## What was built

| Piece | Where | Notes |
|---|---|---|
| Global command bar (Find · Ask · Delegate + scope badge) | `components/shell/TopHeader.tsx` | ⌘K still opens Find; Ask/Delegate open the composer. Unmatched Find queries offer "Ask the agent". |
| Composer with editable scope and plan preview | `components/agent/AgentComposerModal.tsx` | Scope chips can be removed/attached. Every run starts with a plan preview listing checkpoints, sources (incl. not-connected ones), possible pauses, and outputs. Free text with no matching plan says so instead of pretending. |
| Contextual `⚡ Ask / Delegate` | `PageHeader` (automatic for app frames), plot toolbar on ANALYSIS-01 (carries the selected span), HOME-01 queue items, TRANSFER-02, PLAN-01, QUAL-02 | `PageHeader agent={false}` opts out. |
| Shared right slot | `components/shell/Inspector.tsx` | One 440px slot with `Agent Copilot` / `Evidence & Provenance` tabs. Citation chips in the dock switch tabs; task state lives in context, so nothing is lost. Without agent tasks the inspector behaves as before (360px). |
| Agent dock | `components/agent/AgentDock.tsx` | Conversation · Structured plan · Working artifacts. Task switcher, pin, collapse, cancel/resume, redirect messages. |
| Run strip | `components/agent/AgentBottomRunStrip.tsx` | 40px dark strip whenever the dock is not showing; survives route changes; prioritises a blocked task. |
| State machine | `lib/agent/agent-context.tsx`, `lib/agent/types.ts` | All 12 spec states are typed. Runs persist in `sessionStorage`, so a reload resumes. Cancelled runs resume from the last completed checkpoint. |
| Clarification / permission gates | `components/agent/ClarificationPrompt.tsx` | Timestamp-style input gates and permission gates; "hold" options keep the run blocked honestly. |
| Artifacts | `components/agent/InlineArtifactCard.tsx` | Chart diff, hypothesis matrix, table diff, doc redline, schedule diff. Insert into canvas (via `AgentCanvasSlot` on the target screen), Compare, Request revision, Route to REV-01, Pin to WORK-01. |
| Review gate | `components/agent/ReviewRequiredGate.tsx`, `AgentReviewQueue` on REV-01 | Draft → Review required → Approved for handoff → Handoff (simulated) → Monitoring. Signing happens only in REV-01, only by a listed role, never by the requester. |
| Journeys | `lib/agent/templates.ts` | J1 feed/CMMS (ANALYSIS-01), J2 TT-006 mapping (TRANSFER-02 → DOC-01 → REV-01), J3 dossier with subtasks (HOME-01 → QUAL-02 → REV-01), J4 schedule (PLAN-01 → REV-01), J5 continuity via the run strip. |

## Decisions and trade-offs

| Decision | Alternatives | Why / trade-off |
|---|---|---|
| Keep the repo's process facts where the spec disagreed | Use spec text verbatim | The spec has Durham as split-range cascade and Mesa single-loop; existing fixtures and citations say Mesa is a gravimetric cascade and Durham FIC-2201 flow-only. Consistency across screens matters more for trust, so the J2 question was reworded around the real gap. |
| New citations for every new number (`fixtures/citations/agent.ts`) | Reuse nearest existing chip | A chip must actually contain the claim (e.g. Kc 1.85 / Ti 240 s, the 86-parameter map, the schedule solve). Derived values are marked `Manufacturing OS (derived)`. |
| Softened compliance copy | "21 CFR Part 11 electronic signature" | Same rule as the rest of the app: signatures are simulated, stored in the browser, "designed to support" only. Dispatch is labelled simulated and writes nothing. |
| Removed claims without a source | Spec: "σ²=0.012", "media lot p=0.04", "12 h hold limit" | No fixture supports them; the seed-train hold limit is shown as Unknown instead. |
| Dock collapses on navigation unless pinned | Always stay open | Keeps screens uncluttered by default; the run strip keeps the task visible and one click away. |
| Deterministic, browser-simulated runs | Call backend agents | No agent API exists in this static export. Timings are labelled simulated. Swapping `tickTask` for real events is the integration seam. |
| One state machine in context, not per page | Page-local state | Needed for J5 continuity, the REV-01 queue, and canvas insertion across routes. |

## Observable checks

- From any app frame: ⌘K → Delegate → suggestion → plan preview → Start, without leaving the page.
- Every agent output carries a claim tag; every cited number opens a source excerpt that contains it.
- A run started on ANALYSIS-01 keeps progressing while navigating to BATCH-01 and SOURCES-01; "Inspect dock" restores it with elapsed time and checkpoints intact.
- No path changes a system of record; approval requires a different role than the requester.
- `npm run lint` and `npm run build` pass.

## Known gaps

- Revision requests are recorded but drafts are not regenerated.
- "Ask" and "Delegate" share the same plans; Ask only changes the default dock tab.
- DOC-01 is the Q-DEV-031 summary; the J2 memo section is inserted there because the spec routes it to `DOC-UP01-03 v0.3`.
