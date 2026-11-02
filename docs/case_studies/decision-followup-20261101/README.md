# Completed GLM-5.3 decision evaluation

**Result:** Adding the mechanistic tool improved constrained decisions relative to the same agent without it in this frozen simulated cohort. This does not establish real manufacturing effectiveness or added agent value beyond a conventional model selector.

## Shareable files

- [One-page PDF](../../../output/pdf/sievance-evaluation-20261101.pdf)
- [Chart](decision-results.png), [vector version](decision-results.svg)
- [Full results](report.md), [machine-readable analysis](analysis.json)
- [LinkedIn draft](linkedin-draft.md), [email draft](email-draft.txt)
- [Study rationale and limitations](../../research/decision-followup-protocol-20261101.md)

The drafts contain measured results and limitations. No email was sent, public post made, or website deployed.

## Cost and verification

Across the stopped cost pilot and final cohort, token-rate estimates total **$8.09**, with **$6.75** retained as worst-case reservations for three pilot requests whose usage was not recovered: **$14.84 estimated/held in total**, not a verified invoice or an account-wide spending statement. The final cohort itself accounted for $5.64, with all98 requests settled and no budget denials. See [cost and verification receipt](cost-and-verification.json).

All24 A/B input pairs matched; receiving observations respected decision/assay cutoffs; the configured and endpoint-reported models matched GLM-5.3; source hashes remained unchanged. Eighteen software regression checks passed. Eight post-run action replays across four scenarios agreed with the independent Python solver. Those checks substantiate execution and numerical consistency, not real manufacturing validation.

## Measured result

24 prespecified simulated scenarios, 48/48 agent submissions completed. Actual Modal GLM-5.3 responses and usage were recorded for 98 forwarded requests. Both arms saw identical losslessly represented evidence and shared tool schemas; only B had the mechanistic tool. The decision policy was the same for both.

| Outcome | GLM alone | GLM + model | Model-only selector |
|---|---:|---:|---:|
| Correct constrained decisions | 10/24 | 23/24 | 23/24 |
| Constraint-violating operating decisions | 14 | 1 | 1 |
| Correct stops | 0 | 12 | 12 |
| Unnecessary stops | 0 | 0 | 0 |
| Mean simulated inventory, kg | 323.45 | 266.48 | 277.59 |
| Mean constraint-feasible inventory, kg | 219.21 | 255.63 | 266.74 |

The paired correct-decision difference was **+54.2 percentage points**, descriptive95% interval **+33.3 to +75.0**. The prespecified simulated-decision support criterion was met. Constraint-feasible inventory increased by 36.42kg on average, descriptive95% interval7.32–71.20kg. This metric assigns zero to stops/violations; it is not measured quality or released yield. Ordinary inventory decreased because stopping forfeits counted production. These distinctions must remain visible.

Scenarios are independent conditional on the shared source fit and declared synthetic distribution, not independent industrial plants. Half include continuing transfer decay absent from the prediction model. There were no numerical coverage failures, failed final submissions or budget denials. The earlier cost pilot is excluded, including its interrupted/failed attempts.

## Remaining failure

In PF-51008, continued transfer decay made every allowed operating plan infeasible. GLM+model and the model-only selector nevertheless chose `strong_feed_reduction`. The model forecast minimum DO2 was2.5766mg/L; the hidden process reached1.7858mg/L with1.4hours below the assumed2mg/L limit. This is model error under the declared mismatch, not another selection of a centrally predicted infeasible plan. All eight checked action replays across four scenarios, including this failure, agreed with an independent numerical solver.

No post-result prompt/model correction or favorable rerun is included. The earlier real CHO agent forecast comparison remains negative. Its cached model forecasts were reproduced; the source of the biological model bias was not uniquely identified, and no new real intervention qualification is claimed.

## Evidence and reproducibility

Original local run: `backend/results/interventions/decision-followup-final-20261101/`.

- `protocol.json`: frozen design, policy, paths, source hashes, scenario generator and analysis rule.
- `modal-admission.jsonl`: request reservations, response-reported model IDs and usage settlements; no credentials or prompt content.
- `attempts/`: input packets, actual GLM submissions, tool calls and SDK events.
- `results.json`: all scenario outcomes and hidden-menu adjudications.
- `independent-replay-check.json`: post-run numerical audit of eight selected action replays, with no tuning.
- `runtime-observation.json`: observed native-library and SDK-entry hashes.
- `isolation.json`: numerical-tool read/network/credential-denial checks.
- `cost-and-verification.json`: combined pilot/final accounting and final verification.

The diagnostic red baseline is retained in `backend/results/interventions/diagnosis-20261101/`: the recorded26 centrally infeasible model-informed choices failed the proposed constraint-first policy. Development diagnosis is not pooled with final outcomes.

To regenerate this report without model calls, from `backend/`:

```sh
/private/tmp/sievance-eval-20261101/bin/python -m benchmarks.interventions.followup_report \
  --root results/interventions/decision-followup-final-20261101 \
  --output ../docs/case_studies/decision-followup-20261101
```

The temporary Python3.11 environment uses the adjacent pinned dependency list. Native simulator source was restored at commit `e08fc71fef193448f3ee9a304187dc92b88f3acc`; its two scientific implementation files match the previously frozen SHA-256 values. The native library remains separately required. To run a new study, use a fresh output directory and new seed range, freeze it, and dispatch through `scripts.run_bounded_agent_benchmark`; never overwrite this cohort or silently reuse its cases as an untouched holdout.

The chart/PDF/package scripts are `backend/scripts/plot_decision_followup.py` and `backend/scripts/package_decision_followup.py`. Model-output claims should be regenerated from `analysis.json`, not manually copied into a marketing headline.
