# Demo workspaces for prospects

Status: **implemented locally; updated 2026-11-08 for persona model scenarios and optional visitor deliveries.** Governing direction: [the four pillars](../../Main_Culture_andETHOS.md).

## Job

A prospect (Process Engineer, MSAT, QA, Executive) should see the product work on realistic manufacturing problems within a minute, without signing up or sharing data. We learn which scenarios resonate and where the assistant falls short. This is an A/B alternative to the current sales path; measure starts, scenarios tried, feedback and "talk to us" conversions.

## Decisions (product owner, 2026-11-06)

- **Entry:** one click, no sign-up (Supabase anonymous sign-in). Email is optional, in feedback or "Talk to us".
- **Notice:** shown before entering, with a required checkbox: the demo starts with synthetic data; optional authorized, non-confidential uploads are stored for processing; demo conversations and feedback are kept for up to 90 days for product improvement; workspace access expires after 24 hours.
- **Retention:** workspace access for 24 h; conversations/feedback in the improvement copy for up to 90 days. The existing database purge deletes expired tenant records; delivery originals and local caches use their storage retention policy and are not covered by the database purge. Do not claim all uploaded bytes are deleted at 24 h.
- **Limits:** 20 assistant messages per workspace; 300 per day across all demo workspaces.
- **Optional visitor deliveries (user direction, 2026-11-08).** Every persona may create deliveries and upload non-confidential files they are authorized to share. Existing tenant permissions, original hashes, intake validation, file/expansion limits and mapping review apply. Demo runs force local `preview` processing even when hosted extraction is requested. Unsupported formats and ambiguous mappings are exposed for review. Uploading files does not make them verified model configurations or calibrated training data.
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
- Delivery creation, direct uploads and storage uploads use the existing authenticated, tenant-scoped endpoints for demo visitors. Expired tenants are refused through the shared context dependency.
- Deliveries shows both the standard file/folder drop zone and the existing sample-delivery options. Authenticated anonymous visitors use their actual actor identifier for review receipts; no invented reviewer name is required.

### Frontend
- **`/demo`** (public): headline, four persona cards, notice and checkbox, Start. Start runs `supabase.auth.signInAnonymously()`, then POSTs the workspace, selects the organization, and goes to `/home/?scenarios=1`.
- **Demo banner** across the app: "Demo workspace · sample data + optional uploads · access expires in 23 h · 14 of 20 messages left · Try your own delivery · Try the model library".
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

## Pharmaceutical model scenarios (2026-11-08)

Each persona has one additional scenario in the existing assistant scenario cards, with an executable prompt and explicit review expectations. Process Engineer: simulate the synthetic competing-reaction reactor, inspect yield/impurity/temperature and explain permitted neural terms. MSAT: simulate the existing oxygen-transfer configuration and identify receiving-site characterization and adaptation/calibration data needs. QA: execute and review the reaction model's evidence, versions, missing quality attributes and uncertainty limits. Executive: run the reaction example and prepare a concise, conditional transfer-decision brief with proposed next measurements. No scenario treats synthetic predictions as validation, release authorization or workload savings. The existing library, tool loop, result store and approval boundary are reused.
