# A2UI in Trends

The job is to compare accepted batch values and process profiles while retaining the ability to inspect their delivery and export the underlying values. The integration uses the official React renderer (`@a2ui/react` and `@a2ui/web_core` 0.15.0), targeting A2UI protocol 1.0.

A simple alternative is to continue mounting the plots directly. The selected approach registers the existing scientific plots in a restricted A2UI catalog and mounts the comparison and profile charts as surfaces. A broader agent-generated workspace would require a separately reviewed transport, validation, and action contract; it is outside this change.

## Product constraints

- Easy to Start: existing parameter selection and deterministic API reads remain the entry point, without a model call or new configuration.
- Easy to Trust: measurements, identifiers, unit warnings, specification limits, and source links remain controlled by the host workspace. The catalog can select only a comparison or profile chart. It cannot invent measurements, load external content, or run code.
- Easy to Act: highlights, batch visibility, statistics, and the existing export handoff retain their behavior. No manufacturing actions are introduced.
- Easy to Adopt: no service, data migration, or system-of-record change. The renderer loads only on the client; initialization and rendering errors fall back to the native plots with a visible status message.

## Boundaries and trade-offs

`A2uiTrendChart.tsx` isolates loading and error recovery. `A2uiTrendSurface.tsx` registers `TrendChart` in `urn:biodemo:a2ui:trends:1`, creates a local surface using a standard `createSurface` message, and disposes its processor on unmount. Chart data and callbacks are supplied by React context from the authorized host. Each mounted chart owns its processor; data is not shared across workspaces or transmitted to an external A2UI service.

This is a local renderer integration, not an agent-generated chart transport. It deliberately preserves the current plot UI. It adds client bundle and dependency cost in exchange for an A2UI rendering boundary. New custom catalog components require reviewed implementations. External agents cannot currently submit surfaces.

Observe time until charts become usable, renderer fallback frequency, whether filters and highlight selections survive updates, and whether the visible batch selection reaches export correctly. These are evaluation measures, not claimed improvements.

References: [Built with A2UI](https://a2ui.org/built-with-a2ui/), [React renderer](https://github.com/a2ui-project/a2ui/tree/main/typescript/renderers/react), [client integration](https://a2ui.org/guides/client-integration/).

## Verification

TypeScript checking (`npm run lint`) passed. A headless Chromium check with three synthetic batches verified both A2UI charts, statistic changes, batch visibility, verified-delivery filtering, highlighting, and the export parameter handoff, with no page errors. A separate processor check confirmed both protocol surfaces can be created and disposed. Browser validation used local fallback font CSS because external font downloads were unavailable; this does not validate production typography or real manufacturing data.
