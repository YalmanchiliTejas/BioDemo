# Paper flow: one surface for a question and its thread

Governing direction: [Main_Culture_andETHOS.md](../../../Main_Culture_andETHOS.md).
This note records the landing-page and workspace redesign that replaced the
white admin dashboard and the generic biotech hero. The landing now uses a dark
cinematic hero and architecture stage around a light product story.

## Job and context

A visitor needs to understand what the product does, see an actual product view,
and start with a useful question. A returning user needs the current work, its
source context, its open questions, and the next reviewable step without moving
between dashboard modules.

The redesign therefore treats the landing page and the workspace as one product
surface. It does not add a new route, a new data source, an analysis engine, or a
new dependency. Existing browser-local persistence, export, source inspection,
review history and scientific tools remain the systems of record for this demo.

## Design direction

- **Assay blue, culture lime, bone.** Bone paper (`#eeeee7`), near-black ink
  (`#121418`), cobalt (`#2438d4`) as the single action accent, and a culture-lime
  signal (`#d8f45f`) used only as a highlighter, connector or data mark. Oxide
  (`#a64022`) is reserved for uncertainty, warnings and negative deltas. Lime is
  never body text on bone. Manrope carries prose; IBM Plex Mono marks
  identifiers, counts and small labels.
- **Two dark stages, one light middle.** The hero and the architecture section
  are full-bleed night surfaces; the product story between them stays on bone
  paper. The dark navigation ties the stages together without turning the whole
  page into dark mode. The architecture is a normally scrolling system map with
  scroll-linked depth, not a pinned screen.
- **The landscape is a stage, not a card.** On the landing page the supplied
  landscape is the full-bleed hero background, duotoned into the assay palette
  and darkened behind the copy. The sample thread is a glass data panel with the
  result, reference line and next step; the photograph is no longer a random
  object inside the thread. In the workspace, the landscape remains contained in
  the Home sample aside.
- **Depth without a pinned screen.** The hero field, sample panel, architecture
  field and architecture plate move at different rates using CSS scroll
  timelines. The architecture steps and map scroll together in normal flow; an
  IntersectionObserver marks the active layer, and the lime handoff packet moves
  once as that layer becomes active rather than looping. The motion is
  transform/opacity work, and the existing pause control and reduced-motion
  preference stop the ambient, scroll and packet animations.
- **The question stays open.** Home keeps the goal composer inline and always
  visible instead of opening a separate editor. A sample thread sits beside it so
  a first-time visitor can see what a completed thread looks like without a
  fabricated dashboard. Below the composer, Home becomes a two-column workbench:
  saved work on the left, and sources plus the demo boundary on the right.
- **The thread replaces tabs.** Work detail uses a vertical rail numbered 01–05
  for Overview, Evidence, Trends, Next steps and Notes. The rail keeps position
  and counts visible while the reading surface changes. On narrow screens it
  becomes a horizontally scrollable strip above the content.
- **Open surfaces over nested cards.** Evidence rows, claims, notes, source
  scopes and work rows are separated by hairlines and spacing. Raised paper is
  reserved for the current result, action records and source connection cards.

## Alternatives and trade-offs

| Decision | Simpler alternative | Why this choice | Trade-off |
|---|---|---|---|
| Horizontal top navigation | Keep the 232 px sidebar | Removes the admin-dashboard frame and gives the work a wider reading measure. | Recent-work shortcuts move into the mobile drawer; the top bar has less room for many links. |
| Inline composer on Home | Keep a separate new-work screen | Starting is one step, and the saved work stays visible underneath. | The first viewport carries more content, so the hero must stay compact. |
| Vertical thread rail | Keep top tabs | Shows sequence and counts without hiding the current reading context. | Uses a column on desktop; collapses to a scrollable strip below 900 px. |
| Full-bleed landscape hero | Keep the landscape contained in a sample card | The image now acts as a stage behind the headline and composer; the sample thread becomes a data panel instead of a random photograph. | The background needs heavy duotone and dark overlays for contrast, so the hero is darker than the rest of the page. |
| Bone and cobalt surfaces | Warm paper and green | Moves the brand away from the default biotech palette and toward a lab-instrument language. | Cobalt is a stronger accent; it needs disciplined use on actions and links so it does not become decorative noise. |
| Two dark stages (hero and architecture) | Keep the hero light and darken only architecture | Frames the light product story and makes the landscape purposeful rather than decorative. | The page has two inversions; the light middle has to carry most of the editorial reading. |
| Normally scrolling architecture map | Pin the map while the steps pass | The page never takes control of the viewport; the reader can move through the section at their own pace. | The map can leave the viewport while the last step is read, so the steps are compact and the map keeps all three layers legible at once. |
| CSS scroll-driven parallax plus a step observer | A JavaScript scroll listener | No per-frame React state and no scroll handler; the browser can keep the visual work on the compositor, while the observer only updates when a step crosses the reading band. | Browsers without scroll-timeline support see a static hero and architecture; the content and hierarchy remain complete. |

No claim is made that this visual direction improves task time or comprehension.
Those would require user study and real-world measures.

## Four pillars

- **Easy to Start.** The landing hero and Home both expose the same composer with
  examples and a starting-context selector. The landing handoff carries the exact
  draft text; Home accepts it without creating work or running analysis. The top
  bar keeps **New work** visible at every width; below 560 px it becomes a labelled
  icon button.
