# CMO ingestion execution report

100 source batches, deterministic samples per batch; three Raman channels; one generated package per condition. Synthetic Sanofi forms are intentionally limited.

Not conducted. No human-time or time-savings claim is supported.

| Config | Dataset | Layout | Status | Recall | Value accuracy | Auto accepted | Silent errors | Silent omissions | Missed but flagged | Unaccounted elements | Review items | Review groups | Open issues | Seconds |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| D | cho | unseen | executed | 100.00% | 100.00% | 0.00% | 0 | 0 | 0 | 0 | 842 | 8 | 54 | 0.595 |
| D | cho | unseen+confirmed | executed | 100.00% | 100.00% | 100.00% | 0 | 0 | 0 | 0 | 0 | 0 | 54 | 0.160 |
| D | cho | returning | executed | 100.00% | 100.00% | 100.00% | 0 | 0 | 0 | 0 | 0 | 0 | 55 | 0.495 |
| D | cho | changed | executed | 100.00% | 100.00% | 0.47% | 0 | 0 | 0 | 0 | 2103 | 21 | 79 | 0.530 |
| D | cho | changed+confirmed | executed | 100.00% | 100.00% | 99.67% | 0 | 0 | 0 | 0 | 14 | 7 | 77 | 0.592 |

## Protocol

Automated confirmation of public vocabulary proposals on calibration packages; not human work

"+confirmed" rows: proposed layouts on the held-out package confirmed without edits by an automated protocol, then reprocessed. Simulates a reviewer accepting every proposal; not human work.
## Limitations

- A/B/C require installed Docling and configured real inference endpoints; unavailable is not a score.
- preview is an additional diagnostic baseline, not configuration A.
- D unseen has no confirmed templates and must route all values to review.
- PDF provenance is scored at page level. OCR source agreement still requires visual review.
- No controlled comparison with Invert has been conducted.

## Observed failures

