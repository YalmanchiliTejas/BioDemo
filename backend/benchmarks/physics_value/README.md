# Physical-model value: synthetic experiment pilot

This package generates manufacturing decision datasets for the thesis discussed with the user: whether giving an agent executable physical models improves diagnosis, optimization, verified issue resolution and pre-transfer risk detection. The generator creates the environment and outcome checks. The separate `run_agents` command now executes a restricted-tool comparison through the existing Prime SDK; its results remain separate from the simulation audit.

The experiment specification belongs in GitHub Issues (`YalmanchiliTejas/BioDemo`); publication of the preceding draft remains pending because the required `gh` CLI is unavailable in this session. This README documents the executable implementation and its current limitations.

## Design decisions

The job is to give process/MSAT engineers a reproducible pilot in which an agent's decision can be checked against subsequent simulated behavior. Reuse the existing fermentation characterization calculations, freeze-drying representative-vial model and richer transient evaluator. No production service, UI replacement, model qualification or equipment writer is added.

The simple alternative is another table of prepared model calculations; it cannot isolate agent benefit. The selected implementation adds seeded cases, identical A/B inputs, bounded intervention replay and sequential measurements. The more ambitious alternative is a validated full factory simulator with human workflow trials. That requires independent plant data and prospective experiments and is not implied by this pilot.

The four governing pillars apply jointly: one command reduces setup; hashes, explicit synthetic provenance and cutoff-controlled packets support verification; scored interventions and measurement choices connect evidence to decisions; existing scientific kernels and file formats limit integration burden. Trade-offs: the pilot uses ideal assays and small action grids to stay inspectable, so it does not establish real turnaround times, model calibration, manufacturing validity or enterprise deployment readiness. Observable current measures are packet/future separation, deterministic replay, valid trajectories, intervention feasibility, numerical runtime and action-grid coverage. Engineer savings remain unmeasured.

## What is generated

Default: **24 process cases and 96 decision packets**. Each of six mechanisms has two seeded instances in each domain. These are exploratory development samples, not a statistically powered trial.

| Domain | Normal/control | Single causes | Hard cases |
| --- | --- | --- | --- |
| Oxygen supply | Normal oxygen supply | Reduced transfer, increased oxygen demand | Biased sensor, combined transfer/demand change, slow gas response |
| Freeze-drying | Normal receiving process | Increased heat transfer, increased product resistance | Biased temperature sensor, combined mechanism, low specified receiving vapor capacity |

Routine traces include Gaussian sensor noise. Source observations are generated with the nominal source process; receiving mechanisms do not contaminate source history. Source and receiving clocks are explicitly distinct.

Every case provides four tasks:

- `diagnosis`: observations available through receiving hour 6; rank plausible mechanisms and request a distinguishing measurement. A synthetic ground-truth label does not prove a unique diagnosis is identifiable.
- `optimization`: same observations and a declared finite action grid; host-side replay checks feasibility and objective regret using the richer evaluator.
- `resolution`: host-owned sequential measurement requests advance simulated time and reveal only results then available; one committed intervention is simulated and verified after its actual simulated endpoint. Late measurements and prior excursions remain failures or limits.
- `pretransfer`: completed source history plus receiving specifications and future planned commands, with **zero receiving observations**. Receiving outcomes remain evaluator-only. Unknown receiving faults may be impossible to predict; asking for characterization or abstaining is permitted.

The pilot does not force a physics win. Simple tools omit sensor faults, mixed mechanisms, transient gas response, heterogeneous vials or pressure dynamics. Some cases have no feasible action in the allowed grid. In-progress freeze-drying actions cannot change loading; loading changes are offered only before transfer.

The final dataset uses the earlier operations demonstration's planned -18°C shelf step at 8 h in all freeze-drying families. The first completed audit (`pilot-20261027-v2`) used -24°C and did not exercise the shifted thermal-failure cases; it is retained as a development run. The final catalogue changes that shared operating plan before any agent evaluation, rather than changing settings for individual fault families. All cases remain exploratory.

## Evidence and model boundaries

All process trajectories, fault assignments, noise, variation and assay costs are **synthetic assumptions**. Freeze-drying nominal parameters originate from the existing published-parameter reconstruction, not a new experimental dataset. Original Sulfolobus, Pichia, IndPenSim and other benchmark assets are untouched.

The oxygen evaluator integrates oxygen storage, concentration-dependent uptake and an actuator lag with time-varying transfer. The B-arm tool uses steady Henry-law/OTR characterization algebra. No biomass, viability, yield or product kinetics are predicted. Its objective includes partial utility cost and an explicitly arbitrary feed-curtailment penalty, not commercial batch economics.

The freeze-drying evaluator extends the existing two-population finite-thermal-capacity/pressure-response equations with explicit per-population ice-depletion events. The first generation attempt stalled at the original flux-clipping discontinuity; its interrupted output is retained in `backend/results/physics-value/pilot-20261027/`. `lyo_reference.py` restarts a smooth solve at each drying endpoint, with an explicit RHS-evaluation budget. The historical reference implementation is unchanged. The B-arm tool is the existing quasi-steady representative-vial model. The constraint target is the hottest active population, not average thermometry. The objective is primary-drying load/completion time, excluding secondary drying and turnaround. Neither model predicts final product release or an actual saved batch.

