# Limitations, failure analysis and remaining work

## Definition-of-done status

**Not achieved.** Reproducible mixed-format ingestion, hidden-truth experiments,
actual rules comparisons, historical IndPenSim ingestion, simulator gate and the
results UI are implemented and executed. A successful autonomous Prime
investigation, scientifically adjudicated reasoning and defensible simulated
optimization have not been demonstrated. Failed results are retained.

## Ranked next work

1. **Restore authorized inference availability.** Prime's configured provider
   returned HTTP 402 insufficient balance. RAG lacks an OpenAI credential. Use an
   organization-authorized funded configuration, then execute full and bounded
   Prime on identical v2/scaling inputs and budgets. Do not change billing scope
   automatically. Without these runs, no autonomous accuracy, model efficiency,
   subagent benefit or complete successful AI trace can be claimed.
2. **Make discovery robust to distractor growth.** At 100 files the linked rules
   recover all critical spans, but precision is low and scope includes controls.
   At controlled 1,000 files they still miss 25% of the critical spans after the JSON fix.
   Fixed top-24 search is not adequate stopping logic. Use Prime's existing
   iterative tools to expand/revise question-dependent searches, inspect graph
   links, track counterevidence gaps and stop based on evidence sufficiency rather
   than retrieval count. Preserve the failing corpus and score before/after on
   reserved instances; do not tune filenames or embed evaluator mechanisms.
3. **Finish large-corpus ingestion within a stated budget.** The 10,000-file
   stress test timed out with 3,213 indexed sources. Profile document/OCR work,
   per-source metadata/index synchronization and schema/query preparation;
   measure incremental/resumable progress and bounded concurrency. Current
   runner reports partial registration explicitly; it does not establish
   complete 10,000-file discovery or cost scaling.
4. **Strengthen scientific evaluation and benchmark realism.** Current causal
   labels are authored synthetic mechanisms; hidden seeds reserve identities,
   not new mechanism families. Records use relatively regular field schemas
   and short notes, not complete plant eBRs/CAPA packages. Add independently
   authored realistic documents, terminology/schema variation, subtle conflicts,
   adversarial instructions and more inconclusive cases. Have blinded QA/MSAT
   reviewers adjudicate hypotheses, unsupported prose causality, contradictions,
   next actions and scientific stopping adequacy. Current phrase/structured-label
   scoring cannot replace that review. Cross-document linking correctness is
   still `not_evaluated`; co-occurrence is not a validated association.
5. **Extend IndPenSim investigation beyond the batch-mean screen.** Source values
   remain intact, but 2,200 Raman channels are not all ingested, onset intervals
   are not scored, and half the known fault batches are missed. Public batch
   numbering itself reveals published control/fault groups; a future model
   evaluation needs an explicitly blinded identifier mapping and disclosure of
   remaining public-data memorization risk. Add approved variable interpretation,
   temporal fault signatures, source-bound outcome analysis and independent
   annotation. Historical control groups remain confounded, not randomized trials.
6. **Repair/validate the simulator before optimization.** Full baseline biology
   is invalid for the native solver; short-budget SciPy episodes did not finish.
   Compare equations/tolerances with the reference model, establish a supported
   dependency build and run longer diagnostic budgets where justified. Only
   after valid full trajectories and repeatability should a bounded agent policy
   be connected and compared on matched seeds. The current private Python object
   is not a model security sandbox; expose serialized current observations only.
7. **Broaden extraction/provenance checks and freeze experiment versions.**
   Independent 292-field synthetic and 112-value historical checks are limited
   systematic samples. Scanned pages remain unverified OCR; a cited span is not
   an independently validated scientific fact. Add blinded visual checks and
   difficult tables/units. Nested JSON remains narrative rather than a validated
   numerical schema. Early exploratory receipts lack contemporaneous full
   dependency/prompt/SDK hashes; some record the working generator hash at run
   completion rather than generation. Later runner/generator versions capture
   code hashes/environment explicitly. Freeze complete versions before claiming
   cross-model reproducibility or generalization. Early pre-fix runs are diagnostic,
   not interchangeable with the final tables.
8. **Complete product follow-up and deployment validation.** `/case-studies`
   presents executed data and calls the existing Prime API with package binding;
   successful live follow-up is blocked by inference availability. Source drill-down
   requires the matching exported corpus and retained store. The existing header
   identity adapter is development-only. Reuse organizational authorization at
   deployment; no compliance or validated manufacturing status is claimed.
9. **Resolve the two pre-existing CHO/report failures separately.** Restore/run
   the real recorded pilot and deliberately reconcile the stale static report.
   Their assertions were not disabled and their data was not fabricated here.

## Important practical boundaries

- The FDA letter supplies public historical findings, not internal factory data.
  All generated operational evidence is fictional. No Sanofi root cause has been
  discovered, and no real batch action should follow from this challenge corpus.
- The benchmark's historical exclusion depends on deliberately controlled public
  availability metadata. Arbitrary uploaded files can have untrustworthy mtimes;
  the generic directory CLI cannot reconstruct authentic publication dates by
  guessing. Mixed future structured files are conservatively withheld during
  historical CLI runs; full partial-row export/lineage remains future work.
- OS-level hidden-truth isolation currently requires macOS sandbox-exec. Nested
  sandbox execution can fail before it starts; the benchmark fails closed.
- Rules/API cost is zero because no API is called; local compute cost is unknown.
  Failed inference usage is unknown. Tokens/cost/efficiency for successful agent
  workflows and child workers are not inferred from the rules baselines.
- Scope extracted from co-occurring identifiers overstates affected batches.
  Low retrieval precision and missed contradictions make a convincing-looking
  narrative unsuccessful under this benchmark.
- Simulator process response and historical correlations do not establish real
  manufacturing improvement. Concentration is g/L, not yield; invalid terminal
  outcomes are withheld rather than converted into apparent gains.
