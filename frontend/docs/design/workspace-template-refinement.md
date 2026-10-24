# Workspace template refinement

The governing source remains [Main_Culture_andETHOS.md](../../../Main_Culture_andETHOS.md).

## Job and audit

A returning user needs to locate work, inspect actual measurements and uncertainty, and continue an appropriate next step. Screenshot review showed redundant eyebrows, slogans, large explanatory cards, repeated demo notices, and a layout that spread a small amount of information over too many surfaces.

The small alternative was to shorten copy inside the existing cards. The selected alternative changes the hierarchy: a light application shell, compact work list, factual sample row, source shortcuts, and a chart-led detail view with a narrow property column. Interpretation and action rationale expand on demand. No new library, purchased template, system integration, or data migration was introduced.

## References inspected

- [shadcn sidebar blocks](https://ui.shadcn.com/blocks/sidebar): light shell, grouped navigation, restrained borders and compact controls. Browser preview inspected.
- [Untitled UI application components](https://pkg.untitledui.com/react/application-ui) and [dashboard example](https://www.untitledui.com/react/components/dashboards-02/dashboard-01): page hierarchy, table controls and chart-led information display. Browser preview inspected.
- [Tailwind Application UI](https://tailwindcss.com/plus/ui-blocks/application-ui): application shells, lists and description-list patterns.

These inform proportions and presentation. The implementation uses the project's existing React, Radix, chart and workspace components; it does not install or copy a commercial template.

## Pillars and trade-offs

- Start: searchable work is immediately visible. New work accepts a goal and optional sample context. Saved-work entry now opens the editor directly.
- Trust: factual measurements, uncertainty, counterevidence and missing context remain visible. Source queries, rows and limits remain inspectable in place. Sample data and draft goals remain distinguished. A sample's availability is labeled Ready, not an invented review or approval state.
- Act: next steps stay attached to their work; review, progress and outcome records retain their existing separate states. Rationale and requirements remain available behind an explicit disclosure. Consequential changes are not executed.
- Adopt: familiar navigation and lists replace explanatory prose. Existing systems remain systems of record. Browser storage, recovery and export behavior remain intact. The supplied landscape and controllable motion remain in the sidebar.

The visual trade-off is less guidance by default. Field labels, empty states, source limits and review boundaries retain guidance where it is needed. A real list with one saved item remains a list with one item; the design adds no fabricated tasks, connections, activity or performance metrics to fill space.

Checks cover the actual paths: create/resume, landing handoff, filters, source inspection, chart and evidence views, interpretation disclosure, scoped follow-up, persistence, history, mobile overflow and animation preferences. These are functional checks and screenshot reviews, not a claim of user-study validation or measured time savings.
