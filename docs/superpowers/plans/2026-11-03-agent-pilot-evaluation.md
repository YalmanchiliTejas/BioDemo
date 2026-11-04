# Agent pilot evaluation implementation plan

> **For agentic workers:** Execute the independent fixture, grading and runner tasks in parallel; root integrates and verifies.

**Goal:** Produce actual-model evidence about the current assistant before the user's one-hour deadline, with a $50 estimated budget and a hard request ceiling.

**Architecture:** Extend the existing Platform, conversation service, evidence tools and mission runtime. Each episode gets an isolated file-backed store. Hidden reference facts stay outside the application; deterministic graders and a separately prompted semantic judge inspect observed outcomes. Keep all failures and distinguish host tests, real-model local integration, deployed checks and untested coverage.

**Tech stack:** Existing Python, pytest, ModalProvider, SQLite, JSON/Markdown receipts. No new service or dependency.

**Spec:** User-approved controlled synthetic worlds in this conversation; governing Main_Culture_andETHOS.md. The GitHub issue is the canonical tracked specification.

## Constraints and decisions

- Work in the existing non-main branch so this evaluation targets the user's current version, including existing edits. Add only evaluation files; preserve unrelated changes.
- No production database/account updates, manufacturing effects, automatic deployment or undisclosed success retries.
- Keep source/model/code/fixture hashes, raw attempts, timing, token estimates and unknown invoice coverage.
- Use development cases for harness calibration; freeze held-out cases before real-model execution and preserve first-attempt outcomes.
- Prefer the small application adapter over a new factory simulator or an LLM-only source of truth. Trade-off: synthetic functional competence rather than independently qualified manufacturing outcomes.
- All pillars: preparation/questions (Start), evidence/support (Trust), valid draft/follow-up (Act), current interfaces/permissions/recovery (Adopt). User-effort savings need subsequent user observation.

## Review focus

Missing/malformed judges cannot pass. Correct answers with unsupported explanations cannot pass. Waiting cannot substitute for answerable completion. Wrong-scope facts and unauthorized effects fail. Budget admission remains safe under concurrent requests and unknown usage.

## Tasks

- [x] Fixture task: test independently known values and hidden-reference isolation, implement eight case families with development/heldout variation, verify actual ingestion and conversation creation.
- [x] Grader task: write failing tests for false passes and missing coverage, implement deterministic checks plus strict judge contract, verify mutation rejection.
- [x] Runner task: test request/budget admission and reporting, implement bounded recorded real-model calls, file-backed episode replay/restart/events, provenance and incremental reports.
- [x] Integrate: run evaluator tests and preflight every world without inference; perform limited development calibration; freeze and run heldout repeat trials within limits.
- [x] Verify: run appropriate host/security regressions, frontend type check, independent review, inspect actual outputs and failures; publish a local readiness report with explicit unsupported/untested capabilities.

## Execution ledger

- User approved implementation and live evaluation; estimated budget $50. The one-hour deadline begins at 2026-11-04 02:08 UTC.
- Baseline from preceding review: 187 selected backend tests and frontend TypeScript passed. Fresh verification follows implementation.

- Execution complete:105 live trials, including40 corrected-agent trials over24 cases,8 repeated three times. Reused-case regression interpretation and all incomplete/ungraded coverage disclosed.
- Fresh verification:258 selected backend tests and frontend TypeScript passed. Full backend command stopped after696 passes/10 skips at absent historical CHO pilot artifact; not an all-green suite.
- Preserved51/72 older baseline trials and all provider admissions; ran corrected software separately, no success substitution. Independent review covers40/40 corrected trials.
- Accounted estimates/reservations $15.4997; invoice unknown. Recommendation is supervised feedback beta with background follow-up disabled, not a general reliability qualification.
