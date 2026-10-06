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
