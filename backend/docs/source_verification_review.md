# Exact JSON references and scanned-source review

The automatic verifier now reads JSON/text citations from the immutable original
file at the exact physical `span: line:N`. Blank lines and indentation retain
their original coordinates. Original hashes and exact extracted values must
match. The independent benchmark location scorer supports the same JSON lines.
Invalid locations, changed source files and wrong source values remain failures.

Image-only PDF citations remain `human_review_pending`. Rerunning OCR is not
independent confirmation of the extracted text. The new interface displays the
original rendered PDF page beside the extracted citation and exact source
coordinates. Reviewers record `matches`, `does_not_match`, or `unreadable`, with
a note. Receipts bind reviewer attribution to the immutable source hash,
location and extracted-text hash; a stale packet is rejected. Previous receipts
are retained. An exact bound `matches` receipt can resolve the runtime source
gate as `verified_with_human_review`; the automatic `value_matches` remains
unknown and the human-reviewed count is reported separately. A later
`does_not_match` receipt blocks report verification. `unreadable` remains pending.
These receipts do not grant independent scientific qualification, override wrong
original values, or silently promote OCR to automatic verification. The benchmark
location scorer still reports image-only references as pending; independent
qualification requires its separate output-bound review.

## Review interface

With the application configured for the ingested store and tenant, open:

```
/manufacturing-source-review/{observation_id}?as_of=2024-12-01T12:00:00Z
```

The scoped endpoints are:

- `GET /api/manufacturing-os/evidence/{id}/review-packet?as_of=...`
- `GET /api/manufacturing-os/evidence/{id}/page-image?as_of=...`
- `POST /api/manufacturing-os/evidence/{id}/source-review?as_of=...`

The POST body contains `packet_sha256`, `decision`, and `note`. Reviewer identity
comes from the existing API identity adapter; QA/supervisor roles are required.
The application's headers are development identity, not production authentication.
The reviewer-write endpoint is not exposed as an agent skill tool. Full-page
previews are denied if indexed page observations include unavailable future text.

For an offline review, export the packet and original page image:

```sh
.venv/bin/python -m src.manufacturing_data.source_review \
  --store PATH_TO_INGESTED_STORE --scope evaluation \
  --as-of 2024-12-01T12:00:00Z --observation-id OBSERVATION_ID \
  --output /private/tmp/source-review
```

After an actual human comparison, use the same command with `--decision matches`
(or `does_not_match` / `unreadable`), `--packet-sha256 HASH_FROM_PACKET`,
`--reviewer-id YOUR_ID` and `--note 'What was checked'`. CLI identity is explicitly
self-attributed. Receipts are stored under `STORE/source-reviews/` and are visible
in subsequent review packets. Human decisions do not alter the original evidence
or previously recorded benchmark output. A scientific review still needs its
separate run/output-bound qualification process.

## Separate status dimensions

New runtime output and run records include:

- `execution_status`: whether execution returned successfully (run record).
- `investigation_status`: complete/incomplete according to scope and deliverables.
- `source_verification_status`: automatically verified or human review pending.
- `scientific_validation_status`: independent review pending.

A structurally complete final report may now be saved with pending visual source
checks, without requiring the agent to relabel its completed work as a partial
investigation. Numerical, claim, source-hash and source-value failures still
block final submission. The top-level benchmark `status` remains `incomplete`
when source review is pending, preserving conservative publication gating and
compatibility with existing dashboards. Its explicit reason and dimensions
identify the pending gate. Qualification treats image-only source checks as
pending review rather than a proven scientific failure. It does not count them
as passing citations.

## Saved-run replay

Run `ecc25eeed1784828a5ff31450e71f58c` originally had 9 unchecked anchors.
Reverification now passes **1,539/1,543** source checks, including all five JSON
anchors, and verifies all **7** structured calculations. Four scanned-PDF anchors
remain pending. No new model run or human approval was performed. The original
partial report and run result remain unchanged.

Artifacts: `results/verification/ecc25eeed1784828a5ff31450e71f58c-source-review-v1/`.
