# Live synthetic Sanofi ingestion run

- Package: sanofi-unseen (synthetic; not actual Sanofi operational records).
- Configuration: Docling + native Cloudflare Clairic + OpenAI Decisions.
- Run: b8e23324de2f4e8880147ff24b59e0aa
- Execution status: complete; verified package: False.
- Processing: 33.97 seconds.
- Candidate measurements: 56; auto-accepted: 0; needing review: 56.
- Open issues: 14.
- API calls: 8; actual input tokens: 25665; output tokens: 0.
- Clairic: seven responses received; every document extraction failed the confidence gate. Each was reported as uncertain extraction and missing supported measurements.
- OpenAI Decisions: one successful mapping request.
- Total inference cost: unknown because Clairic pricing is unset; configured OpenAI estimate: $0.0005385.
- Human verification time: not measured. No mappings confirmed, values accepted, or records corrected by this automated run.

Execution completion does not mean verified or analysis-ready data. These are execution counts, not held-out accuracy/recall scores. No answer keys were read, and no extraction rules or thresholds were changed based on this run.

Full source provenance, issue list, and usage receipts: [run.json](run.json).

Raw Clairic outputs: [readable field/confidence tables](CLAIRIC_OUTPUTS.md) and [complete audited requests/responses](clairic-responses.json).
