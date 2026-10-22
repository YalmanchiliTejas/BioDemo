# CMO ingestion execution report

100 source batches, deterministic samples per batch; three Raman channels; one generated package per condition. Synthetic Sanofi forms are intentionally limited.

Not conducted. No human-time or time-savings claim is supported.

| Config | Dataset | Layout | Status | Recall | Value accuracy | Auto accepted | Wrong auto | Review items | Seconds |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| A | indpensim | unseen | unavailable | — | — | — | — | — | 0.000 |
| A | indpensim | returning | unavailable | — | — | — | — | — | 0.000 |
| A | indpensim | changed | unavailable | — | — | — | — | — | 0.000 |
| A | sanofi | unseen | unavailable | — | — | — | — | — | 0.000 |
| A | sanofi | returning | unavailable | — | — | — | — | — | 0.000 |
| A | sanofi | changed | unavailable | — | — | — | — | — | 0.000 |
| B | indpensim | unseen | unavailable | — | — | — | — | — | 0.000 |
| B | indpensim | returning | unavailable | — | — | — | — | — | 0.000 |
| B | indpensim | changed | unavailable | — | — | — | — | — | 0.000 |
| B | sanofi | unseen | unavailable | — | — | — | — | — | 0.000 |
| B | sanofi | returning | unavailable | — | — | — | — | — | 0.000 |
| B | sanofi | changed | unavailable | — | — | — | — | — | 0.000 |
| C | indpensim | unseen | unavailable | — | — | — | — | — | 0.000 |
| C | indpensim | returning | unavailable | — | — | — | — | — | 0.000 |
| C | indpensim | changed | unavailable | — | — | — | — | — | 0.000 |
| C | sanofi | unseen | unavailable | — | — | — | — | — | 0.000 |
| C | sanofi | returning | unavailable | — | — | — | — | — | 0.000 |
| C | sanofi | changed | unavailable | — | — | — | — | — | 0.000 |
| D | indpensim | unseen | executed | 100.00% | 100.00% | 0.00% | 0 | 1402 | 1.095 |
| D | indpensim | returning | executed | 100.00% | 100.00% | 78.60% | 0 | 300 | 0.411 |
| D | indpensim | changed | executed | 92.86% | 100.00% | 0.14% | 0 | 1312 | 0.508 |
| D | sanofi | unseen | executed | 97.14% | 100.00% | 0.00% | 0 | 70 | 1.052 |
| D | sanofi | returning | executed | 98.57% | 100.00% | 97.14% | 0 | 2 | 1.042 |
| D | sanofi | changed | executed | 86.84% | 100.00% | 10.53% | 0 | 59 | 1.068 |
| preview | indpensim | unseen | executed | 100.00% | 100.00% | 0.00% | 0 | 1402 | 0.346 |
| preview | indpensim | returning | executed | 100.00% | 100.00% | 78.60% | 0 | 300 | 0.591 |
| preview | indpensim | changed | executed | 92.86% | 100.00% | 0.14% | 0 | 1312 | 0.385 |
| preview | sanofi | unseen | executed | 97.14% | 100.00% | 0.00% | 0 | 70 | 1.358 |
| preview | sanofi | returning | executed | 98.57% | 100.00% | 97.14% | 0 | 2 | 0.744 |
| preview | sanofi | changed | executed | 86.84% | 100.00% | 10.53% | 0 | 59 | 1.052 |

## Protocol

Automated confirmation of public vocabulary proposals on calibration packages; not human work

## Limitations

- A/B/C require installed Docling and configured real inference endpoints; unavailable is not a score.
- preview is an additional diagnostic baseline, not configuration A.
- D unseen has no confirmed templates and must route all values to review.
- PDF provenance is scored at page level. OCR source agreement still requires visual review.
- No controlled comparison with Invert has been conducted.

## Observed failures

- D / indpensim / changed: recall 92.86%, 0 incorrect auto-accepted values.
- D / sanofi / unseen: recall 97.14%, 0 incorrect auto-accepted values.
- D / sanofi / changed: recall 86.84%, 0 incorrect auto-accepted values.
- preview / indpensim / changed: recall 92.86%, 0 incorrect auto-accepted values.
- preview / sanofi / unseen: recall 97.14%, 0 incorrect auto-accepted values.
- preview / sanofi / changed: recall 86.84%, 0 incorrect auto-accepted values.
