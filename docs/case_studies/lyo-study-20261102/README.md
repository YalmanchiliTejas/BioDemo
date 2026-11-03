# Freeze-drying: does a better model produce better decisions?

**This is a completed synthetic primary comparison, with mixed results.** It
supports a narrower claim than preventing real tech-transfer failures: a prepared
mechanistic tool can make a constrained agent workflow more useful, while model
fidelity, missing characterization and the agent's interpretation remain separate
sources of error. Supplemental analyses are reported separately.

Start with the [four-page primary brief](case-study-brief.pdf), then the
[complete primary results](report.md) and
[same-case sensitivity comparison](sensitivity-comparison.md). The
[LinkedIn post draft](linkedin-post.md) incorporates both experiments. The [per-case CSV](per-case.csv) and
[summary JSON](summary.json) retain denominators and failed attempts. The
[implementation and reproduction guide](../../../backend/benchmarks/lyo_study/README.md)
links the frozen protocol and commands.

## What changed

The original model represented a single quasi-steady vial. The revised model
tracks weighted vial populations, their thermal storage, individual ice exhaustion
and the hottest population still undergoing primary drying. A dry vial warming
toward the shelf is distinguished from an active sublimating vial exceeding its
temperature limit. Both old and new models receive the same applicability gate:
once equipment capacity is exceeded, a prescribed-pressure model cannot supply a
valid completion forecast. The comparison therefore does not credit the new
model merely for receiving a better validity rule.

