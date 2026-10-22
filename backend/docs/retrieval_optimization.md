# Retrieval optimization and measured limits

The existing RLM, ingestion, deterministic analysis, scoped DuckDB view, evidence IDs and source verification remain in place. This change concerns retrieval; it does not establish a five-minute investigation runtime.

## Baseline diagnosis

The CHO-04 run `7113f26854294d139a4eb6ad242a05a2` recorded seven search calls totaling **208.502 seconds**, 26 query calls totaling 74.685 seconds, and 11 calculation calls with nine failures. These are operation sums, not a critical-path decomposition: children overlap and bridge calls can wait for its shared lock. Of the 52 tool events, four occurred after the 48-call budget was consumed. Counting attempted events differs from counting budget-admitted calls. Retrieval changes do not change that budget policy.

The old lexical implementation scored substring matches against `name`, `value_text` and `entity_id` across the complete unpivoted observation collection, then sorted by score and ID. Even a negative narrative query opened structured Parquet partitions, unpivoted measurements and tested numeric strings. The multiword query about assay/sample holding time returned `Time (h)` observations. The question about vessel/design returned Time, Status and dissolved-CO2 cells through reactor identifiers. These were literal matches, not narrative answers.

A source-only replay of the same seven searches at limit 10 took **143.383 seconds** (one trial, local conditions). EXPLAIN ANALYZE of the negative `contamination` search confirms Parquet scans and UNPIVOT work; its measured query execution was 4.37 seconds. The saved plan includes no hidden reference answers. The original SDK logs account for the final gap: children completed around 07:22; the lead assembled a 90-fact report, first submitted at 07:25:55, received a source-value validation error at 07:26:24, and resubmitted at 07:26:54 immediately before cancellation. That is report synthesis/correction, not continuing ingestion. This retrieval change does not claim to eliminate that orchestration gap.

## Implementation

`search_evidence` retains `query`, `mode`, `limit`, `offset`, `records` and `evidence_ids`. Additional optional fields are documented in the skill and bridge context.

- **Exact:** observation IDs use existing batched ID resolution, including legacy IDs. Source and entity identifiers route to scoped structured retrieval.
- **Structured:** source/sheet/column selection happens before UNPIVOT, and entity/physical-row predicates enter the Parquet relation before expansion. Time bounds apply to actual source-associated clocks. Original names, units, Mean/SEM distinctions and locations are retained; clock-cell IDs are returned for citation. Unknown names remain queryable by exact original header. Numeric aggregations and complex predicates remain the responsibility of the restricted `query_data` tool.
- **Narrative:** local `retrieval.sqlite` persists an FTS5/BM25 index of nonnumeric prose from document and mixed/string columns. Numerical cells, identifiers, timestamps and routine Status columns are excluded. Status remains intentionally retrievable with `metric="Status", evidence_type="structured"`; exclusions are not assertions that those records are unimportant. Empty text search results describe the indexed narrative collection, not the health of the process.
- **Semantic:** the optional existing fastembed model embeds only authorized narrative chunks. SQLite stores float32 vectors with evidence IDs, model IDs and text hashes. Unchanged vectors are reused across calls and tool instances; changed chunks are re-embedded. Query vectors are computed per search. Hybrid retrieval uses reciprocal-rank fusion (constant 60), with ID tie-breaking. No vector database or additional infrastructure is introduced. Similarity remains a retrieval heuristic, not scientific evidence.
- **Schema:** conservative terminology aliases resolve source headers without converting or merging values. Ambiguous bare DO headers remain unmapped without confirming units. The schema cache is bounded and keyed by metadata version/stat, scopes and cutoff. Stable orientation samples spread across sources/series and select endpoints/extrema as well as ordinary anchors. Samples are capped at 1,000, so they are orientation rather than exhaustive coverage; full data remain queryable.

The text index updates by source/content/version changes, including Parquet metadata and file stats and legacy textual observations. Removed/replaced source versions lose their text entries; unchanged embedding hashes survive. Source membership, scope, record availability and source availability are checked before ranking returned narrative candidates, and results pass through existing scoped evidence resolution. Future text is never embedded for an earlier-cutoff request. Metadata caches include scope and cutoff. A local index can hold future authorized source records internally; those records are excluded from historical retrieval. No unrestricted SQL is exposed.