- **Easy to Trust.** The sample thread keeps the 1.74 g/L result, the −18%
  comparison, the 27 h DO departure and the unresolved cause together. Evidence,
  counterevidence and gaps remain inspectable; source cards state access scope,
  retrieval time and known limits. Sample and browser-local boundaries remain
  visible in the UI.
- **Easy to Act.** Next steps retain owner, rationale, expected evidence,
  constraints and review history. Review records are local; the interface does
  not grant QA approval or execute a plant action.
- **Easy to Adopt.** The landing page states the reference architecture
  directly: systems of record feed a browser-local workspace, and people keep
  review authority. The workspace context strip keeps the site, sample mode,
  read-only snapshots, browser-local storage and human review visible above every
  view. The boundary panel separates what is simulated here from what a real
  deployment would require, and a direct link opens the sample source boundary in
  the workspace. The existing React/Radix structure, routes, keyboard tabs,
  storage recovery, export paths and scientific tools are unchanged. The new
  layer is CSS plus a small amount of React state and one observer; no library or
  backend was added.

## Implementation notes

- `frontend/src/os/flow.css` is imported last in `Hub.tsx`. It restates the
  workspace tokens and layout so the older `os.css` and `workspace-flow.css`
  layers remain available to the scientific host tools.
- `WorkspaceShell.tsx` uses a horizontal `nav` named “Manufacturing OS”, a
  mobile dialog drawer, and a compact context strip above every workspace view.
  Recent work and the demo boundary live in that drawer.
- `Home.tsx` keeps the composer inline, limits the hero height, and places the
  first work row above 800 px at 1440×1000. The sample aside uses the existing
  `Atmosphere` component and adds the 27 h / 48 h / next-step sequence and source
  chips. Below it, saved work and a sources/boundary rail form the workbench.
- `Landing.tsx` adds the dark hero with the glass sample panel, the dark
  navigation, the normally scrolling architecture (three step articles beside a
  map plate), and the boundary panel. The four-pillar product tour was removed.
  `landing.css` owns the palette, the dark stages, the duotone hero, the map
  plate, the handoff packets, and the `@supports (animation-timeline: view())`
  depth rules. There is no scroll listener and no per-frame React state; a
  dedicated IntersectionObserver updates the active architecture step, and
  `data-motion="still"` removes the depth, scan and packet animations when the
  existing pause control is active. The section uses `overflow: clip` so the
  view timeline tracks the page rather than a hidden scroll container.
- `WorkDetail.tsx` exposes exact accessible names for the five work tabs and
  preserves arrow-key navigation, URL state and reload/history behaviour.
- `GoalComposer` and `WorkflowGallery` use the shared paper/pill styles; the
  landing-specific overrides turn the composer into a dark glass panel with a
  lime action, and the mobile toolbar stacks the context selector above the
  full-width action.
- `capture_product_previews.cjs` remains a utility for capturing actual
  workspace views. The landing page no longer renders a product-tour panel.

## Verification

Run against a local Vite server:

- `npm run build` — TypeScript and production build pass.
- `check_reference_refresh` — handoff, workflow filters, removal of the
  four-pillar tour, responsive overflow and draft recovery pass.
- `check_workspace_flow` — Home visibility, work tabs, evidence inspection,
  reload/history, action scoping and 320–1440 px layouts pass.
- `check_ethos_workspace` — notes, export, context attachment, proposal/review
  history, search, mobile drawer and storage recovery pass.
- `check_workspace` — shell navigation, optional assistant, host tools, tablet
  scrolling, mobile overflow and landing source rows pass.
- `check_atmosphere` — ambient motion runs, pauses offscreen, freezes on request,
  honours live reduced-motion changes, and causes no repeated layout in the
  sampled trace.
- `check_landing_depth` — the hero field and sample panel change transform after
  a 500 px scroll; reduced motion removes those transforms and hides the scan
  line and data packets; the architecture has three steps, three map layers and
  two handoffs; each step becomes active as it is centered; the architecture
  field and plate change transform at different rates while the page scrolls;
  the map is not sticky; both boundary states are present; the four-pillar tour
  is absent; and the landing page has no horizontal overflow from 320 to 1440 px.
- The hero and architecture were also checked visually at 1440, 1200, 1024, 900,
  768, 390 and 320 px for hierarchy. Below 900 px the architecture map moves
  above the steps and the layers stack. The section states the demo boundary
  rather than claiming a live integration.
- The workspace was checked at 1440, 900, 768, 390 and 320 px. The context strip
  wraps below 767 px, the workbench becomes one column below 900 px, and the
  first work row remains above 800 px at 1440×1000.

Two older assertions were updated because the redesign intentionally removed
their DOM: `check_workspace` now checks the visible LIMS/MES source rows instead
of the retired source tablist, and `check_atmosphere` scrolls to the current
thread section instead of the retired trust grid. Their intent — source content
is present, offscreen motion pauses, and revealed content is readable — is
unchanged. The hero/architecture refresh updated `check_landing_depth` for the
new hero and normally scrolling architecture, and `check_reference_refresh` to
assert the removed product tour and accept the stacked mobile composer toolbar as
a non-overlapping layout.

These checks verify implementation behaviour in a local browser. They are not a
user study, an accessibility certification, or evidence of production readiness.
