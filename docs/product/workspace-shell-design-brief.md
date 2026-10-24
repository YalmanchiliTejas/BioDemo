# Design brief: workspace navigation / shell

Status: draft for concept exploration. Not an approved design.
Scope: the persistent chrome around work — topbar, navigation, mode truth, assistant
entry, command palette. Not the content of individual views.

## 1. Job to be done

A manufacturing or quality user opens the workspace mid-task and needs three things
answered before reading anything:

1. **What am I looking at, and can I trust it?** Sample data or connected server data,
   which site/tenant, acting as whom, with what roles.
2. **What already needs me?** Work in flight, items awaiting review or approval.
3. **How do I start or resume something?** Without relearning the product each time.

The shell is not decoration. It carries the two claims the product can least afford to
get wrong: *what mode am I in* and *who is acting*.

## 2. Current implementation

| Concern | Where it lives now |
|---|---|
| Navigation | `ws-topbar` + `ws-primary`, five destinations from `View` in `WorkspaceShell.tsx` |
| Mobile navigation | same `links` array rendered in a Radix `Dialog` drawer via `navContent` |
| Mode / identity | `ws-contextbar`, below the topbar, outside the topbar's visual weight |
| Search | `cmdk` palette, `⌘K`, groups: Go to / Saved work / Start |
| Assistant | right-hand `aside`, toggled by `ws-assistant-toggle` |
| Starting work | three entry points: `New work` button (rendered twice), palette, `work-entry.ts` cards |

Layout is a single-column grid with a 64px topbar (`.ws-shell`). The sidebar markup is
mobile-only, so desktop and mobile are two different navigation surfaces kept in sync
only by sharing the `links` array.

## 3. Observed tensions

These are the problems worth designing against. They are observations from the code,
not user research.

- **Trust lives in the quietest strip.** Sample-vs-server, tenant, actor, roles and
  auth mode are rendered as small `ws-contextbar-optional` text. Meanwhile the agent
  toggle sits in the topbar at equal weight to Search. The visual hierarchy is inverted
  relative to the pillars.
- **Three nouns, no visible difference.** `Saved work`, `Work queue` and `Actions` are
  peers in the nav, but their distinction is only inferable from the data model
  (`WorkItem` vs `WorkAction` with `ActionStatus`). A first-time user cannot predict
  which one holds the thing they are looking for.
- **Long-running work is invisible.** Nothing in the shell shows that work is running,
  blocked, or awaiting approval. The only ambient signal is a count on `Saved work`.
  For a product about resumable work, the shell is silent about state.
- **The agent is a sidecar.** `Assistant` opens a right rail. It is one of four ways to
  start, and the only one that implies a chat-first model.
- **Duplicate start affordance.** `New work` appears in both the drawer and the topbar,
  with different markup and icon sizes.
- **Queued vs proposed is unresolved in the chrome.** `ActionStatus` distinguishes
  `proposed` from `reviewed`; nav does not.

## 4. Invariants any direction must preserve

Non-negotiable, because they encode the four pillars:

1. Sample mode vs server mode is unmistakable without hover, click, or scrolling.
2. Acting identity, tenant, and roles are always recoverable in one glance or one click;
   auth mode stays accessible.
3. Human approval boundary is visible wherever actions are proposed; nothing in the
   chrome may imply an agent's proposal is approved.
4. Read-only vs writable state is never ambiguous.
5. Every nav destination maps to an existing `View`. Do not invent destinations the
   model cannot serve.
6. No fabricated counts, no placeholder "3 items need review" that is not computed.
7. `⌘K` search keeps working with correct focus trapping and restore.
8. `aria-current="page"` on the active destination; the mobile drawer restores focus to
   its trigger.

## 5. Directions to explore

### A. Status-forward topbar (simple)

One topbar, rebalanced. Mode truth becomes a persistent chip with a fixed position
instead of muted body text. Work-in-flight gets a nav entry with real counts
(needs review / blocked / running). Assistant toggle demotes to contextual — visible
only where an artifact exists to discuss.

- Cost: low. Mostly CSS and one derived-count selector.
- Start: yes. Every destination is already in the topbar and reachable in one click.
- Trust: yes. Mode moves from footnote to chrome.
- Act: partial. Surfaces pending review, still no outcome tracking in the chrome.
- Adopt: strong. Nothing moves; familiar shape survives.
- Risk: crowded topbar at ~1000–1180px, where labels already collapse.

