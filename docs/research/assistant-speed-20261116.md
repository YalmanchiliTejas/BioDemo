# Why an assistant answer takes minutes, and what was changed

Date: 2026-11-16. Governed by [Main_Culture_andETHOS.md](../../Main_Culture_andETHOS.md). Follows the
[tool loop design](../architecture/assistant-tool-loop.md) and the [workflow trial](workflow-trial-20261114.md).

Nothing here is a production latency figure or a manufacturing validation. Times are from the owner's recorded runs
and from runs made today, in process on one laptop, against the deployed model endpoint.

## The job

A person asks the assistant a question and waits for the answer. The owner's report: complex tasks and questions take
about four minutes. The owner's question: can it be faster, and is the single Modal endpoint the limit?

## Where the time goes

From the recorded runs in `backend/results/workflow-trial-live-20261115` and `backend/results/live-evals-20261116`.

| Finding | Evidence |
|---|---|
| Almost all of a turn is model time. | Model calls took 99–100% of each turn; tools about 0.2 s per turn. |
| The model writes far more than the answer. | The answer was 1–5% of the tokens generated. A 215 s turn generated 38,559 tokens for a 652-token answer. |
| The thinking is between lookups, not in the answer. | On 16 November, calls that ended by choosing a tool took 92% of model time (1,139 s of 1,235 s). Final answers took a median of 5 s. |
| A few calls hold most of the time. | 17 of 84 calls generated 4,000 tokens or more and took 64% of model time. The median call took 6.7 s. |
| The endpoint generates about 190 tokens a second. | Median over calls of 1,000 tokens or more; range 57–328. |
| Every call ran at the model's highest reasoning level. | GLM-5.3 has three levels (low, high, max). Nothing was sent, and nothing sent means max ([Z.ai](https://docs.z.ai/guides/llm/glm-5.3)). |
| Production ran the older planner for every organization except demo workspaces. | `ASSISTANT_LOOP` was not in the deploy template. The planner measured 2–7 min an answer on 7 November; the tool loop 62 s median on the same scenarios. |
| Production ran the quick explanation at the highest level too. | `LIFESCI_INTERPRETER_REASONING_EFFORT=low` existed only in a local settings file. The trial measured 17 s at max against 3–5 s at low, 6/6 right both ways. |

The last two are read from the deploy template and scripts. The live Lambda was not inspected.

## What the endpoint does

