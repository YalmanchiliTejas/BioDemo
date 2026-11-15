# Direct workflows, the decision model and answer time

Written 2026-11-14, revised 2026-11-15 with the completed trial extension and the live model runs. Follows
[the direct-workflow evaluation note](direct-workflow-evaluation-20261114.md) and the
[trial architecture](../architecture/sievance-fast-workflows-trial.drawio). The interface it led to is described in
[the workbench note](../product/workbench.md). Governed by [Main_Culture_andETHOS.md](../../Main_Culture_andETHOS.md).

This note records what the trial code does, how request time is measured, what was measured and what was not.
Nothing here is a production latency figure or a manufacturing validation.

## The job

An engineer selects a routine request (find, check, reconcile, compare, trace, prepare) and needs a correct,
source-backed result in seconds. The target is an answer within 10 seconds. It is measured and shown, never
enforced: a slower correct answer is preferred to a faster wrong one.

## What answers within the target

| Request | Path | Measured |
| --- | --- | --- |
| A task chosen in the workbench or Work, or a typed sentence that is exactly one routine task | Host calculation, no model | 246/246 matched the reference; mean 0.012 s, slowest 0.204 s |
| The same routine request typed in chat | Same calculation, answered in the conversation | 3/3 right, 0.1 s or less (live run) |
| "What does this show, and what should I check next?" about a calculated result | One model call over the calculation, numbers checked against it | Low reasoning effort: 6/6 right, mean 3.2 s, slowest 6.4 s. Default effort: 6/6 right, mean 17.4 s, slowest 28.3 s |
| A routine request phrased loosely ("compare sugar…") | Jev suggests the task; the person confirms with one click | Right task suggested for 32 of 33, about 0.2 s each. Not run unattended: see option C |
| A "why" question in chat that names one delivery and parameter | The same one-call explanation, as a quick first answer | 3/3 right, 3.1–3.4 s one at a time; 12–41 s with three at once on the single deployment |
| A follow-up, or any other open question, through the assistant | Assistant, with the calculation attached | 3/3 answered, 2/3 with the reference figures, 65–137 s |

"Right" in the live rows means the answer states the reference figures: the largest difference, its time, the
mean difference, and both batches. That is necessary, not sufficient; nobody qualified has read the wording.

## Is GLM-5.3 more model than the job needs?

For the bounded explanation, at its default setting, yes. The same model, endpoint and calculated result were
used both ways, and the only change was `reasoning_effort=low` on that one call:

| Setting | Answered | Reference figures | Mean | Slowest | Output tokens (6 answers) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Default | 6/6 | 6/6 | 17.4 s | 28.3 s | 30,462 |
| Low reasoning effort | 6/6 | 6/6 | 3.2 s | 6.4 s | 3,698 |

At the default the model spends most of its output on reasoning before it writes. That reasoning is not needed
here because the host has already done the arithmetic and checks every number in the reply against the result;
a reply with a figure that is not in the result is withheld. An earlier test found low effort chose the wrong
run on a comparison it had to work out itself. That failure cannot occur on this path, because the model no
longer works the comparison out.

For open-ended investigation through the assistant, nothing here says GLM is too much. The assistant alone was
the slowest and least reliable path measured: it could not page through a delivery to the values it needed.

| Path, same deliveries | Request | Answered | Reference figures | Mean | Slowest |
| --- | --- | ---: | ---: | ---: | ---: |
| Assistant alone | Routine | 2/3 | 0/2 | 197 s (answered) | 226 s |
| Assistant alone | Question | 3/3 | 0/3 | 127 s | 215 s |
| Workbench path | Routine | 3/3 | 3/3 | under 0.1 s | 0.1 s |
| Workbench path | Question | 3/3 | 2/3 | 90 s | 137 s |

What follows from this:

- `LIFESCI_INTERPRETER_REASONING_EFFORT=low` is now set in the local configuration. It applies only to the
  one-call explanation, which also asks the endpoint for JSON-only output; the assistant keeps the deployment's
  default. Re-measured in that configuration: 6/6 right, mean 4.9 s, slowest 7.3 s.
