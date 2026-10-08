# Dataset validation report

**Status: PASS**  
Dataset fingerprint: `5db80dca9e36f9c332d8f0f7b0e786a804c226421c71e137669c5f7e2469b47b`

## Dataset composition

- 100 total batches
- 95 non-incident batches
- 8 deliberately benign abnormality batches
- 5 labeled incident batches across three scenario families
- 23 explicit negative controls

## Distribution sanity

- Batch duration: 7.55–11.14 hours; median 9.06
- Median normalized bioburden signal: 0.195
- Alert crossings: 7
- Action crossings: 4
- Environmental/bioburden correlation: 0.776
- Exact duplicate signal patterns: 0
- Normal batches on reconstructed LINE-A: 63
- Normal near-limit hold-duration values: 24

## Threshold and noise behavior

Normal operations contain nonzero variation: **True**.  
Negative controls include abnormal signals without a true incident: **True**.

## Causal sanity

- Results before sample collection: 0
- Same-line batch overlaps: 0
- Invalid start/end/disposition chronologies: 0
- Sterility results before the modeled 14-day minimum: 0
- Shipments before disposition: 0
- Process events outside their batch window: 0
- Future maintenance is excluded by `state_at(timestamp)`: **True**

## Validation issues

None.

All numerical limits are normalized synthetic parameters unless explicitly identified as public facts. This report checks internal consistency and statistical shape; it is not a claim that the distributions reproduce a manufacturer's validated process.
