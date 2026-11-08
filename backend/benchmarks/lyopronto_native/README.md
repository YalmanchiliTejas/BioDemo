# Native LyoPRONTO agent evaluation

Spec: https://github.com/YalmanchiliTejas/BioDemo/issues/29

This replaces the evaluation method, not just an old benchmark's model tool.
It evaluates the current workspace assistant using native LyoPRONTO inputs and
fresh native-model reference executions. It does not compare BioDemo physics
with Purdue physics or establish experimental prediction accuracy.

The actual application conversation service, ToolLoop, model gateway, evidence
access and result storage run in clean local databases. `NativeConversation`
is a research-only connector supplying two typed tools, not a production
integration. Internal scientific model tools are excluded. No equipment action
or approval is authorized. Hidden reference files are not workspace records;
there is no shell or unrestricted file-reading tool available to the agent.

24 authored cases (six per family): scheduled calculations; finite constrained
recipe selection; absent characterization; and units/model-scope limits.
Native physical units and knownRp equations are preserved without fitting.
The reference executes the unmodified pinned upstream solver independently
and extracts bottom temperature, terminal drying event and whole-batch flux.
Recipe references exhaust the declared candidate grid. Time regret is relative
to that grid only. Constraints apply at returned nodes, not continuous maxima.

The first ten grading tests cover native columns, area/vial/pressure units,
incomplete events, required characterization, allowed schedules and exhaustive
infeasibility evidence. The application integration test uses a scripted
provider and actual native solver: it is a zero-inference wiring check, not an
agent performance result.

Set `MODAL_BASE_URL` to the existing deployment’s OpenAI-compatible `/v1` endpoint before the paid command; the runner intentionally has no endpoint default. Credentials stay in the local environment and are never included in the reproduction archive.

From repository root with the repository virtual environment:

```sh
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_lyopronto_native.py -q
PYTHONPATH=backend .venv/bin/python -m benchmarks.lyopronto_native.run preflight --output /private/tmp/lpn-preflight
PYTHONPATH=backend .venv/bin/python -m benchmarks.lyopronto_native.run generate --output backend/results/lyopronto-native-DATE/frozen
# Paid run: uses existing Modal credentials, <=$10 admission estimate.
PYTHONPATH=backend .venv/bin/python -m benchmarks.lyopronto_native.run run --base backend/results/lyopronto-native-DATE/frozen --output backend/results/lyopronto-native-DATE/agent
```

Generation freezes code/environment/input/reference hashes before inference.
`run` refuses changed files. Pin upstream at
`c6a9225a9e551ae4e7c11c1ef056b67c6204afbd` in `/private/tmp/lyohub-rerun-source`
or set `LYOPRONTO_CHECKOUT`. Install upstream requirements separately; this repo
does not vendor its GPL-3.0-or-later implementation. The protocol records exact
Python/NumPy/SciPy/ruamel.yaml versions. Retain solver trajectories, case files,
requests, all episode errors and budget reservations. Provider estimates are
not invoices. Do not silently rerun failed scored attempts.

Local SQLite state stays outside Git and public downloads. Public source
packets, reference trajectories and sanitized result traces can be released
after inference. Keep the rejected `lyohub_study` experiment intact and clearly
mark it as superseded; its raw artifacts are historical records.
