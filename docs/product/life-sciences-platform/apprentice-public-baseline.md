# Apprentice public baseline and architecture evidence

Researched 2026-10-24 for the internal proof of concept. This is a source-backed
functional baseline, not a claim that BioDemo reproduces Apprentice's private
implementation, production behavior, validation, or certifications. Public source
availability is distinct from permission to reuse code: no external code was
copied during this research. Existing capability acceptance evidence remains in
[the checklist](capability-checklist.md).

## Scope and governing decision

The job is to let manufacturing, lab, quality, MSAT, engineering and partner teams
exercise connected workflows in a baseline they can extend. The requested suite
includes native execution as well as coordination across existing systems.
Native record ownership must stay explicit; the request to build a baseline does
not silently migrate any customer's official records. This follows
[ADR 0001](../../adr/0001-record-ownership-and-native-execution.md).

For the proof of concept, exposing existing services through authenticated APIs
and purposeful interfaces is the simple alternative. Replacing persistence,
orchestration and deployment with a guessed microservice stack is the ambitious
alternative; public evidence does not justify that replacement. Retaining shared
identity, evidence, actions and transactions reduces setup and adoption effort,
makes provenance inspectable, and preserves reviewable next steps. The trade-off
is that resemblance to Apprentice's internal deployment remains unestablished.
Measure task completion, time to first executed synthetic run, setup steps,
review effort, evidence coverage and recovery after interruption; no performance
or effort improvements have yet been measured for this expansion.

## Offering-to-code map

The code column describes existing services inspected during research, not a
fresh execution test. A service method alone does not establish a usable product.

