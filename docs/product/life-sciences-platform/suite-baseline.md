# Suite proof-of-concept baseline

This expansion makes existing domain implementations usable through a shared
HTTP API and a connected workspace. It also adds versioned data-processing
flows. The [workflow completion guide](workflow-completion.md) covers the later
designer, laboratory, transfer, media and gateway expansion. Its reference is the
[public offering and architecture research](apprentice-public-baseline.md),
not private Apprentice source code. No external implementation was copied.

## Architecture and trade-offs

The job is to give manufacturing, laboratory, quality and process teams a baseline
they can exercise and extend without re-entering evidence or bypassing approvals.
The simple alternative composes existing domain services, identity, revisions,
evidence, transactions and task gateway. A more ambitious alternative would split
the suite into independently deployed services and replace persistence and
orchestration. Public documentation does not establish Apprentice's private
topology, and that replacement would introduce migrations and distributed
transactions without demonstrating a benefit for this proof of concept.

The chosen architecture retains the transactional composition root and adds
explicit suite APIs. Each domain service stays separate; transport request models
reject unknown fields. Consequential commands retain service-level ownership,
qualification and human authorization checks. Shared services make starting and
adopting the baseline easier; source manifests and versioned review make it
inspectable; the execution and quality APIs connect work to next steps. The
trade-off is one deployment boundary rather than independently scaled services,
plus intentionally limited first-pass editing interfaces.

The data-flow service follows the dependency/version patterns documented by
[Ganymede](https://docs.ganymede.bio/app/intro/Concepts). It is our interpreter over
existing gateway task kinds. It does not reproduce their engine, execute arbitrary
Python/SQL or infer that Ganymede and Tempo share a private architecture. The
separate site gateway is implemented in `edge.py`.

## Try it

Start the backend and frontend using [the implementation guide](implementation.md).
Open `/app?view=suite`, choose **Connect to server**, and enter your configured
tenant/person. The **Manufacturing suite** navigation entry exposes eight areas.
No seed or ownership configuration is changed automatically by this feature.

1. **Procedures:** author recipes, work instructions or measured lab
   methods. Preview, save a draft and submit it. A separate authorized reviewer
   decides in Actions; publication checks the approved content and definition.
   The underlying service supports branches, parallel rules and site variants;
   the designer exposes dependencies, parallel groups, branches, calculations,
   signatures, templates, site variants and revision-aware editing.
2. **Manufacturing:** create a native batch, instantiate an effective procedure,
   start execution, capture step values and inspect the batch record. Units,
   limits, dependencies and native ownership remain domain checks. Signature
   steps have HTTP and explicitly labelled local POC signing controls. Resource
   selection, N/A, exception disposition and controlled amendments are exposed.
   The local confirmation control does not simulate production SSO reauthentication.
3. **Laboratory:** register samples against a batch, capture results and inspect
   custody. The Laboratory screen also covers instruments, method runs,
   aliquots, plates, custody transfers, independent review/release and invalidation.
4. **Quality:** open a case and assemble its existing source-linked review
   package. HTTP also supports deviation, CAPA and report drafts. Empty or
   incomplete cases retain evidence gaps; package creation is not QA approval.
5. **Site network:** inspect visible batches, instances, samples and cases.
   Transfer creation validates procedure references; recipient readiness has a
   dedicated API. Transfers and partners now provides package revisions,
   receipt/readiness/approval, expiring shares, membership, feedback and revocation.
6. **Data flows:** configure dependency-ordered gateway tasks, prepare a run,
   execute/resume it and inspect results. The supplied OEE example is synthetic.
   Literal inputs are captured as user-submitted configuration evidence, not
   labeled as production acquisition. External source references are accepted
   through the API and checked before and after processing.
7. **Remote collaboration:** configured LiveKit rooms with explicit camera,
   microphone and screen-share controls, case-linked chat and drawings.
8. **Site gateways:** enrollment, receipt status, disabling and a configuration
   template for the installable outbound-only acquisition agent.

## HTTP surface

Interactive request schemas are available at `/v1/docs` in development, and
`/v1/openapi.json`. Existing mission, connector, evidence and approval routes remain
available. Explicit new route groups are registered by `suite_api.py`:

| Prefix | Operations |
| --- | --- |
| `/v1/procedures` | Preview, create/update draft, submit, publish, read effective revision |
| `/v1/manufacturing` | Create batch/instance, start, capture/sign step, EBR, exception review, release request |
| `/v1/laboratory` | Samples/custody/results, method runs/steps, plate assignment, result review/release |
| `/v1/quality` | Cases, review packages, artifact drafts |
| `/v1/network` | Scoped site overview, transfer packages, receiving-site readiness |
| `/v1/intelligence` | Save flows with optimistic revision checks, prepare pinned runs, resume |
| `/v1/assurance` | Requirements, submitted JUnit reports, qualification traces; restricted to tenant-wide configuration authority |
| `/v1/collaboration` | Configured media providers, session creation, consent, join/end |

LiveKit is a configurable real media provider. Without configured URL/key/secret,
availability remains false. The collaboration screen joins rooms and enables
media capture only on explicit input. Recording, transcription and AR are not
represented as implemented by this integration. See [setup and verification](workflow-completion.md).

New suite commands that support replay store their idempotency receipt in the
same transaction as their domain changes. Authentication assertions are not
stored in replay receipts. Data-flow results checkpoint per node; completed
nodes survive process restart and are skipped on resume. A blocked node stops
downstream work. Runs pin their definition, and corrections/quarantine invalidate
dependent results. Concurrent flow coordinators use leases and fencing tokens.
Execution is sequential with up to 50 nodes, either directly or through a
separate persisted data worker. Git synchronization, parallel node scheduling
and a code sandbox remain separate work. A crash before a computation checkpoint can
repeat computation; flows have no manufacturing command interface.

## Evidence and remaining work

Acceptance checks include an HTTP recipe publication/execution journey, sample
custody/results, site isolation, invalid/stale revisions, blocked model routes,
dependency validation, restart recovery, quarantine propagation, and unavailable
media providers. JUnit upload is explicitly user-submitted evidence; it is not
independent verification of the claimed build or environment.

The first browser checks created/submitted a procedure and completed the
synthetic OEE flow against an isolated in-memory tenant. These establish local
functionality, not production qualification. No live customer systems or messages
were used. Observable follow-up measures should include setup steps, time to the
first useful synthetic run, reviewer effort, source coverage and recovery after
interruption; no improvement measurements have been established yet.

The named designer, laboratory, transfer, collaboration and edge workflows now
have POC implementations and acceptance evidence. Vendor/device qualification,
production identity/reauthentication, load/recovery exercises and intended-use
qualification remain deployment work. No private Apprentice architecture match
or regulatory qualification is implied.
