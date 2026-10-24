# Model routing, latency and cost

Policy prepared 2026-10-23 and implemented in `backend/src/lifesci/gateway/` (see [implementation status](#implementation-status) below). Prepared using current [OpenAI model-selection guidance](https://developers.openai.com/api/docs/guides/model-selection), [latency guidance](https://developers.openai.com/api/docs/guides/latency-optimization), [pricing](https://developers.openai.com/api/docs/pricing) and [prompt-caching documentation](https://developers.openai.com/api/docs/guides/prompt-caching). Candidate assignments below are engineering hypotheses requiring task-specific evaluation and account/deployment eligibility checks.

## Route by task and risk

| Tier | Initial implementation | Suitable work | Acceptance boundary |
| --- | --- | --- | --- |
| C0: code | Python/SQL, existing Polars/DuckDB tools | Units, arithmetic, limits, exact IDs, permissions, procedure sequencing, state transitions, signature checks, deduplication | Tested deterministic function and explicit inputs/versions. A model cannot override an authorization failure. |
| M1: small | Candidate `gpt-6-luna`, low effort | Document categorization, exact-span field extraction, constrained formatting, short source-grounded summaries, query phrasing | Defined schema plus required-span/value checks. Advisory classification cannot grant access, choose a binding severity or suppress an alert. |
| M2: balanced | Candidate `gpt-6.1-sol`, low/medium effort | Routine sourced synthesis, editable form drafts, bounded procedure interpretation, task decomposition, comparison explanations | Evidence completeness, contradiction checks, applicable procedure context and task evaluation. |
| M3: frontier | Candidate `gpt-6-astra`, medium/high effort | Ambiguous investigation planning, conflicting evidence, difficult cross-source synthesis, constrained optimization reasoning | Deterministic/tool checks plus qualified review where required; stronger reasoning is not approval or proof of correctness. |

Keep provider/model/version mappings in a registry behind the task interface. Existing Prime provider/model configuration stays usable; these candidate models are not installed or enabled by this document. A qualified alternative provider can fill the same tier if tool/format, data handling and evaluation requirements hold. Do not select a life-sciences-branded model merely from its name or assume restricted access is available.

The current official guide places Luna at the efficient end, Sol as a lower-cost complex-work option, and Astra at the demanding end, while explicitly recommending same-task comparisons. These roles inform the candidates, not a validated manufacturing ranking. [Model selection](https://developers.openai.com/api/docs/guides/model-selection)

## Router inputs and decision sequence

The router uses application-owned task kind, intended use, risk class, evidence quality, ambiguity indicators, scope/region restrictions, required tools/modalities, context budget, deadline, allowed spend and approved model profile. Model-produced labels may suggest routing but cannot lower required authority or risk controls.

1. Authenticate and authorize the task. Resolve data/region/provider constraints and task-specific quality profile.
2. Use C0 if a reliable deterministic method fits. Reuse a valid result keyed to exact inputs and method version.
3. Assemble minimal sufficient context with recoverable source references. Missing evidence yields an explicit gap; a stronger model does not repair unavailable facts.
4. Select the least expensive eligible model demonstrated to satisfy this task's quality gate. For ambiguous/high-consequence work, use the prequalified route required by intended-use policy without first spending on a predictably unsuitable small model. Tier size alone does not establish qualification.
5. Reserve estimated input/output/reasoning/tool budget atomically against task, mission and tenant budgets. Check queue/deadline and provider capacity.
6. Execute with explicit token/tool/time limits and validate the result. Permit at most one targeted format repair by default; repeated format failure or substantive contradiction triggers a bounded escalation or an unresolved result.
7. Revalidate evidence versions and permissions before committing output. Record route, reason, policy/eval version, model/reasoning/tool versions, usage, cost and outcome.

Unknown task classes start as unqualified and use the conservative approved profile or human clarification; do not route them to the cheapest model by default. Budget exhaustion saves progress and reports what remains. It never relaxes permissions, hides missing evidence, or replaces a required qualified model with an unevaluated cheaper one.

## Accuracy gates

- Measure extraction against labeled source spans including tables, OCR uncertainty, negative statements and exceptions. JSON validity alone is insufficient.
- Check numerical claims through reproducible tools. Keep measurement quality and interpretation distinct from arithmetic correctness.
- Test procedure scope/revision selection, omission of critical obligations, contradictory evidence, ambiguous ownership and misleading prior cases.
- Compare complete long-horizon task outcomes across repeated trials, including correction retention after compaction and stale recommendation withdrawal.
- Evaluate small-model false negatives as well as precision. A routing system that cheaply misses a critical item fails even if most outputs look good.
- Use independent deterministic checks and qualified human review where warranted. A second model can critique but cannot certify the first model's correctness.
- Establish thresholds from intended use and qualified review before approving a route. Zero failures in a finite test suite is not a guarantee of zero future failures.

Store the approved model profile by task kind and version. Changes to model, prompt, tools, retrieval, context policy or procedure interpretation trigger impact assessment and relevant regression evaluation. Use shadow execution/canaries where suitable, without double-sending notifications or external writes. A fallback must meet the same eligibility and quality gates.

## Context and compute efficiency

Reuse stable task instructions and tool definitions as a cacheable prefix where the provider supports it. Load task-specific skills on demand. Keep large evidence, traces and intermediate analysis in storage; use previews, selected rows/windows and retrieval. Preserve access to full originals after compaction. Context construction includes active constraints, changes, contradictions and unfinished work so savings do not erase essential information.

Application caches are keyed by tenant/scope, current authorization/policy version, source revision, method/prompt/model version and task parameters. Recheck permissions on cache reads. Invalidation follows evidence changes; a cached output can never revive revoked access or stale advice. Provider caching has its own retention, residency and billing rules; configure only eligible options and do not assume cached input is free. [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)

Run independent retrieval/calculation concurrently with bounded fan-out. Small, high-volume extraction tasks can use batches when latency allows; critical notifications and time-sensitive decisions use their required service path. Cancel obsolete subtasks after evidence changes. Use background consolidation only when expected usefulness justifies spend. Cache deterministic calculations before caching model prose.

Keep output formats short and structured when another service consumes them. Avoid asking every specialist to rewrite the whole report. Workers return evidence-backed deltas; the lead assembles necessary synthesis. Aggregate token/tool usage across the full child tree, including retries and unsuccessful runs. The current Prime top-level usage accounting is incomplete for this purpose and is a tracked implementation gap.

## Cost model and example

Calculate cost per successful, reviewable task and per batch mission, including failed attempts, escalations, provider-billed input/cache/output, OCR/embedding/tool services, compute/storage, and reviewer time. Avoid double-counting reasoning: for OpenAI, billed reasoning contributes to output usage; it is not an additional surcharge on the same output tokens. Track latency and quality alongside cost. A cheap call that causes repeated retries or difficult review can be the expensive route. [Usage accounting](https://developers.openai.com/api/docs/guides/agents-api/observability)

Illustrative snapshot of the first Standard/short-context table in the official pricing page, retrieved 2026-10-23; USD per million tokens. Confirm region, context-length, service-tier and billing semantics at deployment. This table is a dated calculation input, not a price commitment. [Official pricing](https://developers.openai.com/api/docs/pricing)

| Candidate | Input | Output | Cached input |
| --- | ---: | ---: | ---: |
| gpt-6-luna | 0.10 | 0.50 | 0.01 |
| gpt-6.1-sol | 2.00 | 10.00 | 0.10 |
| gpt-6-astra | 10.00 | 50.00 | 1.00 |

Example only: 100 tasks, each with 2,000 ordinary input tokens and 500 total billed output tokens (including any billed reasoning), no cache, retries, tools or infrastructure. Assume evaluation permits 80 small, 18 balanced and 2 frontier calls. The token estimate is `80 × $0.00045 + 18 × $0.009 + 2 × $0.045 = $0.288`, versus `$4.50` for 100 frontier calls under identical token assumptions. Actual workloads may have very different task distributions and token usage; this is not measured savings or a mandatory routing ratio.

Escalation changes the calculation: `expected task cost = initial cost + P(repair) × repair cost + P(escalate) × escalation cost + verification/tool cost`. Measure those probabilities; do not invent them to justify a small model. Maintain a versioned pricing registry and reconcile estimated versus provider-reported usage.

## Implementation status

Implemented 2026-10-23 (decisions D36–D39, D43 in the [decision log](decision-log.md)):

| Policy element | Code | Verified by |
| --- | --- | --- |
| C0 deterministic handlers first (statistics, limit checks, unit conversion) | `gateway/gateway.py`, `science.register_handlers` | `test_LS056_*`, `test_end_to_end.py` |
| Route = cheapest evaluated profile at/above the task floor; unknown tasks refused (or frontier + `unqualified` in dev mode); model-suggested risk ignored | `gateway/router.py` | `test_LS055_*`, `test_routes_to_cheapest_qualified_small_model` |
| Activation only via passing, threshold-checked evaluation with impact scope; suspension on drift | `gateway/registry.py`, `science.ProfileMonitor` | `test_LS067_*`, `test_LS089_*` |
| Schema, cited-source and no-probability validation; one repair; one escalation | `gateway/gateway.py` | `test_validation_repair_then_escalation`, `test_grounding_*` |
| Bounded retries, circuit breaker with cooldown, failover to qualified profiles; honest `blocked` | `gateway/gateway.py` | `test_LS080_V09_*` |
| Atomic tenant/mission/run budget reservation; exhaustion pauses with progress | `gateway/budget.py`, `missions.py` | `test_LS058_*` |
| Cache keyed by tenant, registry version, profile, prompt and input revisions; permission + freshness rechecked on read | `gateway/gateway.py` | `test_cache_hit_rechecks_freshness` |
| Descendant-aware trace: calls, retries, tokens, cost, latency incl. queue, reviewer minutes | `gateway/gateway.py` | `test_LS057_LS066_*` |
| Prime investigations take their model from the router; cost recorded in the same ledger | `prime_adapter.py` | `test_prime_adapter.py` |

Default registry: Anthropic `claude-haiku-5-5` (M1), `claude-sonnet-5-5` (M2), `claude-opus-5-5` (M3), plus the OpenAI candidates above, with dated prices. **None is qualified by default**; task-specific evaluations remain to be run before production use.

## Development delegation in this task

The source-extraction and code-inventory subtasks were delegated to `gpt-6-luna` at medium effort. Architecture synthesis and technical trade-offs used the lead/research agents. This is actual delegation for this task; it is separate from implementing BioDemo's runtime router and does not guarantee any particular account quota savings.

Implementation phase (same date): four bounded module builds (science; procedures/execution/lab; integrations/collaboration; network/quality) were delegated to `claude-sonnet-5-5`, and two documentation tasks (assessment records and their status refresh) to `claude-haiku-5-5`. Core contracts, the gateway, missions, API, cross-module review, bug fixes and verification stayed with the lead model (D44).
