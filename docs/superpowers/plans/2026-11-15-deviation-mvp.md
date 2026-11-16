# Deviation Investigation MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Do not spawn subagents from an implementer. Keep task changes uncommitted for the user's review.

**Goal:** Deliver an existing-data signal-to-investigation-to-local-quality-handoff workflow, with scientific evidence, impact assessment, actions and follow-up.

**Architecture:** Extend existing cases, evidence, missions/runtime and registered analytical services. Reuse APIs, auth and direct-manipulation UI; retain optional assistant/Prime paths. Local review never means official GMP closure.

**Tech Stack:** Python/FastAPI/RecordStore SQLite or PostgreSQL; Next.js/React/TypeScript; existing scientific adapters.

**Spec:** `docs/superpowers/specs/2026-11-15-deviation-mvp-design.md` and the user's complete implementation prompt.

## Global Constraints

- Keep existing features and extend existing data structures; no parallel disconnected case implementation.
- No production/customer DB access, live manufacturing control changes, outside messages, deployment, commits or pushes.
- Use isolated synthetic datasets; never present demonstrations as validated real process findings.
- Preserve source/version provenance, permissions, human authorization, immutable reviewed evidence and append-only audit history.
- No fabricated citations/model outputs, unjustified scientific defaults, autonomous GMP decisions or simulated external approval.
- All work remains in the existing feature checkout; preserve the four pre-existing untracked benchmark paths.
- Test behavioral and authority boundaries with meaningful failing tests before implementation; no tests that merely mirror private implementation.

## Review Focus

1. Source or permissions change between preparation, review and export: block stale or unauthorized conclusions.
2. Retry/duplicate events and worker replacement: one case/action/submission per intent, no overwritten prior review.
3. Missing/late/out-of-order observations, incompatible units or unidentified equipment: show the gap and avoid false scientific certainty.
4. Different people/sites/tenants and QA-vs-technical roles: no data leakage or role escalation.
5. Absent executor/model inputs/external eQMS: useful local work and truthful blocked/pending states.

### Task 1: Correct monitoring semantics and extend available event detection

**Files:** `backend/src/lifesci/signals.py`, `specifications.py`, `science.py` if needed, `cmo_datasets.py`, targeted signal tests.
**Interfaces:** Preserve existing SignalService APIs; add optional event_time and observations/association fields; existing callers remain valid. Specification extensions are optional/backward compatible. Support configured duration and cross-batch trend scopes using explicit event time, units, distinct batch identities and meaningful baselines. Reuse numeric normalization; unknown conversion becomes a visible evaluation issue. Categorized equipment/procedural/environmental/quality evidence can raise signals from available mapped records without invented data.
- [x] Write failing tests for duration excursion, unit conversion/rejection, event ordering and exact redelivery, product-specific matching, cross-batch yield deterioration, mapped equipment/lab/environment/post-release exceptions.
- [x] Run targeted tests; observe expected behavioral failures.
- [x] Implement existing-service extensions, preserving warning vs formal-deviation distinction and original OOS evidence.
- [x] Run new tests plus existing deviation/signals/triage tests; record results.

### Task 2: Persistent local quality lifecycle, evidence/impact, actions and follow-up

**Files:** Extend `quality.py`, `container.py`, `runtime.py`, `missions.py` only where necessary; add focused `quality_workflow.py`, `quality_evidence.py`, `quality_workflow_api.py`; tests `test_quality_workflow.py`.
**Interfaces:** `platform.quality_workflow` orchestrates existing `case` records. Public HTTP prefix `/v1/quality/workspaces`: GET list, POST create, GET `/{case_id}`, POST `/{case_id}/prepare`, `/assessment`, `/hypotheses`, `/evidence-requests`, `/actions`, `/transition`, GET `/export`, GET `/evidence/{kind}/{id}` (actual final contract written in task report for UI). Mutations require expected_revision and an idempotency key where a repeated intent creates records. One workspace response includes case, workflow, timeline, sources, hypotheses, impact, requests, actions, reviews, activity, completeness and allowed actions. Export is a complete JSON/HTML package with source manifests and local-only/pending-external labels; no fake receipt.
- [x] Write failing A/B/D/E/F service tests, including unauthorized/stale/duplicate cases and rejection of legacy closure bypass for managed cases.
- [x] Implement case-linked local states and append-only review snapshots, role checks, triage choices and optional external case reference. Owners/reviewers are validated people with current site access. Initial lab assessment is explicit and preserves original OOS.
- [x] Implement bounded authorized evidence collection, timeline, candidate extent/impact draft, missing evidence requests and current-version checks using existing evidence/store APIs. No invented connector queries.
- [x] Link existing missions/runtime for queued preparation, meaningful source-change resume and recurrence/effectiveness concerns without idle inference. Persist visible timing/activity and recoverable failure states.
- [x] Implement actions/CAPA distinction and evidence-bound local technical/QA review with return cycles, completeness gates and pending external handoff. Connect approved generic QMS submission only when existing authorization/writer supports it; otherwise truthful export.
- [x] Run meaningful integration tests and existing quality/mission/runtime regressions; publish exact API types for Task 4.

