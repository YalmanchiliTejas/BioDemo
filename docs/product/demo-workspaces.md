# Demo workspaces for prospects

Status: **build spec, 2026-11-06.** Governing direction: [the four pillars](../../Main_Culture_andETHOS.md).

## Job

A prospect (Process Engineer, MSAT, QA, Executive) should see the product work on realistic manufacturing problems within a minute, without signing up or sharing data. We learn which scenarios resonate and where the assistant falls short. This is an A/B alternative to the current sales path; measure starts, scenarios tried, feedback and "talk to us" conversions.

## Decisions (product owner, 2026-11-06)

- **Entry:** one click, no sign-up (Supabase anonymous sign-in). Email is optional, in feedback or "Talk to us".
- **Notice:** shown before entering, with a required checkbox: *"This is a demo with synthetic data. We keep demo conversations and feedback to improve the product. Don't enter confidential information."*
- **Retention:** each workspace for 24 h; the improvement copy for 90 days.
- **Limits:** 20 assistant messages per workspace; 300 per day across all demo workspaces.
- **No visitor data.** Visitors don't upload; uploads are refused in demo workspaces. Each role gets our synthetic data and **scenarios** to work through, and we ask for feedback on the scenario as well as the answers.
- Multi-agent investigations stay off (paid tier).

## Design

### Workspaces
- `POST /v1/demo/workspaces {persona, accepted_notice: true}`. The caller must be an anonymous Supabase user; `accepted_notice` must be true. This creates tenant `demo_<uuid>`:
  - an organization record named "Demo workspace (synthetic)", with `demo: {persona, created_at, expires_at, owner}`
  - membership for the visitor
  - an org-wide role per persona: process_engineer → `engineering`; msat → `msat`; qa → `qa`; executive → `supervisor`
  - the persona's seed data (below)
  - auto-triage set to `paused`, so seeding never spends model budget
- Idempotent per anonymous user: one active demo workspace per visitor; a second call returns it.
- Refused when today's global cap is reached ("The demo is at capacity today", with Talk to us).
- `GET /v1/demo/workspace` returns persona, expiry, messages used/left, and the scenario list.
- **Expiry:** after `expires_at`, requests for that tenant return 410 "This demo workspace has expired". On the runtime tick, the visitor's role assignments are revoked and the workspace is marked expired. Physical deletion is the purge job.
- **Purge job:** `python -m src.lifesci demo-purge`, run as the schema owner. It deletes all rows of expired `demo_*` tenants in every table, including the append-only ones (triggers disabled only inside that transaction, only for those tenant ids), and corpus entries older than 90 days. It runs daily from a scheduled GitHub workflow using secret `LIFESCI_MIGRATION_DATABASE_URL`.

### Seed data per persona
All records are labelled SYNTHETIC. They're built from fixtures in the repo, quickly, with no model calls and no CMO pipeline run:
- **Shared:**
  - a verified CMO delivery dataset (CHO runs CHO-001…006 with VCD, viability, glucose, lactate, from the Northfield sample)
  - one deviation case (open)
  - two closed cases with root cause, CAPA and outcome, as precedents
  - a DO specification plus historian readings that raise an `action` signal, and a QMS deviation record that raises a `critical` signal
- **Persona emphasis:** each persona gets the same data but a different scenario set and home prompt.

### Scenarios
Static per persona (`lifesci/demo_scenarios.py`): `{scenario_id, persona, title, situation, prompt, look_for[]}`, 3–4 each. Examples:
- **Process Engineer:**
  - "DO fell below 30 % in B-117 at 4 h. Find out why." (signal, links, similar cases)
  - "Forecast growth and glucose for CHO-003-R01 from 72 h."
  - "Compare viability across the six runs."
- **MSAT:**
  - "Which runs in the delivery look unlike the others, and is the data trustworthy?"
  - "What would you check before transferring this process to a new site?"
- **QA:**
  - "A critical QMS deviation (DEV-31) arrived overnight. Triage it and decide whether to open a case."
  - "Have we seen this before? Find similar closed cases."
  - "Prepare what QA needs to review DEV-31."
- **Executive:**
  - "What needs my attention this week?"
  - "Which open deviations are highest risk, and who owns them?"

`look_for` is shown to the visitor as "What a good answer should do" (honest framing, no claimed accuracy).

### Feedback and the improvement corpus
- `POST /v1/demo/feedback {kind: 'answer'|'scenario'|'overall', turn_id?, scenario_id?, rating: up|down|1..5, realistic?: 1..5, useful?: 1..5, comment?, email?}`. Only in demo workspaces; written to the corpus.
- **Corpus:** records in the reserved tenant `__demo_corpus__`, never readable by visitors.
  - Each feedback item, and a **transcript snapshot** of the conversation. That covers user text, reply, questions, steps, tool trace, gateway runs, claims and grounding, `capabilities_used`, `context_used`.
  - Each item carries persona, scenario_id, demo tenant, model route and timestamps.
  - Snapshots are taken on every completed demo turn (runtime follow-up) and at expiry.
- Admin export: `python -m src.lifesci demo-corpus-export --since …` writes JSONL for harness evaluation. No visitor IDs beyond the anonymous user id; emails are stored only if given.

### Limits
- `enqueue` in a demo tenant refuses after 20 turns ("You've used this demo's 20 messages. Talk to us to keep going."). It also refuses once the global daily counter reaches 300.
- Counters are records in `__demo_control__`.

### Uploads
- CMO delivery creation and uploads return 403 "Demo workspaces use sample data" for `demo_*` tenants.
- Deliveries shows the persona's prepared delivery (read-only) instead of the drop zone.

### Frontend
- **`/demo`** (public): headline, four persona cards, notice and checkbox, Start. Start runs `supabase.auth.signInAnonymously()`, then POSTs the workspace, selects the organization, and goes to `/home/?scenarios=1`.
- **Demo banner** across the app: "Demo workspace · synthetic data · deleted in 23 h · 14 of 20 messages left · Talk to us".
- **Scenario panel:** in the assistant's empty state, and as a "Scenarios" button in the header. Each card shows the situation, a **Try it** button (sends the prompt), "What a good answer should do", and **Rate this scenario** (realistic 1–5, useful 1–5, comment).
- **Answer feedback:** 👍/👎 under each assistant answer in demo workspaces, with an optional comment.
- **Feedback button** in the header: overall usefulness, "would you use this?", what's missing, optional email.
- **Talk to us** link (`NEXT_PUBLIC_CONTACT_URL`, e.g. a booking link) on banner, limits and expiry messages.

### Configuration (owner)
- Enable **anonymous sign-ins** in Supabase (Authentication › Providers).
- GitHub secret `LIFESCI_MIGRATION_DATABASE_URL` for the purge workflow.
- Optional `NEXT_PUBLIC_CONTACT_URL`.

### Measures
Demo starts per persona; scenarios tried; feedback rate; mean realistic/useful per scenario; 👎 rate per scenario; messages per workspace; Talk-to-us clicks; return within 24 h.
