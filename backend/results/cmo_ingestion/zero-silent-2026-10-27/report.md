# CMO ingestion execution report

100 source batches, deterministic samples per batch; three Raman channels; one generated package per condition. Synthetic Sanofi forms are intentionally limited.

Not conducted. No human-time or time-savings claim is supported.

| Config | Dataset | Layout | Status | Recall | Value accuracy | Auto accepted | Silent errors | Silent omissions | Missed but flagged | Unaccounted elements | Review items | Review groups | Open issues | Seconds |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| D | indpensim | unseen | executed | 100.00% | 100.00% | 0.00% | 0 | 0 | 0 | 0 | 1402 | 15 | 1 | 1.103 |
| D | indpensim | unseen+confirmed | executed | 100.00% | 100.00% | 78.60% | 0 | 0 | 0 | 0 | 300 | 3 | 1 | 0.248 |
| D | indpensim | returning | executed | 100.00% | 100.00% | 78.60% | 0 | 0 | 0 | 0 | 300 | 3 | 2 | 0.276 |
| D | indpensim | changed | executed | 92.86% | 100.00% | 0.14% | 0 | 0 | 101 | 0 | 1312 | 51 | 19 | 0.317 |
| D | indpensim | changed+confirmed | executed | 92.86% | 100.00% | 67.99% | 0 | 0 | 101 | 0 | 352 | 41 | 18 | 0.296 |
| D | sanofi | unseen | executed | 97.14% | 100.00% | 0.00% | 0 | 0 | 2 | 0 | 70 | 15 | 9 | 0.948 |
| D | sanofi | unseen+confirmed | executed | 97.14% | 100.00% | 97.14% | 0 | 0 | 2 | 0 | 2 | 2 | 9 | 1.331 |
| D | sanofi | returning | executed | 98.57% | 100.00% | 97.14% | 0 | 0 | 1 | 0 | 2 | 2 | 8 | 1.397 |
| D | sanofi | changed | executed | 86.84% | 100.00% | 11.84% | 0 | 0 | 10 | 0 | 58 | 27 | 22 | 2.329 |
| D | sanofi | changed+confirmed | executed | 86.84% | 100.00% | 43.42% | 0 | 0 | 10 | 0 | 34 | 21 | 21 | 1.433 |

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

- D / indpensim / changed: recall 92.86%, 0 incorrect auto-accepted values, 0 silent omissions (101 misses flagged for review).
- D / indpensim / changed+confirmed: recall 92.86%, 0 incorrect auto-accepted values, 0 silent omissions (101 misses flagged for review).
- D / sanofi / unseen: recall 97.14%, 0 incorrect auto-accepted values, 0 silent omissions (2 misses flagged for review).
- D / sanofi / unseen+confirmed: recall 97.14%, 0 incorrect auto-accepted values, 0 silent omissions (2 misses flagged for review).
- D / sanofi / changed: recall 86.84%, 0 incorrect auto-accepted values, 0 silent omissions (10 misses flagged for review).
- D / sanofi / changed+confirmed: recall 86.84%, 0 incorrect auto-accepted values, 0 silent omissions (10 misses flagged for review).
