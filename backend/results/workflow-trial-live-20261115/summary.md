# Workflow trial: live arms, 15 November 2026

## One bounded explanation of a calculated comparison (one model call, requests one at a time)

| Path | Answered | All reference figures | Mean | Slowest | Within 10 s |
|---|---:|---:|---:|---:|---:|
| GLM-5.3, default reasoning effort | 6/6 | 6/6 | 17.4 s | 28.3 s | 0/6 |
| GLM-5.3, low reasoning effort (first run) | 6/6 | 6/6 | 3.2 s | 6.4 s | 6/6 |
| GLM-5.3, low reasoning effort, JSON-only output (as now configured) | 6/6 | 6/6 | 4.9 s | 7.3 s | 6/6 |

## The same requests through chat, on the same deliveries

| Path | Answered | All reference figures | Mean | Slowest | Within 10 s |
|---|---:|---:|---:|---:|---:|
| Assistant alone · routine request | 2/3 | 0/2 | 134.2 s | 226.2 s | 1/3 |
| Assistant alone · question | 3/3 | 0/3 | 127.5 s | 214.6 s | 0/3 |
| Workbench path · routine request (host calculation) | 3/3 | 3/3 | 0.0 s | 0.1 s | 3/3 |
| Workbench path · question, answered by the assistant with the calculation attached | 3/3 | 2/3 | 90.1 s | 137.2 s | 0/3 |
| Workbench path · question, quick answer first, one request at a time | 3/3 | 3/3 | 3.3 s | 3.4 s | 3/3 |
| Workbench path · question, quick answer first, three requests at once | 3/3 | 3/3 | 25.4 s | 41.2 s | 0/3 |


The one "assistant alone" routine request under 10 s is the one that failed (the model returned no content after 7.7 s); it is not an answer.

Three requests at once queue on the single deployment: the same quick answers took 12–41 s. That is the deployment's capacity, not the method.

An earlier run of all arms was discarded: the machine slept during it, and its "low effort" explanation rows had not applied the setting.

Limits: six explanation cases and three delivery pairs, one attempt each; one model (GLM-5.3 on the configured Modal deployment); scored on reference figures only, the wording has not been read by a qualified reviewer. Indications, not rankings.
