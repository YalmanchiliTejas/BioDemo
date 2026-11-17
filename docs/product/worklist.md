# The worklist: the assistant does the work, people decide

Date: 2026-11-16. Governed by [Main_Culture_andETHOS.md](../../Main_Culture_andETHOS.md). Follows
[the workbench](workbench.md) and the [proactive assistant contract](proactive-assistant-architecture.md), and takes
up Direction B of the [shell brief](workspace-shell-design-brief.md), which was held back until real events existed.

This note records a change of interaction model, what was built for it, and what was not. Nothing here is a
measured improvement or a manufacturing validation. The outside evidence it leans on is in
[the evidence synthesis](../research/agent-interaction-evidence-20261116.md).

## The job

Process engineers, MSAT and QA gather the relevant data, see it, keep track of it, get the paperwork done, close the
gap between two processes, and must leave nothing out. The owner's direction (2026-11-16): a chat window is weak
for this, a dashboard only reports, and the product should be an agent that takes real actions.

## What the product did before

- **The assistant could not finish anything.** Every tool it has reads, calculates or drafts. A proposal it or a
  person drafted could be approved only through the API: no screen listed proposals or let an approver decide. A
  Workbench step could read "waiting for approval" indefinitely.
- **A request to a colleague went nowhere.** The Workbench sent it and said it "appears in their work". Nothing
  listed requests for the person asked, and a request could not be answered or leave `open`.
- **Nothing said what was waiting on a person.** That state was spread over the conversation, the bell, Overview
  counts, Workbench plans, the quality queue, routines, investigations, signals and settings.
- **Chat was the slow path.** The trial measured routine work at about 0.01 s by host calculation against 127–197 s
  through the assistant, and the design partner asked for selecting over typing and for no waiting
  ([trial note](../research/workflow-trial-20261114.md), `docs/feedback,txt`).

So the limit was not the model. The loop from "the system found something" to "a person decided and it was done"
was open in the interface.

## What others ship, and what the evidence supports

From the [evidence synthesis](../research/agent-interaction-evidence-20261116.md); vendor rows are vendor claims on
the date fetched.

- **"Competitors only bolt a chatbot onto a system of record" does not hold as a blanket claim.** Apprentice says
  A1 "is not a chatbot": it runs on alarms, events, schedules and file changes, follows steps the user defines, and
  drafts CAPAs, deviations and reports. Veeva documents background agents that complete workflow tasks. Benchling
  and Tulip document triggered agents that can change records. It does hold for some (Körber, Emerson, Kneat).
- **A queue of agent work with states is not new either.** Seal markets a job list with "Working", "Needs your
  input" and "Ready to review", and says its agent "signs, approves and releases nothing".
- **What nobody evidences:** any independent account of an agent working in GMP production; a technology transfer
  run as one owned object across sponsor and CDMO, with its gap assessment, facility fit, documents and open items
  together; a reviewable record of what was searched, found, missing and excluded; and any measurement of whether
  human review of agent output actually catches errors.
- **Approval prompts are a weak control on their own.** In one vendor's data people approved 97% of permission
  prompts and caught 13.6% of planted dangerous commands, but rejected 39% of whole plans. Review a proposal, not a
  step; put the gate at what cannot be undone; do not make disagreeing cost more than agreeing.
- **Regulation leaves room for an agent that prepares and proposes, and none for one that decides.** Draft EU GMP
  Annex 22 (a consultation draft, not adopted) says large language models "should not be used in critical GMP
  applications"; an FDA warning letter of April 2026 requires quality-unit review of AI output; signatures stay with
  named people.

So the worklist is not the moat. It is the floor: without it nothing the system prepares can be finished. What
could be distinctive is listed under "Not done".

## What was considered

| Option | What it is | Why not, or why |
| --- | --- | --- |
| Improve the chat | Better prompts, streaming, more tools in the conversation | Leaves the person as scheduler and memory: they must know what to ask, wait, and find the result again. Does not close the approval or request loop. |
| A status dashboard | Counts per area with links (the Overview as first built) | Reports work; does none. A count of open signals is not the signal with its decision. |
| **A worklist the system fills and people decide from** | One list per person: what needs them, what is in progress, what was finished, each decided in place | Chosen. It needs no new store and no new agent runtime: it reads the records that already exist and closes the two loops that were open. |
| A conversation-free autonomous agent | The assistant acts across systems on standing authority | Not operable today: outbound writes need connector write scope that only seed scripts assign, and consequential actions rightly need a person. Revisit per action once the loop below is in use. |

## The model

1. **Work starts from an event or a standing instruction, not a prompt.** A published delivery is checked against
   the site's approved requirements at once. A signal is raised by detection. A person can still ask.
2. **The system does everything up to the decision.** It reads, compares, checks for what is missing, and drafts the
   request or the proposal. It sends nothing and approves nothing.
3. **A person decides in one place, with what the decision rests on in view.** Then the owning service carries the
   decision: a request reaches the colleague, an approval is recorded against the exact revision.
4. **Everything leaves a receipt.** What was waiting moves to in progress, then to done, with who and when.
   An approval is never shown as carried out without a receipt from the system that carried it out.

Chat remains, as one way to ask an open question. It is no longer where work has to live.

## The surface

The Overview now opens on the worklist, above the summary cards.

