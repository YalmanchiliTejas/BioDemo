# Actual account workflow evaluations — 2026-11-01

Ran through the authenticated deployed Sievance Assistant in the user’s Test1 workspace. The account API verified all 60 saved inputs and answers. These are synthetic CSV desk reviews, not executed manufacturing actions.

Open Assistant → Conversations. The four top-level demo reports begin with:

- Investigation reports — 15 account evaluations
- Deviation reports — 15 account evaluations
- Data ingestion reports — 15 account evaluations
- Scheduling reports — 15 account evaluations

Each overview points to its separate 15-case conversation. A shorter scheduling-04 follow-up is also saved; the original blocked attempt remains unchanged.

| Workflow | First-attempt answers matching reference | App statuses | p90 / p99 seconds |
|---|---:|---|---:|
| investigations | 15/15 | {'completed': 15} | 15.95 / 17.45 |
| deviations | 15/15 | {'completed': 15} | 19.77 / 29.73 |
| ingestion | 15/15 | {'completed': 15} | 15.94 / 18.38 |
| scheduling | 14/15 | {'needs_information': 14, 'blocked': 1} | 28.33 / 31.70 |

First-attempt task matching: 59/60. All 14 accepted scheduling proposals retained needs_information questions; they were not dispatched. The blocked report exceeded the deployed 4000-character reply limit. Its separate short follow-up completed and matched the scheduling reference. The first-attempt score was not changed.

Reported latency is server turn duration across all 15 attempts per workflow, including the blocked request. At this sample size empirical p99 is the maximum, not a dependable production tail estimate.

Uncached list-rate estimate including the report follow-up and four overviews: $2.9286. Invoice not reconciled. The app's unpriced zero-cost profile was not treated as proof of free calls.

These scores cannot be presented as an improvement over the local 53/60 cohort: the deployed interface, report prompt, shared per-workflow conversation history and source interface differ.

Private receipts: backend/results/account-workflow-evals-20261101/. Login credentials and bearer tokens are excluded. Source and helper code are retained; no deployment, model change, approval or manufacturing dispatch was performed.

Demo video: frontend/public/case-study-results/live-app/account-workflows-20261101.mp4. The footage walks through saved reports in the actual account; it is not real-time inference.

Private receipts remain locally in the ignored directory
`backend/results/account-workflow-evals-20261101/` (about 676 KB). Two attempts to
archive them to private DagsHub timed out at the authenticated API; no local
receipt was pruned and no remote archive is claimed. Retry from `backend/`:

```sh
.tools/benchmark-offload/bin/python -m scripts.data_artifacts publish \
  results/account-workflow-evals-20261101 \
  benchmarks/assets/account-workflow-evals-20261101.json \
  --prune-local --mount-path results/account-workflow-evals-20261101
```

The final MP4 is 20.9 seconds and under 1 MB. Five selected report excerpts were
visually checked: investigation, deviation, ingestion, scheduling and the saved
scheduling follow-up. The temporary encrypted login entry and original recording
were deleted; final footage excludes the sign-in screen.
