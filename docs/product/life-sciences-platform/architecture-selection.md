# Architecture selection for the complete workflow baseline

Researched 2026-10-24. Selected for this repository: a modular transactional
application with separately deployable durable workers, site acquisition
gateways and a WebRTC media service. This is a best-fit engineering judgment for
the current code, team proof of concept and operating requirements. It is neither
a universal best architecture nor a reconstruction of Apprentice's private stack.
The comparison covers the relevant architecture families; it cannot exhaust every
possible design or establish performance without measurement.

## Job and constraints

Manufacturing, laboratory, quality and partner teams need complete work: author
and approve a procedure, execute it with resource and signature checks, collect
and review samples, transfer knowledge between sites, collaborate remotely, and
acquire instrument evidence through outages. The output must retain the sources,
versions, permissions and human decisions needed to inspect what happened.

The inspected repository already has React/Vite, a modular FastAPI application,
shared domain services, SQLite/PostgreSQL record adapters, revisions/audit/outbox,
approval-bound actions, mission orchestration and an optional Temporal worker.
`flows.py` adds a checkpointed data-task interpreter. `collab.py` separates case
access from a replaceable media provider. Connectors support local files and
industrial clients, but an API-host-local connector is not an installed site
gateway. The main gaps are completing workflows and operational boundaries,
rather than finding a new language or moving all business rules across a network.
This inventory is source inspection, not a new execution or performance test.

Apply the four pillars jointly:

| Pillar | Design response | Cost or risk to make visible |
| --- | --- | --- |
| Easy to Start | One domain application, progressive forms, local synthetic setup; optional media and edge profiles | Production identity, native ownership and plant endpoints still require deliberate configuration |
| Easy to Trust | Shared authorization, versioned definitions, pinned evidence, explicit decisions and durable receipts | A common data store demands strong tenant binding, careful transactions and tested privileged paths |
| Easy to Act | Complete draft→review→execution→outcome journeys; resumable work and clear blocked states | Retrying external effects requires destination reconciliation and cannot be inferred from a local success flag |
| Easy to Adopt | Preserve existing systems of record, install read-only acquisition near instruments, use replaceable providers | Edge maintenance, network policy and media connectivity remain real deployment work |

## Options compared

These are decisions on different axes: microservices are an application boundary
choice, event sourcing is a persistence model, and serverless is a deployment
choice. They can be combined; none alone supplies a complete regulated workflow.

| Option | Where it helps | Costs for this repository | Decision |
| --- | --- | --- | --- |
| Modular domain application, relational transactions, separate task/media/edge processes | Cross-domain approval and evidence invariants; rapid complete workflows; independent scaling of expensive work | Modules share a deployment lifecycle and core database; boundaries require discipline | Select now |
| Domain microservices with individual databases and a broker | Independent teams/releases, distinct security zones and demonstrated scaling differences | Distributed consistency, service identity, contracts, retries, observability and deployment overhead before a measured need | Preserve extraction seams; defer splitting domain records |
| Event-sourced domain model with projections | Complex historical reconstruction and replay-centered domains | New event schemas, projection recovery and correction semantics; existing revisions already preserve historical state | Keep audit/revisions and transactional events; do not replace all state with event streams |
| Managed functions plus managed queues/workflows | Bursty intake, webhooks and bounded transformations; reduced server maintenance | Function duration, payload/network constraints and fragmented local debugging; durable orchestration and persistent edge/media remain necessary | Optional ingress/compute adapters; not the mandatory runtime |
| Managed containers/database/orchestration/media | Less infrastructure management while retaining process and domain boundaries | Provider dependency, service limits and costs need evaluation | Compatible production hosting choice; do not hard-code a cloud vendor |

