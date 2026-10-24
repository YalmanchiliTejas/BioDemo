# Assessment records

Date: 2026-10-23. Status: engineering draft.

This file holds one reviewed assessment record for each of the 12 `assessment` rows in the [capability checklist](capability-checklist.md). Each record satisfies its row's acceptance text by recording the decision taken, the evidence needed before any claim of our own, and the open questions. Assessing a vendor statement means deciding what evidence is required or rejecting an unsupported assumption. It does not mean building a marketing claim. The vendor statements come from the [source inventory](../../research/apprentice-life-sciences-source-inventory.md) and are cited by feature ID. Governing direction is in [Main_Culture_andETHOS.md](../../../Main_Culture_andETHOS.md); engineering choices are in the [decision log](decision-log.md); verification scope is in [delivery and verification](delivery-and-verification.md).

None of these records is a product claim. Vendor quantitative claims are marked "unverified — not adopted as a product claim". Checklist I and V states remain false for 11 of the 12 rows; LS-044 is marked implemented and verified (see its record). That status does not change its decision.

**Implementation home:** all modules exist under `backend/src/lifesci/`, including `integrations.py`, `procedures.py`, `execution.py`, `lab.py`, `quality.py`, `network.py`, `collab.py`, `missions.py` and `assurance.py`, plus `gateway/`. Status for each capability (implemented, verified, and any partial gap) is in the [capability checklist](capability-checklist.csv). "Verified" means automated tests in a development environment, not customer qualification.

---

## LS-003 — Modality flexibility assessment

**Vendor statement:** "Adaptable workflows and templates support different therapy types, batch sizes, and process changes." (LS03) — **claim**. Related: parameterized templates and mid-run changes (MES02) and central parameterized templates (CMN02) — **documented**, but not tested for any modality.

**Our decision**
- We will assert: parameterized templates, site adaptations and branches/parallel steps are implemented and pass automated acceptance tests (LS-006, LS-007, LS-016); they are not validated for any customer's modality or process.
- We will not assert support for any therapy type, batch-size range or process-change class. Unverified — not adopted as a product claim.
- Modality-specific support requires a qualified template or method package per modality (delivery Phase 5).

**Evidence required before any claim**
- Customer requirements per modality: identity rules, batch-size range, allowed process-change classes.
- For each supported variant: an approved template instance executed in an authorized test environment against the LS-007 scenarios, with a traceability row.
- QA/MSAT review naming modalities, batch-size range and sites covered, with date and reviewer.

**Known boundaries**
- Supported variants (design scope):

| Variant | Basis | Status |
|---|---|---|
| Parameterized template (one procedure, several products) | MES02, LS-007 | implemented and verified (tests) |
| Site adaptation with allowed-parameter validation | CMN02, LS-016 | implemented and verified (tests) |
| Branches and parallel steps | MES01, LS-006 | implemented and verified (tests) |
| Not-applicable steps with recorded reason | MES02, LS-007 | implemented and verified (tests) |

- Unresolved modality constraints (not modeled):
  - Cell therapy: chain of identity (donor-to-patient linkage, custody across lab and manufacturing). Needs customer input and LS-012 custody.
  - Individualized batches: batch-of-one sizing and identity-bound product. Needs customer input.
  - mRNA: process-specific critical parameters and handling constraints. Needs customer input.
  - Critical quality attributes and yield definition are customer inputs (delivery, operational readiness).
- No modality-specific code exists. `procedures.py` is modality-neutral; the variant mechanisms above are generic.

**Open questions**
- Which therapy types, batch sizes and process changes are needed first?
- For cell therapy and individualized batches: which system is authoritative for chain of identity?
- For mRNA: which process parameters are critical?
- Vendor: which modalities have reference templates in customer deployments, and what does "adaptable" cover?

**Review status:** Reviewed by: engineering (draft) — requires product/QA sign-off. Date: 2026-10-23.

---

## LS-010 — Deployment timing claim assessment

**Vendor statement:** "90 days" to go live and six sites in nine months (MES05) — **claim**. Related: multi-site activation and QMS integration (MES04) — **documented**. The services page also states "manufacture in 90 days or less" (SVC03) — **claim**.