Shared physical laws and authored mechanisms limit evaluator independence. This is a structurally different synthetic check, not independent experimental validation. Never grade an agent's intervention solely by its own forward-model output.

Both arms receive identical nominal parameters, model equations and limits. B additionally gets the executable **forward** tool; no causal label, optimizer ranking or evaluator is exposed as a tool. A retains ordinary statistics, code and numerical analysis, including the ability to derive physics itself. Record that usage in future trials.

## Generate and inspect

From the repository root:

```sh
PYTHONPATH=backend .venv/bin/python -m benchmarks.physics_value.generate \
  --output backend/results/physics-value/my-pilot --seed 20261027 --replicates 2
```

Always use a fresh directory. Re-running into an existing nonempty directory fails instead of overwriting a frozen run. Protocol and a running-status receipt are written before simulation; a complete status and file/code hashes are written only after generation. A failed run cannot be mistaken for a completed dataset.

```text
my-pilot/
  protocol.json                 exploratory design, no claimed agent scores
  manifest.json                 code/environment and artifact SHA-256 values
  generation-status.json        completion status and measured generation runtime
  report.md                     human audit, includes hidden-outcome counts
  public/
    catalogue.json              opaque case IDs and task paths
    PV-.../<task>/packet.json   same evidence for A and B
    PV-.../<task>/*-traces.csv   readable observations at the permitted cutoff
  evaluator/
    catalogue.json              private mechanisms and candidate split assignments
    cases/PV-....json           hidden parameters, full trajectories, action outcomes
    simulation-summary.json    environment audit, not agent performance
    simulation-overview.png    evaluator view, never agent input
```

The candidate evaluation pool reserves sensor/mixed/structural-mismatch families rather than renamed instances of the same fault. Since these cases are inspected to debug the generator, do not call them untouched confirmatory holdouts. Fresh independently authored cases, reviewed endpoints and a separate freeze are needed for that claim.

## Stage the comparison

Choose an opaque ID from `public/catalogue.json`. For example:

```sh
PYTHONPATH=backend .venv/bin/python -m benchmarks.physics_value.evaluate stage \
  --dataset backend/results/physics-value/my-pilot --case PV-0123456789ab \
  --task pretransfer --arm A --output /private/tmp/physics-agent-a
PYTHONPATH=backend .venv/bin/python -m benchmarks.physics_value.evaluate stage \
  --dataset backend/results/physics-value/my-pilot --case PV-0123456789ab \
  --task pretransfer --arm B --output /private/tmp/physics-agent-b
```

The example ID is a placeholder; use one actually generated. Common file hashes must match between staging receipts. `tools.json` is the only capability difference. This stages inputs and does not launch an agent. B's host bridge can call `benchmarks.physics_value.public_models.predict(packet, action_id, parameter_overrides=...)`; the tool does not read any evaluator file or select actions.

**File separation is not a security sandbox.** Before a blinded agent evaluation, enforce worker filesystem denial of the full dataset, hidden evaluator code, generation code and report, plus network restrictions preventing answer retrieval. The full source checkout contains scenario construction and must not be exposed unrestricted. Expose host-owned tools through serialization; do not hand an agent a `SimulationSession` Python object with access to its private case. The restricted runner below uses a capability allowlist and separately sandboxed numerical Python. It does not claim the full unrestricted Prime/RLM workflow has been evaluated. Generation and staging perform no inference.

## Score and replay

Static submissions use a ranked `hypotheses` list; optimization/pretransfer action commitments also require an allowed `action_id`. A pretransfer response may instead use `decision: "characterize"` with a nonempty `requested_measurements` list, or `decision: "abstain"`, without committing an operating action. These are not automatically graded as successful characterization or as process failures; usefulness needs independent review. Pretransfer may supply `warn_before_transfer: true`, `false`, or `null` to abstain from predicting risk. `claim_verified: true` is flagged as lacking session measurements; this structural flag does not replace scientific review of prose.

```json
{"hypotheses":["low_transfer","high_demand"],"action_id":"pressure","warn_before_transfer":null,"claim_verified":false}
```

```sh
PYTHONPATH=backend .venv/bin/python -m benchmarks.physics_value.evaluate score \
  --dataset backend/results/physics-value/my-pilot --case PV-0123456789ab \
  --task pretransfer --submission /private/tmp/submission.json
```

Do not treat cause-set coverage alone as diagnostic success: listing every cause attains high coverage. Set size, ranking, identifiability and independent review must accompany it. Optimization reports regret only for feasible actions, relative to the finite feasible action grid. An infeasible action is not assigned an attractive numeric regret. Correct abstention and missing scores are distinct from zero accuracy.

