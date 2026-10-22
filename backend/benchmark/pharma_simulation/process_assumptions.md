# Process assumptions and credibility boundary

This benchmark is a retrospective synthetic reconstruction. It does not reproduce
Fresenius Kabi's internal process, specifications, equipment, or records.

## Provenance categories

- **PUBLIC FACT** — directly supported by the FDA warning letter or FDA-posted recall announcement.
- **REGULATORY / PROCESS-SUPPORTED** — a general sterile-manufacturing concept, not a statement about this facility.
- **SYNTHETIC ASSUMPTION** — a benchmark parameter chosen to produce plausible variation and labeled as such.
- **AGENT INFERENCE** — a time-bounded hypothesis, never a confirmed historical root cause.

## Signal assumptions

| Signal | Meaning in the benchmark | Basis | Confidence |
|---|---|---|---|
| Relative bioburden signal | Upstream microbial result expressed as a ratio to an abstract action limit | FDA publicly documents multiple action-limit failures; the exact sampling point, result, and limit are redacted. Distribution is synthetic. | Medium |
| Relative endotoxin signal | Finished-product or reserve result expressed as a ratio to an abstract specification | The pass-then-later-OOS sequence is public. Numerical ratios and timing are synthetic. | Medium |
| Sterility result | Categorical finished-product test used to preserve the publicly documented sequence | Public sequence; individual result records and dates are synthetic. | Medium |
| Environmental microbial signal | Normal variation with selected synthetic alerts/actions | Process-supported monitoring concept; locations, values, and relationship to batches are synthetic. | Low |
| Gram-negative morphology | A synthetic time-stamped observation consistent with the public statement that gram-negative confluent growth was observed | Public observation; exact lot, sample, and time are not public. | Medium |
| Process-temperature delta | Unitless deviation from a nominal center | Synthetic assumption; avoids claiming a real validated range. | Low |
| Differential-pressure margin | Unitless environmental-control margin | Process-supported concept; parameterization is synthetic. | Low |
| Equipment-pressure ratio | Unitless ratio used for the independent equipment scenario | Entirely synthetic. | Low |
| Hold-duration margin | Unitless proximity-to-boundary signal with many normal near-limit values | Entirely synthetic; deliberately non-predictive of incident status. | Low |
| Sterility-result timing | Categorical result made available at least 14 days after collection | Process-supported duration concept; exact workflow and method are not manufacturer claims. | Medium |
| Deviations and CAPA | QMS records used to evaluate recurrence and cross-system reasoning | General manufacturing workflow; identifiers, wording, timing, and outcomes are synthetic. | Medium |
| Maintenance and operator events | Contextual records that can support or contradict hypotheses | General manufacturing workflow; all records are synthetic. | Low |
| Complaints | A delayed synthetic signal representing the type of adverse-event investigation described publicly | FDA documents reports of apparent pyrogenic reactions; exact synthetic lot assignment, wording, and time are not public. | Medium |

## Causal boundary

The benchmark labels relationships as **known**, **plausible**, or **unknown**:

- Known: the public incident sequence encoded in `public_ground_truth.json`.
- Plausible: repeated related upstream signals can justify expanding an investigation.
- Unknown: the actual historical root cause. The benchmark deliberately leaves the reconstructed public incident root cause null.

Passing finished-product testing is treated as potentially contradictory evidence, not proof that an upstream signal is irrelevant. Maintenance and environmental records may support hypotheses, but the benchmark does not encode them as the confirmed cause of the public incident.

Final recall outcomes are stored only in the benchmark-only outcome table. Live batch rows remain `released`, and `state_at(timestamp)` derives `planned`, `in_process`, `quality_review`, or `released` from information available at the cutoff. Public facts include `available_at` timestamps and are not supplied to the agent before those timestamps.

Manufacturing memory is disabled in the primary full-context condition. A separate memory-enabled ablation measures whether retrieval changes the decision without making the target pattern part of the default input.

## Parameterization

Exact models, bounds, thresholds, missingness, frequency, and confidence are declared in
`data/simulation_config.yaml`. Values are normalized when manufacturer-specific specifications
are not public. A pharmaceutical manufacturing SME should review these assumptions before the
benchmark is used for external performance claims.