Microsoft describes independent deployment/data ownership as microservice
benefits, together with the additional orchestration, communication and
observability components they require. That supports a later split when its
benefits exceed those costs, not a presumption that a larger service count is
better. [Microservices architecture](https://learn.microsoft.com/en-us/azure/architecture/guide/architecture-styles/microservices)

Microsoft's event-sourcing guidance calls out schema, query, concurrency and
migration trade-offs. Existing append-only revisions and audit are sufficient
for the present historical-inspection job without making every state change a
replayed event. [Event sourcing](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing)

AWS Lambda has a bounded invocation timeout, currently configurable up to 900
seconds. A function can perform a bounded task, while longer work needs a durable
coordinator or another execution host. This is not a claim that all managed or
serverless workflow products have that restriction. [Lambda timeout](https://docs.aws.amazon.com/lambda/latest/dg/configuration-timeout.html)

## Selected boundaries and contracts

### Transactional control plane

The authenticated API and domain modules own procedures, batches, samples,
results, cases, transfer packages, permissions and action intents. They validate
current authority, expected record revisions, source lineage and explicit native
ownership. Draft, approval, dispatch and observed outcome stay distinct.
The frontend uses purpose-built controls for the user's task and does not execute
domain policy independently. A procedure preview has no authority to publish;
receiving a transfer package does not establish site readiness.

PostgreSQL remains the shared transactional record store in production. Commit
record changes, revisions, audit and outbox rows together. Publish committed
events later with stable IDs; consumers deduplicate and check aggregate versions.
AWS's outbox pattern addresses the failure between committing application state
and publishing an event, while still requiring duplicate handling. Our inference
is to reuse the existing outbox rather than add a broker to every command.
[Transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)

PostgreSQL's default Read Committed isolation permits different snapshots across
successive reads in a transaction. Preserve conditional expected-revision writes,
uniqueness constraints and fencing rather than assuming a transaction prevents
every race. [Transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html)
Use a separate migration identity and a non-owner runtime identity: table owners,
superusers and `BYPASSRLS` roles can bypass normal row-security restrictions.
Application checks still protect site, partner, evidence and media access.
[PostgreSQL row security](https://www.postgresql.org/docs/16/ddl-rowsecurity.html)

### Durable orchestration and bounded workers

Temporal owns long waits, timers and recovery; domain records own scientific and
business truth. External calls and nondeterministic calculations run in bounded
activities, not workflow replay logic. Activities can retry, so each external
write needs a stable intent key and an explicit reconciliation contract. Temporal
documents activity idempotency and heartbeat recovery; it does not make arbitrary
external manufacturing effects exactly once. [Temporal activities](https://docs.temporal.io/activities)

Keep worker runtime and provider dependencies separate from the API process.
Checkpoint data flows at node boundaries and pin definitions, inputs and operator
versions. A completed task can be reused only while its source permissions and
validity hold. Never put arbitrary submitted Python/SQL in the API process.
An isolated code runner, if added later, is a separate execution boundary with
resource limits, restricted credentials and review appropriate to its effects.

Ganymede documents dependency-ordered nodes, versioned flow changes and a host
gateway/connection model. These are useful behavior patterns; they do not identify
its engine or establish a shared Tempo/Ganymede deployment topology.
[Ganymede concepts](https://docs.ganymede.bio/app/intro/Concepts)

### Site acquisition plane

Install a separate gateway process near instrument networks and file shares.
Give each gateway one configured tenant/site identity and limited connection
configuration. Local acquisition uses the existing file, MQTT and OPC UA adapters
where possible. Its default authority is evidence acquisition; it has no general
manufacturing-command or remote-shell capability.

Persist an event in a local SQLite spool before acknowledging acquisition. Retain
its stable source event ID, original timestamp, quality, content digest and
connection/configuration identity. Send outbound batches over authenticated TLS;
remove or mark a spool item delivered only after the server confirms its durable
receipt. The cloud endpoint binds tenant and site to authenticated gateway
configuration, never trusts labels supplied in the event, and deduplicates retries.
Backoff is bounded; storage exhaustion and rejected records are visible.

Azure's documented offline pattern stores upstream messages locally and forwards
them after reconnection; storage remains bounded by retention and disk. We choose
that pattern without requiring the Azure runtime. Local buffering does not make
official batch execution available offline.
[IoT Edge offline behavior](https://learn.microsoft.com/en-us/azure/iot-edge/offline-capabilities)

MQTT QoS 1 permits duplicates, so broker delivery is not a substitute for
end-to-end event deduplication. Persistent sessions and a durable local queue are
separate responsibilities. The existing client's MQTT 3.1.1 choice can remain;
using these semantics does not require a protocol migration.
[OASIS MQTT 3.1.1](https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html)

OPC UA subscriptions have sequence/acknowledgment and retransmission behavior;
retention and optional capabilities depend on the server. A periodic snapshot
reader must be labeled as such: it cannot establish lossless subscription or
historian backfill. Preserve timestamps/status and disclose missed intervals.
[OPC UA subscription model](https://reference.opcfoundation.org/specs/OPC-10000-4/5.14.1)

### Remote collaboration media plane

Use LiveKit as the first real provider behind `MediaProvider`. Keep room creation,
participant authorization, consent and case linkage in the domain API. Browser
audio/video/screen tracks travel to the SFU rather than through FastAPI or the
record database. The backend signs short-lived, room- and identity-scoped tokens;
provider secrets never enter browser bundles, records or audit payloads.
LiveKit specifies server-side token generation because signing requires API
credentials. [LiveKit authentication](https://docs.livekit.io/frontends/build/authentication/)

Camera/microphone publication requires an explicit user action. Recording is off
by default and is a separate consented operation; a metadata flag alone must not
claim that a recording exists. Browser cleanup stops local tracks and disconnects
the room. Participant removal and session termination must also reach the provider.
Short token lifetime is not a replacement for disconnecting an already connected
participant; provider-side removal is the enforcement mechanism.
[Participant management](https://docs.livekit.io/intro/basics/rooms-participants-tracks/participants/)

Self-hosted media needs its own networking plan, trusted TLS and often TURN for
corporate firewall traversal. Offer a local development service and either a
managed or separately hosted production service. Do not describe a local two-
browser test as qualification of a plant's network or devices.
[LiveKit deployment](https://docs.livekit.io/transport/self-hosting/deployment/)

## Failure and recovery acceptance

| Failure or concurrency condition | Required observable behavior |
| --- | --- |
| Concurrent procedure edits | Stale revision is rejected; submitted content does not silently change beneath approval |
| Approver/site authority changes | Current authority is checked again before consequential publication or execution |
| Sample or result correction | Original observation and correction history remain; released values require the existing controlled invalidation process |
| Transfer revised after approval | Old approval no longer covers the package; receiver sees missing mappings/qualification rather than inferred readiness |
| API/worker process stops | Committed domain state/outbox survives; replacement worker uses checkpoint and fence; in-flight effects may require reconciliation |
| Edge disconnects before server receipt | Locally durable data remains queued; resending preserves identity and does not duplicate evidence |
| Disk full or invalid source record | Visible blocked/rejected state; no premature acknowledgment or silent cursor advancement |
| Provider times out after accepting an action | Delivery is unknown until reconciled; no blind repeat of consequential effects |
| Media endpoint unavailable | Session reports failure/unavailability; no fake token or fabricated video success |
| User leaves, loses access or session ends | Stop local capture; enforce provider disconnect/end; deny new tokens and preserve audit metadata |

## Deployment and later change

For development, run frontend/API plus optional worker, edge and media profiles;
SQLite is suitable for isolated tests and gateway spooling. For shared deployment,
run the API and worker as separate containers/processes against PostgreSQL and
configured evidence storage; place the gateway on its authorized site host and
the SFU on a host/service suitable for media networking. Do not require Kubernetes
or a public broker merely to exercise the proof of concept.

This choice is consistent with [ADR 0001](../../adr/0001-record-ownership-and-native-execution.md),
[ADR 0002](../../adr/0002-transactional-state-and-versioned-evidence.md) and
[ADR 0003](../../adr/0003-persistent-missions-and-runtime-boundaries.md). It refines
their deployment boundaries, rather than replacing their record ownership,
transactional evidence or persistent mission decisions. Those ADRs remain marked
proposed in the repository; this research does not silently relabel their status.

Replace a provider through its adapter and contract tests. Extract a domain
service when measurements show an independent scaling/security/release need,
then designate one record owner and migrate using versioned APIs/outbox events.
An event stream, search service or analytical store can be added as a projection
without becoming the owner of approved operational records. This preserves a
change path without making the initial adoption depend on that migration.

Measure completed task effort, setup steps and review time as well as p50/p95
command latency, worker queue age, outbox lag, edge queue age/bytes, duplicate
suppression, source gaps, flow recovery, failed/retried provider calls and media
join/reconnect success. Record build, workload, device/network and test environment.
Targets need workload-specific agreement; this document establishes no measured
throughput, recovery objective, time savings or compliance result.
