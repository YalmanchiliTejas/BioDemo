# Apprentice reference, adapted through our pillars

The governing product source remains [Main_Culture_andETHOS.md](../../../Main_Culture_andETHOS.md).
The user requested inspiration from [Apprentice's public homepage](https://www.apprentice.io/).

The reference was inspected in a browser at desktop size, including its task-entry
hero and workflow sections. Useful patterns were a prominent work entry, concrete
starting points, dark photographic presentation, and product demonstrations.
These informed our composition and interaction hierarchy. Our supplied landscape,
wordmark, data boundaries, and product model remain our own.

A palette-only adjustment was considered. A shared, functional entry and product
walkthrough was chosen because it reduces the gap between marketing and the
workspace and demonstrates the pillars through actual behavior.

| Pillar | Adaptation |
| --- | --- |
| Easy to Start | An editable goal composer on the landing page and workspace, shared workflow examples, and a draft handoff preserving the user's context choice |
| Easy to Trust | Inspectable sample evidence, visible limits, an always-visible source and boundary rail on Home, and an explicit distinction between a saved goal and completed analysis |
| Easy to Act | Practical follow-up examples and local proposals with owners, review notes and outcomes; the architecture keeps human review as the final layer |
| Easy to Adopt | Existing system context and familiar controls; administrator authorization and reviewed mappings remain explicit requirements for production |

The workflow gallery is a collection of starting points, not a claim of separate
specialist agents or a fixed sequence of screens. No customer logos, performance
claims, model comparisons, compliance claims or proprietary Apprentice imagery
were imported.

## Implementation

- `GoalComposer.tsx` and `goal-composer.css`: one accessible entry control for
  marketing and product; context selection, editable goal and example choices.
- `work-entry.ts`: shared workflow metadata and a versioned, tab-local draft
  transport. User text stays out of the URL. The landing page does not silently
  create a work record or claim that analysis has run.
- `WorkflowGallery.tsx`: filters and scope-preserving example selection, reused
  by both surfaces.
- `Landing.tsx`: dark full-bleed hero with the shared composer, a glass sample
  thread, a normally scrolling architecture map, source evidence and adoption
  boundaries. The four-pillar product tour was removed.
- `Home.tsx`: the same entry beside the contained sample thread, followed by a
  two-column workbench for saved work, sources and the demo boundary. The sample
  thread adds the 27 h / 48 h / next-step sequence and source chips.
- `WorkspaceShell.tsx`: a compact context strip keeps the site, sample mode,
  read-only snapshots, browser-local storage and human review visible above every
  workspace view.
- `capture_product_previews.cjs`: retained as a utility for capturing actual
  workspace views; the landing page no longer renders a product-tour panel.

If tab storage fails, the user's text remains visible and the handoff stops with
an explicit recovery message. A missing draft on arrival is also explained.
Completed handoff tokens are removed from the preceding history entry so Back
navigation does not generate a false recovery error. Canonical work remains in
the existing workspace store after an explicit Start work action.

## Checks

`check_reference_refresh.cjs` exercises exact goal and context preservation,
absence of goal text in URLs, no silent work creation, workflow filters, removal
of the four-pillar tour, selector/button separation at narrow widths, storage
failure and draft recovery. `check_landing_depth.cjs` verifies the normally
scrolling architecture, its scroll-linked parallax, active-layer changes,
reduced-motion fallback and horizontal overflow. The existing scientific,
persistence and motion checks remain applicable.
