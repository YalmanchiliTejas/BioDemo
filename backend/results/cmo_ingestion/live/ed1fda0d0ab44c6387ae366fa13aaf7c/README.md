# Scalar Clairic debug replay

Same synthetic Sanofi-unseen raw package as the initial run; this is a debugging
replay, not a fresh held-out accuracy estimate. No evaluation keys were read.
Original answers, thresholds and historical reports were not changed.

## Executed comparison

| Measurement | Previous aligned lists | Revised scalar records |
|---|---:|---:|
| PDF candidates retained | 0 | 14 |
| Total candidates | 56 | 70 |
| Auto-accepted | 0 | 0 |
| API calls | 8 | 22 |
| Actual input tokens | 25665 | 32240 |
| Processing seconds | 33.97 | 53.46 |
| Open issues | 14 | 16 |
| Human minutes | Not measured | Not measured |

All 14 PDF candidates need original-source review. Candidates are not
verified fields or a claim of correct extraction. There is no measured field
recall, accuracy or completed human-time improvement from this replay.
Total inference cost remains unknown because Clairic pricing is unset.

## What changed

- One small record context per native Cloudflare request, with scalar text/number fields.
- Text spans checked against original source; numerical answers checked against printed raw values.
- Null is missing; guess is never used as a measurement.
- Source-backed low-confidence candidates retained; failures and uncertainty recorded per record.
- A clipped label is expanded only to an adjacent bracketed unit literally present in the source. This is flagged and never upgrades confidence.
- All model-derived candidates remain pending human review; no template was confirmed in this run.
- UI exposes retained answers, confidence, source spans and review reasons.

## Remaining failures

Issue counts: {'EXTRACTION_UNCERTAIN': 14, 'BATCH_MISMATCH': 2}.
Process-hour number answers frequently remain null despite a separately extracted
source text hour. Measurement labels and raw-value spans still have low confidence;
one record lacks its time, and some typed numbers disagree with raw source text.
OCR-corrupted identifiers produce batch mismatch issues. No confidence gate was
lowered. Multiple measurements in one record are flagged as incomplete coverage;
unknown record boundaries remain a limitation. Calls and runtime increased.

## Artifacts

- [Full run and per-value provenance](run.json)
- [Readable native Clairic answers](CLAIRIC_OUTPUTS.md)
- [Complete audited Clairic requests and responses](clairic-responses.json)
- [Open saved run in UI](http://127.0.0.1:5180/?tab=ingestion&run=ed1fda0d0ab44c6387ae366fa13aaf7c)

Verification: 74 Python regressions passed, including manufacturing-data, CHO and
Fresenius tests; UI production build passed. Live independent synthetic development
examples were executed before the package replay. This remains an unverified
manufacturing dataset until a real reviewer completes inspection and corrections.

Browser verification passed: the saved run loaded, all 14 Clairic review records were visible with raw answers, and no page errors were recorded.
