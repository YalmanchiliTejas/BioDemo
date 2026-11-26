# LinkedIn post draft — reviewed experiment results

I rebuilt our freeze-drying model to test a specific question: does giving an AI
agent a mechanistic model improve its predictions and operating suggestions?

The revised model tracks different vial populations, thermal storage and the
hottest vials still drying. Both model arms use the same rule marking forecasts
as outside their valid domain when equipment capacity is exceeded.

We compared the same AI with numerical Python alone, with our original model,
and with the revised model. We included deterministic model-only controls and
retained unsuccessful runs: 24 synthetic cases, two tasks, 144 primary AI sessions.

The results were mixed:

- Before receiving-process observations, model-only mean absolute drying-time error fell from
  2.57 to 1.86 hours. After early-data calibration, it increased from 0.37 to
  0.45 hours. Both comparisons had predictions for all 24 cases.
- In the forecasting task, the agent with the revised model selected 24/24
  feasible simulated schedules; the agent with the original model selected
  22/24. That is a small, exploratory result.
- Both models missed two of 20 capacity violations in a separate 32-condition
  challenge. More model detail did not remove missing-characterization risk.

One useful example: the revised model showed only 0.018°C of nominal temperature
margin. The agent selected a slower schedule with more margin, which avoided the
threshold crossing in the hidden simulation. Its explanation still contained an
unsupported uncertainty estimate. A good decision and a reliable explanation
need separate evaluation.

We also challenged our own workflow comparison. On the same six cases, more time
plus a final submission prompt raised submissions without a prepared model from
3/12 to 8/12. Each model-assisted arm submitted 12/12 under both protocols. The
initial completion gap was partly a workflow-budget effect.

All outcomes are synthetic, with shared physical assumptions between the models
and evaluator. This does not demonstrate prevented CDMO failures or manufacturing
savings. The next test needs independent laboratory data and blinded receiving-
equipment runs.

I'm looking to collaborate with researchers in lyophilization and process
modeling on that test: defined operating decisions, independent characterization,
held-out runs, and success criteria agreed before seeing outcomes.

---

Publishing notes: attach the case-study materials, and link the full primary and
same-case sensitivity results. Do not post the primary completion-gap figure on
its own. The capacity challenge and budget sensitivity were motivated after
inspecting primary results, then frozen before their own execution. No claim of
industrial validation, statistical superiority, or proven failure prevention is
supported. This is a draft; nothing has been posted.

Evidence: [case study](README.md), [primary results](report.md),
[same-case sensitivity](sensitivity-comparison.md), [capacity challenge](stress/report.md),
[illustrative case](illustrative-case.json).
