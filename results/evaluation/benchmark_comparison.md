# Manufacturing OS evaluation v2

Principle: equivalent or better correct, reviewable investigation outcomes with fewer total human-hours.
CHO uses authentic laboratory measurements. Fresenius uses a synthetic FDA-anchored 100-batch reconstruction.
No universal accuracy score, competitor marketing comparison, verified internal RCA or recall-prevention claim is made.

## FRESENIUS

### raw

| Group | Attempts | Qualified rate | Human hours, all attempts | Hours per qualified case | Status |
|---|---:|---:|---:|---:|---|
| A. Manual engineer | 0 | Not measured | Not measured | Not measured | not_tested |
| B. Conventional pipeline | 3 | 0.000 | Not measured | Undefined (zero qualified) | pending_measurement |
| C. Single-pass AI | 3 | 0.000 | Not measured | Undefined (zero qualified) | pending_measurement |
| D. Manufacturing OS | 6 | 0.000 | Not measured | Undefined (zero qualified) | pending_measurement |
| E. Incumbent product | 0 | Not measured | Not measured | Not measured | not_tested |

Paired sample: 0; observed effort reduction: Not measured.
- No matched, quality-qualified, timed pair.

- `20a0c92687014dbf8f4a6bc3fcac0bb1` / FRE-02 / retrieval_llm: incomplete, investigation qualification `failed`. Trace: `20a0c92687014dbf8f4a6bc3fcac0bb1/trace.jsonl`.
  - Emitted field checks: 214/214 correct; 0 missing of 214 expected. Wall clock: 98.552 s. This is technical transcription performance, not investigation qualification.
  - Machine usage: input/output tokens 146077/9744; tool calls None; inference cost Not measured. Scope: all_model_calls; local_compute_cost_unmeasured.
- `27aadbed7000415386a77a74bea71e6d` / FRE-02 / conventional: incomplete, investigation qualification `failed`. Trace: `27aadbed7000415386a77a74bea71e6d/trace.jsonl`.
  - Emitted field checks: 214/214 correct; 0 missing of 214 expected. Wall clock: 21.137 s. This is technical transcription performance, not investigation qualification.
  - Machine usage: input/output tokens 0/0; tool calls None; inference cost 0.000. Scope: all_model_calls; local_compute_cost_unmeasured.
- `39e4673d7a734191bf014ac9d4f7c877` / FRE-02 / conventional: incomplete, investigation qualification `failed`. Trace: `39e4673d7a734191bf014ac9d4f7c877/trace.jsonl`.
  - Emitted field checks: 214/214 correct; 0 missing of 214 expected. Wall clock: 20.785 s. This is technical transcription performance, not investigation qualification.
  - Machine usage: input/output tokens 0/0; tool calls None; inference cost 0.000. Scope: all_model_calls; local_compute_cost_unmeasured.
- `541e0c961c5b4039bdf585841a643fff` / FRE-02 / retrieval_llm: failed, investigation qualification `invalid`. Trace: `541e0c961c5b4039bdf585841a643fff/trace.jsonl`.
- `59c7a3341e804b3e884fcb98f6f3f250` / FRE-03 / full_rlm: incomplete, investigation qualification `failed`. Trace: `59c7a3341e804b3e884fcb98f6f3f250/trace.jsonl`.
  - Emitted field checks: 214/214 correct; 0 missing of 214 expected. Wall clock: 582.916 s. This is technical transcription performance, not investigation qualification.
  - Machine usage: input/output tokens 123852/122126; tool calls 48; inference cost Not measured. Scope: root_sdk_session_only; child, OCR and tool costs may be missing.
- `5edb0bfd0ebb42f298dfd94eaba138cc` / FRE-05 / full_rlm: failed, investigation qualification `failed`. Trace: `5edb0bfd0ebb42f298dfd94eaba138cc/trace.jsonl`.
  - Machine usage: input/output tokens 62588/60001; tool calls None; inference cost Not measured. Scope: root_sdk_session_only; failed_execution_included.
- `7c977c4dfee2427d9fd06595c3b55ee1` / FRE-02 / retrieval_llm: failed, investigation qualification `failed`. Trace: `7c977c4dfee2427d9fd06595c3b55ee1/trace.jsonl`.
  - Machine usage: input/output tokens 345667/10282; tool calls None; inference cost Not measured. Scope: single_pass_provider_response; failed_validation_included.