The endpoint is a Modal Shared Endpoint: Modal runs the hardware, and use is billed per token
([Modal](https://modal.com/docs/guide/shared-endpoints)). Probed today with small requests (a few cents in all).

- **It streams continuously, thinking included.** First byte within 2 s; never more than 0.7 s between chunks. So an
  endpoint that has stopped answering can be told from one that is still thinking within seconds.
- **Reasoning levels.** On one small puzzle: 1,414 tokens and 12.7 s at the default, 809 tokens and 9.8 s at high, 262
  tokens and 2.9 s at low. "medium" is accepted and behaves like max.
- **Overlapping requests can slow each other a great deal.** One thinking request alone ran at 124 tokens a second.
  Four identical ones at once ran at 30–35 each. Later bursts of four ran at 80–200 each. The slow bursts were the
  first after a quiet period, which fits a pool that adds capacity under load; that explanation is a guess.
- **No request was refused.** Up to eight at once all answered. Modal's documentation says requests above a
  per-model limit get HTTP 429, and that the limit is shared by every Shared Endpoint of that model in the workspace,
  so a second endpoint of the same model adds nothing.
- **The prompt cache already works.** 76% of prompt tokens were served from cache on 16 November. An uncached
  12,500-token prompt cost about half a second.
- **A routing key made no difference.** Modal suggests sending `Modal-Routing-Affinity-Key` for agent loops. In four
  rounds each way it changed neither cache hits nor speed, so it is not sent.
- **Other hosts of the same model.** On Artificial Analysis's rolling benchmark of 29 hosts, Modal takes 9.9 min per
  task; the fastest takes 5.2, at about 2.7 times the cost per task
  ([Artificial Analysis](https://artificialanalysis.ai/models/glm-5-3/providers)). A faster host buys about 2×.

So the endpoint is not the main cause. It limits in two ways that matter: overlapping requests share capacity, and
an occasional request is never answered (one took 900 s on 16 November before the client gave up).

## What was considered

| Option | Effect | Cost or risk | Decision |
|---|---|---|---|
| Run production as the evaluations run | Planner 2–7 min to tool loop 1–2 min for organizations; explanation 17 s to 3–5 s | Changes the loop for every customer | Done: deploy defaults |
| Lower the reasoning level on the tool loop | Two to four times sooner (measured below) | Wrong values where the model works something out itself and saves it | Done: high, with the saving rule below |
| Read replies as a stream, give up on a silent endpoint after 30 s | A stalled call costs 30 s, not 150 s | A legitimate silence over 30 s would be cut; none was seen | Done |
| Wait and retry when the endpoint refuses for load | A refused turn waits up to 20 s, where it failed at once and blocked the model for a minute | Hides up to 20 s inside a turn | Done |
| Show the answer on screen as it is written | The final answer takes about 5 s to write | Each partial save is a whole new revision of the turn record: many more database writes per answer | Not done |
| Routing key | None measured | None | Not done |
| A dedicated endpoint, or another host | Isolated capacity; up to about 2× | Billed for the hardware of a very large model, or a higher token price; another host also receives workspace data | Owner's decision; not done |
| More work calculated by the host before the model is asked | 127 s to 3 s for the questions it already covers | Per question shape | Existing direction; unchanged here |

## What was measured

Made on 16 and 17 November, in process on one laptop, against the deployed endpoint, one request at a time. Within
each table the reasoning level is the only thing that changes. Records, drivers and every answer:
`backend/results/reasoning-effort-20261116/`.

### Requests the host calculates

Twelve per level: six "what is the difference" questions and six "save a comparison" tasks on three public CHO
deliveries, scored by objective checks against the answer keys.

| Level | Passed | Mean | Median | Slowest | Tokens written |
|---|---:|---:|---:|---:|---:|
| max (nothing sent; as before) | 12/12 | 34.6 s | 33.1 s | 72.8 s | 40,863 |
| high | 12/12 | 8.6 s | 6.2 s | 17.3 s | 9,105 |
| low | 12/12 | 8.6 s | 6.7 s | 19.4 s | 6,595 |

### Open requests to the assistant alone

Three "compare" and three "why" requests per level, scored on four reference figures from the answer keys.

| Level | Compare: all figures | Compare, mean | Why: all figures | Why, mean | Why, slowest |
|---|---:|---:|---:|---:|---:|
| max | 2/3 | 33.6 s | 1/3 | 98.3 s | 119.2 s |
| high | 3/3 | 9.1 s | 1/3 | 35.4 s | 67.3 s |
| low | 2/3 | 4.1 s | 0/3 | 10.6 s | 14.9 s |

Most missed figures were a batch named only by its short form. All 54 answers of these two evaluations were also
read for sweeping or counted statements ("at every time", "9 of 11") and each was checked against the calculated
series: one answer had a wrong one at max, two at high (the same pair of runs), none at low. That is too few to
tell the levels apart.

The explanation call in this evaluation was left at max at every level, as a control. The same three requests
averaged 19.5 s, 54.7 s and 47.1 s across the three runs: at max the amount of thinking varies several-fold between
identical requests.

### Multi-step cases the model works out itself

Twelve freeze-drying cases with a solver: the first three of each family in the 16 November set, with its reference
answers and its strict grader. Here the model reads solver output, does its own unit conversions, picks among
candidates and saves an assessment.

| Level | Strict grader | Mean | Median | Slowest | Nothing saved | A wrong value saved |
|---|---:|---:|---:|---:|---:|---:|
| max (as before) | 6/12 | 118.4 s | 90.1 s | 380 s | 3 | 0 |
| high | 7/12 | 33.9 s | 18.8 s | 117 s | 0 | 2 |
| high, and max from the first saving step | 8/12 | 111.2 s | 90.1 s | 229 s | 2 | 0 |

At high the model twice saved a value it had worked out wrongly: an infeasible recipe saved before every candidate
had been simulated (it corrected itself in its reply, but the saved draft stayed), and a whole-batch rate about 8.5
times too large. At max it saved nothing wrong, and three times it ran out of steps or time and saved nothing at
all.

Things to know when reading this table:

- The three "missing input" cases fail the strict grader at every level because the grader wants the bare
  parameter name. The missing input was named correctly each time.
- These are authored simulator cases through a research connector that production does not have. In production
  the host does the arithmetic and the assistant's saving tools draft things a person must approve.
- The measurement's own spending cap refused six of the high cases and two cases of a first version of the rule
  before any model call. The six were rerun (`multistep-high-rest`). The first version is kept as run
  (`multistep-high-then-max-before-saving`): it re-thought each saving step singly, and the two levels kept undoing
  each other's work.
- One attempt per case. Indications, not rankings.

### What it cost

About $6.50 at Modal's list prices, from the endpoint's own token counts with cached input at its lower price,
probes included. For three runs the cached share was not kept and is assumed to be like the others; with none of
it cached the total is about $7.60. The harness's own count, which prices every input token as uncached, is about
$13. The Modal usage page is the authority.

## What was decided

- **The tool loop runs at high.** On every automated check it did as well as max, two to four times sooner.
- **Saving is still thought through at max.** The first step in a turn that would save a proposal or a result is
  not carried out as first written. It is taken again at max, and the turn stays at max from there. If that second
  thought does not finish in one try, nothing is saved and the answer says so.
- **Low is not used for the loop.** It was no faster than high where the host calculates, and the two earlier
  findings against it stand (a wrong comparison on 11 November; two of five retried answers wrong on 5 November).
- **What this does not speed up.** A turn that ends by saving something the model worked out takes as long as
  before, because that thinking is where the time goes. The way to speed those up is the existing direction: have
  the host do the working-out.

## The four pillars

| Pillar | What this removes | What it could cost |
|---|---|---|
| Easy to start | Nothing to configure: the deploy defaults are the measured settings. | None found. |
| Easy to trust | A saved proposal or result gets the model's fullest reasoning, as before. A reply cut short is an error, never a shorter answer. Each model call records the level it ran at. | Answers are written with less thinking than before. No loss was measured; the samples are small. |
| Easy to act | A question is answered in a quarter to a third of the time. A stalled call costs 30 s, not 150 s. | A turn that saves something is no faster. |
| Easy to adopt | No change to what people do. One variable returns to the old behaviour. | None found. |

## How we will know

- Seconds per answer, model seconds and model calls, already kept on every chat answer (`timing`).
- The level each model call ran at and its reasoning tokens, now kept on every call.
- Share of answers with a number the check could not trace, already kept (`grounding`).
- Not yet measured: any of this in production, and a qualified person's reading of answers at each level.

## Not done

- **Reading the answers properly.** Nobody qualified has read these answers. My reading checked counted and
  sweeping statements against the series, nothing more.
- **The live deployment.** The settings are in the deploy template; nothing was deployed and the live Lambda was
  not inspected.
- **Showing the answer as it is written, a routing key, another endpoint.** See the table above.
- **Two faults seen in the answer check, not fixed here.** It marks "the largest difference is 0.94 g/L" as
  contradicted when a larger concentration appears in the same sentence (three of six max answers). And it reports
  derived differences as untraced numbers.
- **The per-step time limit.** A step still answering at 150 s is cut off. With streaming the failure now says
  whether the endpoint was silent or still answering, so the next evaluation can tell which it is.
