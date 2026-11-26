# Freeze-drying model and AI comparison

Exploratory synthetic comparison with shared constitutive physics. Reference completion and subsequent thermal outcomes are censored after equipment capacity exceedance. These are not plant measurements or plant validation.



Forecast: population-minus-legacy completion MAE was +0.07 h on 24 common eligible predictions. AI results (A: 1/24 completed, 1 feasible / 0 unsafe selections; B: 24/24 completed, 22 feasible / 2 unsafe selections; C: 24/24 completed, 24 feasible / 0 unsafe selections).
Pretransfer: population-minus-legacy completion MAE was -0.71 h on 24 common eligible predictions. AI results (A: 3/24 completed, 1 feasible / 0 unsafe selections; B: 24/24 completed, 20 feasible / 4 unsafe selections; C: 24/24 completed, 20 feasible / 3 unsafe selections).

The study asks whether an explicit vial-population model and its availability to an AI agent change forecast errors and proposed operating choices. Forecast uses early synthetic receiving observations; pretransfer uses characterization without receiving observations. The tasks are reported separately.

A receives no prebuilt physical model; it can derive its own simulator using the shared Python tool. B uses the legacy representative-vial model. C uses the population thermal model. B and C use the same capacity applicability cutoff. Model-only B/C are deterministic selectors; AI A/B/C are recorded agent runs. These labels do not identify distinct underlying AI models.