The change adds useful structure, not a full spatial heat-transfer solution,
validated uncertainty model, or chamber-pressure controller. Published work
already establishes mechanistic primary-drying models as tools for process
development and transfer; our new question concerns their use by agents.
[Vanbillemont et al. (2025)](https://link.springer.com/article/10.1186/s41120-025-00115-5)
reports experimental process-transfer verification. Our implementation is a
simplified research model and does not inherit that paper's validation.

## What was tested

24 authored synthetic cases cover six equally represented families. Each case
has two tasks: forecasting after six hours of observations, and assessing transfer
before receiving observations exist. Three versions of the same AI receive the
same public evidence: A has numerical Python but no prepared physical model; B
also gets the original model; C gets the revised model. A may build its own model.
Deterministic B/C selectors provide a control for whether an agent adds anything
beyond running a simulator.

Models, public packets and scoring were frozen before the primary runs. The
comparison contains 96 deterministic evaluations and 144 AI slots, one realization
per case/task/arm. The two model arms use identical calibration objectives and
bounds. Hidden outcomes are inaccessible to agent tools. The reference shares
physical laws and approximate population structure with the revised model, which
favors its applicability; this is not independent physical validation. Early
ice-mass observations are synthetic information channels that routine plant
historian records may not contain.

## Primary findings

| Question | Original model | Revised model | Interpretation |
| --- | --- | --- | --- |
| Model-only pretransfer completion MAE, 24/24 predictions | 2.57 h | 1.86 h | Better predictions before receiving observations |
| Model-only forecast completion MAE, 24/24 predictions | 0.37 h | 0.45 h | Worse predictions after calibration |
| Model-only forecast thermal detection, 3 positives | 1 detected, 2 missed; 0 false alarms | 2 detected, 1 missed; 1 false alarm | A detection/false-alarm trade-off with very little positive support |
| Agent forecast operating choices, 24/24 submissions each | 22 feasible, 2 unsafe | 24 feasible, 0 unsafe | Promising in this small simulated action grid |
| Agent pretransfer choices, 24/24 submissions each | 20 feasible, 4 unsafe | 20 feasible, 3 unsafe, 1 characterize | No increase in feasible-choice count |

Here, unsafe means a constraint violation or noncompletion in the synthetic
evaluator, not an observed plant incident. Lower prediction error did not reliably
translate into better operating choices. Deterministic pretransfer selection
produced 19 feasible and five unsafe choices with either model.

Under the primary four-model-call/120-second limit, A submitted only 4/48 answers,
while B and C each submitted 48/48. This measures the cost of constructing a model
within that workflow as well as the usefulness of a prepared tool. It does not
establish that agents cannot reason about physics. The separate budget/submission
sensitivity addresses this limitation and must accompany any public claim about
the completion gap.

That sensitivity is now complete: on the exact six selected cases and both tasks,
A submissions rise from **3/12 to 8/12**; B and C remain **12/12 each**. A's four
failures comprise two no-submission outcomes and two timeouts. Its sensitivity
forecast MAE is 53.99 h on four of six eligible predictions, versus 0.16 h for B
and 0.25 h for C on six of six. These MAEs have different coverage. Pretransfer
error for A improves on the two cases predicted in both protocols, but two cases
cannot establish a stable effect. On this subset, C's pretransfer MAE is slightly
worse than B's, despite its lower error across the full primary set. See the
[full sensitivity results](sensitivity/report.md) and paired comparison for all
outcomes. More time and a submission-only final turn change the workflow result;
this reused-case, joint-policy experiment does not isolate a pure budget effect.

The primary KEEP schedules contain **zero reference capacity violations**. Their
negative warnings cannot establish capacity sensitivity. A separately frozen
[32-condition capacity challenge](stress/report.md), motivated after that gap was
found, gives both models 18 detections, two misses and no false alarms. The new
model has no detection advantage there. In that challenge, it is more accurate
when no additional hidden heat-transfer shift is imposed and less accurate
under an undisclosed receiving-equipment shift. Population factors remain
approximate in both strata.

## A useful choice with an imperfect explanation

In the post-hoc illustrative case `LYO-8f799557ef`, the revised model predicts a
KEEP temperature margin of only 0.0175°C. The deterministic selector accepts the
nominally feasible fastest schedule. Agent C instead chooses the −22°C shelf
alternative, with a predicted margin of about 1.05°C. KEEP later crosses the
threshold in the hidden reference; the selected alternative does not and finishes
at 40.08 h versus KEEP's 37.28 h. This is an example of the agent using a model's
margin to choose a more conservative proposal. It is selected to explain the
mechanism, not an additional independent result.

The explanation still needs scrutiny. Its estimated ±4–6 h uncertainty is not a
validated interval. Calibration RMS combines standardized temperature and ice-mass
residuals; it is not a temperature uncertainty in °C. Agent B also gives an
unsupported capacity-limitation explanation for schedule differences. The
so-called WARM action is cooler than KEEP's later −20°C step; labels alone do not
explain the physics. A feasible answer does not establish correct reasoning.
The [actual submissions and reference summaries](illustrative-case.json) preserve
those flaws rather than rewriting the agents' explanations.

## Evidence needed next

The next useful collaboration is an independent, blinded laboratory transfer
test on one formulation, vial/fill configuration and defined primary-drying
decision. Agree the intended use and acceptable error with the lab before
unblinding outcomes. Characterize source and receiving equipment separately,
including vial heat-transfer variation, formulation resistance and critical
temperature, and pressure-dependent equipment capacity. Agree a feasible sensor
plan instead of assuming access to continuous remaining-ice measurements.

Separate calibration runs from receiving-equipment test runs. Include repeated
conditions, safe operating margins and supervised boundary challenges suitable
for nonclinical material; let the laboratory determine the safe protocol. Freeze
the models and agent comparison before the held-out runs. Score endpoint error,
temperature/capacity warnings, false alarms, abstention, unsafe recommendations,
and engineering review time separately. Compare with an experienced engineer and
the deterministic model selector as well as the agent without a prepared model.
Choose replication and sample size from measurement variability and the effect
that would change an engineering decision, not from a desired headline.

This proposed next step follows the emphasis on intended use, characterization,
uncertainty and validation in the
[2026 lyophilization digital-twin framework](https://link.springer.com/article/10.1186/s41120-026-00150-w).
The current work provides software and a falsifiable protocol to discuss with a
Purdue collaborator; it does not yet establish prevention of CDMO failures or
realized manufacturing savings.

## Verification and provenance

122 targeted tests passed, including conservation, limiting behavior, population
events, capacity applicability, scoring, isolation, recovery and reporting. No
claim is made that the entire repository test suite passes. A broader run was
stopped with unrelated socket-bound connector/database test failures in the
sandbox. The final PDF was visually checked.

The primary campaign encountered macOS process-cleanup errors. Original journals
remain unchanged: two successful B decisions were reconstructed only from
matching accepted and finished records, one A attempt remained an infrastructure
failure, and two never-attempted C slots ran in a separate continuation. No scored
failed answer was retried or replaced. All 144 slots are accounted for: 100
completed submissions, 43 no-submission outcomes and one infrastructure failure.
The primary plus continuation token-based inference estimate is $3.66262224,
with no unresolved reservations; this excludes local compute and engineering
effort and is not an invoice. Three additional cost-accounting tests passed after
the sensitivity run exposed two requests without final usage receipts. Across
all campaigns, the settled token-based estimate is **$4.86440188**, with **$4.50**
still reserved for unknown request costs: **$9.36440188** total conservative
accounting under the original $10 cap. Unknown costs are not treated as zero.
The [sensitivity comparison JSON](sensitivity-comparison.json) preserves all three
ledger hashes and verifies the six actual submission-only provider requests.
