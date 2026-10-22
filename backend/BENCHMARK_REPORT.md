# Manufacturing AI OS benchmark

Fresenius: a synthetic manufacturing reconstruction informed by publicly available FDA-related materials. No internal Fresenius manufacturing data, participation, endorsement or validation. CHO: authentic laboratory measurements. No production or quality improvement has been experimentally demonstrated.

Publication snapshot: every recorded v2 attempt is included. Historical host completion is separate from current report completeness. Source values are not scientific qualification.

| Dataset / method | Attempts | Recorded completed | Incomplete | Failed | Recorded technical checks passed |
|---|---:|---:|---:|---:|---:|
| cho / conventional | 3 | 1 | 1 | 1 | 1 |
| cho / retrieval_llm | 3 | 0 | 1 | 2 | 0 |
| cho / full_rlm | 16 | 3 | 1 | 12 | 0 |
| fresenius / conventional | 3 | 0 | 2 | 1 | 0 |
| fresenius / retrieval_llm | 3 | 0 | 1 | 2 | 0 |
| fresenius / full_rlm | 6 | 0 | 4 | 2 | 0 |

These mixed historical cohorts are descriptive. Matched, fixed-version repeats and independently assessed investigation quality are pending; no relative performance or productivity claim is justified.

## Unfinalized records

- `135cb4fa00b74d17869907e4fec1cd39` / CHO-04: Trace exists without run.json; execution, method and outcome cannot be established. Kept separate from known execution-rate denominators. Last recorded stage: leakage_and_version_audit. Trace: [results/evaluation/135cb4fa00b74d17869907e4fec1cd39/trace.jsonl](results/evaluation/135cb4fa00b74d17869907e4fec1cd39/trace.jsonl).

## Gates

- technical_demonstration: pending_complete_verified_current_full_os_run_and_claim_review
- benchmark_comparison: pending_matched_repeated_quality_checked_trials
- independent_scientific_qualification: pending_approved_policy_blinded_reviews_adjudication_and_output_hash_binding

## Per-attempt measurements

