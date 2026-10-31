# Shared verification for files and connected sources

The job is to make data from existing CDMO systems usable without a manual export while applying the same deterministic quantity and collection checks used for file deliveries. Collection, verification, human review, and publication remain distinct states.

The four product pillars apply together: existing connectors remove manual preparation; original payloads and source locations remain inspectable; the review panel and publication command provide concrete next steps; existing source systems, stores, and permissions remain in place. Useful rollout measures are time to the first accepted observation, the number of mapping corrections, outstanding verification reasons, and the age of published source snapshots. These measures have not been measured in a real onboarding rollout.

Routing live records through generated CSVs would reuse the file entry point but would add another representation and obscure original API record identities. Instead, extraction adapters feed a shared lightweight vocabulary and verification engine. This keeps structured acquisition independent of document/OCR dependencies. Storage and review adapters retain their existing file-specific and platform-specific contracts; this change does not migrate either store or automatically replicate every record into the private Prime analytical store.

## Data path

- Delivered/uploaded files use `manufacturing_data.ingest`, then CMO classification and field mapping. `cmo.pipeline` calls `ingestion.verification.validate_measurement` and `validate_collection`.
- REST polling, signed-webhook queues, file drops, MQTT, and OPC UA all enter the existing `IntakeService`. It retains raw JSON evidence and collection checkpoints, then invokes `SourceVerificationService` using those same shared checks.
- Measurement records use batch, time, parameter, raw value/unit, source identity and revision. Nonmeasurement records retain their mapped and unmapped fields; the bioprocess vocabulary is not imposed on QMS/ERP objects that contain no measurement.
- Shared checks cover explicit unit conversion, finite values, ranges, batch/time context, conflicts, duplicates, and affected-row propagation. Whole-delivery expectations apply to complete file deliveries. Live collections remain open: late arrival is not treated as corrupt file row order, and missing documents are not inferred from one incomplete poll.

## Configuration and review

A connector's optional `source_group` identifies its CDMO or integration namespace. Cross-record checks include current records from all connectors in that group **and site**, within the authenticated tenant. An omitted group defaults to the connector ID, preventing accidental joins across unrelated sources.

`mapping_confirmed` defaults to false. Explicitly confirming a mapping permits automatic acceptance only when all checks pass. Otherwise records require review. Mapping edits recheck retained original payloads without rewinding a transport cursor. Original corrections or policy changes reset prior acceptance decisions and invalidate their downstream basis.

The Sources/onboarding screen exposes **Verify data**, original evidence identifiers, canonical values, retained unmapped fields, and attributed accept/reject decisions. Invalid values or unresolved conflicts cannot be accepted with a free-text reason; correct the source/mapping or reject the reading. Review requires the existing `approve` permission and a human actor, with the expected record revision and a reason. Collection permission does not grant review permission.

## API

| Command | Behavior |
| --- | --- |
| `GET /v1/connectors/{id}/verification` | Source-group records, current review states, reasons, and summary |
| `POST /v1/connectors/{id}/verification/review` | `record_id`, `expected_revision`, `decision` (`accept`/`reject`), `reason` |
| `POST /v1/connectors/{id}/verification/publish` | Publish an accepted observation snapshot; block pending/stale/invalid data and known collection gaps |

Publication requires `export`. Rejected records stay in the audit and coverage accounting. Measurement snapshots use the same `verified_cmo_dataset` content contract and dataset readers consumed by scientific conversations. Generic source objects publish as `verified_source_dataset`; they are not silently converted into scientific measurements.

Snapshots pin original evidence, mapping, and review revisions. Dataset consumption revalidates those references; a changed basis is shown as stale and blocked from reuse. Dependencies are linked so source corrections and review changes invalidate downstream derived work. A snapshot of accepted live observations explicitly reports `collection=open` and `complete=false`; it does not certify a completed batch or the truth of the originating instrument.

## Scope and trade-offs

File-specific parsing, page checks, layout confirmation, and source-element accounting stay with the file adapter. Live intake additionally owns transport checkpoints, source revisions, gap tracking, and collection status. Their **measurement and collection verification rules** are shared; document parsing is not run on already structured API data.

Cross-poll and cross-connector conflict checks operate within live source groups. Comparing an uploaded historical delivery against a live collection is still a consumer operation over the resulting datasets; no implicit join or cross-store migration is introduced. Current verification reads collect a source group's records in memory; production-scale indexing and pagination remain deployment work, not a claimed performance result.

The root `sievance-architecture.drawio` shows this convergence. Regenerate it with `python3 scripts/generate_architecture.py`. The generator checks route geometry and text bounds; its SVG previews support a further visual check.
