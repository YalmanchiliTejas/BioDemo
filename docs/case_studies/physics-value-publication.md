# Physical-model agent comparison: publication implementation

Status: experiment and publication-build verification complete. The user requested a publishable build for review, not deployment to a public host.

## Job and existing constraints

Manufacturing engineers should be able to inspect whether executable physical models changed an agent's diagnosis, operating decision, measurement requests or pre-transfer warning. Reuse `/case-studies/`, its existing selector, typography, teal accent, eight-pixel card scale, scientific plots and companion. Preserve the existing four cases and their deep links. The app remains a static Next.js export; viewing the new comparison requires no inference credential or live process API.

The simple alternative was to append simulation counts to an existing case. That would conflate an environment audit with agent outcomes. The selected change is a fifth case with a paired outcome table, actual decision viewer, cutoff-aware chart and evidence downloads. A separate application or publishing platform would duplicate navigation and source handling without improving this review task.

## Four pillars and measures

- Start: show the question, attempt coverage and observed endpoints before diagnostics. Observe whether recorded results load without a backend or user setup.
- Trust: retain failures, abstentions, authored-label limits, withheld-future boundaries, exact source hashes, model/tool versions and actual decisions. Check paired input hashes and downloadable evidence.
- Act: let reviewers inspect one case/task and each proposed action's independent synthetic replay. A recommendation remains distinct from scientific review or manufacturing execution.
- Adopt: reuse the existing route, design system, scientific plot and static hosting build. Check old case deep links, desktop/mobile layout and read-only behavior.

Trade-offs: this is a restricted-tool SDK experiment, rather than a full autonomous RLM investigation. Numerical Python remains available to both arms under separately verified OS restrictions. Authored mechanisms and richer synthetic evaluators permit objective pilot checks but do not establish real causal accuracy, prospective manufacturing improvement, actual engineer savings or prevented real batches. Human scientific adjudication remains pending.

## Execution records and presentation

- Frozen dataset: `backend/results/physics-value/pilot-20261027-final/`.
- Full comparison: `backend/results/physics-value/agent-comparison-20261027-enums/`.
- `agent-comparison-20261027/` is a separately retained development run, interrupted after identifying shared identifier-schema formatting overhead. Its 148 finished attempts and interruption receipt remain available; they are excluded from the final comparison counts. The revised task schemas enumerate only already-public identifiers in both arms. Data, physical kernels, scoring and budgets are unchanged.
- Earlier calibration failures and native-low correction remain separate records.
- Runner: `backend/benchmarks/physics_value/run_agents.py`, `sdk_experiment.mjs`, `research_sandbox.py`.
- Static export: `frontend/scripts/export_physics_value.py`.
- Page: `frontend/components/process/PhysicsValueStudy.tsx` inside the existing case selector.

Never replace a missing agent decision with a deterministic result. Never present model execution time or assumed assay effort as observed human time saved. Case charts reveal withheld reference trajectories only after evaluation; this retrospective page is not an agent input package. Public archives use an explicit file allowlist and exclude environment files, credentials and SDK memory.

## Observed results and publication claim

The final comparison executed 192 attempts across 24 cases and four tasks. It produced 179 scored decisions and 83 pairs with both arms submitting. Numerical-only A completed 83/96 decisions; model-enabled B completed 96/96. All 96 paired input and shared-tool-schema checks matched.

| Endpoint, all 24 attempts per arm | A | B |
| --- | --- | --- |
| Top-ranked authored mechanism matches | 11 | 14 |
| Feasible selected optimization actions | 10 | 14 |
| Verified simulated full-batch outcomes | 10 | 11 |

Among the 17 optimization pairs where both submitted, each arm selected a feasible action 10 times. Among 22 completed resolution pairs, verified outcomes were A 10 and B 9. These are descriptive, post-run completion-conditioned checks, alongside the all-attempt counts.

B warned on all 24 pre-transfer cases, including all eight controls. Its zero misses therefore match an always-warn policy and do not demonstrate useful risk discrimination. Characterization requests were recorded but not experimentally executed. The publishable claim is **more completed decisions with mixed quality results in a synthetic pilot**, not confirmation of the full thesis.

Computational replay checked 192 attempts, 293 physical calls, 108 measurement results and 179 accepted decisions with zero mismatches. It retained 279 numerical calls without reexecuting arbitrary code. Scientific interpretation, engineer effort savings and real manufacturing outcomes remain unvalidated.

Exact source result SHA-256: `1bf90c29bfe0ed1d7bb967162d8de47ada287efa5fe348831e53cac30764dca7`.

## Build and review verification

- `npm run lint` passed; `npm run build` exported all 38 static pages successfully.
- The physics, agent, publication, fermentation and freeze-drying test selection initially returned 64 passed and one publication-fixture failure. The fixture lacked the newly required model identity. After adding its explicit scripted/no-inference identity, both publication tests passed, covering the previously failing check.
- The finished production build displays 179/192 scored attempts, the mixed-quality interpretation and the all-eight-controls warning limitation. Process and task selection work; oxygen objective gaps retain modeled-USD units.
- All seven evidence links returned HTTP 200. The archived raw result exactly matches its source hash; all 909 archive entries passed ZIP integrity checks, with no environment or auth files.
- Desktop 1440×1080 and mobile 390×844 layouts were visually checked. The page has no horizontal document overflow; the outcome table scrolls within its labelled region.
- Existing `#sulfolobus`, `#pichia`, `#sanofi` and `#indpensim` cases retain their original headings and deep links. The new entry is `#physics-value`.
- Static review package: `frontend/artifacts/physics-value-review-20261027.zip`. Screenshots and a verification receipt sit beside it in `frontend/artifacts/physics-value-review-20261027/`.

Scientific review remains pending. Build verification is not scientific validation or public deployment.
