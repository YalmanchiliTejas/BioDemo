# Measured results — October 25, 2026

**The system has not yet demonstrated autonomous, scalable, evidence-grounded
investigation.** The implemented benchmark runs end to end for deterministic
methods, exposes scaling/precision failures, and preserves real model/simulator
blockers. No completed Prime investigation or optimization gain is claimed.

## Functional synthetic investigation: 100 files

Corpus seed 417, scenario seed 718, version `fictional-manufacturing-v2`.
100 files, 96 available by July 1, 2024; four future documents physically withheld.
Each execution indexed **94/96 = 97.92%**, reported one deliberately corrupt
spreadsheet and preserved one unsupported export. No eligible file disappeared
silently. All available critical files were parseable in these functional tasks.

| Question | Method | Critical span recall | Retrieved-file precision | Counterevidence recall | Affected precision / recall | Tool calls | Wall s |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Microbiological | Keyword rules | 0% | 0% | 0% | unknown / 0% | 2 | 34.54 |
| Microbiological | Linked rules | 100% | 28.57% | 100% | 50% / 100% | 18 | 19.32 |
| Transfer pressure | Keyword rules | 0% | 30.77% | 0% | unknown / 0% | 2 | 17.67 |
| Transfer pressure | Linked rules | 100% | 30.77% | 100% | 50% / 100% | 17 | 22.13 |
| Procedure change | Keyword rules | 0% | 0% | 0% | unknown / 0% | 2 | 19.69 |
| Procedure change | Linked rules | 100% | 23.53% | 100% | 50% / 100% | 20 | 43.83 |
| Inconclusive | Keyword rules | 0% | 100% | 0% | unknown / 0% | 2 | 17.11 |
| Inconclusive | Linked rules | 100% | 20% | 100% | 50% / 100% | 22 | 34.99 |

Receipt: [functional-100.json](results/functional-100.json).
These are **no-model baselines**, not agent results. Linked rules recover source
observations but produce no causal hypotheses (0% exact contributor coverage on
the three conclusive families). They include comparator batches as affected,
which explains their 50% scope precision. Zero structured assertions of verified
causality and correct abstention do not imply a scientifically adequate investigation.

All completed functional runs had 100% accessible source-path validity and
physical-location completeness, with zero future-source citations. This measures
references, not scientific claim validity. Actual hidden-key/raw-root/generator
read probes passed under inherited OS restrictions.

## Controlled distractor growth

The **same 100 source files** and critical spans are preserved byte-for-byte;
the 1,000/10,000-file corpora add only distractors. Scaling seed 912.
The table is for the identical microbiological objective and cutoff.

| Files | Method | Indexed / available | Critical span recall | File precision | Counterevidence recall | Tool calls | Wall s |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 100 | Keyword rules | 94 / 96 | 0% | 0% | 0% | 2 | 34.54 |
| 100 | Linked rules | 94 / 96 | 100% | 28.57% | 100% | 18 | 19.32 |
| 1,000 | Keyword rules | 994 / 996 | 0% | 0% | 0% | 2 | 285.86 |
| 1,000 | Linked rules | 994 / 996 | 75% | 14.29% | 100% | 26 | 138.89 |
| 10,000 | Linked rules | 3,213 indexed at termination / 9,996 available | not evaluated | not evaluated | not evaluated | unknown | 251.18 |

Receipts: [controlled-1000.json](results/controlled-1000.json),
[stress-10000.json](results/stress-10000.json). The stress worker exceeded its
180-second budget; total wall time includes staging/probes/termination. At
termination, the registry contained 3,213 indexed, four pending, one corrupt and
one unsupported source. Remaining files were not all registered. **Discovery and
investigation scores were withheld**, not filled with zeros or assumed success.
Wall times are single measurements on a shared development host with concurrent jobs, not isolated speed comparisons or confidence intervals. No model/API calls occurred in these rules methods; actual local compute dollars
and evidence per dollar are unmeasured.

In the final controlled 1,000-file linked run, the missed critical source was
`03/227e64b47102f2f60d56.pdf`, which contains the post-repair negative-culture
observation. It deeply inspected 21 unrelated sources. Affected recall remained
100%, but precision remained 50%. Missing critical evidence still makes this an
unsuccessful investigation.

The pre-JSON run achieved 50% span recall and missed the contradictory JSON
record. Routing flat JSON arrays through the existing typed pipeline improved
span recall to **75%** and counterevidence recall to **100%** on identical source
bytes. Earlier receipts are preserved as `pre-json-*.json`; timing variation is
not interpreted as a parser speed improvement on this shared host.

An earlier independently generated 1,000-file corpus tested every family before the flat-JSON extension:
both methods missed all critical sources/spans across all four questions after
the retrieval fixes. Ingestion still indexed 994/996 with the same two deliberate
failures. See [independent-1000.json](results/independent-1000.json). That corpus
changes source layout/formats as well as size, so it is reported separately from
the controlled growth experiment.

## Extraction and standalone directory entry point

[Independent structured checks](results/extraction-check.json): **292/292 fields**
in 24 systematically selected CSV/XLSX/Parquet files matched original source
values, units and coordinates. CSV/openpyxl/pyarrow readers independently checked
the ingested store. This is **not** full-corpus, OCR or scientific validation.