- No other model could be compared: the Modal deployment serves only GLM-5.3 and no Anthropic or OpenAI key is
  configured. The harness accepts `--candidates haiku,sonnet,luna,sol` once keys exist.
- Chat now answers a "why" question that names one delivery and one recorded parameter first with that
  explanation, and says it read nothing else; a follow-up goes to the assistant. If the explanation is withheld
  or the model is unavailable, the assistant answers as before. `ASSISTANT_QUICK_ANSWERS=off` restores the old path.
- The deployment answers one request at a time quickly. Three at once took 12–41 s for the same answers.

Records: [summary](../../backend/results/workflow-trial-live-20261115/summary.md) and the row files beside it.
Six explanation cases and three delivery pairs, one attempt each, three assistant requests at a time against
one deployment. These are indications, not rankings.

## How request time is measured

- **Every HTTP request** returns a `Server-Timing` header. `GET /v1/latency` gives the recent window per route:
  count, mean, p50, p95, slowest, and how many were over the target. It is kept in memory per process.
- **Every direct task result** carries `timing`: seconds per phase, the total, the target and whether it was met.
- **Every chat answer** carries `timing`: seconds from sending to the saved answer, time queued, model seconds
  and calls, tool seconds and calls, which path answered, and whether the target was met.
- **Every explanation** carries its total and model seconds.

## The offline benchmark

```sh
PYTHONPATH=backend .venv/bin/python -m benchmarks.workflow_trial.run \
  --output backend/results/<new-directory> --repeats 3
```

It reads the three held-out CHO deliveries with the real ingestion service (configuration D, no model calls),
shares them as provisional evidence because none is verified, and sends every request through the HTTP API in
process. Reference answers are calculated from the deliveries' answer keys, opened only after ingestion and never
given to the application. The reasoning model's entry points are blocked; an attempt fails the run. Failed
requests stay in the report. An existing output directory is never overwritten.

The deliveries carry no batch context, requirements or usage records, so three specifications, two batch records
that differ only in equipment, and one recorded use of a lot are **constructed** for the trial and labelled so in
the report. The measurements remain the real CHO values.

Recorded run: [report](../../backend/results/workflow-trial-20261115/report.md),
[full rows](../../backend/results/workflow-trial-20261115/report.json). 82 distinct requests, three repeats.

| Job | Requests | Matched reference | Mean | p95 | Slowest |
| --- | ---: | ---: | ---: | ---: | ---: |
| 01 Find records | 18 | 18 | 0.024 s | 0.097 s | 0.097 s |
| 02 Select applicable evidence | 27 | 27 | 0.003 s | 0.004 s | 0.004 s |
| 03 Reconcile measurements | 18 | 18 | 0.017 s | 0.204 s | 0.204 s |
| 04 Compare batches | 99 | 99 | 0.009 s | 0.015 s | 0.037 s |
| 05 Suggest causes | 9 | 9 | 0.005 s | 0.006 s | 0.006 s |
| 06 Find gaps | 18 | 18 | 0.025 s | 0.049 s | 0.049 s |
| 07 Trace impact | 12 | 12 | 0.007 s | 0.015 s | 0.015 s |
| 08 Prepare review | 9 | 9 | 0.005 s | 0.005 s | 0.005 s |
| 08 Propose an action, keep it in a work plan | 9 | 9 | 0.017 s | 0.019 s | 0.019 s |
| Prepared delivery profile | 9 | 9 | 0.012 s | 0.034 s | 0.034 s |
| Three tasks as one flow | 9 | 9 | 0.030 s | 0.034 s | 0.034 s |
| Values in review refused unless asked | 9 | 9 | 0.004 s | 0.005 s | 0.005 s |

What each is checked for:

- **Compare and reconcile:** every matched time, the mean and standard deviation of the differences, the largest
  difference and its time, each unit-converted value, inside a time window, and with samples paired up to two
  hours apart (reference pairing is plain arithmetic; a tie is not scored). The injected conflicting duplicate
  must be reported and must stop that comparison from being called complete.
