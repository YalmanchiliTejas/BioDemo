# Manufacturing data layer: findings and limits

## Measured package check

The evaluation used authentic CHO workbooks and the existing synthetic
Fresenius source package. CHO was sampled at the first 20 data rows per
worksheet; all workbook headers were read. Fresenius was ingested without a
row cap. These are extraction and source-link checks, not agent outcomes.

| Check | Result |
| --- | ---: |
| CHO workbooks indexed | 12 |
| CHO observations from bounded sample | 30,006 |
| CHO exact source-header matches against structural map | 1,344 / 1,344 |
| CHO expected experiment/reactor run IDs recovered | 24 / 24 |
| Fresenius source files indexed | 15 |
| Fresenius observations | 22,617 |
| Fresenius nonempty CSV/XLSX source locations recovered | 21,636 / 21,636 |
| Fresenius document source spans exactly reproduced | 575 / 717 (80.2%) |
| CHO sampled reindex wall time | 5.55 s |
| Fresenius reindex wall time | 19.38 s |

The 142 missing document spans are concentrated in the synthetic scanned lab
review. Exact span matching is strict, so OCR punctuation or whitespace
differences count as failures. The reported 3,164 blank structured reference
cells are excluded from nonempty extraction recall because the ingester does
not create observations for blank cells. Source locations and full failure
examples are in `results/manufacturing_data_layer.json`.
No model calls were made, so input/output tokens and inference cost were zero;
no manual field mappings were entered.
The timed runs reprocessed existing private stores after a pipeline version
change. A prior fresh CHO run took 44.31 seconds; these times are machine and
cache dependent.
These measurements used the earlier pypdf/Tesseract document path. The current
`auto` mode routes each source independently and records fallback decisions;
Docling and Chandra route accuracy has not yet been measured on the full
benchmark packages.

## Prime SDK integration

The application opens a Prime SDK session when `BIODEMO_MANUFACTURING_STORE`
and `BIODEMO_MANUFACTURING_SCOPE` are configured. The scoped bridge exposes
the ten ManufacturingTools to Prime's native Python kernel. Evidence already
stored on a Blackboard is checked against the current scope and timestamp
before Prime sees it. Task and evidence-request proposals are persisted through
`src/workflows/proposals.py`; the application namespaces Blackboard files by
store and scope. SDK-host tests use a fake host and do not measure investigation
quality or native child-agent behavior.

## Document backend decision

The measured path used pypdf for embedded text and local Tesseract for scans.
Docling is available as an explicit backend. The code also exposes
PaddleOCR-VL and Docling's Chandra OCR 2 VLM preset, but neither VLM was run
for these measurements. Their accuracy on this package is unknown.

PaddleOCR-VL supports PDF/image parsing and local or served inference, and
the PaddleOCR project is Apache-2.0 licensed. Chandra OCR 2 supports complex
forms, tables and handwriting, but its model license restricts some commercial
use. For CDMO deployment, evaluate model quality and license terms before
selecting a VLM. Sources: [PaddleOCR-VL Python API](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md),
[PaddleOCR license](https://github.com/PaddlePaddle/PaddleOCR),
[Docling VLM presets](https://docling-project.github.io/docling/reference/cli/),
[Chandra model license](https://github.com/datalab-to/chandra/blob/master/MODEL_LICENSE).

## Remaining limits

- CHO numerical reconstruction over every row and comparison to the published
  aligned CSVs was outside this bounded ingestion run. A source-header match
  does not validate biological interpretation or timestamp alignment.
- Fresenius PDFs contain multiple records; the default OCR path stores line
  text with page and line provenance, not fully reconstructed table cells or
  image coordinates. `extract_region` supports crop-based reinspection.
- Historical access uses per-field availability when it is present in the raw
  input. If an export has already flattened away field publication dates, no
  data layer can recover those dates from its contents alone. Supply an
  as-of source snapshot for strict replay.
- Entity associations are candidates from source identifiers and co-observed
  fields. They require verification before making causal claims.
- File permissions protect the private store from other OS users, and tool
  scopes filter evidence. The host application must isolate an agent process
  that has direct filesystem tools from the private store and hidden benchmark
  references; a same-user process with arbitrary file access could bypass
  the tool API.
- Semantic retrieval is optional and was not measured. The local VLM paths
  were not executed, so OCR failure reduction and inference cost are unknown.
- No investigation, RCA, triage, optimization, or full RLM run is included in
  these measurements.