| Offering and public behavior | Existing BioDemo implementation | Exposure or remaining boundary |
| --- | --- | --- |
| Life sciences across clinical, commercial and network contexts; role-oriented assistance, SOP guidance, drift, batch comparison and shift summaries. [Life sciences](https://www.apprentice.io/industries/life-sciences) | `roles.py`, `quality.py`, `science.py`, `missions.py`, `runtime.py`, gateway and connectors | Existing connected workspace emphasizes missions and proposals; explicit suite workspaces and complete user journeys still need verification. |
| Configured repeatable workflows, reviewable manufacturing documents, event/schedule/file triggers and integration across manufacturing systems. [A1](https://www.apprentice.io/product/a1-agent) | Missions, obligations, triggers, artifact generation, qualified model routes, approval-controlled actions | Do not equate a role label with a separate autonomous service. Routes need recorded evaluation; actual external delivery needs configuration. |
| Parameterized recipe authoring, dependency/branch/parallel rules, run changes, N/A and redlining, guarded capture and review by exception. [MES](https://www.apprentice.io/product/manufacturing-execution-system) | `procedures.py`: drafts, validation, previews, approval-bound publication, instances, amendments and site variants. `execution.py`: values, calculations, resources, signatures, EBR and exception review | Dedicated recipe designer and execution HTTP/UI paths are the largest immediate usability gap. Native ownership and intended-use qualification remain prerequisites for official execution. |
| Methods with calculations/limits, samples, plates, custody and site variants. [LES](https://www.apprentice.io/product/laboratory-execution-system) | `lab.py`: methods/runs, instruments/readiness, samples/aliquots, plate positions, custody, results/review/release/invalidation | Dedicated method, sample, plate and result workflows need API/UI exposure. Instrument-specific qualification is separate. |
| Golden templates, contextual transfer packages, recipient readiness, controlled sponsor/partner review and lifecycle oversight. [CMN](https://www.apprentice.io/product/connected-manufacturing-network) | `network.py`: distribution/acknowledgment, transfer checklists and approvals, partner grants/review/export/revocation, readiness and scheduling | Provide receiving-site and partner journeys; receipt of a package must not imply readiness or authorization to manufacture. |
| Scientific acquisition and analysis, including curve fitting, qPCR, chromatography, process and equipment analysis. [Ganymede offering](https://www.apprentice.io/product/ganymede) | `science.py`, scientific task adapters, evidence lineage and source connectors | Existing calculations do not establish parity with instrument formats, notebook applications, scientific models or validated analytical workflows. |
| Remote video, annotations, transcription and device access with enterprise controls. [Remote collaboration](https://www.apprentice.io/product/virtual-remote-collaboration) | `collab.py`: session/participant/consent lifecycle, provider boundary, external expert grants, annotations and transcript review | `FakeMediaProvider` is a fixture; no real conferencing/media provider integration or headset application is demonstrated by it. |
| Configurable ingestion, public API, event subscriptions and ERP exchanges. [Integrations](https://www.apprentice.io/platform/integrations) | `connectors.py`, `integrations.py`, evidence revisions, cursors/outbox, approval-bound REST write-back, Sources setup UI | Family transports are not qualified vendor integrations. A visual mapping editor, external subscriptions and per-vendor contracts need acceptance evidence. |
| SSO, access controls, auditability, human control of GMP actions, qualification/support. [Security](https://www.apprentice.io/platform/security-compliance) | Identity/OIDC, scoped permissions, signatures, audit/revisions, action preflight, `assurance.py` export/retention/requirements/test/deployment/incident services | Controls and test scaffolding do not transfer Apprentice's certifications or establish regulatory compliance. Assurance administration needs product/API exposure. |

At inspection, `api.py` exposes evidence, generic record reads, proposals,
missions/obligations, reasoning tasks/events and connectors. It does not expose
dedicated operations for most manufacturing, lab, network, collaboration,
scientific or assurance service methods. The typed frontend client mirrors that
narrower surface. Reusing service boundaries is a concrete integration task,
whereas describing all services as a completed suite would overstate the result.

## Verified public architecture material

There is useful technical documentation, especially for Ganymede. It establishes
observable components and contracts; it does not prove that Tempo MES, LES and
A1 share the same underlying implementation.

| First-party source | What it establishes | What it does not establish |
| --- | --- | --- |
| [Ganymede concepts](https://docs.ganymede.bio/app/intro/Concepts) | Flows comprise dependency-ordered Nodes; configurable Nodes use Python/SQL templates. Saves store code/configuration in Git and update cloud orchestration. A Gateway on a host manages Connections instantiated from Agent Templates. | Workflow engine vendor, data store schema, service topology or whole-suite internals. |
| [Reference architectures](https://docs.ganymede.bio/app/intro/ReferenceArchitectures) | Capture/contextualize/process/deliver patterns around ELN/LIMS; installable instrument-side services, event processing and browser file watching are alternative acquisition paths. It describes restart and identity limitations. | Mandatory production deployment topology; these are explicitly example integration architectures. |
| [Welcome/components](https://docs.ganymede.bio/) | Shared pipelines, versioned runtimes, notebook-developed analysis applications, file tags, tables, dashboards and environment administration are product concepts. | Implementation language or storage engine for every component. |
| [API setup](https://docs.ganymede.bio/app/configuration/APISetup) | REST access using environment-managed API keys passed in an `api-key` header. | Permission to call a customer environment or access to private endpoints/data. |
| [Self-managed repository](https://docs.ganymede.bio/app/configuration/SelfManagedRepo) | Customer-owned flow source, environment-specific configuration and GitHub Actions for pulling/deploying flow code. | Full platform source code or an invitation to deploy automatically. |
| [Apprentice Navigator](https://navigator.apprentice.io/) and [index](https://navigator.apprentice.io/llms.txt) | Official package documentation entry points; full knowledge base requires login. API developer information is obtained through the delivery lead. | Public availability of complete Tempo API schemas or internal architecture. |

## Public GitHub provenance

The Ganymede documentation itself links these repositories, providing a stronger
provenance chain than a similar GitHub organization name or search result:

- [Documentation source](https://github.com/Ganymede-Bio/website-docusaurus):
  documentation repository, not the runtime platform source.
- [Self-managed flow repository template](https://github.com/Ganymede-Bio/self-managed-repo-template):
  workflow template for customer-managed flow code, not a full platform.
- [Flow commit action](https://github.com/Ganymede-Bio/flow-commit-action):
  environment-specific change packaging and authenticated API submission.
- [Flow pull action](https://github.com/Ganymede-Bio/flow-pull-action):
  signed-URL ZIP retrieval, optional single-flow selection and returned HEAD SHA;
  its documentation recommends passing the pulled SHA on deployment so stale
  changes produce a conflict rather than overwrite newer work.

Do not mistake Seldon's Tempo MLOps or HEPonHPC's Apprentice approximation library
for Apprentice's manufacturing implementation. No verified public repository
containing the full Tempo MES/LES/A1 runtime was identified in this search.

## Architecture implications for this baseline

The following are BioDemo design choices inferred from the public contracts:

1. Keep execution procedures distinct from data-processing flows: both can have
   dependencies, but a data transform must not acquire manufacturing authority.
2. Represent flow definitions, runtime/operator versions, input references,
   per-node results, retries and failures durably; pin published versions and
   require conflict checks when editing or importing definitions.
3. Put site acquisition behind an explicit host/connection boundary so local
   file and protocol access does not assume the cloud API shares instrument disk
   or network access. A local connector is not yet an installable edge agent.
4. Expose the existing suite modules with explicit validated request contracts,
   service authorization, audit and idempotency; avoid a public arbitrary-method
   invocation endpoint as a shortcut.
5. Keep models, scientific operators, connectors, media providers and scheduler
   adapters replaceable. A real provider should be identifiable in status and
   failures, and fixture behavior must be labeled.

An exact private architecture match requires the team's service/deployment
diagrams, API schemas, source repositories and intended baseline release. Public
evidence supports implementing these behaviors now; it does not support claiming
full feature parity, replacing the existing database with an inferred vendor
choice, or treating generated drafts as approved records.