- **Fair comparison:** batches with differing equipment must be reported as differing. Context that is not
  recorded must never be reported as the same.
- **Gaps:** against typed expectations, the gaps must equal the samples the key marks absent. Against approved
  specifications with nothing typed, the unrecorded parameter must be reported as unavailable, the
  specifications cited, and a request drafted but not sent.
- **Impact:** the batch with the recorded use is returned as recorded usage, the genealogy is reported
  incomplete, and exposure is never confirmed.
- **Proposal:** proposing carries nothing out; the proposer cannot approve; the result waits for approval; after
  QA approves, the step reads "approved, not yet carried out".
- **Reuse:** the first calculation is fresh, and an identical repeat is reused after access and source revisions
  are rechecked (0.009 s against 0.013 s).
- **Sources:** each result cites the selected delivery at its current revision, says it used values in review,
  and never contains the copy of a delivery at a site the engineer cannot read.
- **Causes:** checked only for making no claim. These deliveries record no reviewed cause.

Typed sentences through the request router, host rules only: 261 requests. 81 exact routine requests ran the right
task directly (mean 0.012 s including the calculation). 81 questions and unsupported requests were correctly left to
the assistant. 99 loosely phrased routine requests were also left to the assistant: slower, not wrong. No request
ran a wrong task.

Preparation is reported separately: 2.6 s for the calibration delivery and 0.4–1.3 s to read each target delivery.

Limits: three deliveries, one site, laboratory-scale public data repackaged as fictional deliveries; repeats
measure variation, not new cases; in-process requests exclude network and browser time; percentiles of a sample
this size do not establish a production figure.

## Option C: the decision model

Jev (TypeSafe System One) sits behind the gateway in [decisions.py](../../backend/src/lifesci/gateway/decisions.py).
It is off unless `LIFESCI_DECISION_ADAPTER=jev` and `TYPESAFE_API_KEY` are set
([settings](../../backend/engineering-llm.env.example)).

| Task | Question | What the host does with the answer |
| --- | --- | --- |
| Request routing | Which single task, delivery, parameter and batches does this sentence name? | Runs the task only inside a calibrated threshold; otherwise offers it as a suggestion |
| Field meaning | Which recorded parameter is the same quantity as the name typed? | Uses it only inside a calibrated threshold; otherwise asks the person to confirm |
| Applicability | Does this record's text state the requested batch, stage or period? | Keeps "unknown" unless calibrated; shows the suggestion |
| Find records | How relevant is each found record? | Reorders word matches only; exact matches stay first and nothing is dropped |
| Impact links | Does this record document actual use, or only mention the identifier? | Orders what to confirm; exposure is never confirmed by the model |

The host bounds the state and refuses it rather than cutting it; offers `unknown` on every choice; accepts only
supplied candidates; rechecks access before the call and source versions after; records the answering model
version; and writes every call to the audit trail. Disabled, timeout, invalid answer, changed evidence or a
recent failure: the host rules run unchanged.

With a key, the benchmark fits a threshold on one split of the typed sentences, reports precision and coverage
on a held-out split, and writes a calibration file only if every held-out selection at or above the threshold
was right:

```sh
LIFESCI_DECISION_ADAPTER=jev TYPESAFE_API_KEY=... PYTHONPATH=backend .venv/bin/python -m benchmarks.workflow_trial.run \
  --output backend/results/<new-directory> --write-calibration backend/decision-calibration.json
```

### Measured with Jev (15 November)

Run with `--decision-model`, model `jev-1.14.0`. Record:
[report](../../backend/results/workflow-trial-jev-20261115/report.md).

- **The API behaves as documented.** One request with choice, yes/no and score questions returned the documented
  shape in 0.26 s. Across the run a call took 0.18 s on average and 0.30 s at most. 66 calls cost $0.004 at the
  published price.
- **Nothing else changed.** All 246 task requests still matched their reference with Jev on; mean request time rose
  from 0.012 s to 0.032 s.
- **Routing.** Of the 33 loosely phrased routine requests the host rules leave to the assistant, Jev suggested the
  right task, delivery, parameter and batches for 32. The miss read "live cell count" as the wrong parameter.
  It never proposed a task for a question: those do not reach it.
