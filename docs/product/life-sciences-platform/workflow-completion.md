# Complete workflow setup and verification

The five requested gaps now have workflow implementations: advanced procedure
design, laboratory operations, technology transfer and partner access, remote
collaboration, and a site acquisition agent. The [architecture selection](architecture-selection.md)
compares credible alternatives and records why the selected boundaries fit this
repository. This is our implementation, with explicit seams for later changes.

## Start locally

Install `backend` with `pip install -e '.[lifesci-platform]'`, then use the existing
virtual environment and configuration described in [implementation](implementation.md).
The extra declares the API, PostgreSQL, scientific, orchestration and industrial
client dependencies. The frontend uses the normal `npm install` and `npm run dev`.

```bash
cd backend
.venv/bin/python -m src.lifesci seed-suite
.venv/bin/python -m src.lifesci serve --port 8100
```

Open `/app?view=suite` through the frontend and connect to tenant `demo-suite`.
Use `designer`, `operator`, `quality`, `reviewer`, `msat`, `receiver`, or `admin`.
This development sign-in is for local demonstration; the roles are persisted on
the server. `receiver` belongs to S2; the operator and quality roles belong to S1.
`admin` has tenant-wide configuration authority. The seed creates only a separate
synthetic tenant, preserves later edits on rerun, and never auto-approves work.
It does not alter `demo-northfield` or any customer tenant.

Begin as `quality` in Actions to review the two synthetic publication proposals.
Then connect as `designer` and publish their approved revisions in Procedures.
The batch, instrument and draft definitions are clearly synthetic; their fixture
values do not constitute calibration, qualification or scientific validation.
Configured native ownership is limited to this demonstration tenant.

## Exercise the workflows

| Workflow | User journey | Preserved boundary |
| --- | --- | --- |
| Advanced procedures | Create/edit draft → select dependencies and parallel groups → define branches/calculations/signatures/resources → preview with template values → submit → independent approval → publish → optional site adaptation | Expected revision prevents stale edits; publication checks current approver authority; pinned execution definitions do not change with later drafts |
| Manufacturing | Create/select batch → instantiate published recipe with parameters → select lots/equipment → start → capture values → independent signatures → inspect EBR/exceptions → disposition, N/A or approved redline → request QA release | Limits, resource/ownership and role checks remain server-side; local signing confirmation is labelled an unvalidated POC attestation, and disabled for OIDC mode |
| Laboratory | Register instrument → collect sample → aliquot → assign wells → execute approved method against selected instruments/reagents/samples → record calculation → independent review → release → approved invalidation for correction | Volume, plate conflicts, calibration and method readiness are checked; the recorder cannot review their own result; released results cannot be silently overwritten |
| Transfer | Create package with pinned procedure reference and mappings → receiving person acknowledges receipt → inspect inventory/qualification gaps → sender/recipient review → revise and re-review changed content | Receipt is distinct from readiness; approvals bind package content; site-specific visibility applies to dedicated and generic record reads |
| Partners | Tenant admin links distinct partner sign-in to organization → QA grants expiring batch access → partner reads permitted projection and provides feedback → QA revokes the share | Organization comes from stored membership, never request headers; feedback does not release a batch; revocation removes the underlying grants |
| Collaboration | Create case-linked room with authorized participants → agree/join → explicitly enable camera/microphone/screen share → chat/sketch → leave or end for everyone | Server-side room-scoped tokens; capture initially off; provider calls stay outside DB transactions; unconfirmed create/end states are visible and recoverable |
| Site acquisition | Enroll gateway → install agent near instruments → capture to local queue → upload signed event → verify exact server receipt → mark local entry delivered | Read-only acquisition; source cursor and local spool commit together; tenant/site identity is bound to enrollment; duplicate upload receipt prevents duplicate evidence after a lost ACK |
| Background data work | Save flow revision → prepare pinned run and evidence → queue → separate worker resumes nodes → inspect persisted progress | Completed node checkpoints survive restart; no manufacturing command operator; invalidation during computation cannot be replaced by a successful completion flag |

Some complex attributes use labelled advanced JSON editors rather than a visual
editor: resource requirements, receiving inventory, arbitrary method constants,
template declarations, and complete flow configurations. Invalid JSON blocks
form submission. These are usable configuration paths, not a claim of no-code
authoring for every possible domain extension.

## Live media

The adapter works with self-hosted LiveKit or LiveKit Cloud. Set all three:

```text
LIVEKIT_URL=wss://your-media-host.example
LIVEKIT_API_KEY=<server API key>
LIVEKIT_API_SECRET=<server API secret>
```