| Run / case / method | Selected field checks | Citation validity | Seconds | Input / output tokens | Inference cost USD |
|---|---|---|---:|---|---|
| [03b2a580](results/evaluation/03b2a5805de34646975f5b17b2fde42b/run.json) / CHO-04 / conventional | 1300/1300 checked; 0 missing | 1.000 (72 checked) | 99.780 | 0 / 0 | 0 |
| [11590541](results/evaluation/11590541cc714eedbb3c3cdaa3633256/run.json) / CHO-04 / full_rlm | —/— checked; — missing | Not measured (— checked) | 901.477 | Not measured / Not measured | Not measured |
| [1e0cb850](results/evaluation/1e0cb85038cb4e34b96cdd309deb6ec3/run.json) / CHO-04 / conventional | —/— checked; — missing | Not measured (— checked) | 0.628 | Not measured / Not measured | Not measured |
| [20a0c926](results/evaluation/20a0c92687014dbf8f4a6bc3fcac0bb1/run.json) / FRE-02 / retrieval_llm | 214/214 checked; 0 missing | 0.992 (651 checked) | 98.552 | 146077 / 9744 | Not measured |
| [23f02f71](results/evaluation/23f02f7149e446fda4ac41457490d098/run.json) / CHO-04 / full_rlm | —/— checked; — missing | Not measured (— checked) | 901.430 | Not measured / Not measured | Not measured |
| [27aadbed](results/evaluation/27aadbed7000415386a77a74bea71e6d/run.json) / FRE-02 / conventional | 214/214 checked; 0 missing | 0.994 (622 checked) | 21.137 | 0 / 0 | 0 |
| [2d55a826](results/evaluation/2d55a826bcd249efa556c48ff7beba43/run.json) / CHO-04 / retrieval_llm | 1300/1300 checked; 0 missing | 1.000 (190 checked) | 228.128 | 35946 / 8962 | Not measured |
| [39e4673d](results/evaluation/39e4673d7a734191bf014ac9d4f7c877/run.json) / FRE-02 / conventional | 214/214 checked; 0 missing | 1.000 (606 checked) | 20.785 | 0 / 0 | 0 |
| [3a0256e6](results/evaluation/3a0256e6c12c4486bffbd480a69eb542/run.json) / CHO-01 / full_rlm | —/— checked; — missing | Not measured (— checked) | 901.001 | Not measured / Not measured | Not measured |
| [414d3f7a](results/evaluation/414d3f7aed164071b8712a8c53855086/run.json) / CHO-05 / full_rlm | —/— checked; — missing | Not measured (— checked) | 391.212 | 155909 / 50040 | Not measured |
| [4eb2d137](results/evaluation/4eb2d137e12a4afa858f941d7b01dae1/run.json) / CHO-04 / full_rlm | 1300/1300 checked; 0 missing | 1.000 (357 checked) | 910.064 | 111332 / 141649 | Not measured |
| [541e0c96](results/evaluation/541e0c961c5b4039bdf585841a643fff/run.json) / FRE-02 / retrieval_llm | —/— checked; — missing | Not measured (— checked) | 0.027 | Not measured / Not measured | Not measured |
| [59c7a334](results/evaluation/59c7a3341e804b3e884fcb98f6f3f250/run.json) / FRE-03 / full_rlm | 214/214 checked; 0 missing | 0.999 (2155 checked) | 582.916 | 123852 / 122126 | Not measured |
| [5edb0bfd](results/evaluation/5edb0bfd0ebb42f298dfd94eaba138cc/run.json) / FRE-05 / full_rlm | —/— checked; — missing | Not measured (— checked) | 314.324 | 62588 / 60001 | Not measured |
| [64f31ce7](results/evaluation/64f31ce7c7c84f75b8ece90ca4c4329a/run.json) / CHO-04 / full_rlm | —/— checked; — missing | Not measured (— checked) | 72.614 | 0 / 0 | Not measured |
| [6534ccdb](results/evaluation/6534ccdb627c4a538994e2b0d51629b6/run.json) / CHO-02 / full_rlm | 1300/1300 checked; 0 missing | 1.000 (162 checked) | 960.797 | 123948 / 114918 | Not measured |
| [6efaaa88](results/evaluation/6efaaa88f6024220b6d6731077ff7ff0/run.json) / CHO-04 / conventional | 1300/1300 checked; 0 missing | 1.000 (72 checked) | 113.910 | 0 / 0 | 0 |
| [7113f268](results/evaluation/7113f26854294d139a4eb6ad242a05a2/run.json) / CHO-04 / full_rlm | —/— checked; — missing | Not measured (— checked) | 901.003 | Not measured / Not measured | Not measured |
| [73ee3f46](results/evaluation/73ee3f466445438699267c155077a80f/run.json) / CHO-03 / full_rlm | —/— checked; — missing | Not measured (— checked) | 901.539 | Not measured / Not measured | Not measured |
| [78c5effe](results/evaluation/78c5effe0209466a91e4eebc080268f4/run.json) / CHO-04 / full_rlm | 404/404 checked; 896 missing | 1.000 (10 checked) | 854.974 | 92743 / 135297 | Not measured |
| [7af502d3](results/evaluation/7af502d3f16f4715b4a1ae302b00af7a/run.json) / CHO-04 / full_rlm | —/— checked; — missing | Not measured (— checked) | 37.437 | 0 / 0 | Not measured |
| [7c977c4d](results/evaluation/7c977c4dfee2427d9fd06595c3b55ee1/run.json) / FRE-02 / retrieval_llm | —/— checked; — missing | Not measured (— checked) | 84.279 | 345667 / 10282 | Not measured |
| [8e2ea639](results/evaluation/8e2ea639c9ae4176afe6f6b6bcabd8e0/run.json) / CHO-04 / full_rlm | —/— checked; — missing | Not measured (— checked) | 24.686 | Not measured / Not measured | Not measured |
| [915f57c5](results/evaluation/915f57c577d846c0adb849f936436730/run.json) / FRE-02 / conventional | —/— checked; — missing | Not measured (— checked) | 0.027 | Not measured / Not measured | Not measured |
| [9c3b2df2](results/evaluation/9c3b2df29dab4798acac0c54e11eb8ea/run.json) / CHO-04 / retrieval_llm | —/— checked; — missing | Not measured (— checked) | 0.604 | Not measured / Not measured | Not measured |
| [b27a0a3b](results/evaluation/b27a0a3b691b43a0b9e50b73c17cbe43/run.json) / FRE-02 / full_rlm | 214/214 checked; 0 missing | 0.991 (436 checked) | 702.239 | 95146 / 113881 | Not measured |
| [b50ba619](results/evaluation/b50ba619d14e41109e8e8d7e64374bac/run.json) / CHO-04 / retrieval_llm | —/— checked; — missing | Not measured (— checked) | 131.336 | 63453 / 12810 | Not measured |
| [b73a366d](results/evaluation/b73a366df9424b17a4f493ca7ed82c53/run.json) / CHO-04 / full_rlm | —/— checked; — missing | Not measured (— checked) | 71.391 | 0 / 0 | Not measured |
| [b85518cf](results/evaluation/b85518cfe36447a9921c695766e03e67/run.json) / FRE-01 / full_rlm | 214/214 checked; 0 missing | 0.991 (1589 checked) | 810.747 | 89124 / 98856 | Not measured |
| [d174605c](results/evaluation/d174605c213a480d94f294700798a276/run.json) / FRE-04 / full_rlm | 214/214 checked; 0 missing | 0.985 (535 checked) | 774.384 | 137517 / 146417 | Not measured |
| [e0e6241b](results/evaluation/e0e6241b5b1f4e46a4044a72c336e068/run.json) / FRE-06 / full_rlm | —/— checked; — missing | Not measured (— checked) | 218.104 | 50839 / 29310 | Not measured |
| [ea677006](results/evaluation/ea677006bf174d12bcb053c9370aa09e/run.json) / CHO-04 / full_rlm | —/— checked; — missing | Not measured (— checked) | 26.736 | 0 / 0 | Not measured |
| [ec32259a](results/evaluation/ec32259a437d4ccea9dc47bf4ef654c0/run.json) / CHO-04 / full_rlm | 1300/1300 checked; 0 missing | 1.000 (76 checked) | 799.651 | 121435 / 156186 | Not measured |
| [f5f2023c](results/evaluation/f5f2023cd2f94316a98b970a23755500/run.json) / CHO-04 / full_rlm | —/— checked; — missing | Not measured (— checked) | 28.927 | 0 / 0 | Not measured |

