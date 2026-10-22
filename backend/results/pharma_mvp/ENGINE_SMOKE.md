# Actual existing-engine smoke check

A separate invented fermentation CSV was ingested into the existing
ManufacturingStore, then passed to PrimeManufacturingHarness with a 120-second
wall bound and 12-tool-call bound. No cached report or answer key was used.

`engine-smoke-002/result.json` records failure after 120.24 seconds. Persisted
SDK messages identify provider `prime-inference`, model `z-ai/glm-5.3`, and
HTTP 402 insufficient balance. Recorded sessions contain 17 model attempts with
zero reported input/output tokens; cost is unknown. No tool evidence was returned
and no validated investigation report was produced.

The old host only stopped on payment errors in evaluation mode. That condition
has been removed so product calls use the same fatal-payment handling. The follow-up
bounded execution is retained locally in `engine-smoke-003/result.json`.

Raw SDK/session logs are intentionally not tracked. The shared case workspace
uses explicitly labeled existing deterministic analysis functions; it does not
present the failed Prime run as an agent success. Fix approved-provider access
before evaluating the autonomous investigation journey.

The follow-up native run failed explicitly after 8.53 seconds (instead of timing out at 120 seconds). Provider access is still blocked; no report was produced.
