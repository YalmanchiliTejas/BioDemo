# Workspace flow

The current visual presentation is documented in [workspace template refinement](workspace-template-refinement.md); this document records the underlying work navigation.

Governing source: [Main_Culture_andETHOS.md](../../../Main_Culture_andETHOS.md).

The job is to resume a question or goal, inspect its context, challenge its interpretation, and keep a reviewable next step with the original work. The previous large composer hid resumed work; evidence, scientific tools and global actions fragmented that context.

A small option was to reduce the welcome banner and rearrange shortcuts. The selected option also introduces work-level views, using the existing model, evidence viewer and charts. Overview, Evidence, Trends, Next steps and Notes are freely accessible views, not mandatory stages. Expert scientific tools remain available with an explicit return to the originating work. No data migration or new service is required.

- Easy to Start: recent work is visible first; a focused editor accepts a goal with optional sample context. Landing handoff preserves exact text and context without silently creating work.
- Easy to Trust: the overview separates the calculated result, hypothesis, counterevidence and unknowns. Evidence opens source queries, rows and limits in place. User goals remain drafts; attaching sample context does not claim fresh analysis.
- Easy to Act: proposals and recommended checks are scoped to the work. Reviews, progress and observed outcomes retain their separate recorded states. A simulated quality review remains available without claiming approval or execution.
- Easy to Adopt: familiar tabs, search, source viewers and charts reuse existing capabilities. The supplied landscape and controllable ambient motion remain in a compact header. Existing source systems remain systems of record.

Trade-offs: new work requires opening a focused editor, while resumed work gets immediate priority. Source administration and the cross-work action list remain separate workspace views. Work tabs are URL-addressable and survive reload and browser history; transient chart selections remain local to the current work view. Work and action records remain browser-local, with visible recovery/export paths.

Observable checks: saved work visible without desktop scrolling; source inspection returns to the same evidence view; Back and reload preserve the selected work tab; scientific tools return to the originating work; actions from another work item never appear in a scoped view; a consumed new-work request does not reopen on return; landing draft text and context survive handoff; every work view fits widths from 320 to 1440 px. Browser checks exercise these behaviors; they do not establish real organizational time savings or scientific validation.

Verification scripts: `check_workspace_flow.cjs`, `check_ethos_workspace.cjs`, `check_reference_refresh.cjs`, `check_workspace.cjs`, `check_atmosphere.cjs`, and `test_workspace_model.cjs` under `frontend/scripts`.
