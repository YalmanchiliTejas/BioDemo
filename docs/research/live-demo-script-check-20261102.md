# Authenticated product-script check — 2 November 2026

**Verdict: the proposed assistant-led video does not currently work end to end in the live account.** These were actual authenticated requests to `https://www.sievance.com`, in the supplied user's Test1 organization, not local fixtures or mock-provider tests. No password, token or authentication headers are included in this report or evidence export.

## What was tested

| Script element | Observed result |
|---|---|
| Sign in and open Assistant | Passed. Authenticated account and workspace loaded. |
| Ask about the feed-delivery drop | Actual Modal GLM-5.3 response,37.332s. Status `needs_information`; asked for batch/feed/equipment evidence rather than inventing a fault. No computed artifact. |
| Display saved investigations as a chart/table | Passed for the existing synthetic `investigations-15` review: six hold-log rows, three flagged,4h inclusive source limit. These are existing account results, not a newly executed investigation. |
| Inspect a source row | Passed using keyboard activation: `hold_log.csv`, row4, batch44289-C,5h hold, matching the displayed row. |
| Attach displayed work to companion | Passed: selected chart/row snapshot appears in the companion with `/workspaces/` origin and an inspectable selection. It is display context, not a verified source-system connection. No fourth LLM request was submitted for this selection. |
| Run a model, compare an alternative and draft review | Failed. GLM planning completed in69.294s; host workflow validation rejected the plan before execution with `ValueError: unknown dependency`. No scientific artifact or proposal was created. |
| Simplify to one baseline model run | Failed again. GLM planning completed in35.478s; same dependency-validation error, no scientific artifact. This was a real follow-up request, not an edited/replayed success. |
| Automatically collect the narrative's feed/maintenance records | Not demonstrated. No such records were attached; no verified CMO delivery was available. The existing September delivery is displayed as failed with0files. No new ingestion or external connector configuration was attempted. |
| Approval or manufacturing execution | Not tested or performed. Both model requests explicitly prohibit approval/dispatch/execution. No review proposal was created because execution never started. |

Observed **three completed GLM-5.3 planning calls**, provider `modal`, on an explicitly unqualified development route. This is model execution evidence, not scientific validation. One request returned an appropriate information gap; two workflows were blocked. Actual provider billing is unavailable, so the profile's zero-priced compute estimate is not reported as zero cost.

## Exact failure and reproduction

The actual plans place existing source record `phys_01M6A21JGW239J77ZKJCFARF5Q` in a node's `depends_on` and use it as a `$node` binding. That record is attached evidence, not a node in the newly submitted workflow. `node_order` therefore correctly rejects the graph as containing an unknown dependency.

The same problem appears in both the8-node compound plan and the2-node simplified plan. Replaying the **unchanged actual GLM output** through `ChatDecision.model_validate` and `EngineeringConversationService._validate_workflow` reproduced the same error locally for both. No solver or LLM was invoked during that diagnostic replay.

The compound plan also uses `plan_id`/`result_id` binding paths where the host operation contract describes direct records with `id`, and its review node does not declare every node that it binds. Those are additional plan-contract concerns found by inspection, not independently executed downstream failures. Its narrative reply is unexpectedly in Chinese despite the English request. The failed reply is not shown as a completed analysis in the UI.

The immediate repair should distinguish attached source IDs from workflow-node IDs in model instructions/schema, preserve dependency validation, and handle invalid returned plans as a bounded, visible correction/failure. Do not permit unknown dependencies or silently pretend a stored source is an executed node. A fix would need a new actual account run before a claim that the video's model section works.

## Saved evidence and account records

- [Redacted live requests, provider/model identity and returned plans](../../output/verification/sievance-live-script-20261102/live-runs.redacted.json).
- [Local validation replay](../../output/verification/sievance-live-script-20261102/workflow-validation-replay.json).
- [Live assistant clarification](../../output/verification/sievance-live-script-20261102/03-live-glm-clarification.png).
- [Blocked model workflow](../../output/verification/sievance-live-script-20261102/04-live-model-workflow-blocked.png).
- [Source-row and companion selection](../../output/verification/sievance-live-script-20261102/06-verified-row-and-context.png).

New account conversations remain saved:

- `engchat_01M6EF9916XB765RQS51J6CZ4B` — feed-drop evidence request.
- `engchat_01M6EFMA8S9Q1WVN8B7GRHSTN2` — two blocked freeze-drying model requests.

Gateway run IDs: `run_01M6EF9AKRWEFR8P932G6GD64N`, `run_01M6EFMBNK8GHYKXXHP21TESAW`; the third run's exact ID is retained in the JSON export. The app stores these in its conversation records; no public publication or deployment was made.

## Implication for filming

The current reliable filmed path is existing structured workspace results → inspect source row → attach selection to companion → explain/request missing evidence. The feed-pump narrative still lacks its source package. The assistant-generated mechanistic chart/comparison/review sequence needs repair and a passing live run before it can be filmed as functioning product behavior. The public `/demo/` route remains an illustrative synthetic walkthrough and cannot replace that verification.

Unit/orchestration tests passing with test providers do not establish that real GLM output satisfies the host workflow contract; these live failures demonstrate the difference. No source data or existing account results were edited to produce a favorable test.