- `915f57c577d846c0adb849f936436730` / FRE-02 / conventional: failed, investigation qualification `invalid`. Trace: `915f57c577d846c0adb849f936436730/trace.jsonl`.
- `b27a0a3b691b43a0b9e50b73c17cbe43` / FRE-02 / full_rlm: incomplete, investigation qualification `failed`. Trace: `b27a0a3b691b43a0b9e50b73c17cbe43/trace.jsonl`.
  - Emitted field checks: 214/214 correct; 0 missing of 214 expected. Wall clock: 702.239 s. This is technical transcription performance, not investigation qualification.
  - Machine usage: input/output tokens 95146/113881; tool calls 48; inference cost Not measured. Scope: root_sdk_session_only; child, OCR and tool costs may be missing.
- `b85518cfe36447a9921c695766e03e67` / FRE-01 / full_rlm: incomplete, investigation qualification `failed`. Trace: `b85518cfe36447a9921c695766e03e67/trace.jsonl`.
  - Emitted field checks: 214/214 correct; 0 missing of 214 expected. Wall clock: 810.747 s. This is technical transcription performance, not investigation qualification.
  - Machine usage: input/output tokens 89124/98856; tool calls 42; inference cost Not measured. Scope: root_sdk_session_only; child, OCR and tool costs may be missing.
- `d174605c213a480d94f294700798a276` / FRE-04 / full_rlm: incomplete, investigation qualification `failed`. Trace: `d174605c213a480d94f294700798a276/trace.jsonl`.
  - Emitted field checks: 214/214 correct; 0 missing of 214 expected. Wall clock: 774.384 s. This is technical transcription performance, not investigation qualification.
  - Machine usage: input/output tokens 137517/146417; tool calls 45; inference cost Not measured. Scope: root_sdk_session_only; child, OCR and tool costs may be missing.
- `e0e6241b5b1f4e46a4044a72c336e068` / FRE-06 / full_rlm: failed, investigation qualification `failed`. Trace: `e0e6241b5b1f4e46a4044a72c336e068/trace.jsonl`.
  - Machine usage: input/output tokens 50839/29310; tool calls None; inference cost Not measured. Scope: root_sdk_session_only; failed_execution_included.
### clean

| Group | Attempts | Qualified rate | Human hours, all attempts | Hours per qualified case | Status |
|---|---:|---:|---:|---:|---|
| A. Manual engineer | 0 | Not measured | Not measured | Not measured | not_tested |
| B. Conventional pipeline | 0 | Not measured | Not measured | Not measured | not_tested |
| C. Single-pass AI | 0 | Not measured | Not measured | Not measured | not_tested |
| D. Manufacturing OS | 0 | Not measured | Not measured | Not measured | not_tested |
| E. Incumbent product | 0 | Not measured | Not measured | Not measured | not_tested |

Paired sample: 0; observed effort reduction: Not measured.
- No matched, quality-qualified, timed pair.

### held_out

| Group | Attempts | Qualified rate | Human hours, all attempts | Hours per qualified case | Status |
|---|---:|---:|---:|---:|---|
| A. Manual engineer | 0 | Not measured | Not measured | Not measured | not_tested |
| B. Conventional pipeline | 0 | Not measured | Not measured | Not measured | not_tested |
| C. Single-pass AI | 0 | Not measured | Not measured | Not measured | not_tested |
| D. Manufacturing OS | 0 | Not measured | Not measured | Not measured | not_tested |
| E. Incumbent product | 0 | Not measured | Not measured | Not measured | not_tested |

Paired sample: 0; observed effort reduction: Not measured.
- No matched, quality-qualified, timed pair.

### updated

| Group | Attempts | Qualified rate | Human hours, all attempts | Hours per qualified case | Status |
|---|---:|---:|---:|---:|---|
| A. Manual engineer | 0 | Not measured | Not measured | Not measured | not_tested |
| B. Conventional pipeline | 0 | Not measured | Not measured | Not measured | not_tested |
| C. Single-pass AI | 0 | Not measured | Not measured | Not measured | not_tested |
| D. Manufacturing OS | 0 | Not measured | Not measured | Not measured | not_tested |
| E. Incumbent product | 0 | Not measured | Not measured | Not measured | not_tested |

Paired sample: 0; observed effort reduction: Not measured.
- No matched, quality-qualified, timed pair.

### historical

| Group | Attempts | Qualified rate | Human hours, all attempts | Hours per qualified case | Status |
|---|---:|---:|---:|---:|---|
| A. Manual engineer | 0 | Not measured | Not measured | Not measured | not_tested |
| B. Conventional pipeline | 0 | Not measured | Not measured | Not measured | not_tested |
| C. Single-pass AI | 0 | Not measured | Not measured | Not measured | not_tested |
| D. Manufacturing OS | 0 | Not measured | Not measured | Not measured | not_tested |
| E. Incumbent product | 0 | Not measured | Not measured | Not measured | not_tested |