Protocol: [frozen issue #1](https://github.com/YalmanchiliTejas/BioDemo/issues/1). Campaign status: **complete**. All submitted results are rescored from the frozen evaluator files; missing attempts and failed execution remain visible.

Recorded AI model: modal/zai-org/GLM-5.3. Per-attempt limits: 4 model calls, 8 tool calls, 120 seconds; output-token limit 4096.

## Forecast

Completion errors concern KEEP, regardless of the chosen action. MAE uses only eligible cases with a numerical prediction; coverage uses all planned eligible cases. Different coverage can change MAE, so the paired table below also uses common predictions.

| Arm | Planned | Attempted | Completed | Eligible | Predicted | Coverage | MAE (h) | Hindsight-invalid completions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Model B (legacy) | 24 | 24 | 24 | 24 | 24 | 100.0% | 0.37 | 0 |
| Model C (population) | 24 | 24 | 24 | 24 | 24 | 100.0% | 0.45 | 0 |
| AI A (no prebuilt model) | 24 | 24 | 1 | 24 | 1 | 4.2% | 7.80 | 0 |
| AI B (legacy tool) | 24 | 24 | 24 | 24 | 24 | 100.0% | 0.37 | 0 |
| AI C (population tool) | 24 | 24 | 24 | 24 | 24 | 100.0% | 0.44 | 0 |

Hindsight-invalid means the hidden reference later exceeded capacity; it does not establish that the agent could know that from its public evidence.

### Thermal warnings

TP/TN are correct positive/negative calls; FP/FN are incorrect positive/negative calls. Abstain means a submitted unknown. Censored means the reference target cannot be evaluated. Execution failures and unattempted runs are separate. Truth counts include all planned cases regardless of execution. With zero truth positives, sensitivity cannot be estimated; small positive counts also limit interpretation.

| Arm | Attempted | Completed | TP | TN | FP | FN | Abstain | Censored | Failed | Not attempted | Truth positive | Truth negative | Truth unknown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Model B (legacy) | 24 | 24 | 1 | 21 | 0 | 2 | 0 | 0 | 0 | 0 | 3 | 21 | 0 |
| Model C (population) | 24 | 24 | 2 | 20 | 1 | 1 | 0 | 0 | 0 | 0 | 3 | 21 | 0 |
| AI A (no prebuilt model) | 24 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 23 | 0 | 3 | 21 | 0 |
| AI B (legacy tool) | 24 | 24 | 1 | 21 | 0 | 2 | 0 | 0 | 0 | 0 | 3 | 21 | 0 |
| AI C (population tool) | 24 | 24 | 2 | 20 | 1 | 1 | 0 | 0 | 0 | 0 | 3 | 21 | 0 |

### Capacity warnings

TP/TN are correct positive/negative calls; FP/FN are incorrect positive/negative calls. Abstain means a submitted unknown. Censored means the reference target cannot be evaluated. Execution failures and unattempted runs are separate. Truth counts include all planned cases regardless of execution. With zero truth positives, sensitivity cannot be estimated; small positive counts also limit interpretation.

| Arm | Attempted | Completed | TP | TN | FP | FN | Abstain | Censored | Failed | Not attempted | Truth positive | Truth negative | Truth unknown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Model B (legacy) | 24 | 24 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 24 | 0 |
| Model C (population) | 24 | 24 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 24 | 0 |
| AI A (no prebuilt model) | 24 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 23 | 0 | 0 | 24 | 0 |
| AI B (legacy tool) | 24 | 24 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 24 | 0 |
| AI C (population tool) | 24 | 24 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 24 | 0 |

### Proposed actions

Decision coverage counts a manufacturing choice, not characterize. Unsafe means the selected scenario violates a modeled constraint or fails to complete; it is not an observed plant incident. The benchmark throughput score averages synthetic feasible vials/hour over all planned cases, assigning zero to invalid selections, characterize, failed runs and missing attempts. This is not measured plant throughput. Regret is reported only for feasible selections, relative to the best feasible action in the tested grid.

| Arm | Attempted | Completed | Selected / planned | Feasible | Unsafe | Characterize | Abstain with hindsight feasible action | Benchmark throughput score (vials/h) | KEEP score (vials/h) | Feasible regret (vials/h; n) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Model B (legacy) | 24 | 24 | 24/24 | 22 | 2 | 0 | 0 | 159.92 | 143.14 | 0.00; 22 |
| Model C (population) | 24 | 24 | 24/24 | 23 | 1 | 0 | 0 | 163.20 | 143.14 | 1.91; 23 |
| AI A (no prebuilt model) | 24 | 1 | 1/24 | 1 | 0 | 0 | 0 | 7.48 | 143.14 | 0.00; 1 |
| AI B (legacy tool) | 24 | 24 | 24/24 | 22 | 2 | 0 | 0 | 157.12 | 143.14 | 3.06; 22 |
| AI C (population tool) | 24 | 24 | 24/24 | 24 | 0 | 0 | 0 | 168.99 | 143.14 | 2.80; 24 |

![forecast comparison](primary-forecast-comparison.png)

### Matched differences

Differences are right minus left. Completion differences use only cases predicted by both arms. Intervals are descriptive 2,000-resample case bootstrap intervals; one-case pairs have no interval. Authored case families are not manufacturing prevalence, and these intervals do not establish population-level significance.

| Comparison (left → right) | Matched attempts | Common completion predictions | MAE difference (h) | Descriptive interval (h) | Benchmark throughput score difference (vials/h) |
| --- | --- | --- | --- | --- | --- |
| model:B → model:C | 24 | 24 | 0.07 | -0.03 to 0.16 | 3.28 |
| model:B → agent:A | 24 | 1 | 7.15 | — | -152.44 |
| model:B → agent:B | 24 | 24 | 0.00 | -0.00 to 0.01 | -2.80 |
| model:B → agent:C | 24 | 24 | 0.07 | -0.02 to 0.16 | 9.07 |
| model:C → agent:A | 24 | 1 | 6.91 | — | -155.72 |
| model:C → agent:B | 24 | 24 | -0.07 | -0.16 to 0.03 | -6.08 |
| model:C → agent:C | 24 | 24 | -0.00 | -0.01 to 0.00 | 5.79 |
| agent:A → agent:B | 24 | 1 | -7.15 | — | 149.64 |
| agent:A → agent:C | 24 | 1 | -6.91 | — | 161.51 |
| agent:B → agent:C | 24 | 24 | 0.07 | -0.02 to 0.16 | 11.87 |

## Pretransfer

Completion errors concern KEEP, regardless of the chosen action. MAE uses only eligible cases with a numerical prediction; coverage uses all planned eligible cases. Different coverage can change MAE, so the paired table below also uses common predictions.

| Arm | Planned | Attempted | Completed | Eligible | Predicted | Coverage | MAE (h) | Hindsight-invalid completions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Model B (legacy) | 24 | 24 | 24 | 24 | 24 | 100.0% | 2.57 | 0 |
| Model C (population) | 24 | 24 | 24 | 24 | 24 | 100.0% | 1.86 | 0 |
| AI A (no prebuilt model) | 24 | 24 | 3 | 24 | 3 | 12.5% | 51.09 | 0 |
| AI B (legacy tool) | 24 | 24 | 24 | 24 | 24 | 100.0% | 2.57 | 0 |
| AI C (population tool) | 24 | 24 | 24 | 24 | 24 | 100.0% | 1.86 | 0 |

Hindsight-invalid means the hidden reference later exceeded capacity; it does not establish that the agent could know that from its public evidence.

### Thermal warnings

TP/TN are correct positive/negative calls; FP/FN are incorrect positive/negative calls. Abstain means a submitted unknown. Censored means the reference target cannot be evaluated. Execution failures and unattempted runs are separate. Truth counts include all planned cases regardless of execution. With zero truth positives, sensitivity cannot be estimated; small positive counts also limit interpretation.

| Arm | Attempted | Completed | TP | TN | FP | FN | Abstain | Censored | Failed | Not attempted | Truth positive | Truth negative | Truth unknown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Model B (legacy) | 24 | 24 | 0 | 21 | 0 | 3 | 0 | 0 | 0 | 0 | 3 | 21 | 0 |
| Model C (population) | 24 | 24 | 0 | 21 | 0 | 3 | 0 | 0 | 0 | 0 | 3 | 21 | 0 |
| AI A (no prebuilt model) | 24 | 3 | 1 | 1 | 1 | 0 | 0 | 0 | 21 | 0 | 3 | 21 | 0 |
| AI B (legacy tool) | 24 | 24 | 0 | 21 | 0 | 3 | 0 | 0 | 0 | 0 | 3 | 21 | 0 |
| AI C (population tool) | 24 | 24 | 0 | 21 | 0 | 3 | 0 | 0 | 0 | 0 | 3 | 21 | 0 |

### Capacity warnings

TP/TN are correct positive/negative calls; FP/FN are incorrect positive/negative calls. Abstain means a submitted unknown. Censored means the reference target cannot be evaluated. Execution failures and unattempted runs are separate. Truth counts include all planned cases regardless of execution. With zero truth positives, sensitivity cannot be estimated; small positive counts also limit interpretation.

| Arm | Attempted | Completed | TP | TN | FP | FN | Abstain | Censored | Failed | Not attempted | Truth positive | Truth negative | Truth unknown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Model B (legacy) | 24 | 24 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 24 | 0 |
| Model C (population) | 24 | 24 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 24 | 0 |
| AI A (no prebuilt model) | 24 | 3 | 0 | 3 | 0 | 0 | 0 | 0 | 21 | 0 | 0 | 24 | 0 |
| AI B (legacy tool) | 24 | 24 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 24 | 0 |
| AI C (population tool) | 24 | 24 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 24 | 0 |

### Proposed actions

Decision coverage counts a manufacturing choice, not characterize. Unsafe means the selected scenario violates a modeled constraint or fails to complete; it is not an observed plant incident. The benchmark throughput score averages synthetic feasible vials/hour over all planned cases, assigning zero to invalid selections, characterize, failed runs and missing attempts. This is not measured plant throughput. Regret is reported only for feasible selections, relative to the best feasible action in the tested grid.

| Arm | Attempted | Completed | Selected / planned | Feasible | Unsafe | Characterize | Abstain with hindsight feasible action | Benchmark throughput score (vials/h) | KEEP score (vials/h) | Feasible regret (vials/h; n) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Model B (legacy) | 24 | 24 | 24/24 | 19 | 5 | 0 | 0 | 133.37 | 143.14 | 0.17; 19 |
| Model C (population) | 24 | 24 | 24/24 | 19 | 5 | 0 | 0 | 133.51 | 143.14 | 0.00; 19 |
| AI A (no prebuilt model) | 24 | 3 | 1/24 | 1 | 0 | 2 | 2 | 6.18 | 143.14 | 112.87; 1 |
| AI B (legacy tool) | 24 | 24 | 24/24 | 20 | 4 | 0 | 0 | 140.36 | 143.14 | 7.11; 20 |
| AI C (population tool) | 24 | 24 | 23/24 | 20 | 3 | 1 | 1 | 150.72 | 143.14 | 3.07; 20 |

![pretransfer comparison](primary-pretransfer-comparison.png)

### Matched differences

Differences are right minus left. Completion differences use only cases predicted by both arms. Intervals are descriptive 2,000-resample case bootstrap intervals; one-case pairs have no interval. Authored case families are not manufacturing prevalence, and these intervals do not establish population-level significance.

| Comparison (left → right) | Matched attempts | Common completion predictions | MAE difference (h) | Descriptive interval (h) | Benchmark throughput score difference (vials/h) |
| --- | --- | --- | --- | --- | --- |
| model:B → model:C | 24 | 24 | -0.71 | -1.25 to -0.12 | 0.13 |
| model:B → agent:A | 24 | 3 | 50.28 | 7.88 to 109.34 | -127.19 |
| model:B → agent:B | 24 | 24 | 0.00 | -0.00 to 0.01 | 6.99 |
| model:B → agent:C | 24 | 24 | -0.71 | -1.27 to -0.12 | 17.35 |
| model:C → agent:A | 24 | 3 | 50.20 | 7.01 to 109.60 | -127.33 |
| model:C → agent:B | 24 | 24 | 0.72 | 0.11 to 1.28 | 6.85 |
| model:C → agent:C | 24 | 24 | 0.00 | -0.00 to 0.00 | 17.22 |
| agent:A → agent:B | 24 | 3 | -50.28 | -109.34 to -7.88 | 134.18 |
| agent:A → agent:C | 24 | 3 | -50.20 | -109.60 to -7.01 | 144.55 |
| agent:B → agent:C | 24 | 24 | -0.72 | -1.31 to -0.10 | 10.37 |

## Runtime and cost

| Task | Arm | Attempted | Completed | Call-budget exhaustions | Mean recorded wall time (s) | Runtime receipts |
| --- | --- | --- | --- | --- | --- | --- |
| forecast | Model B (legacy) | 24 | 24 | 0 | 1.37 | 24/24 |
| forecast | Model C (population) | 24 | 24 | 0 | 3.25 | 24/24 |
| forecast | AI A (no prebuilt model) | 24 | 1 | 20 | 52.42 | 23/24 |
| forecast | AI B (legacy tool) | 24 | 24 | 0 | 9.95 | 23/24 |
| forecast | AI C (population tool) | 24 | 24 | 0 | 11.24 | 24/24 |
| pretransfer | Model B (legacy) | 24 | 24 | 0 | 0.76 | 24/24 |
| pretransfer | Model C (population) | 24 | 24 | 0 | 2.28 | 24/24 |
| pretransfer | AI A (no prebuilt model) | 24 | 3 | 21 | 51.28 | 24/24 |
| pretransfer | AI B (legacy tool) | 24 | 24 | 0 | 10.42 | 23/24 |
| pretransfer | AI C (population tool) | 24 | 24 | 0 | 9.84 | 24/24 |

Unknown total inference cost: no complete monetary receipt set is available.
Whole campaign proxy ledger, including any preflight or interrupted requests: sum of settled conservative_cost_usd from provider token counts at recorded list rates, not an invoice. Unsettled or abandoned reservations remain unknown spending; total_reserved_usd is the admission accounting amount, not actual charges.



Settled campaign proxy estimate: $3.662622; total admission accounting: $3.662622; unresolved reservations: $0.000000. These are not invoiced charges.

Wall time sums may overlap under parallel execution. Human engineering effort, plant throughput, avoided failures, and operating savings were not measured.

## Interpretation and limits

The evaluator and candidate models share physical laws, so this tests behavior under deliberately introduced synthetic mismatch, not independent physical validity. The population model adds thermal storage and active-vial heterogeneity; it does not resolve temperature fields or predict chamber pressure after overload. Censoring prevents arbitrary post-overload reference pressure dynamics from becoming a physical accuracy target. The half-hourly thermal and ice-mass observations are synthetic information channels, not a claim that routine plant sensors supply them. Pretransfer hidden receiving shifts are unknowable from the supplied characterization alone.

Agents may spend their limited Python and model-call budget constructing a simulator. Budget-exhausted runs remain in attempted counts and receive no decision credit. Any workflow advantage from access to a prepared physical tool is conditional on the recorded call and wall-time limits (4 model calls and 120 seconds per attempt), not evidence that A could not construct a model with more time.

Feasible selections are proposals under the synthetic evaluator and a limited action grid. They are not approved manufacturing actions. Characterization can be an appropriate choice even though it receives no benchmark throughput credit. Lower completion MAE does not establish better action choices or a higher benchmark throughput score, even on common predictions. Forecast error, coverage, feasible choices and unsafe choices must be compared separately; the report does not presume that access to the newer model improves every outcome.

Artifacts: `per-case.csv` preserves every planned row; `summary.json` contains counts, denominators, paired comparisons and source hashes. The PNG and SVG plots are generated from those same aggregate counts.