- **Needs you.** Approvals this person may decide (the proposal's action, reason, expected result, who drafted it,
  what it rests on, the host's own account of the result it cites, who must approve, its conditions; approve, or
  decline with a reason, with common reasons one click away). Requests from colleagues (reply in
  place). Questions the assistant asked (answer in place; it continues). Open signals they may decide
  (acknowledge in place; the evidence is one click away). Missing evidence found in a new delivery, with the
  request already drafted (choose a colleague, send). Quality events and delivery checks waiting on them (open).
- **In progress.** What they started that waits on someone or something else: a proposal with its approvers, an
  approved action a connection here can carry out, a request not yet answered, the assistant working, a delivery
  being read.
- **Done in the last week.** Replies received, proposals approved, declined or carried out, answers finished, deliveries
  checked with nothing waiting.

The list states what it reads and what it does not yet read. A source that cannot be read is named, and the
headline then never says that nothing is waiting.

## What is kept, and by whom

- **The worklist owns nothing.** Each item is read from its own record under the reader's current access; each
  decision goes through the owning service's existing endpoint. The worklist cannot approve, send or change.
- **Requests** stay with the routine service. They gained a reply: one, by the person asked, recorded with their
  name and time. A reply is their statement, not verified evidence. Both people are told in the app.
- **Proposals, approvals and receipts** stay with the action service. High-risk approvals still need a recent
  sign-in; the proposer still cannot approve; an agent still cannot approve. A proposal now also records where it
  came from: that the assistant drafted it, and what the cited result says in the host's words. That record informs
  the approver; it is not part of what is approved. The account is shown only while the proposal still rests on the
  result it describes, and anyone who revised the proposal is named beside its author.
- **The automatic delivery check** is a host calculation: no model call, nothing sent. Its result is the saved gap
  check of the person who published the delivery, private to them like any task result.
- **Systems of record are untouched.**

## The four pillars

| Pillar | What this removes | What it could cost |
| --- | --- | --- |
| Easy to start | Nothing to ask and nowhere to look: what needs a person is on the first screen, with the work already done up to their decision. | One more request on the landing page. |
| Easy to trust | An approval shows what the proposal states, who drafted it, and the host's own account of the result it cites, before the decision. The list names what it covers and what it could not read. Nothing is approved or sent by the system. | An approver reads an account of the cited result, not the result: saved results stay private to their author. Approving can only be done from the opened proposal, which costs a click. |
| Easy to act | The approval and request loops close in the product. A drafted request is one choice and one click from sent. | A second place where proposals and requests appear, beside the Workbench step that raised them. Both read the same record. |
| Easy to adopt | Rows, a reply box, approve and decline. No new operating model and no migration. | People must learn that the Overview is where decisions arrive. |

## How we will know

- Time from a proposal being drafted to its decision, and the share decided at all (before: none in the product).
- Share of proposals declined, by approver. A rate near zero is the warning sign the evidence describes: review that
  has become a formality.
- Share of requests answered, and time to the reply.
- Share of drafted requests that are sent, sent unchanged, or dismissed: a low rate means the check asks for the
  wrong things.
- Items decided from the worklist against items opened elsewhere to decide.
- How often the list reports a source it could not read.

None of these is measured yet. The checks establish that the list and its decisions behave as designed against
fixed records and fixed responses.

## Trade-offs made

- **Reads are filtered and trimmed in the database** (`Transaction.select`), so the list is a few small queries. It
  never loads a chat turn's transcript, a signal's full history for display, or a delivery run.
- **Delivery review is counted, not loaded.** "6 values and 1 issue to check" is counted per run in SQL and agrees
  with each run's own summary. A run with nothing to decide but content still unaccounted for is not listed.
- **Only the latest turn of a person's 12 most recent conversations is read.** An older unanswered question is not
  listed.
- **The automatic check runs for verified deliveries only**, once per delivery revision and person, when the
  delivery is published. A requirement approved afterwards does not re-check earlier deliveries.
- **Signals are acknowledged in place; a case is opened on the signal page**, where the evidence and the owner and
  reviewer choice are.
- **Nothing is polled.** The list is read on arrival, after each decision and when the person returns to the tab.

## Not done

Where the evidence says nobody has shown it working, in the order they follow from what exists here:

- **A transfer as one owned object across both companies**: the sending and receiving process side by side, each
  difference with an owner and an open request, the documents drawn from it. The pieces exist unconnected: transfer
  packages, the pre-transfer check, the Workbench comparison, and now requests with replies.
- **A completeness record as an artifact**: what was searched, found, missing, excluded and why, for a whole piece
  of work. Today that is stated per surface (delivery accounting, the gap check, the worklist's own coverage line).
- **Measured review**: decline rates, time with a proposal open, overrides by site and product.

And what this change leaves open:

- Carrying out an approved action. Dispatch is still a manual API call, and needs a connection with write
  permission, write ownership of the record class and an executor role; only seed scripts assign the last two. The
  list keeps an approved action in progress only where a connection here could carry it out. Where none can, which
  is every deployed workspace today, it reports the approval as what happened and says the action itself is still
  to do; nothing here can record that it was done.
- Letting an approver open the result a proposal rests on, as opposed to reading the host's account of it.
- Routine and rule drafts, investigations waiting to start, and record reviews for connected sources: listed as
  not covered.
- A document from the work (a gap assessment, a request letter, a review package). Output is still CSV, XLSX or
  JSON.
- Comparing a sending and a receiving process as two sides. The Workbench compares batch pairs on one parameter.
- A demo visitor's list shows the two seeded signals and the prepared check of the seeded delivery. It shows no
  approval, because nothing in the seed proposes an action for the visitor to decide.
