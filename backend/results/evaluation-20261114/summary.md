# Initial workflow evaluation — 14 November 2026

The fresh current-agent pilot recorded **1/4 passes (25%)**. Diagnostic AI review found **2/4 correct core outcomes**: the missing-certificate case was penalized by two reproduced evaluation defects. Original grades remain unchanged. Average answer time was **222.29 seconds**, with **0/4 answers within 10 seconds**.

| Agent task | Recorded verdict | Answer time | Audit finding |
|---|---|---:|---|
| Glucose/lactate change | FAIL | 271.17 s | Located the delivery but did not open it; no requested values or differences returned. |
| Batch comparison | FAIL | 184.30 s | Only one lot was reported. The application clipped the model-visible artifact, and the planning limit prevented completing retrieval. The judge incorrectly treated the full stored artifact as model-visible; missing requested values still justify task failure. |
| Conflicting measurement | PASS | 148.75 s | Reported both values and the same-sample conflict, withheld confirmation and proposed QC reconciliation. |
| Missing certificate | FAIL | 284.94 s | Identified the correct missing certificate and refused to substitute LIMS values. Both failed gates have reproduced defects: full-artifact/model-excerpt visibility mismatch and CSV delimiter removal that hides the actual 231.00 h value. |

The unchanged model was `zai-org/GLM-5.3`. The pilot took 674.92 seconds with two workers, including grading. There were 15 agent requests and four judge requests, with no provider errors. Estimated token cost was **$1.5436**: $1.2647 for the agent and $0.2789 for grading. Prices were checked against [Modal's published rates](https://modal.com/library/zai/glm-5-3); the invoice and infrastructure costs are unknown.

| Separate deterministic evaluation | Fresh result | Timing / boundary |
|---|---|---|
| CHO field recovery | 4,791/4,791 expected fields; exact matched values, canonical units and source locations | Mean 1.218 s per target package; 2.221 s calibration ingestion separately |
| Emitted-field identity | 4,791/4,798 matched; seven additional fields belong to the injected duplicate | 99.854% precision under the existing key |
| Injected defects | 4/4 detected, including correct batch/time | False-positive rate not established |
| Verified-package readiness | 0/3; actual publication gate returned HTTP 409 for all three | 54–79 open issues per package; review still required |
| Workflow contracts | 55/55 passed | Regression checks, not manufacturing task accuracy |
| Direct workflow smoke replay | 6/6 passed; two synthetic tasks × three repeats; zero inference | Mean service 0.875 ms; all-attempt wall p95 1.635 s, including setup |

The CHO source is the [public cultivation dataset](https://zenodo.org/records/20829178). Eighteen cultivation runs formed three evaluation deliveries; six runs formed the separate calibration delivery. Measurements are real laboratory data, while delivery companies, layouts, certificates and injected defects are constructed. The original archive checksum and regenerated reference keys were checked. These are existing repository fixtures, not an untouched external benchmark. No human review time was measured. All deterministic runs made zero model calls.

The fourth agent case exposes two reproducible issues. The application clips each workspace artifact at 8,000 characters for the model, while the judge sees the full saved artifact; the model’s truncation statement was therefore supported. Separately, the grounding normalizer treats the comma in `S-009-R01-16,231.00` as a thousands separator, erasing the independently verified `231.00` value. The original recorded failure is retained; the 2/4 diagnostic result is not a new validated benchmark score.

The main measured latency is model inference: the 15 agent calls consumed 888.07 seconds across the four tasks, versus 889.16 seconds total answer time. This pilot supports prioritizing deterministic retrieval and orchestration, completing required source reads, and fixing the evidence/grounding checks before expanding the campaign. No production code was changed for these evaluations.

The four agent cases are newly authored, unreviewed, single-attempt cases with task-category hints in their source identifiers and a same-model judge. Causal diagnosis, downstream impact, effective real-world actions, browser/deployed latency and manufacturing qualification remain unmeasured. The 2–10 second target is unmet for this agent pilot. Numerical direct-task resolution on the CHO packages was not scored because verification remained blocked. Official PRONTO, DABstep, BIRD and RCAEval campaigns have not run.

Full receipts: [consolidated JSON](summary.json), [CHO summary](cho-ingestion-5ci_it3p/summary.json), [CHO source and scoring audit](cho-ingestion-5ci_it3p/audit.json), [original agent report](reasoning/run/report.json), [measured latency and cost](reasoning/measured-summary.json), [model-visible text audit](reasoning/private/prompt-visibility-audit.json), [numeric-grounding audit](reasoning/private/grounding-number-audit.json), [workflow replay](contracts/run-wjcq0qcl/replay-smoke.json).
