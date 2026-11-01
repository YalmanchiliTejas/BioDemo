# Extensive manufacturing-agent benchmark campaign

**Current user constraint: maximum $50 total incremental spend.** The active
pre-demo design is [the $50 benchmark plan](benchmark-budget-50.md). The 4,008-run
campaign below is an unfunded expansion proposal, not the current execution target
or spending authorization. No paid run may rely on its earlier cost envelope.

Status: proposed campaign and execution design, not executed or independently
approved. This supersedes the suggestion to restrict evaluation to small local
fixtures. It does not replace the existing evaluation specification or scorecards.

The job is to establish whether the deployed manufacturing agent completes useful,
verifiable work across unfamiliar evidence, scientific tasks, long-running work,
and operational failures. Resource limits determine where jobs execute, not how
much evidence they are allowed to inspect. The developer laptop is a control and
reporting client, not the benchmark compute host.

## Experimental scope

Proposed authoring targets, subject to a source/label inventory and independent
review before freezing:

| Competency | Target base cases | Required evidence and checks |
|---|---:|---|
| Raw ingestion and reconciliation | 40 | Complete workbook/document packages, units, clocks, joins, duplicates, coverage and original-source coordinates |
| Process and batch comparison | 40 | Authentic measured trajectories, reproducible numerical references, confounding and counterevidence |
| Deviation investigation | 40 | Time-valid source packages, affected-scope checks where labels exist, alternative explanations, negative controls and reviewer-scored follow-up |
| Sequential evidence and recovery | 30 | Multi-step sessions, corrected results, contradictory revisions, tool outages, restarts, checkpoint recovery and changed conclusions |
| Transfer and intervention reasoning | 30 | Existing simulator/physical-model endpoints, blind evaluator replay, constraint violations, identifiability and useful abstention |
| Permissions and action boundaries | 20 | Tenant/cutoff enforcement, document prompt injection, denied retrieval, approval/execution separation and duplicate-action prevention |

The target is 200 separately specified base tasks, not a claim that 200 independent
reviewed cases exist now. Existing CHO/Fresenius objectives, physical-model tasks,
and synthetic scaling corpora are starting material. The current default suite's
eleven objectives and filename variants do not fill this target. Shared batches,
experiments, scenarios and source packages must have explicit cluster identifiers.
New independent evidence and reviewed labels are required for untouched
generalization claims; generated variants cannot supply that independence.

Run all three machine methods against each frozen base task five times:
deterministic tools, single-pass AI, and the full manufacturing agent. This yields
3,000 planned base assignments if all 200 cases are admitted. Freeze an additional
100 explicit stress case/condition packages and run each method three times,
adding 900 planned assignments. Missing records, changed layouts/units, stale SOPs,
conflicting evidence and distractors must preserve task-specific answerability
labels. A stress variant is not an additional independent factory incident.

Evaluate stored 100-, 1,000-, and 10,000-document synthetic corpora separately:
four frozen questions, three methods, three repeats at each scale gives 108 planned
assignments. Verify actual corpus sizes and eligible questions before admitting
them. Synthetic scaling measures capacity, not real-factory generalization.

The resulting planning target is 4,008 machine assignments, not a power calculation
or measured result. Case availability, annotation validity and compute/inference
budgets must be resolved before this can become a frozen execution schedule.
Repeated runs measure stability; they do not multiply the independent sample size.

## Comparisons and qualification

Use the same authorized evidence, objective, cutoff and predeclared acceptance
criteria within each comparison. Match model/provider assignments for the AI arms;
record prompts, reasoning settings, tools, dependencies, image digest, parser/OCR
versions and budgets. Retain a run of the exact demo configuration. Any altered
agent settings are separate experimental conditions, not substituted product scores.

Raw-input end-to-end results are primary. Reusing identical parsed evidence is a
separate diagnostic arm to isolate reasoning from ingestion; it cannot stand in
for raw-input performance. OCR remains in scope. Install and pin its weights on
the designated remote worker/image and test extraction quality, time and cost;
do not silently omit scans, substitute already-clean text or redownload model
weights per assignment.

Independent reviewers approve rubrics and objective labels before evaluated runs.
Keep evaluator references on the trusted evaluator only. Qualify calculations,
material claims, supporting/counterevidence, scoped recommendations and uncertainty.
Unsupported root-cause certainty, fabricated citations, unauthorized access and
unauthorized consequential actions are failures. Preserve failed, timed-out and
out-of-memory attempts in denominators. Infrastructure retries link to the original
attempt and never replace it in the record.

Conduct an observed manual-versus-assisted study on a preselected stratified subset
of at least 20 base tasks if qualified participants are available. Count every
participant's setup, preparation, investigation, verification, correction and
coordination time. Counterbalance assignments and avoid within-person repeated-case
learning. The sample is an exploratory planning target; general labor-savings claims
need an appropriate study design and sufficient independent observations.

