# Biopharma Factory Benchmark

A deterministic, discrete-event MVP for benchmarking operating models in a small
biologics factory. The current milestone intentionally implements only the shared
factory/environment and the **Traditional** operating model. It does not contain
an LLM or agentic controller.

## What is modeled

- One product, one upstream train, one downstream train, one QC lab
- Twelve scheduled batches over a 30-day campaign
- Five major assets, material lots, workforce qualifications, and maintenance
- Eight simulated systems of record: MES/eBR, historian, LIMS, QMS, CMMS, ERP,
  scheduler, and LMS
- Twelve deterministic failure scenarios with explicit ground-truth causes
- A Traditional controller with information-retrieval, meeting, escalation,
  investigation, approval, and manual replanning delays
- Complete JSONL event logs plus a JSON baseline summary

The physical model and scenario manifest are controller-independent. Future
controllers must consume the same `CampaignDefinition` and `ScenarioManifest`.

## Run

Requires Python 3.11+ and has no runtime dependencies.

```bash
python -m benchmark run --mode traditional --seed 20250921 --output runs/baseline
python -m benchmark replay runs/baseline/events.jsonl
python -m unittest discover -s tests -v
```

The run command writes:

- `campaign.json`: immutable campaign and scenario manifest
- `events.jsonl`: replayable audit/event log
- `summary.json`: released product, manufacturing, quality, and MSAT metrics

## Scope boundary

`point_ai` and `agentic` modes are reserved but deliberately unavailable. This
prevents later decision layers from silently changing factory physics, failures,
materials, staffing, or quality limits before the Traditional baseline is stable.

This simulator is a benchmark abstraction, not a validated GMP system or a
mechanistic bioprocess model. `benchmark/factory/process.py` exposes the narrow
process-model interface where BIOPRO-Sim, PenSimPy, or another physical model can
later be connected without changing controllers or systems-of-record APIs.