**Our decision**
- We will not state a go-live duration or site-rollout duration as a product claim. Unverified — not adopted as a product claim.
- Any estimate we give must state scope, assumptions, evidence, uncertainty and customer dependencies (checklist row). Delivery doc: rollout duration is not promised.

**Evidence required before any claim**
- Reference deployment measurements per phase (align/scope, configure, validate, launch/hypercare, per SVC01), with start and end dates and a stated sample of completed deployments.
- Scope of each measured deployment: site count, process, modality, device set, connectors.
- Customer dependency log (approvals, IT access, source readiness, validation staffing) and its effect on duration.
- Stated uncertainty range and the date the evidence was collected.

**Known boundaries**
- No deployment has been performed. There are no measured durations.
- Site rollout with QMS reconciliation (LS-009, `network.py`) is implemented and verified against a caller-supplied QMS snapshot; no live QMS was exercised. Deployment plans (LS-048, `assurance.py`) are implemented; no deployment has been run.
- Implementation home for rollout tooling: `backend/src/lifesci/network.py` and `backend/src/lifesci/assurance.py`.

**Open questions**
- Vendor: what does "go live" mean (first batch, validated, or all sites)? Which sites, processes and modalities were in the reference deployments? What was validation scope and duration?
- Customer: what validation and QMS approvals constrain go-live timing at our target sites?

**Review status:** Reviewed by: engineering (draft) — requires product/QA sign-off. Date: 2026-10-23.

---

## LS-020 — Transfer-speed claim assessment

**Vendor statement:** "One-click" transfer and months-to-hours transfer reduction (CMN06) — **claim**. Related: transfer package contents of batch templates, master data, resource mapping and audit trail (CMN03) — **documented**.

**Our decision**
- We will not claim one-click transfer, or any reduction in transfer time or effort. Unverified — not adopted as a product claim.
- Transfer readiness is defined by the recipient checklist, not by sending a package (LS-017). Transmitting files is not completing tech transfer.

**Evidence required before any claim**
- A defined transfer scenario: one batch template, stated number of mappings, stated number of recipient sites.
- Baseline: the customer's current manual transfer measured on the same scenario, same reviewers, same period.
- Measured effort per transfer: person-hours and elapsed time from package creation to recipient checklist cleared.
- Sample: at least 5 transfers across at least 2 recipient sites (proposed; to be agreed with QA before measurement), with the distribution reported, not only the mean.
- Recorded missing-mapping and rework counts, since fast transfer that leaves gaps is not an improvement.

**Known boundaries**
- Transfer packages and the recipient checklist (LS-017) are implemented in `network.py` and verified by tests. No transfer effort has been measured.
- Transfer packages will contain versioned procedures, parameters, mappings, qualifications, open gaps and approvals (architecture, network section).

**Open questions**
- Vendor: what is "one click" measured against, and what does a transfer include (mappings, qualifications, approvals)?
- Customer: which transfer types occur most often, and what does a transfer cost today in person-hours?

**Review status:** Reviewed by: engineering (draft) — requires product/QA sign-off. Date: 2026-10-23.

---

## LS-026 — Availability and model claim assessment

**Vendor statement:** "24/7," "fault-tolerant," "always available" and model-performance comparisons (A1-06) — **claim**; no independent measurement reviewed. Human final decisions for GMP-related actions (A1-05) — **documented**. Evaluation protocol, failure behavior and customer-specific availability (A1-07) — **unknown**.

**Our decision**
- We will not claim 24/7, fault-tolerant, always-available, or any model-quality comparison. Unverified — not adopted as a product claim.
- Availability of required controls is designed separately (LS-080): with all models down, deterministic authorization, required alerts and record retrieval continue, and agent work reports blocked progress.
- Any quality claim is tied to task-level evaluation (LS-067), not to a vendor benchmark.

**Evidence required before any claim**
- Availability: measured success of required paths over a stated window (proposed minimum: 90 days of production-like monitoring) in a named environment (topology, region, provider, model profile versions from the registry), with excluded periods and incidents reported.
- Model quality: labeled task sets per task kind, repeated trials, thresholds set before evaluation, false-negative and unsupported-claim rates reported alongside average accuracy (delivery, quality section).
- Evaluation record and impact scope for each activated profile (registry `qualify` requirement).
- Provider availability is an external input; measure gateway-level outcomes, not provider marketing.