The natural-language directory command was also executed before the final JSON extension, without a case manifest
or evaluator labels. It completed ingestion/discovery through the existing
isolated worker. Inspect the complete [directory investigation and decision trace](results/directory-investigation.json):
96 discovery/format records, explicit extraction failure, searches, source
inspection/deprioritization, cited source spans, scope and limitations.
It used 18 tool calls, zero model calls, 5.95 s worker wall time, 6.35 CPU seconds
and a 401,866,752-byte worker high-water RSS. Parallel/native numerical threads
can make CPU time exceed wall time. Compute dollars remain unknown.

The final-pipeline [complete investigation trace](results/investigation-trace.json) additionally contains typed JSON record/field citations. Example inspected critical observations are the matching isolate results in
`03/22563fa726c8c775345c.parquet`, the sampling-manifold defect in
`06/8059f0ee57309e1c663d.csv`, and the contradictory media-lot evidence in
`04/60ffd3cc62bc3c162293.json`. These are **fictional factory observations**, not
Sanofi records or proof of a real root cause. Full source coordinates and evidence
IDs are in the trace, and original bytes can be opened in the local case-study view.

## Actual model attempts

| Method | Executed outcome | Quality / billed usage |
| --- | --- | --- |
| Full Prime/RLM | Configured `prime-inference/z-ai/glm-5.3` returned HTTP 402 insufficient balance; no investigation completed. | not evaluated / unknown |
| Bounded Prime, SDK depth 0 | Same provider billing failure; isolation passed. Attempt used the initial v1 corpus, disclosed in its receipt. | not evaluated / unknown |
| Conventional RAG | Existing OpenAI adapter failed credential preflight: no `OPENAI_API_KEY`; no model call executed. | not evaluated / no call; total compute cost unknown |

Inspect [agent attempts](results/agent-attempts.json),
[bounded attempt](results/bounded-agent-attempt.json),
[full provider error](results/full-provider-error.txt) and
[bounded provider error](results/bounded-provider-error.txt).
There is **no complete successful AI investigation trace** to hand off. A failed
agent is not relabeled as a deterministic agent, and no baseline inference scores
or token/cost savings are invented.

## IndPenSim historical measurements

All **100 files / 113,935 rows** for the selected 14 variables ingested; the store
contains **2,050,830 observations**, including source-row/time metadata. The first
uncached ingestion took 6.653 s. The saved latest run is an incremental replay:
100 unchanged files, zero new indexed files, 0.577 s ingestion. It explicitly
reports 100 currently indexed sources rather than miscalling the replay a failure.
All **112 sampled original values** in eight batches matched the ingested values.
These checks cover selected rows/variables, not every point or all Raman channels.

| Historical fault screen | Measured value |
| --- | --- |
| Recall against publisher fault batch flags | 5 / 10 = 50% |
| Precision | 5 / 11 = 45.45% |
| False-positive batches | IP-007, IP-039, IP-061, IP-067, IP-073, IP-075 |
| Missed fault batches | IP-091, IP-095, IP-097, IP-099, IP-100 |
| Fault-onset interval accuracy | not evaluated |
| Prime investigation / causal accuracy | not evaluated |

The predeclared screen compares full-batch means against robust recipe-group
statistics; it is intentionally limited. It can miss transients and confuse
controller strategy with a fault. Full-trajectory min/max/mean/final-observed
values and final concentration associations are saved with numerical query
specifications in [the historical receipt](results/indpensim-historical.json).
For example, mean dissolved oxygen and final observed penicillin concentration
have descriptive Pearson r = −0.3314 across 100 batches. This confounded
association is **not causal evidence or an optimization recommendation**.

An early checker compared against the lexicographically first evidence ID, which
was physical row 1000 rather than row 2, and falsely reported 14.29% value accuracy.
The checker was corrected to bind exact physical rows and batch the reads; the
source data was never altered. The final 112/112 check is separately stated from
that discarded checker result. This illustrates why evaluator logic needs review.

## Simulator feasibility

The real isolated simulator installation executed matched seeds 1/2, repeats and
a bounded +1% feed change at 20 h, using both exposed solvers: **12 episodes**.
The native solver develops invalid states at 134.2/135.4 h; alternate SciPy runs
exceed their 12-second episode budgets. Valid-prefix repeats agree. A valid
feed change at 20 h changed observed dissolved oxygen from 11.18296119 to
11.17108214 mg/L in seed 1, establishing a simulated response, **not improvement**.

**0/12 valid full-batch outcomes. Feasibility gate failed; optimization remains
`not_evaluated`.** See [simulator gate receipt](results/simulator-gate.json),
[environment receipt](results/simulator-environment.json) and the
[full feasibility report](indpensim_feasibility.md). No terminal concentration
gain, yield gain, valid controller ranking or GMP improvement is claimed.

## Regression and demo verification

Executed the command in [implementation.md](implementation.md): **116 passed,
2 failed in 87.58 s**. The failures are exactly those found before implementation:
missing recorded CHO Prime pilot, and stale committed comparison HTML (0 vs 7
recorded attempts). Existing Fresenius/CHO definitions and report artifacts were
not rewritten to hide them. The focused tools/runtime/simulator tests also pass.

`npm run lint` and `npm run build` pass. The static Next.js build includes all
36 existing/new pages and `/case-studies`. Browser inspection confirmed the real
results table, explicit failed model rows, source links, both case-study tabs and
the process-variable comparison control. Interactive model success remains
unverified because billing is blocked; API package mismatch is regression-tested.
