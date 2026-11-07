# Assistant tool loop

Status: design, 2026-11-07. Governing direction: [the four pillars](../../Main_Culture_andETHOS.md) and the
[proactive assistant contract](../product/proactive-assistant-architecture.md). Owner priority: correctness and ease of use
first; a rewrite is acceptable when it is the right fix.

## Job

A person asks a question in their workspace ("why did DO drop in B-117?", "is this delivery trustworthy?") and gets a
correct, evidence-linked answer quickly, with a safe next step. Every claim must trace to records the person may read.

## Why the current loop fails (measured)

Two end-to-end runs of the 12 demo scenarios on sievance.com (2026-11-07):

| | Run 1 | Run 2 |
|---|---|---|
| Plain answer | 0/12 | 8/12 |
| Blocked / unavailable | 4 | 4 |
| Time per answer | 1.5–6 min | 2–7 min |

The planner asks the model, each round, for one JSON document: a reply plus a complete workflow graph, validated
against a large schema, with a fixed cap of three rounds. Each round re-sends a 5k–19k-token prompt (30 rules, all tool
schemas, every prior result). GLM reasons 17k–28k tokens per round (50–100 s), sometimes exhausting the 32k output
budget (`finish_reason=length`), sometimes spending the last round on more work so nothing answers, sometimes writing a
payload the validator rejects, which costs a whole round.

The same Modal endpoint answers a native tool call (`read_case(DEV-31)`) in 1 s with 31 reasoning tokens. The model is
not the bottleneck; the loop is.

## Design

A native tool-calling loop, inside the existing Python conversation service and gateway (deployable on the current
Lambda, no new infrastructure).

1. **Messages, not plans.** System message: short role and rules. Context message: the person (you), role, site,
   mission corrections, standing rules, recent conversation (text only), attached sources, the case index. Then the
   question.
2. **Tools are the existing operators.** Each registered operation (search, read, links, similar cases, CHO forecast,
   simulations when a context exists, proposals) becomes one function with its existing Pydantic schema, filtered by the
   capability packs and entitlements as today. `ask_user` ends the turn with one question.
3. **The host executes every call** through `_operator`: the same permission checks, mission fence, validation and
   persistence (each result is saved as an artifact with provenance). The model sees a bounded result. Nothing the model
   writes can widen access or approve an action.
4. **A bad call is a tool error, not a lost round.** Validation errors (unknown field, out-of-range cutoff, missing
   record) go back to the model as the tool's result, and it corrects itself in seconds.
5. **Budgets, and a guaranteed answer.** Per turn: wall time, tool calls, model calls. When any is near its limit, the
   final call is made with tools disabled: "answer now from what you have, name what you could not check". There is no
   round in which work can be planned but never interpreted.
6. **Visible progress.** Each tool call is a step (title, status, timing, error) checkpointed on the turn, so the UI
   shows work as it happens.
7. **Resumable.** The message log (bounded tool results) is checkpointed after every step under the existing turn
   lease; a replaced worker resumes from the log instead of repeating side effects.
8. **Same trust checks on the answer.** The final reply goes through the existing grounding check against every
   artifact the turn produced; the basis-staleness and quarantine checks on view are unchanged.

Rollout: `ASSISTANT_LOOP=tools|planner`, per deployment; demo workspaces first. Both loops share tools, persistence and
grounding, so they can be compared on the same scenarios. The planner is removed once the tool loop passes.

## Alternatives

| Option | Benefit | Cost |
|---|---|---|
| Keep patching the planner (PR #21) | Small diffs | Ceiling reached: each fix moves the failure; still slow |
| **Native tool loop in the Python service (this design)** | Fixes the failure classes at the root; fast; reuses every permission, provenance and grounding path; Lambda-deployable | Rewrite of the turn runner (~400 lines) and a provider chat API |
| Move the assistant into Prime (Node) | Richest harness (sub-agents) | Needs a separate worker deployment and a production task contract (contract: not yet built); larger migration. Prime stays the investigation engine |

## Pillars

- Start: the assistant discovers records itself and asks at most one question, only when blocked.
- Trust: every claim traced to persisted artifacts; tool calls auditable step by step; failures visible with reasons.
- Act: proposals remain drafts requiring human approval, enforced by the host.
- Adopt: no new infrastructure or configuration for organizations.

## Measures (before switching the default)

On the 12 demo scenarios (live, sievance.com) and the contract tests: answered without error 12/12; questions only
when needed; median and worst time per answer; tool calls per answer; grounding: unsupported numbers per answer;
spot-check of each answer's facts against the seed. Record provider, model, tool trace and failures for every run.

## Measured (2026-11-07, before deploy)

Local, in-process, real model (Modal `zai-org/GLM-5.3`, the deployed provider), in-memory demo workspaces, the same 12
scenarios. The planner numbers are the live sievance.com runs.

| | Planner, live run 2 | Tool loop, local |
|---|---|---|
| Answered | 8/12 | **12/12** |
| Ended in questions | 0 | 0 |
| Failed (unavailable / blocked) | 4 | 0 |
| Median / worst time | ~3.5 / 7 min | **62 s / 111 s** |

Fixed during measurement: numerical tools were hidden until a dataset was attached (the assistant said it could not
forecast and drafted an unrelated proposal), so a readable verified delivery now counts as context; a truncated raw
forecast led the model to integrate equations itself, so it now sees the bounded summary and is told never to compute
model outputs; Modal calls that hung for 300 s are cut off at 150 s per step.

Known gaps: answer wording varies between runs (one compare named CHO-003-R02 as the outlier, another CHO-001-R02, both
defensible; one said "only run that never crashed" while CHO-003-R01 also stayed healthy within its shorter window; one
read R01/R02 as reactors). Answers are longer than the 3–6 sentences asked for. The grounding check flags derived
numbers (unit conversions, differences) as unsupported. Live verification on sievance.com follows deploy.