**Known boundaries**
- Gateway routing, retries, failover, budgets and statuses are described in LS-027 (code in [gateway](../../../backend/src/lifesci/gateway/gateway.py)).
- The default registry qualifies no profile for any task. No evaluation records are attached. No availability measurements exist.
- Provider outage behavior for required controls (LS-080) is implemented in `gateway.py` and verified by tests. No availability measurements exist.

**Open questions**
- Vendor: what measured window, environment and definition support "24/7" and "fault-tolerant"? Which evaluation protocol produced the model comparisons?
- Customer: what availability and response targets apply to each control class, and which are critical enough to need redundancy?

**Review status:** Reviewed by: engineering (draft) — requires product/QA sign-off. Date: 2026-10-23.

---

## LS-027 — Unpublished AI design assessment

**Vendor statement:** Model internals, grounding/retrieval design, evaluation protocol, failure behavior, approval granularity and customer-specific availability are not established by public pages (A1-07) — **unknown**. We do not assume any vendor design.

**Our decision**
- Our gateway behavior is specified by this record, and it governs our implementation. Vendor internals are unknown and are not assumed or compared.
- Model confidence is not a probability of correctness. Calibrated risk and authority are enforced outside the model (decision log D13, D14).

**Evidence required before any claim**
- Versioned design record: this section, plus the gateway code version and registry version recorded on each run.
- Executed scenarios for provider timeout, rate limit, malformed output and budget depletion (delivery V09), plus stale-basis and invalid-citation cases.
- Eval records per task kind before any model route is active.

**Known boundaries (observable gateway behavior, from `backend/src/lifesci/gateway/`)**
- **Deterministic first:** task kinds whose policy is deterministic run registered code (route tier C0). No model is called.
- **Eval-gated routing:** a model profile is used for a task kind only with a passing, threshold-checked qualification and impact scope. With no qualified route, the call returns `unresolved` or `blocked` (the dev-only unqualified route is flagged and marks results for review). Routing picks the cheapest qualified route at or above the policy floor.
- **Risk is policy-owned:** model-suggested risk is recorded and ignored. High-ambiguity consequential tasks prefer the frontier qualified route.
- **Grounding:** input evidence references are access-checked before the call. Output must cite only supplied source IDs; citing others fails validation.
- **Schema validation:** required keys and types come from policy. Invalid JSON fails. A `confidence_probability` field is rejected.
- **Failure:** retryable provider errors retry up to 2 times. After that the profile is marked unavailable and the next qualified profile is tried.
- **One repair:** a validation failure gets one targeted repair on the same model.
- **One escalation:** if repair fails and policy allows, one escalation to the next profile in the chain.
- **Terminal statuses:** `completed`; `unresolved` (validation failed after repair and escalation); `blocked` (no attempt succeeded, e.g. provider outage); `budget_exhausted` (returns attempts and issues, with progress in the run trace); `stale_basis` (an input changed during execution, so output is withheld); `denied`.
- **Budgets:** tenant, mission and run scopes reserved all-or-nothing before each call, then settled to measured cost. Exhaustion never relaxes routing or review. Resumption after exhaustion is not yet verified.
- **Cache:** access and input freshness are rechecked on every read.
- **Outage:** deterministic (C0) routes do not call providers and continue during an outage.
- **Not established:** that outputs are correct; that the system prompt's labeling of observations, calculations and hypotheses is followed; that budget resumption works end to end. The LS-027 row has no linked test evidence (checklist I and V false). The gateway behaviors above are covered by tests linked to LS-055, LS-057, LS-058, LS-067, LS-068 and LS-080.

**Open questions**
- Customer: what is the approval granularity (per output, per batch, per procedure version), and who holds it?
- Vendor: none required for this row; the design does not depend on vendor internals.

**Review status:** Reviewed by: engineering (draft) — requires product/QA sign-off. Date: 2026-10-23.

---

## LS-032 — Unpublished data-cloud interface assessment