Paired sample: 0; observed effort reduction: Not measured.
- No matched, quality-qualified, timed pair.

## CHO

### raw

| Group | Attempts | Qualified rate | Human hours, all attempts | Hours per qualified case | Status |
|---|---:|---:|---:|---:|---|
| A. Manual engineer | 0 | Not measured | Not measured | Not measured | not_tested |
| B. Conventional pipeline | 3 | Not measured | Not measured | Not measured | pending_measurement |
| C. Single-pass AI | 3 | 0.000 | Not measured | Undefined (zero qualified) | pending_measurement |
| D. Manufacturing OS | 16 | Not measured | Not measured | Not measured | pending_measurement |
| E. Incumbent product | 0 | Not measured | Not measured | Not measured | not_tested |

Paired sample: 0; observed effort reduction: Not measured.
- Repeated assignments require explicit independent pairing; no cherry-picked fastest run.
- Repeated assignments require explicit independent pairing; no cherry-picked fastest run.
- Repeated assignments require explicit independent pairing; no cherry-picked fastest run.
- Repeated assignments require explicit independent pairing; no cherry-picked fastest run.
- Repeated assignments require explicit independent pairing; no cherry-picked fastest run.
- Repeated assignments require explicit independent pairing; no cherry-picked fastest run.
- Repeated assignments require explicit independent pairing; no cherry-picked fastest run.
- Repeated assignments require explicit independent pairing; no cherry-picked fastest run.
- Repeated assignments require explicit independent pairing; no cherry-picked fastest run.
- Repeated assignments require explicit independent pairing; no cherry-picked fastest run.
- Repeated assignments require explicit independent pairing; no cherry-picked fastest run.
- No matched, quality-qualified, timed pair.

- `03b2a5805de34646975f5b17b2fde42b` / CHO-04 / conventional: incomplete, investigation qualification `failed`. Trace: `03b2a5805de34646975f5b17b2fde42b/trace.jsonl`.
  - Emitted field checks: 1300/1300 correct; 0 missing of 1300 expected. Wall clock: 99.780 s. This is technical transcription performance, not investigation qualification.
  - Machine usage: input/output tokens 0/0; tool calls None; inference cost 0.000. Scope: all_model_calls; local_compute_cost_unmeasured.
- `11590541cc714eedbb3c3cdaa3633256` / CHO-04 / full_rlm: failed, investigation qualification `failed`. Trace: `11590541cc714eedbb3c3cdaa3633256/trace.jsonl`.
- `1e0cb85038cb4e34b96cdd309deb6ec3` / CHO-04 / conventional: failed, investigation qualification `invalid`. Trace: `1e0cb85038cb4e34b96cdd309deb6ec3/trace.jsonl`.
- `23f02f7149e446fda4ac41457490d098` / CHO-04 / full_rlm: failed, investigation qualification `failed`. Trace: `23f02f7149e446fda4ac41457490d098/trace.jsonl`.
- `2d55a826bcd249efa556c48ff7beba43` / CHO-04 / retrieval_llm: incomplete, investigation qualification `failed`. Trace: `2d55a826bcd249efa556c48ff7beba43/trace.jsonl`.
  - Emitted field checks: 1300/1300 correct; 0 missing of 1300 expected. Wall clock: 228.128 s. This is technical transcription performance, not investigation qualification.
  - Machine usage: input/output tokens 35946/8962; tool calls None; inference cost Not measured. Scope: all_model_calls; local_compute_cost_unmeasured.
- `3a0256e6c12c4486bffbd480a69eb542` / CHO-01 / full_rlm: failed, investigation qualification `failed`. Trace: `3a0256e6c12c4486bffbd480a69eb542/trace.jsonl`.
- `414d3f7aed164071b8712a8c53855086` / CHO-05 / full_rlm: failed, investigation qualification `failed`. Trace: `414d3f7aed164071b8712a8c53855086/trace.jsonl`.
  - Machine usage: input/output tokens 155909/50040; tool calls None; inference cost Not measured. Scope: root_sdk_session_only; failed_execution_included.
