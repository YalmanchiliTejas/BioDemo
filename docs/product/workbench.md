# The workbench: working in the evidence, not in a conversation

Date: 2026-11-15. Governed by [Main_Culture_andETHOS.md](../../Main_Culture_andETHOS.md). Builds on the
[trial architecture](../architecture/sievance-fast-workflows-trial.drawio) (page 2) and the
[trial note](../research/workflow-trial-20261114.md).

## The job

QA, MSAT and process engineers do not ask their data many questions. They **consolidate** it, **see** what is
happening, **decide the next steps**, and **act**. A chat window makes them describe in words what they would
rather select, hides the evidence behind prose, and loses the plan when the conversation scrolls away. A design
partner said the same thing from the other side: select fields, show the evidence visually, never make me open
the original document, and do not make me wait.

The product has to hold that sequence and keep it.

## What was considered

| Option | What it is | Why not, or why |
| --- | --- | --- |
| Keep the assistant as the frame | Chat with tools; results as attachments | Measured at 148–285 s per answer. The person types what they could select. The plan lives in a transcript. |
| Add panels to Trends | Compare, gaps and action buttons beside the chart | Quick and familiar, but nothing is kept: the selection, findings and decisions disappear on reload. |
| **A workbench with a working file** | One surface in the person's own order, saved as a work plan | Chosen. It costs a new page and one new record, and keeps what was looked at, decided and done. |

The assistant stays, as a tool inside the workbench rather than its frame: one bounded explanation of the picture
on request, and a hand-off of the current result for a longer investigation.

## The surface

One scrolling page, four regions, no wizard. Each feeds the next; none is forced.

1. **Data in view.** Deliveries, batches, parameter and time window are selected, not typed. A delivery still in
   review is used only when the person ticks "Include values still in review". A line under the controls says
   what is in view: values, batches, parameters, open checks, conflicting sample times.
2. **What the data shows.** A line per batch, the comparison per pair with its spread, and whether the batches
   share product, process version, equipment, scale and stage. Selecting a value shows the file and location it
   came from. The picture recalculates when the selection changes; there is no run button.
3. **Gaps and findings.** Conflicts, differing context, evidence missing against the site's approved
   requirements, values in review. Each finding carries its own action: ask for the evidence, trace a lot or
   equipment, list causes to check, explain the picture.
4. **Next steps.** A checklist the person owns. A step can come from a finding, be a request sent to a
   colleague, or be an action proposed for review. Each shows where it stands, read from the proposal or request
   itself.

## What is kept, and by whom

- **The work plan** is the person's private working file: the selection, the results it cites, and the steps.
- **Results** are saved only when something cites them: a step, a request or a proposal. Looking does not write.
- **Proposals, approvals, dispatch and receipts** stay with the action service. A step points at a proposal and
  reports its standing; it never approves or carries anything out. "Approved" is shown as "approved, not yet
  carried out" until there is a receipt.
- **Requests** go to a named person and stay attributed to them. The person asked sees the request on their
  Overview and replies there; the reply comes back to the step ([the worklist](worklist.md)).
- **Systems of record are untouched.** Batch context is read from records projected from the MES; nothing is
  written back.

## The four pillars

| Pillar | What this removes | What it could cost |
| --- | --- | --- |
| Easy to start | No setup: the first picture appears with nothing typed, on the latest verified delivery. | The default selection may not be the one wanted; it is one click to change. |
| Easy to trust | Every figure is calculated by the host and traceable to a file location. Missing context is shown as not recorded, never assumed equal. Values in review are labelled. | A model explanation is still a model's wording. Its numbers must all appear in the result, or it is withheld. |
| Easy to act | Findings turn into steps, requests and proposals in place, with who must approve. | A second place to see proposals. The standing is read from the action service, not copied. |
| Easy to adopt | Dropdowns, a chart, a table and a checklist. No new operating model, no migration. | One new page beside Trends and the assistant. If it earns its place, the assistant's Work tab can be retired. |

## How we will know

- Time from opening the page to the first useful picture, with nothing typed.
- Share of pictures that update within the 10-second target (measured on every request).
- Share of findings that become a step, request or proposal, and share of steps that are closed with an outcome.
- Share of proposals approved without revision, and time waiting for approval.
- How often people open the assistant from the workbench, and for what: a high rate means the surface is
  missing something.

None of these is measured yet. The browser checks establish that the page behaves as designed against fixed
responses; they say nothing about whether engineers find it quicker.

## Trade-offs made

- **A picture that follows the selection** needed an unsaved preview, so a saved result exists only once
  something cites it. A person who wants to keep a picture without acting adds a note step.
- **Reads are sequential.** A template's tasks run as parallel flow nodes, but the store serializes reads, so
  the gain is small. A whole picture measures about 30 ms; it was not worth more machinery.
- **Requirements are approved specifications only.** Procedures and sampling plans are not read for gaps yet.
- **Recorded usage is read per request** from executed steps. It is honest about batches with no recorded
  steps, and it is not a maintained genealogy index.
- **Physical models are not in direct tasks.** They need a model context per process and stay in the model
  library, reached through the assistant.