### Task 3: Structured scientific work and investigation integration

**Files:** `investigations.py`, `local_executor.py`, `cloud_backend/agent.py`, `prime_runtime` bridge/harness as needed; focused scientific case adapter; model-library/services; tests.
**Interfaces:** Integrate Task 2 case workspace with existing model catalog/derived model artifacts and Prime report records. Ordinary investigation tools can inspect catalog, prepare/run supported source-backed models and retain references in the frozen snapshot. Structured case analysis persists support/counterevidence/assumptions/unknowns, never claims a confirmed cause without a person's reviewed assessment.
- [x] Write failing tests for ordinary registered model-tool reachability, source-backed oxygen/heat calculation and observed comparison, withheld missing parameters, exact evidence handoff including counterevidence, preserved review versions, and truthful executor unavailable behavior.
- [x] Wire registered models into the ordinary executor context without granting arbitrary platform access. Automatically select compatible supplied source configurations; reject absent/invalid inputs. Preserve model hashes, units, assumptions and uncertainty.
- [x] Connect generated hypotheses/results to case workspace and preserve citation-to-original lineage. Fix runs/items contract compatibly; validated reports retain support and counterevidence or explicit unresolved mapping instead of dropping references.
- [x] Run model/investigation tests and Task 2 acceptance regressions. Record tested calculation vs inference boundaries.

### Task 4: Connected role-specific quality workspace and source inspection

**Files:** `frontend/lib/quality-workflow-api.ts`, existing navigation and signals/investigations pages, `frontend/components/quality/*`, `frontend/app/(app)/quality/page.tsx`, real evidence inspector components; browser check script.
**Interfaces:** Use Task 2 actual API contract. One connected case workspace with Engineer/MSAT/QA focus, not divergent records. Retain old pages/direct Workbench, make natural language secondary. Backend remains authority.
- [x] Add browser assertions for no-prompt signal→case→prepare→sources/hypotheses/impact→review→export, QA return, unresolved evidence and permission boundaries. Confirm missing UI fails against the real local API.
- [x] Implement event queue, manual initiation, triage/assignment/deadlines, timeline/trend links, scientific assessments, action/evidence requests, local review/return and labelled export. Use real source preview/original endpoints; preserve supplied record revisions.
- [x] Link abnormal chart points/signals to case creation/context, preserve investigation human start and pinned snapshots, display live activity/results/hypotheses. Repair real citation routing and keep demos labeled.
- [x] Run TypeScript checks and real browser acceptance; no fulfilled API fixtures as runtime proof.

### Task 5: Full scenario verification, review and handoff

**Files:** synthetic acceptance dataset/fixture, `backend/tests/lifesci/test_deviation_mvp_scenarios.py`, browser harness/result artifacts and concise implementation report.
- [x] Run A–F through actual mounted API/local runtime and source/model services. Preserve original OOS, failed review snapshots and source corrections; demonstrate recurrence links.
- [x] Run relevant regression suites, TypeScript build/check and real browser scenario with roles. Record source retrieval, deterministic execution and inference durations separately; no fake LLM accuracy claims.
- [x] Perform fresh-context code/spec review of all changes; fix significant findings with failing regression evidence.
- [x] Document added record fields/kinds (no unnecessary SQL schema migration), architecture/event flow, scenario outcomes and real external/model/validation limitations. Stop only evaluation servers started for this work; leave changes reviewable and uncommitted.
