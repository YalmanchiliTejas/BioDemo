# Workspace rebuild governed by Main_Culture_andETHOS.md

This document records implementation decisions. The governing source remains
[Main_Culture_andETHOS.md](../../../Main_Culture_andETHOS.md); this implementation
does not redefine its scope or prescribe a universal workflow.

## Job and context

A pharmaceutical manufacturing team member should be able to begin with an
intent, inspect relevant context, resume saved work, and record a reviewable next
step. The initial experience should not require navigating a plant dashboard or
phrasing every task as a conversation. Charts, tables, source records, and a
contextual guide remain useful tools where the task calls for them.

The repository already supplies an illustrative batch scenario, scientific
charts, source viewers, a quality-review sheet, an optional scripted assistant,
and separate backend case/ingestion APIs. This rebuild reuses those capabilities.
It does not claim the sample sources are live or a new user goal has been analyzed.

## Alternatives considered

| Option | Benefit | Cost / limitation |
| --- | --- | --- |
| Refresh the existing dashboard and its fixed batch finding | Small implementation change; familiar entry | Keeps the product centered on one batch, loses work on reload, and gives no durable path from intent to outcome |
| Build a general work surface around the existing tools | Supports multiple entry points, retained context and reviewable follow-up | Requires a work model, persistence, recovery, and navigation outside the original prototype |

The second option was selected. A wholesale backend or UI-framework replacement
was unnecessary for this local demonstrator. The existing Radix primitives,
React, fonts, Remix icons, and scientific components remain in use. The supplied
landscape, ambient lighting, image motion, pause preference, and reduced-motion
behavior are preserved.

## Joint pillar review

| Pillar | Concrete behavior | Trade-off |
| --- | --- | --- |
| Easy to Start | Enter a goal directly, choose an optional starter, use available sample context, or attach context later | Arbitrary goals remain drafts until relevant authorized data and analysis are available |
| Easy to Trust | Distinguish calculated result, hypothesis and unknowns; open original evidence and limitations; preserve correction notes | Notes record a challenge; they do not silently revise a scientific finding or trigger an analysis |
| Easy to Act | Record a proposal with owner, rationale, expected result and constraints; retain local review, progress and observed-outcome events | These local records do not substitute for QA approval, operational execution or a QMS handoff |
| Easy to Adopt | Keep existing source workspaces and scientific tools accessible; support browser-local resumption and JSON export | Browser storage is local to this origin/profile, can be cleared, and is not a multi-user or regulated record store |

## Architecture and boundaries

- `workspace-model.ts`: UI-independent work, note, action and event types;
  immutable operations; schema decoding; legal action-stage transitions.
- `WorkspaceProvider.tsx`: the browser-local demo persistence adapter, versioned
  storage key, storage-event synchronization, recovery messages and export helper.
  A corrupt saved copy is preserved; a failed write switches to session-only work.
- `WorkspaceShell.tsx`: navigation, current-context breadcrumb, saved-work search,
  mobile dialog and optional assistant surface. Work identities survive URL
  navigation and reloads; record tabs are encoded in the URL.
- `workbench/`: intent entry, saved work, work detail, source-access review,
  proposals and follow-up. None of these views invokes a fictional analysis job.
- `Hub.tsx`: composition and routing. Scientific record tools and the scripted
  assistant load on demand.
- `lab/state.tsx`: optional persistence for sample progress, missing-evidence
  requests, assay state and simulated quality receipts. Prototype routes keep
  their original session behavior when no persistence key is supplied.

Evidence remains in the scenario/source layer, separate from user notes and
proposals. User-authored proposals with no source links are identified as such.
An action cannot advance from proposed directly to in-progress or outcome-recorded;
intermediate stages require an explanation. Recorded local review explicitly does
not grant manufacturing authorization. This state machine is a demo behavior,
not an enterprise authorization boundary.

The original tenant-scoped backend case and ingestion APIs are unchanged. Real
source integration must use their identity, permission and provenance mechanisms;
the browser-local sample adapter must not be used as a production record store.
Models, ingestion and orchestration have not been replaced or coupled to the new UI.

## Observable verification

The checks exercise user effort and correctness boundaries without claiming
measured productivity gains:

- Starting a goal without an upload or mandatory configuration.
- Resuming the same goal and notes after reload and via search.
- Exporting the actual saved work without inventing attached evidence.
- Proposing a next step, recording each stage, and retaining the observed outcome.
- Inspecting supporting evidence, counterevidence and missing data.
- Keeping scientific tabs, source workspaces, history, keyboard search and mobile
  navigation functional.
- Keeping the interface usable when storage fails and preserving corrupt data.
- Keeping motion pause/resume, persistence, offscreen pausing and live
  reduced-motion changes functional.

Commands:

```sh
npm run build --prefix frontend
node frontend/scripts/test_workspace_model.cjs
# Browser checks require Playwright and a running local frontend:
node frontend/scripts/check_workspace.cjs
node frontend/scripts/check_ethos_workspace.cjs
node frontend/scripts/check_atmosphere.cjs
```

Set `WORKSPACE_URL` and `PLAYWRIGHT_MODULE` when the preview port or Playwright
installation differs. Browser screenshots and short performance traces are local
review artifacts; they are not field performance, scientific-validation,
regulatory-compliance, or customer-adoption evidence.

Verification outcome for this rebuild: the production build, eight model tests,
the scientific-workspace browser suite, and the new ethos-workspace browser suite
passed. Browser suites reported zero page errors. The motion suite also passed;
its bounded 1.5-second steady-state trace recorded zero Layout and zero Paint
events. Responsive checks covered 320, 390, 768, 1024 and 1440 px widths. Export,
late context attachment, note retention, staged action history, quota failures
and corrupt-storage preservation were exercised. The build continues to report
large chunks in the existing scientific/benchmark application.
