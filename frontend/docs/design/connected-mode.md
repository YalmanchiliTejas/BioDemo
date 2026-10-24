# Connected mode

Governing source: [Main_Culture_andETHOS.md](../../../Main_Culture_andETHOS.md).
Sample mode (browser-local, no network) stays the default and is unchanged.
Connected mode is an explicit, reversible choice that reads and writes through the
`/v1` HTTP API (`backend/src/lifesci/api.py`).

## Job and alternatives

A person who already has goals, proposals and approvals on the server should be
able to continue them from `/app` without export, import or a second tool.

| Option | Benefit | Cost |
| --- | --- | --- |
| Replace the local workspace with the server | One code path | Breaks the offline sample, forces setup before first use |
| **Chosen:** keep both, gate the server path behind `connection.mode === "connected"` | Sample needs no setup; server mode is opt-in and can be left at any time | Two data sources; sample work is not copied to the server (stated in the connection sheet) |

## Pillars

- Easy to Start: connect with a tenant and person; the first server goal needs no other setup. The goal is saved with the signed-in person as owner and their sites as scope.
- Easy to Trust: the server is the system of record for roles; the client never sends a role. Basis shows evidence titles and revisions; a mission-only basis reads "User-authored — no source evidence linked". Stale reasons, approval history (who, role, comment, sign-in method) and outcomes are shown, never hidden.
- Easy to Act: decision, delivery, outcome and effectiveness are shown as four separate facts. Approve/Reject appear only for roles the server lists in `can_decide`. High/critical risk needs the development-only attestation, which is labelled as such. Outcomes need evidence from the proposal basis and attribution limits.
- Easy to Adopt: no new dependency; the Vite dev server proxies `/v1` to `127.0.0.1:8100`. Development headers are used today; the client has one place (`api/client.ts`) to swap in bearer tokens for SSO.

## Files (`src/os/api/`)

- `types.ts`, `client.ts`: wire types, typed fetch client, readable errors, `Idempotency-Key` on POSTs.
- `connection.ts`: `manufacturing-os:connection:v1`; decoding never throws and never overwrites a corrupt value.
- `mapping.ts`: pure display mapping (no React) — the status labels, basis labels, stages.
- `ConnectedWorkspace.tsx`: provider, `/v1/me` and `/v1/health` loading, `useOpenMission` (polls the stream every 5 s).
- `ConnectedViews.tsx`, `ProposalCard.tsx`, `ProposeSheet.tsx`, `ConnectionSheet.tsx`: views and sheets.
- `../connected.css`: the few styles these views need.

`Hub.tsx` chooses connected or sample views; `WorkspaceShell.tsx` swaps the context strip, recent work and identity display only when connected.

## Status vocabulary

| Server state | Label |
| --- | --- |
| proposed | Awaiting approval: <roles still needed> |
| approved, queued | Approved — not yet sent |
| stale, or awaiting_reassessment | Evidence changed — needs reassessment |
| rejected | Rejected |
| delivered | Sent to <system> |
| unknown | Delivery unconfirmed — reconciling |
| outcome recorded | Outcome recorded (effectiveness shown separately) |

## Live updates

The open mission polls `/v1/missions/{id}/stream?after=<cursor>` every 5 s (paused while the tab is hidden) and reloads proposals when events arrive. The stream only carries events that name the mission, and approval/outcome events currently do not, so proposals are also re-read every 30 s. A decision is protected by `expected_revision`; a conflict closes the sheet and asks the person to review the current version.

## Observable checks

`node scripts/test_connected_mapping.cjs` covers every label, the user-authored basis label, corrupt-connection decoding, error messages and request headers. `node scripts/test_workspace_model.cjs` and `npm run build` must still pass. Browser behaviour was exercised against a seeded dev server; these checks are not evidence of validation or compliance.
