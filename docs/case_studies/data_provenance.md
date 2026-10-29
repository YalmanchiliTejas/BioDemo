# Source provenance and evidence boundaries

## Public FDA context

Primary source: [Sanofi warning letter 690604, amended January 15, 2025](https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/sanofi-690604-01152025).
Retrieved and inspected during this implementation. The stored HTML is
`backend/benchmarks/cmo_ingestion/provenance/fda-sanofi-690604.html`, 54,567 bytes,
SHA-256 `c6c4e7bc537b2edb262f1e5a2ea754116afb465f6a8c782c9d3c4aa80e498760`.
The amended letter replaces its December 16, 2024 version. It concerns Genzyme,
a Sanofi subsidiary, following the June 12–July 9, 2024 inspection.

| Source location in letter | Verified finding, paraphrased | What it cannot establish |
| --- | --- | --- |
| Finding 1, introductory paragraph | Approximately 20% of attempted bioreactor runs in January 2022–July 2024 were rejected for contamination **or other quality failures**. | Not a contamination-only rate; denominator and detailed batch histories are not published. |
| Finding 1A | Particle/appearance OOS investigations were inadequate; an engineering study conflicted with an assigned explanation and documentation was incomplete. | Not a verified internal scientific root cause or complete experiment record. |
| Finding 1B | Three high-pressure transfer/leakage events required better investigation. | Not raw pressure trajectories, component identities or internal batch associations. |
| Finding 2B | Informal pre-job instructions and a substituted shipping bag lacked adequate controlled documentation/change evaluation. | Redacted process details and internal approvals cannot be reconstructed reliably. |
| Finding 3 | Equipment design and floor-level cart brake handling raised concerns. | A demonstrated contamination mechanism cannot be inferred from the public description alone. |

The FDA HTML is context, not operational training data or synthetic ground truth.
It is **not staged into the historical July 1, 2024 factory investigation**: the
letter was unavailable then. No real Sanofi batch, equipment, operator or causal
label is claimed. All operational documents explicitly state they are fictional.

## Fictional factory corpus

Generator: `backend/benchmarks/autonomous/generate.py`. Version:
`fictional-manufacturing-v2`. Development seeds: corpus 417, scenarios 718.
Reserved scenario identifiers: corpus seed 991, scenario seed 1283; generated but
not scored or used to tune retrieval. These reserve identifiers/layouts, **not
unseen biological mechanisms**: the four authored scenario templates remain the
same. Independent scenario authoring/adjudication is still required.

The four families concern microbiological recurrence, transfer pressure,
procedure/change-control conflict and deliberately inconclusive investigations.
Each family has four available critical documents and one future document.
Batch/equipment/campaign identifiers are fictional random identifiers. Opaque
filenames contain no family, relevance or answer labels. Routine and misleading
records share target campaigns; a campaign match alone does not establish relevance.

The 1,000-file independently generated corpus has 150 batch, 200 historian,
100 laboratory, 100 deviation, 100 maintenance, 100 procedure and 250 distractor
files. Formats include native/scanned PDF, XLSX, CSV, JSON, DOCX, TXT and Parquet,
plus deliberately corrupt and unsupported inputs. Historian tables preserve
24-point numeric series where applicable. This is a controlled challenge, not a
validated digital twin or a realistic full factory simulation.

Controlled scaling uses `--base`: the original 100 files remain byte-identical;
only ordinary distractors are added to 1,000/10,000 total files. Critical evidence,
future documents, objectives and hidden labels are unchanged. This differs from
independently generating different corpus sizes, which also changes format/layout.

`raw/` contains only source records. `evaluator/truth.json` contains critical
spans, support/counterevidence, affected/comparator scope, contributors, unknowns,
future availability and next-test expectations. It is not indexed, copied into
the input workspace, included in prompts or exposed through agent tools.
The source owner controls the public availability metadata; labels never decide
which eligible files are staged.

## Real historical IndPenSim data

[Stephen Goldrick, IndPenSim dataset version 2](https://data.mendeley.com/datasets/pdnjz7zz5x/2),
published October 8, 2019; DOI `10.17632/pdnjz7zz5x.2`; **CC BY 4.0**.
Publisher metadata: `backend/benchmarks/cmo_ingestion/provenance/mendeley-v2.json`.
Archive: `backend/benchmarks/cmo_ingestion/raw/100_Batches_IndPenSim.zip`,
503,792,426 bytes, SHA-256
`bc434c6cf96444fee3c915d434ac84e2a9c6492be4daebcfa4aed9cdff181f00`.

The historical adapter retains all **113,935 rows / 100 batches** for 14 selected
variables, including three Raman channels. Original decimal strings are written
unchanged, alongside original archive member and physical CSV row. The immutable
archive retains all 2,200 Raman channels; the projection is explicitly partial
in variable coverage. No genuine measurement is replaced by synthetic values.

The publisher CSV has two unquoted commas in the PAT header. Only the verified
three header fragments at physical header fields 34–36 are joined; numerical
rows are untouched and their widths/selected headers are validated. Source
field units include temperature K, dissolved oxygen mg/L, penicillin/substrate
g/L, flow L/h, agitation rpm and volume L. Raman channel units are unspecified.
Batch-statistics penicillin mass units are not used because their magnitude and
label require further verification; no undocumented unit correction is applied.

Batches 1–30 use a recipe, 31–60 operator control, 61–90 APC/Raman and 91–100
fault conditions. These are simulation-derived historical groups, **not randomized
matched experiments**. Fault-reference, fault-flag, controller and PAT-reference
columns are excluded from model-accessible projections. Evaluator batch-group
labels do not supply independently annotated fault onset intervals or causes.

Simulator source versions, licenses, numerical dependencies and exact execution
commands are documented in [the feasibility report](indpensim_feasibility.md).
