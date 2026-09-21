# Fidelity and validation status

Status: **illustrative benchmark, not calibrated or GMP-validated**. No real
manufacturing, QC, maintenance, staffing, or financial data have been provided.
The numbers in `runs/baseline/summary.json` must not be interpreted as expected
performance at a CDMO or as evidence of agent benefit.

## Model boundaries

The simulator has a fixed 30-day clock, one product, 12 batch plans, one
upstream train, one downstream train, one QC lab, and a Traditional controller.
Stage durations, target mass, base yield, fault magnitudes, response times, and
human effort are **explicit assumptions**, not fitted distributions. The
scenario seed changes the incident time by at most two hours. The ground-truth
cause in `campaign.json` and the event log is evaluator-only; a future
controller must see only time-appropriate systems-of-record responses.

Implemented fidelity safeguards:

- Time-stamped abnormal pH/DO, viability, pressure, and pump observations are
  written to the historian; OOS is written to LIMS.
- QC results cannot be reported before their due time, and delayed results keep
  release blocked.
- Media inventory is consumed once per started batch and buffer is consumed on
  entry to downstream purification. A quarantined lot cannot be used in a new
  batch/step; an unstarted or not-yet-purified batch can be manually reassigned
  to a released lot after the Traditional response delay.
- QMS deviations open after detection and close at their modeled closure time.
- Batch release requires passing QC, a released material lot, and no open
  batch-linked deviations.
- The same campaign and seeded fault manifest are independent of any future
  controller; non-Traditional modes currently fail closed.

## Important remaining gaps

1. **Bioprocess physics:** stage durations and yield effects are simplified.
   There is no mass balance, cell-growth kinetics, chromatography breakthrough,
   sensor calibration model, process-control loop, or mechanistic simulator.
   Fault traces are sparse observations, not continuous stochastic trajectories.
2. **Records and integrations:** system APIs are in-process Python objects. They
   do not yet model independent databases, asynchronous replication, access
   controls, electronic signatures, data corrections, API failures, or site-
   specific schemas. The event log is privileged and must never be an agent tool.
3. **Human workflow:** delay and engineer-hour figures are fixed assumptions.
   Shift calendars, weekends, review queues, role-specific permissions,
   approval handoffs, and competing investigations are not yet calibrated.
4. **QC and release:** assays are simplified pass/OOS results. Sampling plans,
   method variability, repeat testing, stability, specification rules,
   batch-record exceptions, and disposition paths need subject-matter review.
5. **Materials and maintenance:** supplier lead times, expiry, cold-chain,
   genealogy, spare-parts stock, repair uncertainty, and maintenance resource
   contention are not yet modeled in detail.
6. **Metrics:** equipment utilization is a coarse production-hour proxy.
   Unplanned downtime counts unavailable asset-hours for the bioreactor,
   chromatography skid, and transfer pump; it is not plant-calendar downtime.
   The current model does not support a defensible OEE calculation. There is no
   calibrated economic valuation yet.

## Evidence required before a credible comparison

- Obtain de-identified batch/event histories or SME-approved distributions for
  stage times, yields, process signals, assay turnaround, failures, approvals,
  labor effort, and release times.
- Fit or configure those assumptions **before** evaluating another controller;
  freeze a versioned scenario set and hold out separate validation campaigns.
- Check that the Traditional mode reproduces observed baseline distributions
  and tail behavior, not just average throughput. Test sensitivity across many
  seeds and alternative incident mixes.
- Review batch record and system interfaces against ISA-88 (batch procedures and
  records) and ISA-95 (manufacturing operations and system exchanges), then have
  QA/MSAT/manufacturing specialists review the mappings and intervention rules.
- Preserve common random numbers and identical physical inputs across modes;
  report confidence intervals and paired differences, not one 30-day run.

Standards references: [ISA-88](https://www.isa.org/standards-and-publications/isa-standards/isa-88-standards),
[ISA-95](https://www.isa.org/standards-and-publications/isa-standards/isa-95-standard).
