# LyoHUB modeling-tool rerun

Additive experiment requested in [issue #28](https://github.com/YalmanchiliTejas/BioDemo/issues/28), retaining the original freeze-drying study. This uses **LyoPRONTO as an agent tool**, not as ground truth. The separate results route is `/research/lyohub/`.

24 reused synthetic cases × two tasks × three fresh agent sessions = 144 slots. A gets numerical Python without a prepared solver; B gets LyoPRONTO; C gets the existing heterogeneous solver. B/C share remaining-ice-only calibration and bounds. This changes the historical C fitting objective; it avoids falsely equating LyoPRONTO front/bottom temperature with weighted transient thermometry. Pretransfer is unfitted. The existing separately executed synthetic reference remains the scorer and shares approximate population assumptions with C, limiting scientific independence.

## Reproduction

Use the repository Python environment with NumPy, SciPy, Matplotlib, ruamel.yaml and pytest. Install the existing adjacent Prime SDK and saved Modal research authentication as in the original study. No production route changes are needed.

```sh
git clone https://github.com/LyoHUB/LyoPRONTO.git /private/tmp/lyohub-rerun-source
git -C /private/tmp/lyohub-rerun-source checkout c6a9225a9e551ae4e7c11c1ef056b67c6204afbd
# LYOPRONTO_CHECKOUT may select another clean checkout of that exact commit.
PYTHONPATH=backend .venv/bin/python -m benchmarks.lyo_study.study generate --output backend/results/lyohub-rerun-NEW/frozen
PYTHONPATH=backend .venv/bin/python -m benchmarks.lyohub_study.campaign prepare --base backend/results/lyohub-rerun-NEW
PYTHONPATH=backend .venv/bin/python -m benchmarks.lyohub_study.campaign controls --base backend/results/lyohub-rerun-NEW
PYTHONPATH=backend .venv/bin/python -m benchmarks.lyohub_study.campaign preflight --base backend/results/lyohub-rerun-NEW
mkdir -p backend/results/lyohub-rerun-NEW/cost
PYTHONPATH=backend .venv/bin/python -m scripts.run_bounded_agent_benchmark --suite backend/results/lyohub-rerun-NEW/cost --budget-usd 10 --max-requests 1152 --command .venv/bin/python -m benchmarks.lyohub_study.campaign agents --base backend/results/lyohub-rerun-NEW
PYTHONPATH=backend .venv/bin/python -m benchmarks.lyohub_study.report --base backend/results/lyohub-rerun-NEW
```

The eighth provider call, if reached, exposes only submission. Earlier plain-text stopping can still yield no accepted structured decision after the shared follow-up prompt; an eight-call ceiling does not guarantee eight calls or a forced final submission.

The default seed exactly reconstructs all 48 public packets of the original 24-case study; `prepare` verifies against its archived hashes. Protocol/source/input hashes are written before inference. Re-running the agent command retains earlier receipts and interrupted attempts; it never retries scored failures. Existing output paths are immutable with respect to the protocol. Preflight sends zero inference and verifies OS denial of hidden files/network/credentials plus SDK tool allowlists.

## Boundary and mapping

The upstream process receives only a public config through JSON. Its clean Git commit is checked on each execution. No source is vendored or imported by the production app. LyoPRONTO is GPL-3.0-or-later; retain the upstream license and attribution when reproducing/distributing its software. Output publishing does not claim a Purdue affiliation or endorsement.

SI conversions preserve pressure-dependent Kv and Rp. `cSolid=1.5*(1-porosity)` g/mL preserves initial frozen height under upstream's fixed-density assumption; native initial ice differs by approximately 0.85%. Its mass/flux remain native and unrescaled. `dt=None` retains the exact drying event; an unfinished horizon is not a completion. Finite 1e6 native-unit/min ramps approximate schedule steps, from batch start including past conditions. The supplied LyoPRONTO temperature is the sublimation front, not a transient weighted thermal node or hottest vial. Vapor/condenser/thermal guards are explicitly the **BioDemo wrapper**, not capabilities of upstream knownRp. Pressure-controlled forecasts become invalid after overload.

Controls precompute four action predictions per packet/model using only public packets. The agent tool returns only the requested action output; it cannot reveal the selector, evaluator, hidden shifts or optimal action. Precomputation excludes solver cost from session wall time equally for B/C; controls retain solver runtime separately. The AI session deadline therefore measures reasoning/tool interaction and numerical code in A, not total engineering effort.

Run tests with `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/test_lyohub_study.py backend/tests/test_lyo_study_agents.py`. Results retain denominators, failures, characterize, common-prediction error, wrapper limits and conservative/unknown cost coverage. No physical equipment is operated or manufacturing recommendation approved.
