# Interaction study v3, revision 2: familiar first

Run `cd ui && npm run dev`, then open http://127.0.0.1:5180/concepts (keys **1–4** switch; add `&instant` to skip the detection sequence). The main app at `/` and the FastAPI and Prime Agent code are unchanged.

## The brief for this revision

People who are used to the old environment (historian, MES, LIMS, QMS) should not be shocked by it, and their work should get easier. So:

- **Their screens, their words.** Work queue, Batches, Trends with a pen list, Lab results, Events and alarms, Deviations. Tabs, tables, a list with a detail pane, a status bar.
- **The agent is "the Assistant", never a new kind of screen.** It shows up as one more row in the work queue, a pen on the trend ("Added by Assistant"), drafted sections in the deviation form, and a side panel. Its symbol and the word Draft mark everything it did.
- **Every claim points to its record** in the system it came from (LIMS sample, historian tag, MES step).
- **One explanatory line** for the one new thing, dismissible ("Got it").
- **Nothing is submitted by the Assistant.** People tick Reviewed and send, or save with their QMS's own button.

## taste-skill

Style redrawn from `editorial-greeting` to **`framed-sheet`** (light), the reason recorded: the product is used through long shifts like the historian and MES beside it, not glanced at like a personal home. The style's move: one tinted L-frame for the sidebar and the 48 px top bar, the work on a white sheet inset 8 px, a 2 px underline on the active tab. Face: the frame tinted a fermenter green-grey. Type: IBM Plex Sans, with IBM Plex Mono for tags and sample IDs only. Signature element: the batch phase strip from the MES batch record (Batch, Fed-batch, Harvest) with the alarm and maintenance marks.

Gate results: lint **0 FAIL, 0 WARN**. Inspector at 1440/768/390: A **clean**, B **0 FAIL** (1 warn: a tab label 12 px from the phone edge), C **0 FAIL** (1 warn: the simulated host keeps its own Segoe UI face, on purpose), comparison **0 FAIL** (1 warn: a centred reading column).

## The three concepts

- **A · Work queue.** The shift's to-do list with a detail pane. The Assistant's finding is the first row (High, New); its prepared records (harvest record, cleaning verification) carry its symbol. Selecting the finding shows the summary, the titer chart, the evidence lines (one click to the source record) and the plan. ↑ ↓ move through the queue; R reviews.
- **B · Batch record.** The batch header with the phase strip, then the usual tabs: Summary, Trends (pen list, reference added as a pen), Lab results (LIMS table with reference ranges), Events and alarms, and Investigation (the deviation form, each section drafted by the Assistant with a Reviewed tick). The Assistant panel on the right answers by opening the right tab, and says what it opened.
- **C · Inside your apps.** Their own historian and QMS, unchanged. The Assistant is a small button that opens a side panel, can add the reference band to their trend, and drafts the QMS form for them to check and save.

## Recommendation

Roll out **C first** (nothing to learn), make **A** the daily start (a queue is how a shift is already planned), and keep **B** for digging in. Times were not measured; interactions to a source record are 1, 2 and 3 for A, B and C.

## Sample data to replace

Everything lives in `frontend/src/lab/scenario.ts`: the work queue, batch record, lab results, events, vessels, batches F-2377 to F-2410, people, tag names, LIMS samples, QMS event EV-2026-0418 and the connector scopes.