**Vendor statement:** Deployment topology, supported connectors by version, transformation semantics, lineage detail and integration boundaries with Tempo/A1 are not specified in the product overview (GAN05) — **unknown**. Documented: capture from instruments, ELN/LIMS, OPC interfaces, PC files and historians (GAN02) — **documented**. The newsroom announces the Ganymede acquisition dated 2026-01-21 (S13); it does not establish technical integration.

**Our decision**
- We will not assume any Ganymede connector, data model, transformation or integration with other vendors' products.
- Interface boundary decision: we integrate with sources through our own versioned connector contract (LS-044) and treat any vendor data cloud as an external source with its own contract, not as an internal dependency.
- Unverified — not adopted as a product claim: any statement that the vendor's data cloud offers a particular integration.

**Evidence required before any claim**
- Written vendor responses to each unknown in GAN05, with the version and date of the response.
- A technical document or an authorized test connection for each connector we intend to use, passing the LS-004 scenarios (read, identity, version, mapping, gap).
- Written decision on integration boundaries with other vendor products, approved by the owner of the record.

**Known boundaries**
- Ingestion from generic sources (`manufacturing_data/ingest.py`) and connector catalog exist as foundations. No Ganymede-specific adapter exists.
- Implemented home: `backend/src/lifesci/integrations.py` (generic REST, file, webhook and simulated MQTT/OPC UA transports). It has no Ganymede or other vendor data-cloud adapter. Benchmark code under `backend/benchmark/integration/` is not a production authority.

**Open questions**
- Vendor: which deployment topologies are supported (cloud, on-premise, hybrid)? Which connector versions are supported? What transformations are applied to ingested data, and what lineage is retained?
- Vendor: where is the boundary between the data cloud and Tempo/A1, and who owns records?
- Customer: which instruments and historians are in scope, and who is the system of record for each?

**Review status:** Reviewed by: engineering (draft) — requires product/QA sign-off. Date: 2026-10-23.

---

## LS-036 — Authoring benefit claim assessment

**Vendor statement:** Conversion of PDFs and paper procedures "in minutes," improved accuracy and reduced errors (DWI04) — **claim**. Related: AI authoring from PDFs/paper with step guidance (DWI02) — **documented**.

**Our decision**
- We will not claim conversion time, accuracy improvement or error reduction. Unverified — not adopted as a product claim.
- Interpreted instructions require source spans, review and controlled publication before execution (decision log D16). Mandatory hand-mapping is not imposed on all users.

**Evidence required before any claim**
- A representative sample of customer procedures (proposed: at least 20 documents across at least 2 procedure families), labeled by QA with ground-truth steps before measurement.
- Baseline: time and error count for current manual authoring of the same documents, by the same reviewers.
- Measured outcomes: authoring time, reviewer correction time (reviewer effort), errors against ground truth, with confidence intervals.
- Environment and versions: model profile, prompt version, document types, reviewer qualification.
- Reported uncertainty and a comparison of correction effort, not only time to first draft.

**Known boundaries**
- Instruction authoring with revision control (LS-033) is implemented in `procedures.py` and verified by tests.
- Document-to-instruction interpretation (LS-034) is partial in `procedures.py`: text only, with source spans and review-gated publication. PDF/paper OCR is not built.

**Open questions**
- Vendor: which documents, sample sizes and reviewers support "in minutes" and the accuracy claim? What does "accuracy" measure?
- Customer: what procedure families are in scope, and what review is required before publication?

**Review status:** Reviewed by: engineering (draft) — requires product/QA sign-off. Date: 2026-10-23.

---

## LS-040 — Collaboration benefit claim assessment

**Vendor statement:** Reduced delays, travel and costs (VRC04) — **claim**; no measurements in the reviewed page. Documented: remote video, annotation tools and external-expert view with permissions and logs (VRC01–VRC03) — **documented**.

**Our decision**
- We will not claim reduced delays, travel or cost. Unverified — not adopted as a product claim.
- Remote assistance is designed with session authority, case linkage and recording controls (LS-037, LS-038, LS-039). Transports are integrated, not built (decision log D25).

**Evidence required before any claim**
- A baseline from the customer's logged incidents: time to expert availability, travel days and cost per incident, over a stated period.
- Observed sessions for the same incident types, with sample size and site mix stated.
- Outcome measures: time to resolution, repeat visits avoided, session-level permission and recording compliance.
- Reviewer effort to verify session records.

