# Benchmark methodology

## Shared execution boundary

All methods start with the same natural-language objective, eligible raw files
and July 1, 2024 availability cutoff. `benchmarks.autonomous.run` copies **every**
eligible file into `benchmark-case-*/agent_input`; it never selects by relevance.
Future source bytes are absent, not merely filtered in a prompt. The existing
`benchmarks.common.isolated_runner` executes the existing worker under inherited
macOS sandbox-exec restrictions. Negative read probes cover the actual answer key,
original raw root, source manifest, generator/evaluator code, legacy references
and an unrelated tenant canary. A failed boundary check withholds scores.

The evaluator reads labels only outside the worker. No generator or rubric code
is an agent import. Scored agent processes can read existing source/tool code,
their staged evidence and normal SDK authentication/configuration, but not the
evaluator tree. The runner records the failed nested-sandbox attempt separately;
successful scored trials require macOS sandbox-exec to start outside the enclosing
Codex sandbox. Linux requires an equivalent established isolation adapter; no
in-process substitute is treated as secure.

Existing `ManufacturingStore`, columnar ingestion, FTS5 retrieval,
`ManufacturingTools`, scope/cutoff enforcement, original-source verification,
Prime harness, SDK, native RLM and isolated worker are reused. No second agent
framework, vector store or ingestion pipeline is introduced.

## Comparison methods

Flat JSON record arrays remain in the shared columnar data plane with record/field
provenance and original decimal tokens. Nested JSON remains narrative and has not
been validated as a complete numerical schema. Corrupt JSON produces an explicit error.

| Method | Actual implementation and limitation |
| --- | --- |
| `keyword_rules` | Existing lexical evidence search; identifier extracted from the objective; at most 24 narrative hits plus scoped structured search. No LLM, causal reasoning or genuine agent autonomy. |
| `linked_rules` | Same tools, with one initial lexical hit per source, then deeper source inspection within 48 tool calls. Fixed deterministic exploration; not a bounded AI agent. Scope extraction intentionally exposes the weakness of including comparator identifiers. |
| `directory_rag` | Same extracted evidence plane and keyword retrieval, then the existing single-pass `RetrievalLLM` adapter. Requires actual OpenAI credentials; no response or accuracy is fabricated when unavailable. |
| `bounded_agent` | Existing full Prime adapter with native SDK `rlmMaxDepth=0`; recursion is disabled at the SDK boundary. Same scoped evidence tools/report obligations. Actual attempt failed at provider billing. |
| `full_rlm` | Existing Prime SDK and native recursive orchestration, report/citation verification and telemetry. Actual attempt failed at provider billing. |

Rules have zero model calls and zero API spend; local compute is not free and its
dollar cost is unmeasured. Failed model attempts have unknown billed tokens/cost,
not zero cost. RAG and Prime have different provider/model defaults, disclosed
rather than presented as resource-matched successful comparisons. No inference
comparison is possible until funded credentials are available.

Source diversity is optional and only supported for lexical search. Default
retrieval behavior remains unchanged. Stable source-path tie-breaking prevents
temporary staging paths/source IDs from changing lexical rank under ties.
An empty source-inspection query no longer infers every unmapped metric and
silently omits narrative observations. Tests cover both regressions.

## Scores and practical interpretation

- File recall: distinct available critical source paths discovered / four critical paths.
- Span recall: exact normalized critical text recovered in cited observations,
  including ordered adjacent document lines. Finding a campaign ID in a file
  earns no span credit. This is a controlled extraction/discovery proxy, not semantic understanding.
- File precision: available critical files / distinct cited files. Other campaign
  files are distractors for these specific questions, not universally irrelevant.
- Counterevidence recall: critical contradictory spans actually retrieved.
  Semantic recognition/disposition requires a successful investigator and independent review.
- Affected-run precision/recall: submitted batch set against hidden affected and
  comparator sets. Reporting all related identifiers can achieve full recall
  while failing precision; that failure is explicitly reported.
- Citation source validity and provenance completeness: source belongs to the
  frozen historical allowlist and has physical row/cell/paragraph/page references.
  This does not validate an arbitrary scientific claim; original-value
  verification and independent field checks remain separate measures.
- Hypothesis coverage: exact hidden contributor phrase in submitted hypotheses.
  It is intentionally limited; semantic scientific adequacy is not evaluated.
- Unsupported causality: structured assertions of verified/established causality
  are errors because these records do not establish a verified root cause.
  Free-prose causal overstatement still needs blinded scientific adjudication.
- Correct abstention: inconclusive scenario reports causality unresolved and
  makes no structured assertion of an established cause. An always-abstaining
  baseline can pass this while failing every discovery/hypothesis measure.
- Future leakage: cited future source paths; negative filesystem probes also
  test access independently. Zero leaked citations is not a general security proof.
- Efficiency: wall time includes staging/isolation overhead; ingestion reports
  its own runtime. Tool/model calls and token/cost fields remain explicit.
  Worker peak RSS and CPU are captured where implemented, with scope stated.

Independent structured extraction checks use csv/openpyxl/pyarrow readers against
the existing ingested store, systematically selecting first rows of 24 files.
They measure value/unit/coordinate round trips. OCR, all time points and causal
interpretation are not covered. IndPenSim checks 112 original values in eight
batches at the actual first physical data row, not lexicographic observation-ID
order; a preliminary checker bug is documented in the failure analysis.

## Scalability and reproducibility

100-file functional trials cover all four questions. Independent 1,000-file
trials exercise all families; **controlled** 1,000/10,000-file scaling additionally
preserves the 100-file evidence byte-for-byte while adding only distractors.
Each question retains four available critical sources and one inaccessible
future source: question-specific prevalence declines from 4/96 to 4/996 to
4/9996. This tests distractor growth, not constant-prevalence sample expansion.

Per-run `run.json` records objective, source hashes/availability, generator seeds,
corpus version/hash, configuration, recursion setting, time/tool budgets, errors,
metrics and runtime artifact paths. `investigation.json` contains citations and
decision traces; failed runs remain failed. Early v2 source manifests did not
capture generator-code hashes; early receipts can contain the working code hash
at run completion rather than a contemporaneous generation hash. Later
generations capture it, and the runner marks legacy missing generation hashes
as `unknown`. Early trials were exploratory and are qualified in limitations. See limitations for remaining version/compute gaps.

Paired simulator experiments use matched seeds 1/2, recipe/initial conditions,
repeat episodes and one bounded feed change at 20 h. Terminal objective is
penicillin concentration g/L, never yield. All full episodes failed the numerical
gate/time budget, so optimization scores remain `not_evaluated`.
