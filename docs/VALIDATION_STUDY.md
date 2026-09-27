# Prospective validation study

The simulation comparison is a business-case hypothesis. Use this study to
produce evidence for claims about actual time savings and output improvement.

## Study unit and arms

Use a completed, de-identified investigation case as the unit. Include at least
30 representative cases across process, equipment, material, laboratory, and
compound deviations. Freeze the source-record snapshot for each case and run two
arms against identical information:

1. **Traditional:** qualified personnel use the current approved workflow.
2. **Agent-assisted:** qualified personnel use the application, retain decision
   authority, and record every accepted, edited, and rejected recommendation.

Randomize case order. Do not expose the known final root cause to either arm.
Have two independent QA/MSAT reviewers score redacted outputs without knowing
which arm produced them; adjudicate disagreements.

## Primary endpoints

Capture timestamps and active human effort separately.

| Endpoint | Definition | Desired result |
|---|---|---|
| Active human time | Minutes of hands-on investigation and document preparation | Lower |
| Time to review-ready package | Elapsed time from case start to submitted package | Lower |
| Critical-error rate | Unsupported cause, wrong scope/disposition, or missed required evidence | Non-inferior or lower |
| Evidence coverage | Required evidence items present and correctly linked / applicable items | Higher |

Secondary endpoints are reviewer correction minutes, citation correctness,
counter-evidence coverage, approval-policy violations, recommendation acceptance
rate, and reviewer-rated completeness on a fixed rubric.

## Claim gates

Pre-register thresholds before scoring. A defensible default is:

- at least 25% lower median active human time;
- at least 20% lower median time to a review-ready package;
- no increase in critical-error or approval-policy violation rate;
- at least 10 percentage points higher evidence coverage; and
- the paired uncertainty interval for the primary time endpoint excludes zero.

Report the sample, exclusions, medians, paired changes, uncertainty intervals,
and all safety failures. Segment results by case type and complexity. Do not turn
the simulation's configured 59% labor reduction or its composite quality score
into a customer claim until this study reproduces the effect.

## Safe claim language

Before validation: “In a paired simulation using explicit operating assumptions,
the agent-assisted workflow reduced modeled investigation effort while preserving
human approvals.”

After validation: state the observed effect, sample, study design, and uncertainty;
for example, “Across N retrospective shadow cases, median active preparation time
was X% lower, with no increase in critical errors.”
