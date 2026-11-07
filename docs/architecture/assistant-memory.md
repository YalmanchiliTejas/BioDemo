# Assistant memory

Status: implemented 2026-11-07. Governing direction: [the four pillars](../../Main_Culture_andETHOS.md). Builds on the
[tool loop](assistant-tool-loop.md) and [per-user memory privacy](../../backend/src/lifesci/memory.py). Reference:
Anthropic, [The components of agent memory](https://www.anthropic.com/research/components-of-agent-memory) (2026-11-06).

## Job

The assistant should build on earlier work, for the same person and across conversations: remember what it learned, what
the person decided and prefers, and what is still open, and find it again when asked in different words. In a regulated
plant it must never let memory stand in for the records.

## Layers (after Anthropic's hierarchy)

| Layer | Here | Loaded |
|---|---|---|
| Transcripts | Conversation turns, tool steps and results, saved with provenance | On demand: `recall`, `open_result`, `workspace_read` |
| Notes | `memory_note`: lesson, decision, preference, open thread or warning; with its basis (observed, calculated, user-stated, inferred) and the records it rests on | On demand: `recall`, `open_memory` |
| Representations | `memory_page`: one page per entity (batch, lot, equipment, case), the owner's notes about it quoted verbatim | On demand: `recall`, `open_memory` |
| Injected | Standing rules, corrections, and `memory_index`: up to 12 notes / 3 KB | Every turn |

## Where we differ from general-purpose memory

- **Records are the ground truth, not the transcript.** A note may cite only records this conversation actually read
  (host-checked), or be the person's own statement. Every read re-checks the cited records' current revision; a changed
  record makes the note *stale* until it is checked again. Consolidation persists that status.
- **Private by default, permission before ranking.** Notes, pages and vectors are the owner's memory (scope
  `conversations`); candidates are filtered by ownership and grants before any similarity search, so a colleague's notes
  never surface without their grant. Grants are read-only: a colleague's agent cannot write into someone's memory.
- **Nothing is silently deleted.** The owner can forget a note, mark it wrong, or restore it; consolidation can only
  mark notes stale or superseded, with a reason. Every change is in the note's history and the audit log.
- **Organization-wide knowledge needs a person.** Notes used repeatedly are offered as *site rule* suggestions, which go
  through the existing approval of assistant rules.

## Writing

The model decides what is worth keeping (Anthropic: rules like "record only failures" cost strong models most of the
benefit). It is told what memory is for, not when to write: what the records will not tell next time — validated
lessons and how they were established, decisions, preferences, open threads, traps; never record values. Near-duplicates
(cosine ≥ 0.93) reaffirm the existing note instead of adding a copy.

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