Search diagnostics report route, counts, schema/index/ranking/lookup durations, structured database setup/execution/materialization, CPU time and process peak RSS. Trace events retain these numeric diagnostics without source text, prompts or tokens. Database rows scanned are explicitly unavailable in production diagnostics; saved offline EXPLAIN ANALYZE plans provide query-plan evidence. Process peak RSS is not per-call incremental memory.

## Measurements

Artifacts: `results/retrieval/baseline.json`, `routed.json`, `structured-checks.json`, and the two `routed.*-plan.txt` files.

| Measurement | Before | After |
|---|---:|---:|
| Seven original searches, local replay | 143.383 s (one trial) | 0.165 / 0.117 / 0.114 s (three trials) |
| Search p50 / p95, after | — | 0.0163 / 0.0207 s |
| VCD, source/entity/time-filtered, 20 rows | 1.808 s unpruned scoped SELECT | 0.276 s |
| Glucose, same filters, 20 rows | 1.533 s unpruned scoped SELECT | 0.053 s |
| DO, same filters, 20 rows | 1.688 s unpruned scoped SELECT | 0.625 s |

The structured comparisons measure equivalent source-derived queries and identical returned IDs. The narrative comparison intentionally changes retrieval semantics: irrelevant numeric matches are no longer narrative candidates. It is not a claim of identical general lexical recall. Empty narrative results are fast because CHO's text columns are categorical Status fields, which require structured retrieval. The first routed replay may reuse a persisted index from a previous test; CHO's initial empty-index build was also measured under 0.1 seconds, but text-heavy cold-build performance is not established. Baseline and optimized trials did not use identical concurrent workloads, and the old baseline has only one local repeat. Reported times are observations, not universal speedup guarantees.

All three structured probes returned the same IDs as independent unpruned scoped queries and passed original-source checks for one representative each. All 12 retained original source hashes match ingestion metadata. The regression suite passed **90 tests with 2 skipped**; the final retrieval-focused run passed **9 tests**. Synthetic tests cover ranking, numerical filtering, text within mixed numeric columns, index invalidation, persisted embeddings, canonical aliases, deterministic samples, exact locations, scopes, cutoffs and SQL restrictions. No live model investigation was rerun for this retrieval change. End-to-end runtime, model tokens, scientific completeness, critical evidence recall and relevance precision remain **unscored**; CHO has no independent relevance judgments for these seven queries. No quality threshold or human-effort saving is invented.

## Reproduce

```sh
export STORE=benchmarks/runtime/benchmark-case-7113f26854294d139a4eb6ad242a05a2/state/store
PYTHONPATH=. .venv/bin/python scripts/profile_retrieval.py --store "$STORE" --scope evaluation --as-of 2026-10-17T07:11:56Z --legacy --repeats 1 --output results/retrieval/legacy-repeat.json
PYTHONPATH=. .venv/bin/python scripts/profile_retrieval.py --store "$STORE" --scope evaluation --as-of 2026-10-17T07:11:56Z --repeats 3 --explain --output results/retrieval/routed-repeat.json
PYTHONPATH=. .venv/bin/python scripts/check_structured_retrieval.py --store "$STORE" --scope evaluation --as-of 2026-10-17T07:11:56Z --output results/retrieval/structured-repeat.json
.venv/bin/python -m pytest -q tests/test_retrieval.py tests/test_columnar_ingestion.py tests/test_manufacturing_data.py
```

The profiler reads only agent-source metadata/partitions and writes diagnostic artifacts; it does not read scoring references, invoke models or modify source workbooks. The structured checker is a CHO measurement probe using general metric aliases, not a benchmark-specific agent rule.

## Remaining work

A new isolated RLM trial is needed to measure retrieval recall and final report completeness together. Specialist budgets, synthesis cost, calculation-error recovery, checkpointing and early report validation are separate bottlenecks. Semantic persistence was tested with a deterministic local embedding stub; actual bge-small latency, retrieval quality and model download behavior have not been benchmarked. Semantic ranking still scans authorized narrative vectors locally and should be profiled before scaling to large text corpora. Site-approved quality thresholds, triage rules and human approvals remain required as before.
