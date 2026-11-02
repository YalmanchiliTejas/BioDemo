# Proactive assistant implementation and verification

Date: 2026-11-02. Local implementation; not deployed, account-populated, or manufacturing-qualified. Governing direction: [four pillars](../../Main_Culture_andETHOS.md). Requirement: [proactive assistant contract](../product/proactive-assistant-architecture.md).

## Implemented behavior

The assistant can discover permitted workspace records without attachments, inspect current revisions, observe tool results or stale-read errors, and continue reasoning. Discovery covers cases, evidence, batches, samples, procedure instances, claims, proposals, process contexts, and the owner's saved conversation turns. Case discovery orders by case-opened time and explicitly distinguishes this from deviation occurrence. Synthetic examples and prior assistant interpretations remain distinct from verified manufacturing evidence.

Read and search results persist as evidence-linked artifacts. The UI renders discovery tables, case timelines, source metadata, and expandable originals. Source inspection rechecks tenant, site, revision, lineage, and conversation ownership. Delegated background access also checks the person's current authority. Current process contexts found through tools can become inputs to the existing registered scientific workflows. There is no arbitrary record-store query, code execution, browser, or terminal capability in these tools.

The agent can prepare a draft retest request, hold, work order, batch rescheduling proposal, or deviation submission proposal through the existing ActionService. Its basis must consist of sources inspected in the current turn at current revisions. Saved conversation answers cannot themselves authorize draft action evidence. Approval, dispatch, production execution, and observed effectiveness remain separate. This change exposes no automatic approval or dispatch tool.

The **Follow-up responsibility** control saves a standing objective, selected source kinds, optional hourly follow-up, and a finite background run allowance. Source changes activate the existing mission runtime, which coalesces revisions of the same record and processes at most five source records per envelope. Events outside that envelope remain pending. A persisted event-to-turn association prevents redelivery from creating duplicate model work. Results appear as **Background follow-up** turns without another user message. Idle waiting does not call the model.

Owner controls start, update, and pause follow-up; **Stop work** cancels the current turn at the next host boundary. Completed artifacts remain available. Run admissions survive pause/resume, and exhausted responsibilities pause rather than silently resetting their allowance. Scheduled follow-up coalesces missed intervals instead of spending inference on every elapsed hour. The existing local runtime and Temporal coordinator share this path; Temporal deployment itself was not exercised.

Each turn admits at most three planning rounds, each with at most two provider attempts across retries/repair/fallback. Numerical executions retain a total of three and 96 admitted solver calls across continued rounds. Scientific interpretation tools can make additional gateway calls under their own limits. Working context bounds workspace excerpts and older instructions while preserving original artifacts and searchable authorized history. Formal mission corrections and rejected hypotheses enter subsequent prompts, with linked-source access checked again.

These are request-count and tool limits, **not a $50 monetary guarantee**. Modal invoice rates are unknown to this code. Gateway profile estimates do not establish actual hosted billing. No always-on paid inference is enabled automatically.

## Architecture decision

Extend the existing Python conversation service, gateway, FlowService, mission state, and runtime coordinator. Reuse their validation, leases, audit, task routing, and scheduling boundaries. This avoids requiring the separate Node/compiled Prime SDK in the current Lambda image. It also preserves the existing typed scientific workflows.

Prime remains specialized to incident investigations. The broader contract's general Prime task interface, a separately packaged tool worker, general computer use, reviewed knowledge consolidation, and broad cross-domain outcome qualification remain future work. This implementation supplies bounded proactive manufacturing responsibilities; it does not reproduce Dots' or Muse's proprietary internals. The [reference audit](proactive-assistant-reference-audit-20261102.md) separates vendor documentation from our design inferences.

## Real GLM functional checks

Runner: [verify_proactive_assistant_live.py](../../backend/scripts/verify_proactive_assistant_live.py). Explicit `--execute` is required. It creates an isolated local store with synthetic records, reads the configured Modal credentials without printing them, verifies the endpoint's returned model identity, and caps the entire check at six provider requests. It does not use a production database or the user's production account.

Successful final run: [receipt](../../output/verification/proactive-assistant-live-20261102-04/receipt.json), [conversation and tool trace](../../output/verification/proactive-assistant-live-20261102-04/conversation.json), [inspected records](../../output/verification/proactive-assistant-live-20261102-04/inspected.json).

