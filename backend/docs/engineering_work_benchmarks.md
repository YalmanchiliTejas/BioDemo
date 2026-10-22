# Measuring correct investigations and human effort

The governing specification is [README_benchmarks.md](../README_benchmarks.md).
The v2 implementation is documented in [benchmarks/README.md](../benchmarks/README.md).

## Investigation qualification

The unit is one assigned investigation, with its frozen evidence package,
objective, condition, cutoff, output requirements and policy. A completed model
response is not a qualified case. Qualification requires objective evidence and
data checks, independent blinded investigation review above an approved minimum,
and every integrity gate. Disagreements require independent adjudication.

The policy drafts deliberately contain no passing threshold or noninferiority
margin. Approve those with domain reviewers **before** freezing evaluated case
versions. Do not approve them retrospectively to fit a model output.

A correct declaration of unanswerability can qualify only for a deliverable
predeclared unanswerable and supported by review evidence. Generic abstention
cannot complete an analysis assignment. Unsupported verified causes,
unverifiable material citations, future leakage, unauthorized access, changed
original measurements and autonomous GMP-critical actions fail integrity.

## Human time

Record person-time in seven non-overlapping stages: setup, data preparation,
investigation, verification, corrections, coordination and ongoing configuration.
Sum all people, retries, failed attempts and rework. Unobserved time is null;
zero means an observed zero. Machine waiting and wall-clock duration are separate.

A direct active-work timer is available:

```sh
python -m benchmarks.common.human_work time --case-id FRE-02 --run-id RUN_ID --participant ENGINEER_ID --stage verification --trace human-work.jsonl
```

Enter `a` for a manual action, `p` to pause/resume and `s` to stop. Repeat for each
stage and participant. Import the observed intervals:

```sh
python -m benchmarks.common.human_work import-trace --run-id RUN_ID --trace human-work.jsonl --complete > observed-human-work.json
```

Unrecorded stages remain null. Use `--observed-zero STAGE ...` only to explicitly
attest stages that took zero human work. `--complete` attests that all people,
stages, retries and failures are accounted for. Timers record active intervals,
pauses, stage and participant, without copying proprietary source content.
An agreed observed work-log protocol can also fill the capture template.
Self-reported estimates are labeled and withhold measured savings.

For shared setup, supply a setup-group record with observed `active_seconds`,
`time_source: observed`, an evidence reference, `allocation: equal`, the exact
`run_ids` using it and `measured_case_count` equal to their count. All must be
actual attempts using the same workflow, including failures. Allocation across
conditions is applied before reporting cohorts separately; future hypothetical
cases cannot amortize setup. First-case, repeat-case and unamortized costs are
retained per run.

## Report quantities

- Quality-qualified rate: qualified / all attempted supported investigations.
- Human hours per qualified case: all measured effort, including failures and
  allocated setup/maintenance, divided by qualified cases. Zero qualified cases
  makes this undefined.
- Paired effort reduction: shown only for matching packages, objectives,
  conditions, budgets, policy and seed, with both outcomes qualified and the OS
  meeting the approved noninferiority margin. Report paired N and all-attempt
  rates/effort alongside it. Ambiguous repeated assignments withhold the pair.

Pending reviews or incomplete logs withhold the corresponding metric. Do not
pool CHO and Fresenius, or raw and structured conditions, into universal accuracy
or time-savings scores.

## Exploratory human study

Use approximately 4–6 process engineers/MSAT scientists with fictional, public
or authorized de-identified evidence. Counterbalance task order or assign
independent operators to matched cases. Freeze tools, allowed hints, time limits
and package/task hashes. Reviewers remain blind to method and independent of
operators. Report participant experience, disagreements, failures and requested
clarifications. Small-N results remain exploratory.

No participants have been recruited and no human-study measurements are
established by implementing this harness. The earlier five-stage ledger and
simulation/pilot artifacts are preserved as legacy diagnostics, not v2 evidence.