`LIVEKIT_API_URL` optionally specifies the server's administrative HTTP(S) origin
when the browser URL and internal container address differ. It is administrator
configuration, never a request parameter. The secret is never returned to the
browser. Join tokens use opaque participant identities and expire after 120
seconds; they carry no room administration or recording grant. Camera/microphone
permission is requested only when the user enables capture.

LiveKit URL/key setup follows its [token](https://docs.livekit.io/frontends/reference/tokens-grants/)
and [self-hosting](https://docs.livekit.io/transport/self-hosting/local/) contracts.
Deleting a room disconnects its participants. Access monitoring removes users
whose current case authority is lost. Short TTL does not itself terminate an
active session: provider removal is retried by the runtime. Self-hosted token
reuse is limited by TTL and repeated access monitoring; this is not instantaneous
revocation during a network partition. Provider failures are visible rather than
reported as completed removal. Recording/transcription and AR are not enabled.

## Install a site agent

Use [edge.example.json](../../../backend/deploy/lifesci/edge.example.json) and
[the systemd unit](../../../backend/deploy/lifesci/biodemo-edge.service). Install
the Python package into `/opt/biodemo/venv`, create the `biodemo-edge` service
account and place its config in `/etc/biodemo/edge.json` with permissions limited
to that account. Set its environment in `/etc/biodemo/edge.env`:

```text
BIODEMO_EDGE_SHARED_SECRET=<at least 16 characters; provision the same secret on the API>
LIFESCI_CONNECTOR_FILE_ROOT=/srv/instrument-exports
LIFESCI_CONNECTOR_ALLOWED_HOSTS=<explicit REST/MQTT/OPC UA source hosts if used>
```

Enroll its gateway ID/site and the **secret environment variable name** through
Site gateways. The shared value is provisioned separately at both ends. Agent
files use the same family/transport/options contract as Sources: file exports,
REST reads, MQTT subscriptions and secured OPC UA snapshots. No write operations
are accepted by the agent. Network acquisition uses the existing allowlists and
credential references. HTTPS is mandatory for remote uploads; loopback HTTP is
allowed for local checks. Request timestamps and HMAC signatures are checked by
the API, and enrollment can be disabled without changing plant systems.

```bash
python -m src.lifesci.edge --config /etc/biodemo/edge.json --once
python -m src.lifesci.edge --config /etc/biodemo/edge.json
```

The agent holds a process lock, persists source checkpoints and spool entries in
local SQLite, retries with bounded backoff, and stops acquisition at the configured
pending-event capacity. A wrong/missing receipt leaves the entry queued. Delivery
is at least once with idempotent server receipts; it is not a universal exactly-once
transport. Rejected source rows and upload failures appear in structured stdout.
Source queue history and disk maintenance remain operator responsibilities; the
pending cap is not a total disk-retention policy. Use host disk protection for
site evidence; the default spool is not application-encrypted.

## Process boundaries

```bash
# Existing durable mission worker, with TEMPORAL_ADDRESS configured:
python -m src.lifesci worker
# Separate checkpointed data-flow worker; explicit tenant list is required:
LIFESCI_TENANTS=demo-suite python -m src.lifesci.data_worker
```

[Compose](../../../backend/deploy/lifesci/compose.yml) and the dedicated
[Dockerfile](../../../backend/deploy/lifesci/Dockerfile) implement API, PostgreSQL,
migration job, Temporal mission worker, data worker and optional media boundaries.
Copy the adjacent `.env.example`, set distinct URL-safe owner/runtime passwords,
and run Compose with `--profile media up --build` for a local demonstration.
The migration identity creates the non-owner runtime role; API/workers use that
role. Database storage, migrations and workers share versioned domain contracts.
The site agent belongs on its authorized acquisition host, not inside the cloud
API's filesystem.

The Compose Temporal `start-dev` and LiveKit `--dev` services are development
processes. Shared deployment requires configured TLS/OIDC/network policy, approved
image digests, production orchestration/media service configuration, backups and
intended-use qualification. No external infrastructure was deployed by this change.

## Verification evidence

`test_complete_workflows.py` exercises the cross-domain HTTP journeys, scoped
partner sign-in and revocation, independent result review/release, transfer
revision invalidation, durable edge recovery after a lost server ACK, queued
worker execution, media grants/removal, and idempotent synthetic setup. The flow
tests cover a source quarantined during computation as well as restart recovery.
Existing protocol tests exercise real Paho/OPC UA clients against local servers.

Browser checks against an isolated synthetic API created a recipe, collected a
sample, allocated aliquots, prepared a transfer and enrolled a gateway. Against
LiveKit server v1.13.10, a browser joined with capture off, explicitly published a
synthetic camera track, and a second SDK peer received video. Ending the room
disconnected the second peer and removed the preview. These are local POC checks,
not measured WAN performance, physical-device qualification or a compliance claim.
Compose configuration was validated; a complete production deployment was not run.
