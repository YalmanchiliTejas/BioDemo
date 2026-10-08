# Manufacturing OS — Famotidine Incident Replay

A polished MVP demonstrating an **AI Operating System for pharmaceutical
manufacturing** through one retrospective incident reconstruction.

The demo replays the 2025–2026 Fresenius Kabi famotidine injection case described
in public FDA records. It contrasts the same reconstructed event stream under:

- a traditional, fragmented cross-system workflow; and
- one orchestrating Manufacturing Agent that detects, correlates, triages,
  investigates, coordinates human work, and retrieves incident memory.

The purpose is decision-support demonstration, not factory simulation.

> Reconstructed simulation based on publicly documented FDA findings.
> Operational telemetry shown in this demo is synthetic.

## Run

Requires Python 3.11+.

```bash
python3 -m pip install -e '.[app]'
python3 -m benchmark serve
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) and click
**Replay Incident**.

Run the test suite with:

```bash
python3 -m unittest discover -s tests -v
```

## Reproducible validation benchmark

### v1.1 Manufacturing OS RLM

The additive `data/v1.1` layer preserves the original 100 batches and adds
`occurred_at`, `available_at`, field-level availability, evidence availability
types, and ambiguous precursor signals with negative controls. The Manufacturing
OS runtime is explicitly a bounded Lead RLM with a persistent Blackboard, Causal
Hypothesis Graph, and Decision Graph. Run its four context modes with:

```bash
PYTHONPATH=. python3 run_rlm_validation.py
```

Every run performs a leakage audit before executing or reporting results. The
canonical behavior and tool contract are in [`system.md`](system.md), and the
implementation architecture is in [`docs/architecture.md`](docs/architecture.md).

The polished replay is backed by a separate 100-batch SQLite benchmark containing
normal variation, negative controls, benign abnormalities, and three incident
families. Generate and validate it with:

```bash
python generate_dataset.py --seed 42
python validate_dataset.py
python validate_public_facts.py
python run_validation.py
python generate_report.py
python run_robustness.py --seeds 20 --start-seed 100
```

The committed benchmark report uses the deterministic contextual agent so it is
reproducible and free to run. To benchmark a configured structured-JSON LLM provider:

```bash
python run_validation.py --live
```

Live evaluation calls the provider at each replay decision point and can incur
meaningful API usage. It fails explicitly when no provider is configured rather than
silently presenting fallback results as an LLM benchmark.

Dataset `v1.0-frozen` uses seed `42` and is frozen at the fingerprint stored in
[`frozen_seed_42.sha256`](benchmark/pharma_simulation/data/frozen_seed_42.sha256).
The validation step fails if generation with that seed drifts. Change the generator
only as a versioned benchmark change—never in response to an agent score. Once a
dataset version is frozen, improve the agent against held-out behavior rather than
tuning the data until the agent looks good.

The harness evaluates:

- incident recall, precision, and false-positive rate;
- median time-to-detection and triage accuracy;
- evidence grounding and future leakage;
- investigation-scope recall; and
- hypothesis and action relevance.

It runs a deterministic local-event baseline and four context ablations: current
event only, current batch plus LIMS, current batch plus LIMS/QMS, and full OS
context (`current_event_only`, `lims_only`, `lims_qms`, and `full_os`). A separate A/B experiment compares full context without manufacturing
memory against memory-enabled retrieval. Evaluation labels and final outcomes live
in benchmark-only tables and are never returned by `state_at(timestamp)`.

The generator enforces a minimum modeled 14-day interval between sterility-sample
collection and result availability. Disposition follows completed release testing,
and shipment follows disposition. Most normal batches run on the same reconstructed
line as the incident lots, while at least 20 normal batches have near-limit hold
values. This prevents `LINE-A` or hold duration from acting as trivial answer keys.

Key benchmark artifacts:

- SQLite: [`pharma_simulation.db`](benchmark/pharma_simulation/artifacts/pharma_simulation.db)
- Agent-safe operational layer: [`agent_data.json`](benchmark/incident_demo/data/agent_data.json)
- Hidden evaluation layer: [`benchmark_ground_truth.json`](benchmark/incident_demo/data/benchmark_ground_truth.json)
- UI-only replay layer: [`replay_ui.json`](benchmark/incident_demo/data/replay_ui.json)
- Inspectable JSON: [`pharma_simulation.json`](benchmark/pharma_simulation/artifacts/pharma_simulation.json)
- CSV exports: [`artifacts/csv`](benchmark/pharma_simulation/artifacts/csv)
- Public facts: [`public_ground_truth.json`](benchmark/incident_demo/data/public_ground_truth.json)
- Simulation model: [`simulation_config.yaml`](benchmark/pharma_simulation/data/simulation_config.yaml)
- Computed results: [`benchmark_results.md`](benchmark/pharma_simulation/artifacts/benchmark_results.md)
- Statistical validation: [`validation_report.md`](benchmark/pharma_simulation/artifacts/validation_report.md)
- Twenty-seed robustness report: [`robustness_report.md`](benchmark/pharma_simulation/artifacts/robustness_report.md)
- Process assumptions: [`process_assumptions.md`](benchmark/pharma_simulation/process_assumptions.md)
- Blind SME cases: [`sme_review_cases.md`](benchmark/pharma_simulation/artifacts/sme_review_cases.md)
- SME response template: [`sme_review_template.csv`](benchmark/pharma_simulation/artifacts/sme_review_template.csv)

> This dataset is a synthetic reconstruction designed to test manufacturing
> decision-support workflows. Public incident facts are sourced from regulatory
> records. Internal process measurements, timings, MES/LIMS/CMMS records, and
> equipment telemetry are synthetic and are not representations of the
> manufacturer's actual internal data.

> The benchmark tests whether the system can identify and investigate emerging
> patterns from information available at each point in simulated time. It does not
> establish that the system would have prevented the historical event.

## The 60-second story

1. Plant Overview shows a high-risk famotidine signal among normal and low-risk work.
2. Incident Replay starts in **Without OS** mode: LIMS, QMS, MES, CMMS, historian,
   and complaint records remain separate and require manual reconciliation.
3. Switch to **With Manufacturing OS** and replay the same underlying events.
4. The agent raises the assessment from `MEDIUM` to `HIGH`, scopes related batches,
   ranks evidence-linked hypotheses, and proposes human-governed actions.
5. In Coordination, complete the Microbiology task with the provided gram-negative
   finding. The shared incident state updates and the agent reassesses to `CRITICAL`.
6. Test a future synthetic signal to show retrieval of structured incident memory.

The end-state comparison is labeled **SIMULATED DEMO RESULTS**. It does not claim
that a recall would have been prevented.

## Public facts vs. reconstruction

Public FDA facts used in the product narrative:

- famotidine manufacturing experienced multiple bioburden action-limit failures;
- the firm's response acknowledged gram-negative confluent growth;
- passing finished-product sterility and endotoxin results preceded release;
- later retain testing identified an endotoxin failure;
- lots `6133156`, `6133194`, and `6133388` were recalled; and
- FDA criticized investigation scope, root-cause support, reliance on final-product
  testing, and CAPA effectiveness checks.

Official sources:

- [FDA warning letter, September 22, 2026](https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/fresenius-kabi-usa-llc-733107-09222026)
- [FDA-posted recall announcement, November 7, 2025](https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/fresenius-kabi-issues-voluntary-nationwide-recall-three-lots-famotidine-injection-usp-20-mg-2-ml-10)

The following are synthetic: exact manufacturing timestamps, CFU and EU/mL values,
equipment telemetry, work orders, deviations, complaint wording, handoff counts,
hypothesis confidence, tasks, and replay performance metrics. The application labels
these records `SYNTHETIC FACTORY SIGNAL`.

This prototype is a retrospective reconstruction for demonstrating manufacturing
decision-support concepts. It does not establish that a different system would have
prevented the real-world event.

## Agent modes

The deterministic fallback is always available and drives the default demo.

To use a configured reasoning provider, set one of the existing provider-neutral
adapters and enable **Use configured live LLM** in the replay:

```bash
BIODEMO_DYNAMIC_AGENT_COMMAND='your-json-command' python3 -m benchmark serve
```

or:

```bash
BIODEMO_DYNAMIC_AGENT_URL='https://your-endpoint.example/reason' \
BIODEMO_DYNAMIC_AGENT_TOKEN='...' \
python3 -m benchmark serve
```

An adjacent Prime Agent checkout can also be auto-discovered. Model output is treated
as untrusted: the backend validates the response shape and removes any evidence ID
that was not visible at the current replay timestamp. If the provider fails, the
request falls back to deterministic reasoning so the demo remains usable.

For a direct OpenAI implementation, use Structured Outputs with a strict JSON Schema;
the shipped provider-neutral contract is documented in [Agent prompt](docs/AGENT_PROMPT.md).

## Key files

- Seed dataset: [`benchmark/incident_demo/data/fresenius_famotidine_demo.json`](benchmark/incident_demo/data/fresenius_famotidine_demo.json)
- Sequential state and metrics: [`benchmark/incident_demo/service.py`](benchmark/incident_demo/service.py)
- Agent, fallback, prompt, and validation: [`benchmark/incident_demo/agent.py`](benchmark/incident_demo/agent.py)
- FastAPI endpoints: [`benchmark/application/api.py`](benchmark/application/api.py)
- UI: [`benchmark/application/static/index.html`](benchmark/application/static/index.html)
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Agent prompt: [docs/AGENT_PROMPT.md](docs/AGENT_PROMPT.md)

## Scope

This MVP intentionally excludes authentication, multi-plant management, real MES
integration, digital twins, regulatory submissions, and autonomous GMP disposition.
The Manufacturing Agent prepares and proposes; authorized humans decide.
