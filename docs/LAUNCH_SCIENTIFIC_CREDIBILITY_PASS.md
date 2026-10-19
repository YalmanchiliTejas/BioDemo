# Launch scientific credibility pass — October 18, 2026

## Scope and deployment

Reviewed https://bio-demo-mauve.vercel.app/ and the corresponding local UI.
The live site served `index-Cjkb6RDU.js` during inspection. These corrections
are prepared and tested locally; the user will push/deploy them. No live-site
update or benchmark rerun is claimed by this document.

## Presentation policy

All featured free-form agent assessments, hypotheses and selected observations
have been replaced by a separately labeled **Publication review · editorial
interpretation**. This is not a repaired agent quotation or an upgrade of an old
run. `ui/src/publicReviews.mjs` binds each review to its original output hash;
new/changed outputs have no reviewed narrative until reviewed explicitly.
Editorial observations retain links to original evidence IDs and exact source
coordinates. The original report narratives and recommendations remain in
clearly labeled legacy artifact downloads and are not featured as validated
findings. These public notes are not independently approved scientific reviews.

## Corrections by case

| Case | Public presentation change | Remaining evaluation work |
| --- | --- | --- |
| CHO-01 | Runtime failure, no scientific report; no wall-clock-exhaustion inference | Fresh execution required |
| CHO-02 | Acquisition/write-order/export explanations are possibilities; device/acquisition/export records requested | Corrected rerun or independent adjudication before qualification |
| CHO-03 | Earlier 51–67 h viability decline separated from later VCD deterioration; no assurance that unresolved anomalies are harmless | Temporal/causal adjudication or rerun. Early viability check is explicitly supplemental from CHO-04, not work performed by CHO-03 |
| CHO-04 / EXP011 | Viability 90.78% at 51 h → 38.47% at 67 h; feed records end at 67.139 h, physical delivery unknown; initiating cause unknown; no substrate-exhaustion conclusion | Corrected rerun or independent claim adjudication; obtain pump/controller records, material balance and time-aligned offline/inline measurements |
| CHO-04 / EXP001 | Measurement variability remains a hypothesis; similar peaks at different times do not prove an offline artifact | Time-aligned comparison, replicate assays and sampling records |
| CHO-05 | SEM definition, underlying replicates and replicate count unavailable in scope | Source-owner metadata plus corrected rerun/adjudication |
| FRE-01 | Real deviation closure unknown; inadequate batch-local assessment/release is the public narrative. Second export repeats one recorded result, not biological confirmation. QA tasks investigate original result and sampling integrity; additional tests only under approved procedures with all results assessed | Versioned revised scenario and fresh run required to evaluate release narrative; original earlier synthetic assumptions have not been rerun |
| FRE-02 | Site QA must classify/escalate action-level microbiology under approved policy; no objective severity assigned | Approved matrix/policy and adjudication or fresh run |
| FRE-03 | Recurring signal; no established shared organism, reservoir or cause | Organism identification and pathway evidence; causal adjudication/rerun |
| FRE-04 | Partial result — scientific and source review pending; five unlinked assessment numbers and one source check pending; original hypothesis cards quarantined | Fresh completed run with linked numbers/source review; independent scientific review remains separate |
| FRE-05 | Real closure unknown; no invented routing labels/severity definitions. Procedure DEV-0008 and equipment DEV-0007 are different categories | Versioned scenario, approved policy and fresh run for revised evaluation |
| FRE-06 | Separate synthetic Electrolyte Injection / LINE-C; normal scoped historian points are bounded negative evidence | No rerun solely for scope-label edit; independent scientific/source review still pending |

No case was rerun in this pass. A rerun alone would not establish causation or
scientific qualification; missing process records, approved policy and independent
domain review must still be obtained where applicable. Technical final-report
counts remain 9/11, with four automatically source-checked reports, five final
reports awaiting visual source review, one partial result and one runtime failure.

## Replay and layout

- Removed the planning/cost-saving visual, lot-hold batch strip and shipped-lot
  exposure plot from the public replay. No counterfactual plot is substituted.
- Remaining headline differences (“2 fewer”, 735.6 modeled lot-days and about
  289 days) each carry “Illustrative, assumed outcome”. QA acceptance, holds,
  dates and counterfactual outcomes are explicitly scripted at point of display.
- Removed invented routing/severity meanings from the projected event feed.
  New labels explicitly identify editorial scripted QA-review tasks.
- Case charts render only when a matching source trajectory exists. Cases and
  experiments without a plot lead directly into their evidence/publication notes,
  with no empty graph container. No synthetic chart data was added.
- Observation, unverified hypothesis, proposed/unperformed task and measured
  execution/source/math counts remain separate. Those checks do not certify
  scientific conclusions.

## Verification and reproducibility

Passed: production TypeScript/Vite build; six exporter tests; four presentation
tests; three publication-review tests. The publication tests require exact
original output hashes and existing source IDs/coordinates, and reject a changed
hash. FRE-04's public hypothesis list is explicitly empty/quarantined.

Browser checks ran against the built local production preview at 1363×936 and
390×844: both tabs, all eleven case selectors, all available CHO experiment
choices, both replay event tabs, expanded disclosures/source references, and 57
rendered views. No browser exceptions or horizontal page overflow. The same
read-only baseline scan of the live site confirmed the old positive feed claim,
late collapse wording, write-order/logger explanations and invented routing
labels were still present before deployment.

The corrected rendered-text scan found no unqualified old phrase. Its sole match
for `feed delivery stopped` was in the explicit negative qualification: “Feed
records end at 67.139 h; the data do not establish whether physical feed delivery
stopped.” No featured positive “released while open”, “toxic event killed”,
“after 73.5”, “SEM over timepoints”, or invented routing meaning remained.
Raw legacy downloads deliberately retain original content. A cell coordinate
such as `L2` is not a routing meaning; coordinates must never be altered to
satisfy a textual scan.

Commands from repository root:

```sh
node --test ui/scripts/test_presentation.mjs ui/scripts/test_public_reviews.mjs
.venv/bin/python -m pytest -q tests/test_ui_benchmark_export.py
cd ui
npm run build
npm run preview -- --host 127.0.0.1 --port 5182
```

`ui/scripts/check_publication.cjs` performs the rendered scan. It requires
Playwright and Chrome. Use `PLAYWRIGHT_MODULE` to point to an existing Playwright
installation if it is not available to Node's normal resolver:

```sh
node ui/scripts/check_publication.cjs http://127.0.0.1:5182/
node ui/scripts/check_publication.cjs https://bio-demo-mauve.vercel.app/
```

After pushing, run the second command to verify the newly deployed build. Its
strict assertions intentionally fail against the old live presentation. The
optional `--baseline` flag records matches without claiming the old build passes.

## Artifact integrity

Original evaluation run/output records, source inputs, output hashes and evidence
coordinates were not edited. Public benchmark JSON artifacts were not regenerated
or rewritten in this pass. An in-session before/after SHA-256 comparison covers
33 protected files: retained run/output/public-case artifacts and the source seed.
The added review data and components affect public presentation only.
Prior source/math verification is not retroactively presented as scientific
approval of these editorial corrections.
