---
status: proposed
---
# Transactional state with versioned evidence

Use PostgreSQL for BioDemo's domain records, revisions, decisions and transactional outbox, with versioned object storage for original evidence and large artifacts. Analytics, search and dependency views remain derived; we do not make every store authoritative or event-source every aggregate. This trades some bespoke historical replay flexibility for clearer consistency and lower operational burden while retaining auditable revisions and traceable evidence. See D04–D06 and D21 in the [decision log](../product/life-sciences-platform/decision-log.md).
