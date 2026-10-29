# Experimental fermentation transfer benchmark

Repository audit: docs/research/fermentation/repository-audit.md. Original literature sources and reviewed transcriptions are preserved with hashes in docs/research/fermentation/.

## What executed
Both cases executed through the existing model catalog, bounded deterministic runner, FlowService, versioned evidence and review records. No production write occurred.
Source extraction was reviewed manually. Autonomous raw-publication ingestion performance and engineering time savings have not been established.

## Sulfolobus
- 20L: predicted kLa 35.532h^-1 versus measured 40.5h^-1; error -12.3%. Source: Rastädter et al. (2023) Table2. Assumed sensitivity range 17.77–71.06h^-1, not a confidence interval.
- 200L: predicted kLa 25.410h^-1 versus measured 41.1h^-1; error -38.2%. Source: Rastädter et al. (2023) Table2. Assumed sensitivity range 11.59–59.27h^-1, not a confidence interval.

Source-only correlation does not identify receiver sparger/geometry response. Error is reported even when it challenges the model; characterize receiver water and broth kLa before relying on settings.
No 200 L viability measurement or biological forecast was invented. Source kLa is water characterization at 75°C. Full receiving characterization must establish broth effects, gassed power, sparger response and certified limits.

## Pichia
- Same-composition Henry saturation ratio at 100 versus 50 kPa gauge: 1.33041, using 101.325 kPa ambient.
- Under the recorded hypothetical flow/efficiency/price assumptions: oxygen-delivery cost difference $0.3407/h, or $40.89 over the common 120h basis. This is partial modeled cost, not experimental dollars or complete batch COGS. Methanol, occupancy and other excluded costs can reverse the result.
No measured kLa/OUR or calibrated Pichia kinetics: absolute oxygen transfer and mechanistic productivity validation are unavailable. Constant10L endpoint error is an empirical comparator only; changes in feeding, DO and biomass confound pressure effects.
Table 1 direct comparison is 30 L and uses different durations. Published 100 / 1,000 L Table 2 production summaries are held out; a constant 10 L endpoint comparator is explicitly empirical, not pressure-based kinetics. The 1,000 L / 112 h endpoint is not peak or harvest.

## Agent comparison and operational boundary
- sulfolobus: actual Prime adapter attempt = unresolved; scientific uplift, unsupported-recommendation count and human timing remain unavailable.
- pichia: actual Prime adapter attempt = unresolved; scientific uplift, unsupported-recommendation count and human timing remain unavailable.
The existing Prime harness, bridge, ingestion and native subagents are retained. No fake reports, fake model qualification or synthetic agent success are substituted. External retrieval/pretraining remain additional concerns for a published blinded score.
Blinded trials fail closed before starting an agent until provider-only network isolation is available; the existing filesystem boundary alone is insufficient.

## IndPenSim and optional industrial case
Existing IndPenSim integration is retained. The prior successful-prefix/failed-full-run feasibility gate remains authoritative; the previously isolated executable environment is absent on this host. No simulator was rebuilt and no new stress-run result is claimed. Bernemann is deferred until the two required cases and their scientific limitations have been reviewed.

## Sources
- Rastädter et al. (2023), https://doi.org/10.3389/fbioe.2023.1160012 and supplementary TableS1.
- Liu et al. (2016), https://doi.org/10.1038/srep18439, Methods and Tables1–2.
- Per-file SHA256, source locations, summary SD interpretations and source conflicts are in the research manifests.

## Required follow-up
Receiver broth kLa/OUR/DO characterization, rated motor/pressure/torque limits, replicated product and feed measurements, actual utility quotations, observed conventional-workflow timing, and qualified isolated Prime execution with blinded scientific review are needed before an incremental-agent efficiency or production-readiness claim.

## Recorded verification
See verification.json and ui/checks.json for the executed commands and scope. The platform/Prime regression run passed414 tests; the targeted fermentation suite passed14. Production build and real-API desktop/mobile browser checks passed.
The separate case-study regression run passed114 tests and skipped2. Four CHO checks fail because the recorded pilot and aligned-reference files are absent locally; the saved static report consequently differs and the series endpoint returns404. Those fixtures and case-study implementations were not regenerated or changed by this feature.
The existing parser indexed3 original PDF/DOCX files (1,495 observations) without extraction errors; scoped lexical retrieval verified9 excerpts against original files. These are parser/retrieval checks, not autonomous extraction accuracy or saved human effort.
