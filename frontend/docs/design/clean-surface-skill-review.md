# Clean surface redesign

Governing direction: [Main_Culture_andETHOS.md](../../../Main_Culture_andETHOS.md). No gstack skills were used, per the user's instruction.

## Skills actually applied

| Skill | Scope and concrete application |
|---|---|
| design-taste-frontend | Landing-page audit, conservative B2B design read (variance 4 / motion 3 / density 4), asymmetric image-led hero, four distinct section layouts, short copy, no repeated feature-card grids, real product screenshots, responsive preflight, Lighthouse check. Its marketing layout rules were not imposed on the scientific workspace. |
| web-design-guidelines | Fresh [guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md) reviewed against Landing, GoalComposer, WorkflowGallery and changed workspace surfaces. Applied heading balance, named fields, group focus, touch behavior, image dimensions, keyboard tabs, reduced motion and contained sheet scrolling. |
| micro-interaction | Short arrow feedback and press acknowledgement. No decorative animation framework or repeated looping interactions added. |
| accessible-animation | Hover displacement and press movement become static under reduced motion; opacity feedback remains. Existing live system-preference handling, pause preference and ambient-motion controls are retained. |
| vercel-react-best-practices | Existing primitives and state reused, no new dependency, existing route split retained, no React state driven by frame/scroll values, no new data fetching or sequential request chains. |

## Job, alternatives and trade-offs

Visitors need to understand the product, inspect an actual view, and start with a useful question. Returning users need their work and its evidence without surrounding explanations. The earlier landing page repeated the same principles through eight sections, labels, cards and captions. The workspace still boxed individual source shortcuts and sample context.

The small alternative was to remove card borders. The chosen change also consolidates the landing narrative into four sections and removes repeated metadata, output descriptions, numbered pillar strips and footer CTAs. Starting points become open two-column groups with one description and one action each. Workspace sample context becomes an inline row; sources become open shortcuts; actions, connection records and evidence lose enclosing panel chrome. Input and overlay boundaries remain where they help interaction.

The trade-off is less explanatory content up front. Source provenance, hypotheses, counterevidence, missing data, required authorization and action histories remain inspectable. Local drafts do not imply new analysis; sample records do not imply live access.

## Four pillars

- Easy to Start: the question composer, examples and exact-text handoff remain; saved work remains immediately visible.
- Easy to Trust: existing evidence inspection, calculation context, gaps, counterevidence and sample labels remain. Screenshots show the actual product, not fabricated preview components.
- Easy to Act: scoped next steps retain owners, rationale, constraints, local review, progress and observed outcomes. Consequential operations remain outside this demonstrator.
- Easy to Adopt: the existing React/Radix stack, source tools, browser persistence and export/recovery paths remain. Familiar navigation and free movement between work views are preserved.

## Review findings resolved

- `frontend/src/os/Landing.tsx` — duplicate pillar/control/adoption sections removed; one product tour retained; vertical tab orientation corrected to match the horizontal layout.
- `frontend/src/os/landing.css` — one continuous theme; two-line hero; open section layouts; mobile entry remains in view; focus, anchor spacing and motion feedback covered.
- `frontend/src/os/WorkflowGallery.tsx` — repeated category/output blocks removed; real scope label and single action retained.
- `frontend/src/os/workflow-gallery.css` — bordered six-card grid replaced by open two-column groups; compact editor uses one column.
- `frontend/src/os/GoalComposer.tsx` — goal/context fields have meaningful names; goal field avoids password-manager autocomplete; accessible labels retained.
- `frontend/src/os/workspace-flow.css` — action/source/evidence wrappers flattened; word wrapping, contained sheet scrolling, touch feedback and reduced-motion equivalents added.

Checks exercise keyboard tabs, mobile widths 320–1440 px, handoff, storage recovery, history, source inspection, notes, proposal/outcome tracking, animation pause and live reduced-motion changes. These verify implementation behavior, not user-study results or real-world time savings. Lighthouse is an automated lab audit, not a regulatory or accessibility certification.

## Verification result

- Production build and whitespace check passed.
- Five browser suites passed: `check_reference_refresh`, `check_workspace_flow`, `check_ethos_workspace`, `check_workspace`, and `check_atmosphere`; no reported browser errors.
- Production landing-page Lighthouse run: performance 95/100; automated accessibility 100/100; LCP 2.9 s, CLS 0.001 and total blocking time 0 ms in this local lab run. LCP remains above the skill's 2.5 s target; no field-performance claim is made.
- Production workspace automated accessibility audit: 100/100.
- Actual workspace screenshots were refreshed for the product tour.