Report by dataset, competency, condition and source/scenario cluster. Show qualified
case rate, critical-evidence misses, false positives, numerical correctness, review
burden, action usefulness, complete human effort, completion/timeout/OOM rates,
latency distribution, peak RAM, peak disk and inference cost. Include intervals
using an analysis appropriate to clustered cases; do not treat five repetitions
of one case as five independent manufacturing cases. No universal accuracy average.

## Remote execution

Reuse the private DagsHub artifact store, case manifests, `run_case`, source checks,
quality scorer, human-work ledger and the configured hosted model provider. The
existing storage offloader still executes on its caller's computer: it does not
provide remote compute. The current scored isolation runner uses macOS
`sandbox-exec`; a Linux container adapter is an implementation prerequisite.
The pilot cloud application's 2-GiB agent limit is not a measured allocation for
this benchmark and must not be copied as its capacity plan.

Start capacity planning with one dedicated remote host with 8 vCPUs, 64 GiB RAM
and approximately 200 GiB SSD. These are proposed starting resources, not validated
sizing. Initially admit at most four 2-vCPU/12-GiB workers, leaving host/evaluator
headroom. Profile representative full-size cases in every family, then adjust
worker allocations and concurrency. Large OCR/GPU workloads use a separate worker
class if measured needs justify it; do not require a GPU host for every agent run.

The trusted host downloads/version-checks one source package per active assignment
and stages only authorized evidence into the agent container. The container runs
as non-root with a read-only image and input mount, bounded writable scratch,
explicit memory/CPU/process/disk limits, no host socket, no evaluator mount and no
artifact-store/admin credentials. Model traffic uses an allowlisted egress proxy.
Probe the actual denial boundaries, including descendants, before accepting scores.

The worker image contains Linux-compatible Prime, Python/Node dependencies and
explicitly pinned document tooling. Build it remotely; do not upload macOS
`node_modules`, local virtual environments, credentials, full source evidence,
global memories or hidden references into the agent image. Keep evidence-generator
and evaluator code outside the image available to the agent.

Use durable assignment IDs, leases/heartbeats, explicit termination status and
reconciliation after scheduler restart. Checkpoint persistent trials by mission
and evidence version. Reuse the existing persistent trial semantics rather than
independently reimplementing state restoration. The current sequential suite needs
remote dispatch/claiming; launching multiple copies against its single lock is
not a parallel scheduler.

Upload complete outputs, traces, usage, failure receipts and resource measurements
after each attempt. Verify remote bytes before deleting scratch; failed uploads
retain the sole copy under a bounded quarantine and stop admission before disk
exhaustion. Compress/upload incrementally rather than holding the campaign in RAM.
Use a bounded remote model cache shared read-only by compatible jobs. The laptop
retains only manifests, progress and small summaries, with no automatic dataset or
OCR-weight downloads. Set a campaign deadline and budget admission policy; destroy
temporary compute only after retained results have been verified.

## Cost envelope and launch prerequisites

DigitalOcean's public regular memory-optimized 8-vCPU/64-GiB/200-GiB plan is listed
at $0.50/hour, inspected 2026-10-31:
https://www.digitalocean.com/pricing/droplets

At that rate, one host costs $12 for 24 hours or $36 for 72 hours. These are only
VM arithmetic examples, not campaign-duration or all-in cost estimates. Storage,
transfer, hosted model inference, optional OCR/GPU service, annotation and human
review are additional. Regional availability, account credits and current account
rates must be checked before provisioning.

Estimate total inference from actual full-size calibration receipts, including
child-agent usage and failures. The existing zero-price SDK ledger is not proof
of free inference. With average inference cost C per assignment, 4,008 assignments
would cost 4,008*C before other services. Apply an explicit approved total budget,
reserve worst-case cost for in-flight work, and stop dispatch before exhausting it.
Provider spend limits are needed where telemetry/billing is delayed.

Implementation prerequisites: Linux agent isolation adapter; reproducible remote
runtime image including OCR; durable dispatch and artifact retention; resource
telemetry and admission limits; independently reviewed case catalogue and rubrics;
verified model billing/capabilities; cloud access, region and approved spend cap.
No paid infrastructure or inference campaign was launched by writing this document.

## Product constraints and alternatives

Easy to Start: minimize manufacturer preparation while preserving unfamiliar raw
inputs. Easy to Trust: retain source lineage, held-out references, independent
review and complete failures. Easy to Act: evaluate useful recommendations,
authorization and outcome follow-up. Easy to Adopt: keep original systems of record
and measure setup, integration/training and recurring human effort.

A single remote host with bounded containers is the simpler execution choice.
An autoscaled pool and specialized OCR/GPU workers can shorten the full campaign
at greater operational and cost-control complexity. Start with the former while
preserving the complete campaign scope; scale the pool when measured throughput
justifies it. Running the full campaign on the laptop risks another resource
incident and is not the selected execution design.