- `4eb2d137e12a4afa858f941d7b01dae1` / CHO-04 / full_rlm: completed, investigation qualification `pending_review`. Trace: `4eb2d137e12a4afa858f941d7b01dae1/trace.jsonl`.
  - Emitted field checks: 1300/1300 correct; 0 missing of 1300 expected. Wall clock: 910.064 s. This is technical transcription performance, not investigation qualification.
  - Machine usage: input/output tokens 111332/141649; tool calls 34; inference cost Not measured. Scope: root_sdk_session_only; child, OCR and tool costs may be missing.
- `64f31ce7c7c84f75b8ece90ca4c4329a` / CHO-04 / full_rlm: failed, investigation qualification `failed`. Trace: `64f31ce7c7c84f75b8ece90ca4c4329a/trace.jsonl`.
  - Machine usage: input/output tokens 0/0; tool calls None; inference cost Not measured. Scope: root_sdk_session_only; failed_execution_included.
- `6534ccdb627c4a538994e2b0d51629b6` / CHO-02 / full_rlm: incomplete, investigation qualification `failed`. Trace: `6534ccdb627c4a538994e2b0d51629b6/trace.jsonl`.
  - Emitted field checks: 1300/1300 correct; 0 missing of 1300 expected. Wall clock: 960.797 s. This is technical transcription performance, not investigation qualification.
  - Machine usage: input/output tokens 123948/114918; tool calls 32; inference cost Not measured. Scope: root_sdk_session_only; child, OCR and tool costs may be missing.
- `6efaaa88f6024220b6d6731077ff7ff0` / CHO-04 / conventional: completed, investigation qualification `pending_review`. Trace: `6efaaa88f6024220b6d6731077ff7ff0/trace.jsonl`.
  - Emitted field checks: 1300/1300 correct; 0 missing of 1300 expected. Wall clock: 113.910 s. This is technical transcription performance, not investigation qualification.
  - Machine usage: input/output tokens 0/0; tool calls None; inference cost 0.000. Scope: all_model_calls; local_compute_cost_unmeasured.
- `7113f26854294d139a4eb6ad242a05a2` / CHO-04 / full_rlm: failed, investigation qualification `failed`. Trace: `7113f26854294d139a4eb6ad242a05a2/trace.jsonl`.
- `73ee3f466445438699267c155077a80f` / CHO-03 / full_rlm: failed, investigation qualification `failed`. Trace: `73ee3f466445438699267c155077a80f/trace.jsonl`.
- `78c5effe0209466a91e4eebc080268f4` / CHO-04 / full_rlm: completed, investigation qualification `failed`. Trace: `78c5effe0209466a91e4eebc080268f4/trace.jsonl`.
  - Emitted field checks: 404/404 correct; 896 missing of 1300 expected. Wall clock: 854.974 s. This is technical transcription performance, not investigation qualification.
  - Machine usage: input/output tokens 92743/135297; tool calls 48; inference cost Not measured. Scope: root_sdk_session_only; child, OCR and tool costs may be missing.
- `7af502d3f16f4715b4a1ae302b00af7a` / CHO-04 / full_rlm: failed, investigation qualification `failed`. Trace: `7af502d3f16f4715b4a1ae302b00af7a/trace.jsonl`.
  - Machine usage: input/output tokens 0/0; tool calls None; inference cost Not measured. Scope: root_sdk_session_only; failed_execution_included.
- `8e2ea639c9ae4176afe6f6b6bcabd8e0` / CHO-04 / full_rlm: failed, investigation qualification `failed`. Trace: `8e2ea639c9ae4176afe6f6b6bcabd8e0/trace.jsonl`.
- `9c3b2df29dab4798acac0c54e11eb8ea` / CHO-04 / retrieval_llm: failed, investigation qualification `invalid`. Trace: `9c3b2df29dab4798acac0c54e11eb8ea/trace.jsonl`.
- `b50ba619d14e41109e8e8d7e64374bac` / CHO-04 / retrieval_llm: failed, investigation qualification `failed`. Trace: `b50ba619d14e41109e8e8d7e64374bac/trace.jsonl`.
  - Machine usage: input/output tokens 63453/12810; tool calls None; inference cost Not measured. Scope: single_pass_provider_response; failed_validation_included.
- `b73a366df9424b17a4f493ca7ed82c53` / CHO-04 / full_rlm: failed, investigation qualification `failed`. Trace: `b73a366df9424b17a4f493ca7ed82c53/trace.jsonl`.
  - Machine usage: input/output tokens 0/0; tool calls None; inference cost Not measured. Scope: root_sdk_session_only; failed_execution_included.
