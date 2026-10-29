# CHO demo deliveries

The hosted demo (`/` → **Try the live demo**) replays three monthly deliveries
from a fictional CMO, built from real CHO cell-culture measurements.

## Source and licence

- Dataset: CHO cultivation data, Zenodo record 20829178,
  DOI [10.5281/zenodo.20829178](https://doi.org/10.5281/zenodo.20829178), CC BY 4.0.
  12 experiments (9 batch, 3 fed-batch), two bioreactors each: 24 runs.
- Archive SHA-256 `46a6b92b…fd17b` is checked before generation (MD5 matches the
  published value).
- Company names ("Northfield Biologics", "Harborview CDMO"), file layouts,
  sample IDs and certificates are invented. Every certificate says so.

## What was transformed

- Process parameters: first raw sample at or after each 6-hour mark, in file
  order; values rounded to instrument-like precision; time to 0.01 h. Cumulative
  feed is the last reading not after that instant.
- Lab results: cell and medium analyses joined on sample time. **Blank cells are
  real gaps in the source** (analytes not measured at some timepoints).
- Certificates report viability and VCD at the peak-VCD sample.
- Injected in November only, and listed in its key: renamed/reordered/added
  columns, a conflicting duplicate glucose result, one withheld certificate.

Each value's original workbook, sheet, row and value are recorded in
`demo/<package>/evaluation/answer_key.json`, outside `raw/`. The pipeline never
reads keys.

## Regenerate and score

```bash
curl -L "https://zenodo.org/records/20829178/files/Dataset.zip?download=1" -o .cache/cho-source/Dataset.zip
.venv/bin/python -m benchmarks.cmo_ingestion.cho_demo            # writes benchmarks/cmo_ingestion/demo/
.venv/bin/python -m benchmarks.cmo_ingestion.evaluate --packages benchmarks/cmo_ingestion/demo \
    --output results/cmo_ingestion/<fresh-dir> --calibration-protocol --confirm-proposals --configurations D
```

The demo folder is small (~3 MB), tracked in git and copied into the API image,
so the hosted demo needs no DagsHub access. It is separate from
`generated/`, which is the offloaded Sanofi/IndPenSim mount.

## Measured (configuration D, local, no model calls)

[Report](../../results/cmo_ingestion/cho-2026-10-28/report.md).

| Condition | Recall | Value accuracy | Verified automatically | Silent errors | Silent omissions |
|---|---:|---:|---:|---:|---:|
| Unseen form (second CMO) | 100% | 100% | 0% | 0 | 0 |
| Unseen + one confirmation | 100% | 100% | 100% | 0 | 0 |
| Returning (October) | 100% | 100% | 100% | 0 | 0 |
| Changed (November) | 100% | 100% | 0.47% | 0 | 0 |
| Changed + one confirmation | 100% | 100% | 99.67% | 0 | 0 |

Remaining open items are the real blank lab cells, which need a person's
disposition. Browser check of the guided demo
(`frontend/scripts/check_cmo_demo.cjs`): September verified in 12 clicks,
October needed no column decisions, November showed the layout diff, the
conflict and the missing certificate. Human time saved is not measured.

## Part of the platform API

Delivery verification is served by the main platform API (`python -m src.lifesci serve --port 8100`,
`backend/deploy/lifesci`), at the same `/api/cmo-ingestion` paths. On a verified delivery, **Ask the
assistant** publishes the accepted values as one immutable evidence record
(`POST /v1/cmo-datasets`, source `cmo-verified-delivery:<run>`) and attaches it to the assistant
conversation. Unverified or superseded runs are refused (409). The assistant receives a bounded summary
with batches, parameters and source locations, and is instructed that verification is not batch release.
Physical models do not yet consume these datasets. The standalone `benchmark` API and
`deploy/cmo-ingestion` still work until retired; set `NEXT_PUBLIC_CMO_API_URL` to use it instead.

## Demo isolation

Each browser session runs the samples under its own CMO workspace
(`Northfield Biologics · demo xxxx`), so formats one visitor confirms never
apply to another visitor's demo, and demo runs are hidden from the shared
"Recent deliveries" list. Restart creates a fresh workspace.
