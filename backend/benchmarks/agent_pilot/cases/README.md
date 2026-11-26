# Authored cases

One JSON file per case. These are the only cases that measure the agent on situations a
domain expert recognises; synthetic worlds and perturbations measure regressions.

| Field | Meaning |
|---|---|
| `id`, `family` | Unique slug; `expert` or a pilot family |
| `review_status`, `reviewer` | Must be `reviewed` with a named reviewer to grade the agent |
| `provenance` | Where the content came from (expert-written, public FDA 483 / warning letter, harvested correction) |
| `prompt`, `followups` | Exactly what the user types |
| `sources[]` | `{key, content}` records seeded into the workspace; the agent must discover them |
| `cases[]` | Optional `{key, description, source_keys}` case records linking sources |
| `truth.required_read` | Source keys the agent must inspect |
| `truth.required_facts` | Statements a correct answer must make (judge-graded) |
| `truth.forbidden_claims` | Statements that make an answer wrong or unsafe |
| `truth.banned_tokens` | Exact strings a correct reply cannot contain (deterministic) |
| `truth.answerable` | `false` when the right answer is "the evidence does not say" |

Write at least a third of cases as unanswerable or partially answerable. Never put
customer data in this repository; keep real or harvested cases in a git-ignored directory.

`cmo-aggregation/` holds six AI-drafted cases from a customer interview (cross-CMO units, superseded retests, conflicting results, missing units, site filtering, resent rows). They are `draft` and run only with `--allow-unreviewed`, whose report says it is development signal. A QA/MSAT reviewer must check the expected answers, especially whether conflicting CMO and in-house results should be called a failure, before setting `reviewed`.

`examples/` shows the format and is intentionally not runnable (`review_status: example`).

**Sealed held-out set:** keep a separate directory nobody debugs against and run it only
before a release with `--suite authored --cases-dir DIR --sealed`. The report shows
aggregates only, and `DIR/SEAL_LOG.jsonl` records every use; after you read its
individual failures, move those cases into the development set.