- `ea677006bf174d12bcb053c9370aa09e` / CHO-04 / full_rlm: failed, investigation qualification `failed`. Trace: `ea677006bf174d12bcb053c9370aa09e/trace.jsonl`.
  - Machine usage: input/output tokens 0/0; tool calls None; inference cost Not measured. Scope: root_sdk_session_only; failed_execution_included.
- `ec32259a437d4ccea9dc47bf4ef654c0` / CHO-04 / full_rlm: completed, investigation qualification `pending_review`. Trace: `ec32259a437d4ccea9dc47bf4ef654c0/trace.jsonl`.
  - Emitted field checks: 1300/1300 correct; 0 missing of 1300 expected. Wall clock: 799.651 s. This is technical transcription performance, not investigation qualification.
  - Machine usage: input/output tokens 121435/156186; tool calls 48; inference cost Not measured. Scope: root_sdk_session_only; child, OCR and tool costs may be missing.
- `f5f2023cd2f94316a98b970a23755500` / CHO-04 / full_rlm: failed, investigation qualification `failed`. Trace: `f5f2023cd2f94316a98b970a23755500/trace.jsonl`.
  - Machine usage: input/output tokens 0/0; tool calls None; inference cost Not measured. Scope: root_sdk_session_only; failed_execution_included.
### clean

| Group | Attempts | Qualified rate | Human hours, all attempts | Hours per qualified case | Status |
|---|---:|---:|---:|---:|---|
| A. Manual engineer | 0 | Not measured | Not measured | Not measured | not_tested |
| B. Conventional pipeline | 0 | Not measured | Not measured | Not measured | not_tested |
| C. Single-pass AI | 0 | Not measured | Not measured | Not measured | not_tested |
| D. Manufacturing OS | 0 | Not measured | Not measured | Not measured | not_tested |
| E. Incumbent product | 0 | Not measured | Not measured | Not measured | not_tested |

Paired sample: 0; observed effort reduction: Not measured.
- No matched, quality-qualified, timed pair.

### held_out

| Group | Attempts | Qualified rate | Human hours, all attempts | Hours per qualified case | Status |
|---|---:|---:|---:|---:|---|
| A. Manual engineer | 0 | Not measured | Not measured | Not measured | not_tested |
| B. Conventional pipeline | 0 | Not measured | Not measured | Not measured | not_tested |
| C. Single-pass AI | 0 | Not measured | Not measured | Not measured | not_tested |
| D. Manufacturing OS | 0 | Not measured | Not measured | Not measured | not_tested |
| E. Incumbent product | 0 | Not measured | Not measured | Not measured | not_tested |

Paired sample: 0; observed effort reduction: Not measured.
- No matched, quality-qualified, timed pair.

### updated

| Group | Attempts | Qualified rate | Human hours, all attempts | Hours per qualified case | Status |
|---|---:|---:|---:|---:|---|
| A. Manual engineer | 0 | Not measured | Not measured | Not measured | not_tested |
| B. Conventional pipeline | 0 | Not measured | Not measured | Not measured | not_tested |
| C. Single-pass AI | 0 | Not measured | Not measured | Not measured | not_tested |
| D. Manufacturing OS | 0 | Not measured | Not measured | Not measured | not_tested |
| E. Incumbent product | 0 | Not measured | Not measured | Not measured | not_tested |

Paired sample: 0; observed effort reduction: Not measured.
- No matched, quality-qualified, timed pair.

### historical

| Group | Attempts | Qualified rate | Human hours, all attempts | Hours per qualified case | Status |
|---|---:|---:|---:|---:|---|
| A. Manual engineer | 0 | Not measured | Not measured | Not measured | not_tested |
| B. Conventional pipeline | 0 | Not measured | Not measured | Not measured | not_tested |
| C. Single-pass AI | 0 | Not measured | Not measured | Not measured | not_tested |
| D. Manufacturing OS | 0 | Not measured | Not measured | Not measured | not_tested |
| E. Incumbent product | 0 | Not measured | Not measured | Not measured | not_tested |

Paired sample: 0; observed effort reduction: Not measured.
- No matched, quality-qualified, timed pair.

## Limits and next measurements

Draft investigation and routing policies await independent domain approval. Human timers and blinded reviews must be collected; legacy supplied estimates are not v2 measurements.
Raw, clean, held-out, updated and historical conditions remain separate. Existing CHO data have been inspected during development, so no untouched generalization claim is supported.
Root-session Prime token/cost counts exclude child usage unless independently captured. Unknown costs remain unknown.
Existing v1 parser scores and modeled simulations remain in the supporting report; they are not migrated into qualified-case scores.
