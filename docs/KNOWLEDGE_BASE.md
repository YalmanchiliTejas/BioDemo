# CDMO knowledge base

The knowledge subsystem implements the manufacturing digital thread behind the
application's Context / Memory layer. Systems of record remain authoritative;
the knowledge base retains evidence, provenance, relationships, controlled
knowledge, working cases, and retrieval indexes.

## Write path

```mermaid
flowchart LR
    SOR[Systems of record] --> BUS[Redpanda / Kafka]
    BUS --> EVIDENCE[MinIO immutable evidence]
    EVIDENCE --> NORMALIZER[Canonical event normalizer]
    NORMALIZER --> MONGO[MongoDB documents]
    NORMALIZER --> NEO[Neo4j digital thread]
    NORMALIZER --> CASES[PostgreSQL cases and outbox]
    MONGO --> VECTOR[Qdrant semantic index]
    CASES --> BUS
```

`DigitalThread.ingest_raw_event` writes the unmodified source payload to the
content-addressed evidence store before it creates a canonical event. The event
contains event time and ingestion time, tenant/site/classification scope,
explicit entity references, source identity, correlation, and the evidence id.
`DigitalThread.ingest_controlled_document` follows the same evidence-first path
for SOPs, specifications, MBRs, CAPAs, validation documents, and other controlled
records; its content hash becomes the revision's immutable evidence reference.

Digital-thread mutation paths create idempotent outbox messages. `KafkaOutboxPublisher`
publishes pending messages and marks only confirmed deliveries as published.

## Storage responsibilities

- **MinIO/S3:** immutable original bytes, keyed by tenant and SHA-256 digest.
- **MongoDB:** extracted text, metadata, source payloads, controlled revisions,
  decisions, and exact lexical search.
- **Neo4j:** events, entity timelines, document lineage, evidence provenance,
  cases, decisions, approvals, and applicability relationships.
- **PostgreSQL:** transactional working cases, human tasks, optimistic locking,
  and the durable outbox.
- **Qdrant:** optional tenant-filtered semantic search using local FastEmbed
  embeddings.
- **Redpanda:** Kafka-compatible integration and normalized-event transport.

## Core graph relationships

`PREVIOUS_EVENT`, `SUPPORTED_BY`, `REVISION_OF`, `SUPERSEDES`, `APPLIES_TO`,
`CONTAINS`, `BASED_ON`, `FOLLOWED_PROCEDURE`, `AFFECTED`, and `APPROVED_BY` are
projected by the application service. Domain relationships are tenant scoped.

## Security boundary

Every application operation receives an `AccessContext`. Tenant identity,
site scope, and classification clearance are enforced before writes and during
context retrieval. Production APIs must create this context from authenticated
claims; callers must never be allowed to supply arbitrary tenant claims.

The adapters provide application-level controls, not a validated GxP security
boundary by themselves. Production deployment still requires database roles,
network policies, encryption keys, backups, monitoring, retention configuration,
electronic-signature procedures, and validation evidence.

## Local services

```bash
python3 -m pip install -e '.[knowledge,semantic,eventbus,documents]'
docker compose -f docker-compose.knowledge.yml up -d
python3 -m benchmark knowledge-ingest runs/baseline/events.jsonl \
  --tenant sponsor-a --site site-01 --source benchmark
```

Environment variables:

| Variable | Default |
|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` |
| `MONGODB_URI` | `mongodb://localhost:27017` |
| `POSTGRES_DSN` | `postgresql://biopharma:biopharma-dev@localhost:5432/biopharma` |
| `S3_ENDPOINT_URL` | `http://localhost:9000` |
| `EVIDENCE_BUCKET` | `cdmo-evidence` |
| `QDRANT_URL` | `http://localhost:6333` |

REST source connectors are enabled independently with `<SYSTEM>_BASE_URL` and
optional `<SYSTEM>_API_TOKEN`, `<SYSTEM>_EVENTS_PATH`, `<SYSTEM>_WRITE_PATH`, and
`<SYSTEM>_SITE_ID` settings. Supported catalog names are MES, eBR, PAT, LIMS,
CDS, QMS, SCADA, Historian, CMMS, ERP, WMS, and ELN. Setting a write path to
`none` keeps that connector read-only.

For local MinIO, set `AWS_ACCESS_KEY_ID=biopharma` and
`AWS_SECRET_ACCESS_KEY=biopharma-dev` before running the ingestion command.
PDF and DOCX extraction use open-source Python libraries. OCR of scanned images
or PDF pages additionally requires the Tesseract executable on the application
host.

## Production caveats

- Enable S3 Object Lock retention rather than relying only on hash-addressing.
- Use a transactional inbox at event-bus consumers for effectively-once
  projection.
- Run an identity-resolution review queue for unmatched source identifiers.
- Chunk controlled documents by stable section/page coordinates before vector
  indexing so citations resolve to exact source locations.
- Validate electronic signatures and audit controls under the applicable GxP
  and 21 CFR Part 11 procedures before regulated use.
