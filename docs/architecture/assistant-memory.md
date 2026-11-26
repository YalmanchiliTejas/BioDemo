# Assistant memory

Status: implemented 2026-11-07. Governing direction: [the four pillars](../../Main_Culture_andETHOS.md). Builds on the
[tool loop](assistant-tool-loop.md) and [per-user memory privacy](../../backend/src/lifesci/memory.py). Reference:
Anthropic, [The components of agent memory](https://www.anthropic.com/research/components-of-agent-memory) (2026-11-06).

## Job

The assistant should build on earlier work, for the same person and across conversations: remember what it learned, what
the person decided and prefers, and what is still open, and find it again when asked in different words. In a regulated
plant it must never let memory stand in for the records.

## How a note changes over time

Open the [current system architecture in draw.io](sievance-current-architecture.drawio) and select **04 · Assistant memory**. Follow the diagram from a finished turn or a `remember` call to a later turn that uses memory.

1. **Saving the turn and saving a note are two writes.** A finished reply stays in its conversation. The tool loop can index its question and answer for recall, and the conversation service marks the owner active. A note is created or reaffirmed when the model calls `remember` or when consolidation proposes a note that passes the same write checks. The note has its own ID, owner, classification, basis, and history. [Finish the turn](../../backend/src/lifesci/process_engineering/tool_loop.py#L453) · [Mark activity after the turn](../../backend/src/lifesci/process_engineering/conversation.py#L889) · [Write a note](../../backend/src/lifesci/agent_memory.py#L78).
2. **A note can cite the `DEV-77` artifact's source.** The model supplies the case kind and ID. `inspected_refs` resolves these from the conversation's inspection receipts and artifact inputs. `remember` requires a source reference for an observed, calculated, or inferred note and checks the resolved references again before saving. A `user_stated` note can be saved from the person's statement and records an excerpt of the user message. Saving twice can reaffirm the same note rather than add a second copy. [Resolve inspected sources](../../backend/src/lifesci/agent_memory.py#L57) · [Save or reaffirm](../../backend/src/lifesci/agent_memory.py#L85).
3. **Changing the case changes how the note is presented.** Suppose a note points to `DEV-77` revision 2 and the case advances to revision 3. Opening the note or building a fresh index checks the saved source revision and presents the note as stale. It still points to revision 2. Consolidation can persist the stale status and add a history entry. A new read of the case is how an assistant can establish what the current record says. [Present a note](../../backend/src/lifesci/agent_memory.py#L195) · [Consolidation](../../backend/src/lifesci/agent_memory.py#L349).
4. **A later turn gets a small index and can search for more.** The native tool loop supplies recent exchanges and a bounded `memory_index`. `recall` searches permitted earlier answers, notes, and entity pages. It filters by site and the applicable owner grants before ranking by meaning or words. A recall snippet is a lead. `open_memory` retrieves the note view, including its source references and stale reasons. [Assemble turn context](../../backend/src/lifesci/process_engineering/tool_loop.py#L241) · [Recall](../../backend/src/lifesci/agent_memory.py#L273) · [Open a note or page](../../backend/src/lifesci/agent_memory.py#L234).

The owner can mark a note wrong, forget it, or restore it in Settings › Memory & sharing. These are recorded status changes. Background consolidation runs on the application runtime tick for eligible owners. The same panel can trigger an explicit pass with **Tidy now**. [Note status and consolidate endpoints](../../backend/src/lifesci/api.py#L719) · [Runtime tick](../../backend/src/lifesci/runtime.py#L154) · [Memory panel](../../frontend/components/memory/AssistantMemoryPanel.tsx#L31).

Prime keeps investigation state in its SDK sessions, specialist checkpoints, and incident blackboard. The draw.io memory tab describes the workspace assistant's per-person notes. See the [Prime runtime map](../../backend/docs/manufacturing_os_architecture_map.md#runtime-boundary) and [workbook memory exercise](../../backend/docs/agent-code.md#4-find-what-survives-a-turn-and-what-happens-when-you-stop-it) to trace each kind of persistence in code.

## Layers (after Anthropic's hierarchy)

| Layer | Here | Loaded |
|---|---|---|
| Conversation history | Conversation turns, tool steps and results, saved with provenance | Bounded recent exchanges in the native loop. Older work on demand through `recall`, `open_result`, and `workspace_read`. |
| Notes | `memory_note`: lesson, decision, preference, open thread or warning; with its basis (observed, calculated, user-stated, inferred) and the records it rests on | On demand: `recall`, `open_memory` |
| Representations | `memory_page`: one page per entity (batch, lot, equipment, case), the owner's notes about it quoted verbatim | On demand: `recall`, `open_memory` |
| Injected | Standing rules and corrections in mission context, plus `memory_index` of up to 12 notes / 3 KB | Assembled for each native tool-loop turn |

## Where we differ from general-purpose memory

- **Records ground the note.** A note may cite only sources the conversation has inspected, or record the person's own
  statement. The note view checks whether cited records still exist at the saved revision. A change can surface as
  *stale* before consolidation persists the status.
- **Private by default, permission before ranking.** Notes, pages and vectors are the owner's memory (scope
  `conversations`); candidates are filtered by ownership and grants before any similarity search, so a colleague's notes
  never surface without their grant. Grants are read-only: a colleague's agent cannot write into someone's memory.
- **Nothing is silently deleted.** The owner can forget a note, mark it wrong, or restore it; consolidation can only
  mark notes stale or superseded, with a reason. Every change is in the note's history and the audit log.
- **Organization-wide knowledge needs a person.** Notes used repeatedly are offered as *site rule* suggestions, which go
  through the existing approval of assistant rules.

## Writing

The workspace prompt asks the model to use `remember` before its final answer for information worth keeping across
turns, such as lessons, decisions, preferences, open threads, and warnings. The source records keep their own values.
An exact or sufficiently similar active note can be reaffirmed. The host retains its ID and adds a history entry.
[Workspace prompt](../../backend/src/lifesci/process_engineering/assistant_prompt.py) · [Duplicate check](../../backend/src/lifesci/agent_memory.py#L153).

## Recall

Ranking by meaning (embeddings) with a boost for shared identifiers (B-117, L-8812) and exact phrases. Lexical-only when
the embedding service is unavailable, and recall says so.

Embeddings: `Qwen/Qwen3-Embedding-0.6B` on Modal (workspace `gauntlet`, app `biodemo-embeddings`,
`backend/deploy/modal/embeddings_app.py`), behind Modal proxy auth with the existing proxy token; text stays in our Modal
workspace; scales to zero. Vectors are records (`memory_vector`), searched in process.
`ponytail:` in-process cosine over all of a tenant's vectors; move to pgvector when a tenant passes ~10k items.

Measured (`backend/benchmarks/memory_recall`, 16 items, 20 re-asks in different words):

| Ranking | recall@1 | recall@3 |
|---|---|---|
| Words only | 0.35 | 0.70 |
| Reciprocal-rank merge of words and meaning (first attempt) | 0.50 | 0.75 |
| **Meaning + identifier boost (shipped)** | **0.70** | **0.95** |

The set is small and written by us; extend it with real (anonymised) conversations before relying on the numbers.

## Consolidation ("dreaming")

On the runtime tick, for owners with new activity and not consolidated in the last 10 minutes (idle owners cost
nothing): embed anything missing; mark notes stale whose records changed; merge duplicates; one model pass over recent
conversations proposes notes and retirements — every proposed source is checked against what those conversations read,
unsupported notes are dropped, and the model may retire but never call a note wrong; rebuild entity pages; promote the
index; offer rule suggestions. Owners can run it from Settings › Memory & sharing ("Tidy now").

Measured (real GLM, one demo session): the assistant saved an inferred open thread on DEV-31 and the person's CoA
reminder, each with sources; consolidation added the stated glucose-unit preference and a cross-case lesson (new
antifoam lots preceded both BR-07 DO dips); a new conversation asked in different words recalled the earlier work
(13 s), and "what units do I like for sugar?" was answered from the index without any lookup (4 s).

## Person's view

Settings › Memory & sharing › *What your assistant remembers*: every note with kind, basis, sources, stale reasons and
the conversation it came from; *This is wrong*, *Forget*, *Restore*; entity pages; rule suggestions; *Tidy now*.

## Open

- Semantic recall quality on real conversations (extend the test set).
- Consolidation cost: one model call per active owner per 10 minutes at most; tune cadence by use.
- Pages are deterministic collections of notes; a model-written synopsis (Anthropic's wiki) is not added, to keep pages
  verbatim and checkable.
