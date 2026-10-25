# 32-screen Manufacturing OS implementation — decisions

Source: handoff packet `MOS-CODEGEN-HANDOFF-v1.1` (written spec only; the referenced Stitch
frames and `STITCH_MANUFACTURING_OS_COMPLETE_SPEC.md` were not available, so screens were
built from the text specification, tokens, fixtures and component contracts).

## Job to be done

Give MSAT, QA, supervisors and operators a demonstrable, end-to-end path from “something is
off in campaign CMP-26-10” to a reviewable, signed decision: notice (Home, Opportunities) →
verify (Workbench, Batch, Timeline, Lab) → reason (Investigation) → propose (Optimization,
Planning, Transfer) → document and approve (Documents, Reviews), with the cleanroom tablet
covering the same incident at the point of work.

## Decisions and trade-offs

| Decision | Alternatives considered | Why / trade-off |
|---|---|---|
| Replace the Vite SPA in `frontend/` with Next.js 14 static export | New app alongside; embed in Vite | Chosen by the user. Static export to `dist/` keeps the existing nginx Docker image working (`trailingSlash` lets `try_files $uri/` resolve). Cost: the `/app` connected mode to the backend `/v1` API and the `/benchmarks` viewer are no longer in the UI. |
| Literal route folders (`batches/MES-26073`) instead of dynamic segments | `[batchId]` + `generateStaticParams` | Matches the route map exactly with no fake “any id works” behaviour; unknown ids 404 with an explanation. Trade-off: adding real records later needs dynamic routes. |
| One evidence registry (`CITATIONS`) behind every chip | Free-text citations per page | Easy to Trust: every chip resolves to an excerpt, timestamp, transformation and hash in the same inspector. |
| `ClaimTag` on findings | Colour alone | Ethos requires distinguishing observation / calculation / hypothesis / proposal / unknown. |
| Spec compliance claims softened | Ship spec text verbatim | The spec asked for “GAMP 5 Category 4 / Fully Qualified” and Part 11 sign-off. Without evidence these are false claims, so copy says “designed to support” and demo signatures are labelled as not Part 11 records. |
| Confidence → match score / fit statistic | Show “99.4% confidence” | Uncalibrated numbers must not read as probability of correctness. |
| Simulated agent run in global state | Static banner | The run strip appears only while work is in progress, can be stopped, and finishes by asking for review — never auto-applies. |
| Role switch in header and Home | Separate apps per role | Easy to Adopt: one experience with different entry points. Labelled as demo-only; production roles come from the IdP. |

## Observable checks

- Every CTA in the handoff route table navigates to its target (see `lib/routes.ts`).
- Every factual claim on a screen opens a source excerpt in ≤1 click.
- No screen states a cause without a hypothesis/contradicted label; no signature path writes
  outside the browser.
- `npm run build` produces all 32 routes as static HTML.