**Known boundaries**
- Collaboration code is in `backend/src/lifesci/collab.py`. Remote sessions with participant access checks and case linkage (LS-037, LS-039) are verified against a fake media provider. Annotations (LS-038) are partial, with no device testing.
- Existing auth foundation (`cloud_backend/auth.py`) covers general access, not remote-session authority.

**Open questions**
- Vendor: what baseline and sample support "reduced delays," "travel" and "costs"?
- Customer: which incident types would use remote assistance, and what do they cost today?

**Review status:** Reviewed by: engineering (draft) — requires product/QA sign-off. Date: 2026-10-23.

---

## LS-044 — Connector contract assessment

**Vendor statement:** The public overview does not enumerate a complete connector matrix, API schema or version lifecycle, throughput limits, or per-connector data ownership and error semantics (INT04) — **unknown**. Documented: no-code connection wizard and automatic shop-floor capture (INT01), public Web API and event subscription (INT02), ERP bidirectional exchange (INT03).

**Our decision**
- We will not claim a connector matrix, API version, throughput or error behavior for any vendor system. Unverified — not adopted as a product claim.
- Each connector is described by a versioned contract (below). A connector may only be listed as supported after its scenarios pass (LS-088). Otherwise it is listed as simulated or unavailable.

**Versioned connector contract (required fields)**

| Field | Meaning | Implementation (`ConnectorContract` in `backend/src/lifesci/integrations.py`) |
|---|---|---|
| system | Source system name (MES, LIMS, ERP, …) | Present: `system` |
| vendor | Product vendor and product | Present: `vendor` |
| version | Supported product version(s) | Present: `version` |
| transport | REST, webhook, MQTT, OPC UA, file | Present: `transport`, validated against the five transports |
| operations | Read events, write actions, pagination | Present: `read_operations`, `write_operations` (pagination is not a separate field) |
| auth | Auth scheme and credential owner | Partial: `auth` and `write_auth` (free text); no structured credential-owner field |
| schema version | Payload schema and field mapping version | Present: `schema_version` |
| rate limit | Documented or measured limit and backoff | Present: `rate_limit` and `limits` fields; values are declared per contract and none are measured |
| error semantics | Retryable vs. terminal errors, unknown-outcome handling | Present: `error_semantics`; values are declared per contract |
| owner | Team or system owning the record and the contract | Present: `owner` (required by `validate()`) |
| status | `supported` \| `simulated` \| `unavailable` | Present: `status`; `supported` is set only by `ConnectorMatrix.qualify` |

**Evidence required before any claim**
- Vendor documentation or an authorized test connection for each field above.
- Executed LS-004 and LS-088 scenarios per connector version, with measured limits.
- Owner sign-off on the contract.

**Known boundaries**
- `ConnectorContract` and `ConnectorMatrix` are implemented in `backend/src/lifesci/integrations.py` and verified by tests (LS-044, LS-088). The generic REST connector is qualified only against a local fake server. No vendor system or version is qualified.
- Benchmark code under `backend/benchmark/integration/` is not a production authority.

**Open questions**
- Vendor: full connector list and supported versions; API schema and version lifecycle; throughput limits; error and retry semantics; data ownership per connector.
- Customer: which systems and versions are in scope, and who owns each connection?

**Review status:** Reviewed by: engineering (draft) — requires product/QA sign-off. Date: 2026-10-23.

---

## LS-045 — Certification claim assessment

**Vendor statement:** SOC 2 Type II and ISO 27001:2022 certification, plus cGXP/21 CFR Part 11, GDPR, SSO, MFA and monitoring (SEC01) — **claim**. Certification evidence and scope were not independently checked.

**Our decision**
- We will not claim SOC 2, ISO 27001, Part 11, GDPR or any other certification or compliance status for the vendor, and we will not claim it for ourselves. Unverified — not adopted as a product claim.
- Certification is not validation. Part 11 and cGXP support require our own validation evidence (decision log D26; delivery doc, Phase 5).

