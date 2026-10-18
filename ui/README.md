# Manufacturing OS result viewer

The default tab displays the latest paired CHO/Fresenius background benchmark
batch, sourced from retained `results/evaluation/*/run.json` records and bound
output hashes. All attempts in the batch are shown, including failures and
partial reports. Final investigations with pending source checks are distinguished
from verified sources and unfinished work. Independent scientific qualification
remains a separate gate. Unknown costs and unavailable results are not zero scores.

```sh
cd /Users/tejas/Desktop/BioDemo/ui
npm run export-benchmarks
npm run dev
```

Open http://127.0.0.1:5180/. After another benchmark batch finishes, run
`npm run export-benchmarks` again. `npm run build` creates `dist/` with the exported
summary and detailed case data. Runtime stores can be offloaded: this view reads
retained reports and, optionally, checksum-matching original CHO workbooks.

The viewer includes outcome and runtime bar charts, an example selector, source
coordinates, competing hypotheses, unresolved questions, numerical-review flags,
and a table of every attempt. Source viability trajectories are optional: they
are read from a frozen-hash-matching CHO workbook and shown only when the selected
paired cited measurements share the same original source time. Lines connect
sampled means, without inventing replicate statistics or establishing event onset
or causation. The example selection method is disclosed beside the chart.

Case exports are under `public/benchmarks/`; the summary is also stored at
`src/data/benchmarks.json`. These are presentation snapshots, not modifications to
the recorded benchmark outputs. Inspect full case JSON to see all findings and
the source/run/output hashes. Case examples on the page are explicitly selected
excerpts rather than the complete report.

The second tab is a separately labeled synthetic workflow replay. Its projected
holds, earlier escalation and market-exposure changes are deterministic simulation
outputs, not measured agent performance or actual manufacturing interventions.
Fresenius is a synthetic reconstruction informed by public FDA-related materials;
no internal company data, participation, endorsement or validation is implied.

The public recall announcement (November 6, 2025) and FDA posting (November 7,
2025) are linked separately from the assigned 2024–2025 simulation events. First
shipment calendar dates match the public notice; timestamps within those days
are assumptions. Simulated early escalation and QA holds are scripted, not RLM
performance measurements. The planning sandbox defaults to zero assumed labor
reduction and reports gross modeled labor value, with excluded costs listed.

Publication labeling audit: [docs/UI_PUBLICATION_AUDIT.md](../docs/UI_PUBLICATION_AUDIT.md).
Run `node --test ui/scripts/test_presentation.mjs` from the repository root to
check exposure cutoff, elapsed-day rounding and the missing-measurement scope.
Exports redact workstation paths; original result records remain unchanged.

Shadow-pilot CTAs use the approved Google Calendar booking URL. They request a
discussion of a de-identified deviation, not uploads of confidential records.
Case details are displayed only after their run ID matches the selected case;
CHO report excerpts can be explored by experiment without mixing chart and
hypothesis scopes. Partial-report self-descriptions stay in the technical
artifact; evaluated status is shown in the interface.

The public release narrative is versioned `v2-investigation-adequacy`: release
after inadequate broader-risk assessment is distinguished from administrative
deviation closure (unknown in the public record). The investigation-depth panel
uses original FRE-01 excerpts with source coordinates, counterevidence,
alternative explanations and proposed checks. It explicitly discloses that the
recorded run retains earlier synthetic open-deviation assumptions. This does not
change frozen data or establish superior performance on a revised scenario.

Visual hierarchy: the measured page leads with compact status cards and outcome/
runtime charts. The replay leads with a short synthetic-data label, model figures
and the animated workflow. Detailed context, original report excerpts, methodology
and the illustrative calculator are expandable below the visuals. Material
provenance and scientific-review qualifications stay visible near the figures.