- **Its probabilities do not separate right from wrong here.** Right suggestions scored 0.46–0.77. The one wrong
  suggestion scored 0.52, and a request with a condition the task cannot take ("…after 48 h") was suggested at 0.63.
  No threshold accepts ten or more fit-split suggestions with none wrong, so no calibration file was written and
  nothing runs unattended. A first pass, where the probabilities fell slightly differently, did find a threshold
  (0.56) with 15 of 15 held-out suggestions right; the second pass did not. The difference between the two
  passes is the finding: the margin is too thin to rely on.
- **So Jev is a suggester for now.** In Work the suggestion appears as "Use this selection": one click instead
  of a one-to-two-minute assistant turn.
- **The other four uses added nothing measurable on this data.** Reordering found records gave every candidate
  nearly the same score. For applicability with no recorded date, it answered "unknown" twice (right) and
  "applies" once at 0.45 (wrong, and not applied). For impact links it said a delivery that lists a batch does
  not document use (right).

What would most likely improve it, in order: ask Jev a separate yes/no question, "does the request ask for anything
beyond this task (a time window, a condition, a reason)?", so unsupported requests are caught explicitly; give
each parameter a short description and known synonyms in the choices; and collect real typed requests from
engineers, since 33 authored sentences cannot calibrate anything.

## What the trial architecture asked for, and where it stands

| Item | Now |
| --- | --- |
| Preparation on source change | A delivery's profile is calculated when it is published or shared, once per revision, and reused. |
| Versioned results | Identical comparisons and reconciliations are reused per person, keyed by request, delivery revisions, batch records and analysis version, with access rechecked. Other tasks always recalculate. |
| Indexed retrieval | Search text is cached per record revision. It is still a scan, not the full-text index. |
| Direct tasks as flows | One template runs its three tasks as parallel flow nodes and saves each result. The store serializes reads, so the gain is small. |
| Polars, DuckDB, statistics | DuckDB builds the delivery profile; Polars pairs samples within a tolerance and gives difference statistics. |
| Physical models | Not in direct tasks. They need a model context per process and stay in the model library. |
| Fair-comparison checks | Product, process version, equipment, scale and stage from batch records; not recorded is never assumed equal. |
| Gaps against requirements | Against approved specifications, in three states, with a drafted request the person sends. Procedures and sampling plans are not read yet. |
| Usage genealogy | Recorded usage from executed steps is told apart from mentions, and batches with no recorded steps are counted. Read per request, not a maintained index. |
| Proposals | A result becomes a proposal through the action service; approval, dispatch and receipt stay there. |
| Workbench panels and time window | Built as [the workbench](../product/workbench.md). |
| Assistant baseline on identical evidence | Run, using the person's per-message choice to include deliveries in review. |

## The three reported problems

**Truncated retrieval.** Every result holds the complete series for every selected batch and a comparison summary
over every matched time; rows are a page of a table. What the assistant is shown is shortened in place with a count
of what is not shown. The grounding check no longer reads a comma between CSV fields as a thousands separator.

**Unresolved verification.** Verification stays a reviewer's decision. A person can run direct work on a delivery
still in review by choosing to include its values; the result says it is provisional and lists the open checks.
Forecasts and specification checks still require a verified delivery. The assistant uses such a delivery only when
the person chose that for the message.

**Establishing causation.** Software cannot establish a cause from these records and does not claim to. "Suggest
causes to check" orders linked records in time, marks candidates the recorded times weaken, and lists similar
closed cases and what was not checked. Everything is a hypothesis with the check that would settle it.

## What would change these conclusions

- Real typed requests from engineers, to calibrate Jev's routing or show that it cannot be.
- A key for another model, to compare it with GLM on the bounded explanation.
- A qualified reader for the explanations and assistant answers: the figures are checked, the reasoning is not.
- Cases with reviewed root causes, to measure whether cause screening orders the right candidate first.
- Engineers using the workbench, to measure whether it is quicker than what they do today.
