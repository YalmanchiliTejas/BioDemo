# Saved assay demo review

Local change, 2026-11-02. User-authorized temporary demo path while broader agent evaluations are developed. No deployment or production-account modification performed.

## Behavior

Questions about deviations or assays can use a rule-based calculation over the owner's saved synthetic assay sources. The handler reads original `assays.csv` and `specifications.csv` text, selects the applicable source specification, compares inclusive limits, and produces a short answer, chart, table, source-row references, and review steps. It does not use previous assistant conclusions. Asking why or what next after this answer retains the same path and leaves cause unresolved.

The customer-facing component is titled **Deviation review** with a **Sample data** label. Implementation terminology is omitted from that view. Internal method, source revisions, and execution mode remain recorded accurately. This path makes no model requests and must not be counted as an agent-accuracy evaluation or a real GLM run.

Selection uses the most recent saved synthetic review, or an explicitly requested `deviations-NN` label. Saved time is not represented as manufacturing event time. The handler checks tenant, site, owner, source revision and lineage. Changed sources make old answers stale. Existing formal cases retain the regular agent path unless the person explicitly requests a demo/sample. Other questions retain existing agent behavior.

The six-row fixture produces three flagged values, 1, 9 and 11 mg/L, against inclusive 2–8 mg/L bounds; 2, 5 and 8 pass the comparison. Missing/nonfinite values, duplicate result IDs, malformed tables and ambiguous specifications require source review. An `available_at` timestamp is a test-time proxy, not verified test execution time. This qualification remains in source details.

No formal deviation, proposal, approval or manufacturing action is created by this response. Next steps are displayed instructions for human review.

## Verification

- New calculation and permission tests plus conversation/gateway tests: **65 passed**.
- Existing CI selection plus the new demo tests: **159 passed in 77.56 seconds**.
- Frontend `npm run lint` (TypeScript) and `git diff --check`: passed.
- An isolated browser preview displayed **Deviation review**, six assay rows, a chart and four next steps. The page contained no implementation-mode wording and no false LLM-run badge.
- The preview provider was configured to throw on any inference attempt; the review completed successfully.

Screenshots: [initial reply](../../output/verification/assay-demo-review-20261102/review.png), [findings](../../output/verification/assay-demo-review-20261102/findings.png).

After deploying both API and frontend, use: **What are the recent deviations and what should be done next?** The account must already contain authorized synthetic CSV reviews, as the supplied account does. This change does not seed or overwrite customer data. Refreshing an old failed answer requires a new question; historical replies remain unchanged.
