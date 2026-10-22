# Executed results and remaining work

Source: [machine-readable final report](../../results/cmo_ingestion/report.json).
All numbers below are from executed ingestion jobs, not targets. The final
extractor SHA-256 and dependency versions are recorded in
[verification receipts](../../results/cmo_ingestion/verification.json).

| Dataset | Layout | Field recall | Auto acceptance | Incorrect auto-accepted | Values requiring review |
|---|---|---:|---:|---:|---:|
| IndPenSim | Unseen | 100.00% | 0.00% | 0 | 1,402 |
| IndPenSim | Returning | 100.00% | 78.60% | 0 | 300 |
| IndPenSim | Changed | 92.86% | 0.14% | 0 | 1,312 |
| Sanofi synthetic | Unseen | 97.14% | 0.00% | 0 | 70 |
| Sanofi synthetic | Returning | 98.57% | 97.14% | 0 | 2 |
| Sanofi synthetic | Changed | 86.84% | 10.53% | 0 | 59 |

These are configuration D results. Unseen has no confirmed template, so its
values remain drafts. Returning/changed use explicitly labeled automated
calibration confirmations on disjoint batches; they are not human-study results.
The separate diagnostic baseline has the same extraction behavior for these
bounded forms. It is not the generative configuration A.

Value/unit accuracy among matched extractions and accuracy among auto-accepted
values were 100% where those denominators were nonzero. This does not imply
100% package completeness: recall and review counts show omissions and
uncertainty. Source provenance was correct at the stated scoring granularity
(exact spreadsheet coordinates; PDF page plus field identity). Filename-based
classification was 100% on these generated families, which is not evidence of
classification performance on arbitrary CMO documents.

Injected changed-layout defects were detected by the matching stable rule code
and affected file, including missing fields and conflicting duplicate values.
This covers the defects actually generated, not all possible record omissions.
Document relationship recall on Sanofi was 85.71% unseen, 100% returning, and
87.50% changed. Misread identifiers/times and deliberately conflicting IDs can
prevent otherwise valid relationships from being assembled.

The IndPenSim returning acceptance target was **not met**: 78.60% is below 80%.
The 300 spectrum values retain undeclared source units and require review.
Sanofi unseen and both changed cases missed the 98% recall target. Unmapped
changed columns are flagged instead of guessed; scanned text also needs review.
The tests found no incorrect auto acceptance in this finite fixture set; this
does not establish a population-wide error rate.

The final D jobs took approximately 0.4–1.1 seconds per sampled package with no
model calls, tokens, or inference charges. The full 503 MB source archive was
acquired and checked separately; these timings do not represent processing every
source timepoint and Raman channel. A separate local Docling smoke ingestion
indexed eight sources without errors in 35.548 seconds and retained physical
page/box provenance. It did not run mapping-model inference.

A/B/C have **no numerical extraction results** because the endpoint variables
remain empty. Their 18 dataset/condition entries are explicitly unavailable.
Docling and local model assets were installed and exercised; endpoint values
can now be filled in `.env.local`. Clairic/Jev require the documented structured
bridges; direct vendor API compatibility is not yet established.

Human work is **not measured**. The UI logs partial active interaction time,
excludes automated browser checks, and does not infer savings from processing
speed. A completed study and an equivalent manual baseline are needed to
evaluate ≤15 minutes per package or any reduction in human effort.

Validation completed: 66 focused and existing regression tests passed; the
frontend production build passed; browser checks passed actual ingestion,
source-cell highlighting, acceptance, template confirmation, zero-call returning
reuse, visible PDF page rendering, changed-layout defects, export, and mobile
layout with no JavaScript errors. Existing CHO/Fresenius benchmark and source
review tests are included. Docker is optional and its image/runtime was not
tested. See [known limitations and deployment](README.md) and
[the human study protocol](HUMAN_STUDY.md).