Root-session token totals do not include all child usage in historical runs. Total costs, including compute/OCR/tools, remain unmeasured. A zero reported by an unpriced provider is preserved as a raw telemetry value in JSON and shown as unknown.

Claim support, scientific plausibility, relevance precision, contradiction coverage, human effort and untouched generalization remain unmeasured unless explicitly annotated per run. Pending review is neither an approved result nor a scientific failure.

## Recorded investigation example

{
  "recorded_run_id": "ec32259a437d4ccea9dc47bf4ef654c0",
  "selection": "Illustrative largest paired viability difference among rechecked cited cells at matching source rows; not an outcome ranking.",
  "values": [
    {
      "value": 38.47,
      "source": {
        "source_id": "087788e56bfdec1e042906dc",
        "path": "EXP011_fed-batch.xlsx",
        "sheet": "R02_offline_CellAnalysis",
        "row": 9,
        "column": "Viability Mean (%)",
        "cell": "F9",
        "page": null,
        "span": null,
        "region": null
      },
      "evidence_id": "b1:087788e56bfdec1e042906dc:13:9:6"
    },
    {
      "value": 92.56,
      "source": {
        "source_id": "087788e56bfdec1e042906dc",
        "path": "EXP011_fed-batch.xlsx",
        "sheet": "R01_offline_CellAnalysis",
        "row": 9,
        "column": "Viability Mean (%)",
        "cell": "F9",
        "page": null,
        "span": null,
        "region": null
      },
      "evidence_id": "b1:087788e56bfdec1e042906dc:12:9:6"
    }
  ],
  "original_output_sha256": "36aef87c148bc49801248726830e3cb1b509a5fa130704276aef8727ea8392fd",
  "audit_status": "requires_numerical_review",
  "current_source_sha256_matches_frozen": true,
  "trajectories": [
    {
      "sheet": "R02_offline_CellAnalysis",
      "time_column": "Time (h)",
      "value_column": "Viability Mean (%)",
      "points": [
        {
          "time_hours": 0,
          "value": 81.35666666666667,
          "source_row": 2
        },
        {
          "time_hours": 3,
          "value": 89.16000000000001,
          "source_row": 3
        },
        {
          "time_hours": 18.5,
          "value": 86.03000000000002,
          "source_row": 4
        },
        {
          "time_hours": 27,
          "value": 87.20666666666666,
          "source_row": 5
        },
        {
          "time_hours": 42.5,
          "value": 88.81,
          "source_row": 6
        },
        {
          "time_hours": 48,
          "value": 91.72666666666667,
          "source_row": 7
        },
        {
          "time_hours": 51,
          "value": 90.78333333333335,
          "source_row": 8
        },
        {
          "time_hours": 67,
          "value": 38.47,
          "source_row": 9
        },
        {
          "time_hours": 73.5,
          "value": 45.74333333333333,
          "source_row": 10
        },
        {
          "time_hours": 90.5,
          "value": 1.65,
          "source_row": 11
        },
        {
          "time_hours": 95,
          "value": 0.7000000000000001,
          "source_row": 12
        },
        {
          "time_hours": 125,
          "value": 0.03666666666666667,
          "source_row": 13
        },
        {
          "time_hours": 148.5,
          "value": 0,
          "source_row": 14
        },
        {
          "time_hours": 162.5,
          "value": 0,
          "source_row": 15
        },
        {
          "time_hours": 171,
          "value": 0,
          "source_row": 16
        },
        {
          "time_hours": 186,
          "value": 0,
          "source_row": 17
        },
        {
          "time_hours": 195,
          "value": 0,
          "source_row": 18
        }
      ]
    },
    {
      "sheet": "R01_offline_CellAnalysis",
      "time_column": "Time (h)",
      "value_column": "Viability Mean (%)",
      "points": [
        {
          "time_hours": 0,
          "value": 82.17333333333333,
          "source_row": 2
        },
        {
          "time_hours": 3,
          "value": 90.13,
          "source_row": 3
        },
        {
          "time_hours": 18.5,
          "value": 90.88333333333333,
          "source_row": 4
        },
        {
          "time_hours": 27,
          "value": 89.51333333333332,
          "source_row": 5
        },
        {
          "time_hours": 42.5,
          "value": 93.21666666666665,
          "source_row": 6
        },
        {
          "time_hours": 48,
          "value": 93.50333333333333,
          "source_row": 7
        },
        {
          "time_hours": 51,
          "value": 92.38666666666666,
          "source_row": 8
        },
        {
          "time_hours": 67,
          "value": 92.56,
          "source_row": 9
        },
        {
          "time_hours": 73.5,
          "value": 94.34333333333332,
          "source_row": 10
        },
        {
          "time_hours": 90.5,
          "value": 95.59333333333332,
          "source_row": 11
        },
        {
          "time_hours": 95,
          "value": 94.17999999999999,
          "source_row": 12
        },
        {
          "time_hours": 125,
          "value": 87.98,
          "source_row": 13
        },
        {
          "time_hours": 148.5,
          "value": 64.24,
          "source_row": 14
        },
        {
          "time_hours": 162.5,
          "value": 42.97666666666667,
          "source_row": 15
        },
        {
          "time_hours": 171,
          "value": 32.00333333333333,
          "source_row": 16
        },
        {
          "time_hours": 186,
          "value": 17.06333333333333,
          "source_row": 17
        },
        {
          "time_hours": 195,
          "value": 9.466666666666667,
          "source_row": 18
        }
      ]
    }
  ],
  "source_checks_passed": 76,
  "source_checks_count": 76,
  "replayed_report_status": "incomplete",
  "competing_explanations": [
    "Operating strategy differences",
    "Measurement or acquisition problems",
    "Biological/process stress requiring further evidence"
  ],
  "contradiction_and_uncertainty": "Source-value agreement does not prove biological interpretation. Operating intent, calibration and causal direction remain unresolved. Matching rows alone do not establish temporal alignment.",
  "next_actions": [
    "Review approved recipes and setpoints",
    "Check independent viability and sensor measurements",
    "Resolve source clocks before making event-order claims"
  ],
  "artifact": "results/verification/ec32259a437d4ccea9dc47bf4ef654c0-review-v2"
}

## Safe public statements

- The system ingests laboratory/manufacturing evidence, computes descriptive signals, retrieves source locations and proposes tasks for human review.
- Selected source values and structured calculations can be checked against original files; that does not prove a root cause.
- This is an engineering demonstration under development. Reliability, scientific qualification and effort savings require further evaluation.