**Evidence required before any claim**
- For each certification: the issuer's current document (SOC 2 Type II report with audit period; ISO 27001:2022 certificate with scope statement and certification body), checked against the deployed services.
- Scope check: named products, hosting regions and sites covered by the certificate match the deployment.
- Expiry date recorded; reviewer and check date recorded; renewal tracked.
- For Part 11 and GDPR: separate evidence (validation records, data processing terms), not certificates.

**Known boundaries**
- No certification evidence is held by this repository.
- `assurance.py` implements qualification traces and deployment plans (LS-046, LS-048). No deployment evidence packet exists (LS-047 is not implemented). Electronic signature and audit code is in `records.py` and `store.py` (LS-002), with foundations in `cloud_backend/schema.sql`.

**Open questions**
- Vendor: which products, regions and sites are inside each certificate's scope? What are the audit period and expiry dates?
- Customer: which compliance evidence does the customer require for its deployment?

**Review status:** Reviewed by: engineering (draft) — requires product/QA sign-off. Date: 2026-10-23.

---

## LS-047 — Deployment security assessment

**Vendor statement:** Tenant isolation, encryption and key management, backup and restore objectives, data residency, model data retention and certification report scope are not established by the reviewed pages (SEC03) — **unknown**.

**Our decision**
- We will not claim tenant isolation, encryption, recovery objectives, residency or retention for any deployment until the evidence packet below exists for that deployment. Unverified — not adopted as a product claim.
- Our design uses explicit role separation and row-level policies (decision log D23) and recovery by record class agreed with the customer (delivery doc, operational readiness).

**Evidence required before any claim**
- Tenant controls: results of cross-tenant and cross-site denial tests (delivery V01), with build and environment.
- Encryption: at-rest and in-transit configuration and key-management description per deployment.
- Restore: test results against RPO and RTO chosen with the customer, across records, evidence, sessions and orchestration (LS-082, V15).
- Residency: declared region for storage, compute and model providers, checked against the deployment.
- Retention: retention policy per record class, and model-provider data-retention terms, reviewed by the customer.
- Subprocessors list and review date.

**Known boundaries**
- Runtime role separation exists in `backend/src/cloud_backend/runtime_roles.sql`; backups in `backend/src/cloud_backend/backup.py`. Neither has been tested against this checklist.
- `assurance.py` provides signed scoped export and verified restore of lifesci records (LS-082, partial). Recovery objectives are not agreed and no timed restore drill exists. No deployment packet exists.

**Open questions**
- Vendor: what are tenant isolation, encryption, key management, backup objectives, residency and model retention for the hosted service?
- Customer: which RPO and RTO apply to each record class, and which regions are allowed?

**Review status:** Reviewed by: engineering (draft) — requires product/QA sign-off. Date: 2026-10-23.

---

## LS-050 — Service-timeline claim assessment

**Vendor statement:** "Manufacture in 90 days or less" and low annual upgrade burden (SVC03) — **claim**; actual scope and conditions are not specified. Documented delivery outline: align, configure, train, validate, launch and hypercare (SVC01) — **documented**.

**Our decision**
- We will not state a delivery timeline or an upgrade burden as a product claim. Unverified — not adopted as a product claim.
- Any estimate we give must expose assumptions, customer dependencies and evidence basis (checklist row). Delivery doc: no rollout duration is promised.

**Evidence required before any claim**
- Measured durations from reference deployments per SVC01 phase, with scope and sample size.
- Customer dependency list (validation staffing, IT access, approvals, source readiness) with the effect of each delay recorded.
- Upgrade effort measured across at least one controlled release (LS-049), including in-flight workflow handling.
- Stated date of evidence and uncertainty range.

**Known boundaries**
- No delivery history exists. Deployment plans (LS-048) and controlled release notices (LS-049, partial) are implemented in `assurance.py`. Support escalation, searchable guides and in-flight workflow upgrades are not built.

**Open questions**
- Vendor: what scope and conditions does "90 days or less" assume? What counts as manufacture or go-live?
- Vendor: what upgrade effort is measured, and across how many releases?
- Customer: which validation and IT dependencies apply to the target sites?

**Review status:** Reviewed by: engineering (draft) — requires product/QA sign-off. Date: 2026-10-23.
