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
