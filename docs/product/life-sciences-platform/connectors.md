# Configuring source connections

The connected workspace's **Sources** page and `/v1/connectors` API configure MES,
LIMS, QMS, ERP and historian sources. ELN, CMMS and WMS mapping profiles reuse the
same contracts. Existing systems retain ownership. No vendor credentials or live
customer connections are included in this checkout.

## Runtime setup

Install the industrial drivers when using MQTT or OPC UA:

```bash
cd backend
.venv/bin/pip install -e '.[industrial-connectors]'
```

Set these server environment variables (or CLI-loaded `backend/.env.local`):

```dotenv
LIFESCI_CONNECTOR_ALLOWED_HOSTS=mes.example.com,lims.example.com,historian.example.com
LIFESCI_CONNECTOR_FILE_ROOT=/approved/exports
LIFESCI_TENANTS=your-tenant
LIMS_READ_TOKEN=replace-in-your-secret-store
```

Only explicitly listed hosts can be contacted. HTTPS is required for remote REST
endpoints and MQTT uses TLS remotely; plaintext HTTP/MQTT is allowed on loopback for
development. HTTP redirects are refused. File sources must be directories under
the configured root; symlink escapes are rejected. An administrator supplies
credential **environment variable names** in connection settings; secret values
are resolved on the server and never stored in connector records or sent to the UI.

`LIFESCI_TENANTS` enumerates tenants for restart recovery in standalone workers and
idle API processes. `DEPLOYMENT_TENANT` is also recognized; active API requests and
committed events register their tenant while a process is running. The runtime
polls saved configuration and resumes stored cursors. It does not require a
cross-tenant database role. Use Temporal for durable mission scheduling across
process restarts; the local scheduler runs configured tasks while the API is alive.

## Connection contracts

| Transport | Configuration and source contract | Limits |
| --- | --- | --- |
| REST | `base_url`, `events_path`, optional `auth_env`; JSON response `{records: [...], next_checkpoint: "...", has_more: false}`. Each record has stable `id` and timezone-bearing `timestamp`. `records_field`, `next_checkpoint_field`, `id_field`, `timestamp_field`, `cursor_parameter`, `limit_parameter` can adapt field names. | Vendor paths/auth schemes beyond bearer tokens need an adapter. Pagination must advance; retrying a batch deduplicates evidence. |
| File | `directory`; CSV, JSON array/`records` envelope, or JSONL with stable IDs and timezone-bearing timestamps. | Changed file digests trigger replay and source corrections. Rejected rows and mapping issues remain visible; deleted files do not imply record deletion. |
| Webhook | `secret_env`; POST to `/v1/webhooks/{tenant}/{connector_id}` with `X-Timestamp`, `X-Delivery-Id`, `X-Signature`. Signature is HMAC-SHA256 of `timestamp + '.' + raw body`, as implemented by `integrations.sign_payload`. | Five-minute tolerance, durable delivery replay protection, 1 MB request limit. Sync moves accepted records from the durable queue into evidence. |
| MQTT | `base_url` (`mqtts://host:8883`), `addresses` (topics), optional `username_env`, `password_env`, `ca_file`. JSON messages carry stable `id`, `timestamp`, and source fields such as `value`, `unit`, `quality`. | Paho 2.x, MQTT 3.1.1, persistent session and QoS 1 subscription. Raw records are persisted before QoS acknowledgements. QoS 0 has no delivery guarantee. Publisher history/backfill is not assumed. Topic is retained as provenance. No publish/control API. |
| OPC UA | `base_url` (`opc.tcp://host:4840/path`), `addresses` (node IDs), `security_string_env`, optional `username_env` and `password_env`. The security setting contains `Basic256Sha256,SignAndEncrypt,client-cert,client-key,server-cert`. | Read-only bounded snapshots with source timestamp and quality. All nodes must fit `batch_size` (default 100, max 1000). No control writes, subscription republish or historical backfill is claimed. asyncua 2.1+ is used for Python 3.14 compatibility. |

`poll_seconds=0` means manual sync; values of at least 10 enable periodic sync.
Manual and scheduled sync use the same current permission checks and connector
lease. A failure preserves the previous checkpoint and records a visible status.
Evidence source namespaces include the family and connector ID (`LIMS@northfield-lims`)
so independent source instances can reuse record IDs without collisions.

Default family templates retain every original field. Custom versioned mappings
can rename, validate and convert fields through the existing `ConnectorTemplate`
contract. Preview shows conversions, unmapped fields and mapping errors without
advancing ingestion cursors. MQTT begins durable collection at sync rather than preview.

## Write-back

Connections start read-only. REST write-back must explicitly list permitted
`write_operations` and configure `write_path`, `lookup_path`, and a separate
`write_auth_env`. The owning-system registration and exact-version human approval
are still required. The executor calls:

```text
POST /v1/connectors/{connector_id}/intents/{intent_id}/dispatch
POST /v1/connectors/{connector_id}/intents/{intent_id}/reconcile
```

The intent's family, operation and site must match the connector. Dispatch checks
current evidence and the approver's current authority at that site. Unconfirmed
network outcomes become `unknown`; reconciliation uses the destination's
idempotency key. Lookup responds `{status: "delivered", receipt: {...}}`,
`{status: "not_found"}`, or leaves the outcome unconfirmed. Control writes via
MQTT and OPC UA are unavailable.

## Evidence and trade-offs

The implementation reuses generic transport contracts and configurable mappings
instead of adding speculative vendor SDKs. This reduces setup and maintenance,
preserves source evidence, makes sync errors actionable, and fits existing records.
The trade-off is that vendor-specific authentication, schemas, device behavior and
customer qualification still require endpoint-specific work.

Tests exercise REST endpoints, file corrections, signed webhooks, the real Paho
client against a local MQTT protocol fixture, and encrypted asyncua reads against a
local OPC UA server. These are development tests, **not vendor qualification**.
Connector contracts remain simulated until separately qualified through the
existing matrix. Observe setup steps, mapping/rejection counts, successful syncs,
replay duplicates, source-to-evidence latency and recovery after failure; no user
effort or performance improvement is claimed without measuring it.

Driver references: [Paho client](https://eclipse.dev/paho/clients/python/docs/),
[asyncua](https://github.com/FreeOpcUa/opcua-asyncio),
[Python 3.14 issue in asyncua 1.1.8](https://github.com/FreeOpcUa/opcua-asyncio/issues/1880).
