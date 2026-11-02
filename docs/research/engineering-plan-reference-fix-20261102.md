# Engineering assistant workflow-reference fix

Implemented locally on 2 November 2026. **Not deployed; the live account is still on the earlier backend until deployment.** This repairs the plan-contract failures recorded in the [authenticated script check](live-demo-script-check-20261102.md).

## Problem and resulting behavior

Actual GLM responses put an attached `phys_...` source in `depends_on` and `$node`, even though that source already existed and was not a step in the new workflow. Both the compound request and simplified baseline failed with `unknown dependency` before any calculation. Other returned bindings confused input names (`plan_id`/`result_id`) with the output record's `id` field.

The planner now receives explicit contracts for literal attached IDs, new workflow node dependencies, permissible producer operations and direct record IDs. Host validation rejects missing dependencies, undeclared bindings, wrong producer types and incorrect ID paths **before** creating a flow or running a solver. It does not reinterpret an unknown dependency, silently alter a model's plan, or relax access control.

Request-scoped host validation participates in the **existing model gateway repair loop**, capped to one validation correction for conversation planning. The rejected response and validation error remain in the gateway attempt record. Valid plans execute once. Repeated invalid plans stop with an explicit explanation that no simulation ran. The generic gateway retains its existing bounded transport/failover rules and budget accounting; no second agent retry loop was introduced.

English requests now explicitly request English replies, with concise narrative and calculated artifacts carrying the numbers. Review proposals can depend directly on calculated results; an unrequested interpretation step is not made a prerequisite. Conversation checkpoints renew the worker's fenced lease as work progresses. Existing record ownership, source checks, solver limits, approval separation and production-dispatch boundaries remain enforced.

## Verification

1. A regression test using the actual simplified live GLM output failed before the fix with `AssertionError: ['ValueError: unknown dependency']` in1.64s. The only fixture alteration substitutes the account source ID with a placeholder; the invalid plan is not repaired by the fixture loader.
2. Focused orchestration/gateway/bioprocess checks: **50 passed**. These include one correction before execution, repeated invalid-plan rejection, no duplicate calculations, literal-source handling, wrong output-ID rejection, cache-contract versioning/revalidation, and preservation of failed output.
3. Full backend life-sciences regression: **504 passed in109.33s**. It required local socket access for throwaway HTTP/connector/PostgreSQL fixtures; the initial restricted run's socket failures were environmental, not hidden passing results.
4. **Actual Modal GLM-5.3 verification on the updated local host succeeded**, with one returned provider request and53.524s total workflow time. This used an isolated seeded store and reconstructed synthetic freeze-drying context, not the production account or database.

The live model selected a seven-step workflow: prepare/execute the baseline; create a6000-vial alternative; prepare/execute it; compare results; draft an engineering review proposal. All seven completed. Both model results contain152 trajectory points; the comparison and proposal were persisted. The proposal remains `proposed`; no action intent or manufacturing dispatch occurred. The reply is in English. It was accepted on its first attempt, so this live check demonstrates the improved first-pass plan; unit tests separately exercise bounded correction of the captured invalid plan.

Endpoint response model: `zai-org/GLM-5.3`. Provider request ID: `54af9d9dc67045e9a40e3a1e6cc538f3`. Actual provider billing is unavailable and is **not** claimed to be zero. This single functional case does not establish agent reliability across arbitrary requests or manufacturing-model validation.

Evidence:

- [Live receipt, model identity and implementation hashes](../../output/verification/engineering-plan-fix-local-live-20261102-02/receipt.json).
- [Actual conversation, accepted workflow and step statuses](../../output/verification/engineering-plan-fix-local-live-20261102-02/conversation.json).
- [Calculated trajectories, comparison and review proposal](../../output/verification/engineering-plan-fix-local-live-20261102-02/artifacts.json).
- [Regression fixture](../../backend/tests/lifesci/fixtures/glm_attached_source_plan.json).

The earlier local attempt in `engineering-plan-fix-local-live-20261102-01` was blocked by sandbox DNS resolution; it returned no model response and is preserved as a failed connection attempt. The successful verification was rerun with network permission into a fresh directory.

## Design choice and trade-offs

Job: a user asks the assistant to calculate and compare supported scenarios without writing workflow plumbing. Easy to Start: correct references are supplied by the host contract. Easy to Trust: invalid and corrected responses remain inspectable and no fabricated calculation replaces failure. Easy to Act: actual computed artifacts can support a draft review proposal. Easy to Adopt: existing gateway, registered models, flow runtime and identity controls are reused.

Chosen alternative: explicit record/node contracts and validation integrated with the existing bounded repair mechanism. A new workflow compiler or lenient dependency normalizer would add a parallel runtime or guess missing intent. An invalid response may now incur one additional model correction; the attempt remains visible and budgeted. A repeated failure remains a failure.

## Reproduce and deploy

From the repository root:

```sh
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/lifesci -q --tb=short
```

The live verification command is opt-in and billable; it refuses overwrite and caps provider attempts at two:

```sh
.venv/bin/python backend/scripts/verify_engineering_chat_live.py --execute --output output/verification/engineering-plan-fix-local-live-NEW
```

It reads credentials through existing ignored environment files, redacts any credential values from saved errors, and never opens the production database. It verifies the returned model identity. The local script is not a production-account verification substitute.

The existing AWS deployment path is `backend/deploy/aws/deploy.sh`; it builds the changed API source and deploys the Lambda stack. No frontend change is needed for the calculated artifacts or gateway execution record. Deployment was not run, respecting the earlier instruction to prepare changes locally and leave publishing to the user. After deployment, rerun the ordinary assistant request in the authenticated account and inspect its actual artifacts before recording the video. Earlier failed account conversations remain preserved.

The feed-pump story still lacks source records in the account. This fix does not fabricate that dataset, enable unavailable simulators, or turn the public illustrative `/demo/` page into a live calculation. Use the supported freeze-drying workflow when testing model-backed behavior.

GitHub issue tracking could not be updated: the repository-required `gh` CLI remains unavailable. No issue, commit, push or deployment is claimed.