| Scenario | Observed result |
| --- | --- |
| Latest deviation, no attachments | Three real GLM responses. The agent inspected the newest case, its near-tied predecessor, and linked MES source. It stated that ordering used opened time, labeled the data synthetic, and distinguished the observed pressure alarm from untested sensor/valve hypotheses. |
| New case while following an objective | Two real GLM responses, triggered by a runtime tick with no new user message. The agent inspected the current case and evidence inventory, reported a fill-weight excursion, and requested missing source/scale verification evidence rather than asserting a cause. Terminal state was `needs_information`, an explicit evidence wait. |
| Model identity | All five endpoint responses identified `zai-org/GLM-5.3`. No substitute model or fake provider was used in this run. |
| Production effects | No action intents or manufacturing dispatch occurred. |

Provider-reported request latency sums were 82.832 seconds for the interactive investigation and 31.466 seconds for follow-up. These are two scenarios, not p90/p99 estimates or a speed benchmark. The archived turn `elapsed_seconds` originally counted only its final round; the implementation now accumulates round time. Use the individual gateway attempt latencies when reading that archived run.

Earlier attempts remain available:

- [01 receipt](../../output/verification/proactive-assistant-live-20261102-01/receipt.json): sandbox DNS prevented reaching Modal; no successful model response.
- [02 receipt](../../output/verification/proactive-assistant-live-20261102-02/receipt.json): real interactive investigation produced a useful answer and evidence wait; background work stopped when the model requested an obsolete revision from two event versions. This exposed the need for event coalescing and stale-read recovery.
- [03 receipt](../../output/verification/proactive-assistant-live-20261102-03/receipt.json): a real response exhausted its output allowance on reasoning and returned no answer. The host recorded an unavailable agent rather than inventing a result.
- After those failures, the host coalesces event revisions, replans bounded read errors, and discloses numerical tool schemas only after an appropriate context or demo permission exists. The final run's initial prompt used about 3,000 tokens, compared with about 8,600 in the earlier run. This is a context-size observation, not proof that the change eliminates provider failures.

This functional evidence does not establish retrieval recall/precision, causal decision accuracy, safe plant intervention, transfer success, or manufacturing benefit. Those require the labeled, held-out task campaign in the architecture contract. Failed runs are not excluded from an accuracy claim; no such claim is made.

## Host and UI verification

Executed the life-sciences regression suite: **512 passed** before the final context and regression-test additions. Subsequently ran the affected conversation/gateway/mission set: **72 passed**, and the exact CI selection previously supplied by the user: **150 passed**. The final repeat of that CI selection, after the last action-evidence guard, also passed **150 tests in 21.82 seconds**. Final frontend `npm run lint` (TypeScript) and `git diff --check` passed.

Coverage includes discovery without attachments, current-revision inspection and bounded stale-read recovery, tenant/site/owner boundaries, draft-only actions with inspected evidence, request caps, redelivery, retained events outside a bounded envelope, scheduled follow-up without idle inference, coalesced missed intervals, pause, revoked owner access, stop during a model call, and preserved mission corrections. Test doubles exercise host behavior; they are not model-quality measurements.

Frontend TypeScript validation passed. An isolated local browser fixture checked the source timeline and follow-up form, enabled a responsibility, observed an automatically appended background turn, and paused follow-up. That UI fixture uses fake responses and is separate from the real GLM evidence above. Screenshots: [responsibility controls](../../output/verification/proactive-assistant-ui-20261102/responsibility.png), [conversation view](../../output/verification/proactive-assistant-ui-20261102/background-result.png).

## Using the change

After deploying the updated API and frontend, ask the assistant about existing workspace records. No attachment is needed for permitted indexed records. It should inspect source evidence before explaining cause and state missing evidence explicitly.

In a saved conversation, expand **Follow-up responsibility**, describe the objective, select source kinds, optionally enable hourly follow-up, set the run allowance, and authorize background inference. The existing runtime must run: local server lifespan starts it; Lambda uses the existing scheduled `runtime_tick`; Temporal uses the shared coordinator. Configure connectors and their permissions separately—this change does not create MES/LIMS/QMS connections or populate missing formal cases from synthetic UI reviews.

No deploy, push, production-account update, email, or external notification was performed. Proposed actions still require the existing review/authorization and owning-system integration before execution.
