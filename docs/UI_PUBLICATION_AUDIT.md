# Benchmark UI publication labeling audit

Reviewed October 18, 2026. Scope: both React UI tabs, chart calculations,
exporters, public case snapshots and measured batch 20261017-224014.
This is a presentation/provenance audit, not independent scientific qualification
or a legal determination.

## Public dates and provenance

The [FDA-hosted company recall announcement](https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/fresenius-kabi-issues-voluntary-nationwide-recall-three-lots-famotidine-injection-usp-20-mg-2-ml-10)
lists company announcement November 6, 2025 and FDA publication November 7, 2025.
Its corrected first-ship calendar dates are January 2, February 4 and April 15,
2025, for public lots 6133156, 6133194 and 6133388 respectively.

The generator assigns background batches from February 2024, incident production
December 1, 2024 / January 4, 2025 / March 12, 2025, and subsequent investigation
events. These are simulation assumptions. UI aliases 075/084/099 are not public
lot numbers. The UI now separates the real announcement/posting dates and public
first-ship dates from assumed production, lab, release, complaint and QA times.
All event-display dates use UTC. No dates in frozen source data were moved.

## Findings corrected

| Prior presentation issue | Correction |
| --- | --- |
| Simulated history could appear to be Fresenius operations | Prominent date/provenance panel, company participation disclaimer, scenario labels throughout |
| Default workflow-impact tab could be mistaken for measured results | Measured benchmarks is default; replay tab explicitly synthetic |
| 288-day earlier-detection claim | About 289 elapsed days, explicitly dependent on assigned simulation dates; scripted replay, not measured prediction |
| Market chart counted lots as unaddressed after complaint/recall | Stops at assumed cross-batch escalation; monthly snapshot bars; no implication of physical recovery; brief January exposure disclosed |
| All 100 batches implied 100 measurements / one Line A population | 99/100 available values, one missing disclosed; three-line scope; equal batch spacing disclosed |
| Missing bioburden could be colored normal | Missing measurements use gray |
| Timeline said both paths identical despite differing initial task times | First-signal task aligned with the same source event; no identical-workflow claim; tasks explicitly scripted |
| Compressed timeline implied proportional time / quiet operations | Compression stated explicitly; no claim of operational quiet |
| Task counters implied completed scientific investigation | Scripted task labels, not observed agent completeness |
| Scenarios portrayed QA holds as agent actions | Assumed QA response labels; human decision assumption retained |
| Failure summary attributed CHO-01 to wall-clock exhaustion | Neutral execution-failure wording; original TimeoutError diagnostic retained |
| Source checks implied all scientific statements validated | Extracted values/locations distinguished from inference support and independent review |
| Partial Fresenius numerical issues easy to miss | Numerical review item count in all-attempt table; five unresolved FRE-04 literals retained |
| Calendar-delay ratio used to justify labor/cost reductions | Replaced industry calculator with explicit illustrative inputs and zero reduction default; gross labor value and excluded costs disclosed |
| Runtime labels suggested entire orchestration duration | Recorded investigation timer distinguished from timestamp overhead; median explicitly includes failures |
| Dates varied with viewer timezone / batch launch looked like event date | UTC export/execution dates; batch labeled as identifier; source/simulation/execution dates distinguished |
| Full event log was filtered | Renamed selected synthetic replay events |
| Failure JSON exposed local workstation paths | Export redacts workstation paths; original records and hashes preserved |

## Measured results retained

The replay now includes three adjacent public-context cards: the November 2025
three-lot recall, the September 22, 2026 FDA investigation findings, and the
assumed simulation. Each public claim has a direct source link and section
locator. The 2026 letter is explicitly retrospective; it is not represented as
evidence available during simulated January 2025 detection. The recall notice
describes one lot with reserve-sample endotoxin OOS and two precautionary lots;
the UI does not infer that all three real lots had the simulated upstream failures.
The measured tab links directly to these distinctions.

All eleven attempt records and available output hashes matched the exports during
the audit. Nine final investigations: four automatically source-verified CHO
reports and five Fresenius reports pending visual source review. One partial
Fresenius report and one failed CHO execution remain visible. No independent
scientific qualification is claimed. These are one trial per case in this batch,
not a repeated reliability estimate. No matched baseline results are displayed.

Selected model observations and hypotheses remain attributed report excerpts,
not endorsed causal conclusions. Case-specific coverage is reviewed/screened
units, not universal accuracy or critical-signal recall. Unknown costs remain
unknown; provider telemetry may omit child activity. Scientific validation,
human savings, net economic benefits, prevention of the real recall, production
improvement and generalization remain unestablished.

## Verification

- TypeScript and production Vite build.
- Six exporter tests, including hash rejection, missing records, pending statuses
  and workstation-path redaction without original-record modification.
- Three presentation tests for escalation cutoffs, exact elapsed-day calculations,
  and multiple-line/missing-measurement scope.
- Browser checks: all eleven attempts, case switching, pending/failed statuses,
  both tabs' disclosures, zero savings default, explicit timeline compression,
  rounded simulated lead, desktop/mobile layout and browser exceptions.

Remaining independent work: blinded domain review, claim-support/causal review,
source-image review and matched comparative trials. The interface does not turn
those pending gates into passes.

## Launch review follow-up

The supplied launch review described an older interface. Reconfirmed the existing
exposure cutoff, removal of the unsupported 24%/lost-batch/$14k calculator claims,
explicit FDA/synthetic panel, and measured-default navigation. Additional fixes:

- Detail payloads are bound to requested run IDs and stale responses ignored.
  Label, metrics, chart, findings and artifact link are masked together while
  loading. Browser test delayed a CHO request, switched to FRE, and confirmed the
  late CHO response could not replace FRE content.
- Public CHO-01 view shows concise runtime failure and elapsed time; full
  path-redacted diagnostic remains downloadable. No wall-clock-timeout inference.
- FRE-04 consistently reads partial report, with five unlinked assessment numbers
  and one pending source check. Raw model self-descriptions are available in the
  artifact, not promoted to evaluated completion in the interface.
- CHO scope is visible above the plot. Experiment selector groups report excerpts
  by their first explicit experiment reference, or cited workbook if none is
  present. EXP001 chart is hidden when selecting EXP011; hypotheses from EXP011
  are not displayed as explanations for the EXP001 plot. Full-scope interpretation
  and ungrouped findings remain available in the complete artifact.
- Fixed nullable coverage entity IDs found while checking all eleven cases.
- Timeline summary now follows scrub/restart and uses the current replay frame.
- Consistent exact elapsed UTC-hour / 24 convention, no inclusive counting:
  288.86-day lead (about 289), 738.1 baseline and 2.5 assisted modeled lot-days,
  735.6 modeled difference. Sum before display rounding; explanatory note visible.
- Batch-strip subset range is explicitly distinguished from the full population.
- Approved Google Calendar shadow-pilot CTA at the hero and end of both tabs,
  explaining inputs and proposed reviewable outputs. Opens booking only; records
  are not uploaded through the dashboard.
- The recorded investigation appears before aggregate runtime/outcome charts;
  the illustrative planning sandbox follows the replay evidence.

Verification: production build, six exporter and three presentation tests, and
browser checks at 1363×936 and 390×844. All eleven case panels, delayed-response
race, experiment grouping, partial/failure copy, booking href, scrub/restart,
disclosures and horizontal overflow checked. No browser exceptions.