### B. Two-rail workspace (ambitious)

Left rail carries durable structure (work, queue, actions, sources) and expands on
demand. Right rail becomes an **activity ledger** — an append-only list of what the
agent did, what it proposed, and what a human decided — replacing the chat sidecar as
the default. Center is the artifact. Chat becomes one input to the ledger rather than
its container.

- Cost: high. Real component work, plus a source of activity events that does not fully
  exist today (`ActionEvent` covers actions only).
- Start: neutral. Adds structure up front, but the rail is collapsed by default.
- Trust: strongest. The ledger *is* the audit trail, visible by default.
- Act: strongest. Proposed → reviewed → in progress → outcome is legible in chrome.
- Adopt: weaker. A second permanent rail is new operating territory for enterprise
  users; needs a story for narrow screens.
- Risk: inventing an event model before the runtime produces one. If the ledger can be
  empty, it must look intentionally empty, not broken.

### C. Query-first shell, navigation emergent (radical)

Collapse persistent navigation to a composer plus recent artifacts. Destinations appear
in context. Lowest chrome, highest novelty.

- Cost: medium to build, high to learn.
- Start: excellent for a returning user with a question in mind.
- Trust: worse. Less persistent surface for mode and identity.
- Adopt: worst. Removes the anchors enterprise users use to orient.
- Verdict: keep as a thought experiment, not a direction. It optimizes the first
  minute at the cost of the twentieth.

## 6. Recommendation

Prototype **A** and **B** against the same three scenarios, and let the comparison be
about the ledger, not the styling:

- cold open with two items awaiting review;
- resuming a long-running investigation after a day away;
- an action moving from proposed to outcome recorded.

A is the likely shipping shape. B is worth building if the ledger can draw on real
events — otherwise it becomes a decorative audit panel, which is worse than none.

## 7. Measures

Chosen to be observable in a usability session, not aspirational:

| Question | Measure |
|---|---|
| Can users tell what data they are looking at? | % correctly stating sample vs server mode on first screen, no click |
| Can users find pending work? | Time from open to locating items needing review |
| Is the nav vocabulary learnable? | % correctly predicting where a given item lives, after 30s exposure |
| Does the shell imply false authority? | Any participant believing a proposed action was approved |

## 8. Guardrails for generated concepts

If concepts come from a generative design tool (MagicPath or similar), they must be
treated as proposals and evaluated against §4. Specifically, reject output that:

- invents metrics, counts, or charts the product does not compute;
- presents a clean dashboard as if it were measured evidence;
- hides sample/server mode, roles, or approval state below the fold;
- drops the distinction between proposed and approved;
- adds nav destinations with no model behind them.

Harvest structure and layout ideas. Rebuild in the existing component vocabulary
(`os/` shell, Tremor where the data views already use it). Do not paste generated code
into this codebase.

## 9. Prompt pack

Self-contained prompts, one per direction. Send after the MCP server is connected.

**A**

> Desktop workspace shell for a pharmaceutical manufacturing intelligence product, not a
> demo dashboard. 1440×900. Top bar only, 64px: product mark, five nav destinations
> (Workspace, Saved work, Work queue, Actions, Sources), one primary "New work" action,
> search, and a compact status chip reading "Sample data · read-only". Below the top bar
> a thin context strip: site, acting user, role, connection state, and a link labelled
> "Human approval". Counts appear only on Work queue and Actions. No KPI cards, no
> charts, no invented numbers. Muted paper background, dense but calm typography, one
> accent colour used only for the mode chip and the active nav item. Show an empty state
> where the main region would be.

**B**

> Three-column workspace shell for a pharmaceutical manufacturing intelligence product at
> 1440×900. Left rail 220px: workspace identity, "New work", then destinations Workspace,
> Saved work, Work queue, Actions, Sources, with counts only where meaningful. Centre:
> an artifact area, empty state. Right rail 320px: an activity ledger, a chronological
> list of entries each labelled Observation, Proposal, or Human decision, with actor and
> timestamp; the newest entry is a proposal awaiting review with an explicit "awaiting
> human approval" marker. Bottom of the ledger: a single-line input, secondary. Paper
> background, restrained colour, no charts, no fabricated statistics, no decorative
> gradients. The ledger must look intentional when empty.

**Variant to compare**

> Same as the two-rail layout but collapsed to a single top bar at 900px wide, showing
> how the ledger becomes a drawer and how sample/read-only mode stays visible.
