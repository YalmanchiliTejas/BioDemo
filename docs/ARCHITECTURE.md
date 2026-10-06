# Architecture overview

## Product boundary

The application demonstrates one workflow: sequential reconstruction of the public
Fresenius Kabi famotidine incident using synthetic operational records.

```text
MES   LIMS   QMS   CMMS   Historian   Complaints
  \     |      |      |       |          /
       time-bounded incident state
                  |
       one Manufacturing Agent
                  |
 Detect → Correlate → Triage → Investigate
                  |
        human-governed tasks/actions
                  |
               Learn
```

## Components

### Seed dataset

`benchmark/incident_demo/data/fresenius_famotidine_demo.json` contains:

- 12 batches, including the three publicly identified recalled lots;
- reconstructed laboratory results, process events, deviations, maintenance work,
  one complaint, and one prior incident-memory record;
- the chronological replay event stream;
- five functional tasks; and
- timestamp anchors used to compute comparison metrics.

Each fact carries a provenance value:

- `public_fda_fact`
- `synthetic_factory_signal`
- `ai_inference`
- `human_decision`

### Sequential state service

`IncidentDemoService.visible_state(cursor)` constructs the only state the agent may
see. It filters every table by the timestamp at the replay cursor. Gated laboratory
evidence is invisible until its human task is completed. Final disposition and recall
fields are stripped from visible batch records, preventing hindsight leakage.

### Manufacturing Agent

`ManufacturingAgent` supports:

1. deterministic assessment for a reliable offline demo;
2. provider-neutral live reasoning through a command or HTTP JSON adapter;
3. a structured response contract; and
4. evidence-reference validation against the time-bounded allow-list.

The deterministic path changes severity as evidence accumulates:

```text
No excursion                       LOW / L1
First bioburden excursion          MEDIUM / L2
Repeated cross-batch excursion     HIGH / L3
Gram-negative or reserve OOS       CRITICAL / L3
```

The agent has no batch disposition or execution authority.

### API

FastAPI exposes:

- `GET /api/incident-demo`
- `POST /api/incident-demo/assess`
- `POST /api/incident-demo/tasks/{task_id}/complete`
- `POST /api/incident-demo/reset`
- `GET /api/incident-demo/future-match`

### Frontend

One dependency-free operations UI provides four views:

1. Plant Overview
2. Incident Replay
3. Investigation Workspace
4. Coordination

The replay timer is a presentation device. Manufacturing timestamps and calculated
metrics remain in the dataset and backend.

## Trust and credibility controls

- The permanent header disclosure identifies synthetic telemetry.
- Public facts and reconstructed signals have distinct badges.
- The agent never receives public outcome facts during the active replay.
- Every inference exposes exact evidence references.
- Unknown model evidence IDs are removed server-side.
- Consequential recommendations retain a human-approval flag.
- Live-provider failures fall back without breaking the demo.

## Comparison metrics

The UI does not embed outcome numbers. The backend calculates recognition time from
the replay's timestamp anchors and derives source-system counts from the dataset.
Handoff and scope counts are explicit synthetic workflow parameters in the same seed
file. All results are labeled simulated.