Scoring and sequential replay reject a current implementation that differs from the dataset's frozen code hashes. Use the recorded code snapshot for a historical run, or generate a new dataset; do not silently replay old inputs with changed physics.

Sequential sessions are host-side APIs:

```python
from pathlib import Path
from benchmarks.physics_value.evaluate import SimulationSession

session = SimulationSession(Path("backend/results/physics-value/my-pilot"), case_id)
result = session.request_measurement("sensor_check")  # simulated time advances
verification = session.commit("keep", hypotheses=["sensor_bias"])
```

Assays are exact and their turnaround/human work costs are explicit synthetic assumptions in this first version. Verification is an additional assumed one-hour/15-minute measurement after the simulated physical endpoint. `verified_process_constraint_resolution_h` is null when full-batch criteria fail, including prior excursions. It is neither actual engineer time saved nor proof of root-cause repair. `commit` is single-use; these sessions do not implement repeated failed receiving batches, equipment repair or adaptive continuous control.

## What remains before testing the thesis

The restricted runner now executes the same configured agent with equal ceilings and scores its actual chosen actions. Independent scientific adjudication, realistic assays/document formats, fresh holdouts and prospective manufacturing outcomes remain necessary. Measure human preparation, characterization, review and correction effort before claiming real engineering savings. Report the four endpoints separately; do not collapse them into one accuracy score. A numerical improvement in this inspected synthetic pilot does not establish real failed batches avoided or real resolution-time savings.

## Run the actual agent comparison

The runner reuses the installed Prime SDK, saved Modal model registry, project provider authentication and the existing physical kernels. The two arms use the same model, native low reasoning setting, prompt, response ceiling, wall/tool budgets and case packet. Arm order is counterbalanced within each pair; independent pairs can run concurrently. Each task has a fresh, memory-free SDK session. No production model qualification is created.

```sh
.venv/bin/python -m benchmarks.physics_value.run_agents \
  --dataset backend/results/physics-value/pilot-20261027-final \
  --output backend/results/physics-value/my-agent-comparison --workers 4 --timeout 120
```

The command loads the existing ignored `backend/.env.local`; it never copies credentials into packets or receipts. Run it where macOS `sandbox-exec` is permitted. The preflight verifies arithmetic works, the evaluator catalogue cannot be read, network access fails and inference credentials are absent from numerical workers. If these checks fail, no model call is started.

Only `python_analysis`, `submit_decision`, and (for resolution) `request_measurement` are active in A. B additionally gets `physical_forward_model`. No native kernel, filesystem, shell, browser, global context, extension, memory or child-agent tools are active in the SDK. General numerical Python is available equally to both arms under inherited OS file-content/network restrictions; it may derive physical calculations itself. The trusted host sees evaluator state, but the model receives only serialized permitted tool results. Submission returns an acceptance receipt, never hidden scores that would allow revising the decision.

The first model-connectivity calibration used a generic SDK reasoning-off setting. GLM-5.3's native template defaulted to maximum reasoning; both attempts exhausted responses without submitting. Those actual receipts and source snapshots remain under `agent-connectivity-20261027`. The corrected calibration (`agent-connectivity-20261027-low`) used the documented native low setting in both arms and produced both submissions. The full comparison uses this separately frozen configuration. Source: [vLLM's GLM-5.3 reasoning modes](https://recipes.vllm.ai/zai-org/GLM-5.3#reasoning-modes). These calibration attempts are not silently merged into the final run.

The first full development run (`agent-comparison-20261027`) was interrupted after148 finished attempts because agents sometimes put explanatory prose into exact-ID fields, creating formatting-repair overhead. The final comparison (`agent-comparison-20261027-enums`) uses exact enums taken from the public packet for hypothesis, action and measurement IDs in both arms. Explanations have separate fields. The dataset, physical kernels, outcome rubric and execution budgets did not change. Earlier receipts remain separately downloadable and are excluded from the final counts. To stop a running batch cleanly, create a `STOP` file in its output directory; active attempts are bounded and queued pairs will not start.

`protocol.json` and `runner-source/` are written before inference. `isolation.json` contains actual access probes. Each attempt retains SDK metadata/usage, tool arguments/results, actual submission, score and status. Hosted monetary billing remains unknown; a zero-priced SDK ledger is not free inference. Failed/unsubmitted attempts remain in denominators. The four endpoint summaries are descriptive, with no prespecified power, independent scientific review or confirmatory generalization claim.

Export a recorded comparison into the case-studies page:

```sh
.venv/bin/python frontend/scripts/export_physics_value.py \
  --dataset backend/results/physics-value/pilot-20261027-final \
  --run backend/results/physics-value/my-agent-comparison
```

Open `/case-studies/#physics-value`. The export includes actual decisions, post-evaluation reference traces, failure states, a protocol, hashes and an explicitly allowlisted reproducibility archive. It does not execute a model or generate a fabricated score. Running exports remain labelled in progress; the final review build must be exported again after completion.

Verification:

```sh
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_physics_value.py -q
```
