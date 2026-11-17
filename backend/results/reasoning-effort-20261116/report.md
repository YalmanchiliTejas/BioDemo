# Reasoning level of the assistant's tool loop: live comparison, 16–17 November 2026

Real GLM-5.3 calls to the configured Modal endpoint. The question, findings and decision are in
[the speed note](../../../docs/research/assistant-speed-20261116.md); this folder holds the records.

Every run was in process on one laptop, one request at a time, on fresh local stores holding public or authored
data. No production database was used. One attempt per case: indications, not rankings.

## Results

| Evaluation | max (nothing sent) | high | low | high, max from the first saving step |
|---|---|---|---|---|
| Requests the host calculates: objective checks | 12/12 | 12/12 | 12/12 | same code path as high |
| ...mean time | 34.6 s | 8.6 s | 8.6 s | |
| Open "compare" requests: all reference figures | 2/3 | 3/3 | 2/3 | same code path as high |
| ...mean time | 33.6 s | 9.1 s | 4.1 s | |
| Open "why" requests: all reference figures | 1/3 | 1/3 | 0/3 | same code path as high |
| ...mean time | 98.3 s | 35.4 s | 10.6 s | |
| Multi-step cases: strict grader | 6/12 | 7/12 | not run | 8/12 |
| ...mean time | 118.4 s | 33.9 s | | 111.2 s |
| ...nothing saved | 3 | 0 | | 2 |
| ...a wrong value saved | 0 | 2 | | 0 |

"Same code path as high": none of those requests calls a tool that saves a proposal or a result, so the rule does
not apply to them. That is covered by unit tests, not by a live run.

## What is in each folder

| Folder | What ran |
|---|---|
| `answers-max-default`, `answers-high`, `answers-low` | `benchmarks/skills/answers.py`, one repeat, one worker |
| `assistant-max-default`, `assistant-high`, `assistant-low` | `benchmarks/workflow_trial/live.py`, assistant arms only, one worker. The explanation call was left at max in all three, as a control |
| `multistep-max-default` | Twelve cases of the 16 November freeze-drying set (the first three of each family), its references and grader |
| `multistep-high` and `multistep-high-rest` | The same twelve at high. The first folder's last six cases were refused by this measurement's own spending cap before any model call; they were rerun into the second |
| `multistep-high-then-max-before-saving` | A first version of the rule, which re-thought each saving step singly. Kept as run; its last two cases were refused by the cap. Superseded |
| `multistep-high-careful-saves` | The rule as shipped: the first saving step is taken again at max, and the turn stays there |
| `drivers/` | The scripts that ran the series and made the summaries |
| `summary.json`, `multistep-summary.json`, `progress.json` | Numbers behind the table, and the first series' running cost estimate |

The multi-step runs are not frozen-protocol runs: the application code has changed since 16 November, so they
compare levels on one day and nothing more. The multi-step folders hold each case's working database (66 MB in
all); the traces used for every figure here are in the `result.json` files beside them.

## Cost

About $6.50 at Modal's list prices from the endpoint's own token counts, cached input at its lower price, probes
included. The cached share of the three `assistant-*` runs was not kept and is assumed to be like the others; with
none of it cached the total is about $7.60. The harness's own count prices every input token as uncached and comes
to about $13. The Modal usage page is the authority.

## Limits

- Small samples, one attempt each, one model, one endpoint, one day.
- Objective checks and reference figures are necessary, not sufficient. Nobody qualified has read the answers.
- The multi-step cases are authored simulator tasks through a research connector that production does not have.
- Three "missing input" cases fail the strict grader at every level for wording it does not accept.
