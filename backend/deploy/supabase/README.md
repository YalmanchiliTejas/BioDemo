# Hosting CMO deliveries on Supabase

The API keeps parsing local and stores its system of record in Supabase:
PostgreSQL for runs, confirmed mappings, ignore rules, deliveries and the
hash-chained audit trail; a private Storage bucket for original files. Without
these variables it falls back to local SQLite and files (development only).

## One-time setup

1. Apply `migrations/0001_cmo_ingestion.sql` in the Supabase SQL editor (or
   `psql "$SUPABASE_DB_URL" -f migrations/0001_cmo_ingestion.sql`). It is
   idempotent, enables RLS with no policies, revokes `anon`/`authenticated`,
   and makes templates, ignore rules and audit events append-only.
2. Create a **private** Storage bucket named `cmo-evidence` (no public access).
3. Set these on the API service (never in the frontend):

```dotenv
CMO_DATABASE_URL=postgresql://postgres.<ref>:<password>@<pooler-host>:5432/postgres?sslmode=require
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service role key>
CMO_STORAGE_BUCKET=cmo-evidence
CMO_API_TOKEN=<long random token shared with testers out of band>
CMO_INGESTION_ROOT=/data/cmo          # local parse cache; safe to lose
BIODEMO_ALLOWED_ORIGINS=https://<frontend-host>   # only if UI and API are on different origins
# Hosted extraction for PDFs in unfamiliar layouts (customer files are sent to these providers):
CMO_HOSTED_INFERENCE_APPROVED=true
OPENAI_API_KEY=...
CLOUDFLARE_ACCOUNT_ID=...
CLOUDFLARE_AUTH_TOKEN=...
CMO_ALLOWED_ORIGINS=https://api.openai.com,https://api.cloudflare.com
DOCLING_ARTIFACTS_PATH=/models/docling
```

Use the session-mode pooler (port 5432) connection string; the audit chain
uses a transaction-scoped advisory lock. Build the frontend with no
`NEXT_PUBLIC_CMO_API_URL` when nginx proxies `/api/` on the same origin, or set
it to the API URL otherwise.

## What happens on restart

Runs, mappings, decisions and audit history are in PostgreSQL. Originals are
restored from Storage on demand and re-hashed before display or export; a
mismatch blocks the request. Runs that were processing when the service stopped
are marked `interrupted` and must be started again; nothing partial is accepted.

## Verified so far

The PostgreSQL repository and migration were exercised against local
PostgreSQL 16 (`CMO_TEST_DATABASE_URL=... pytest tests/test_cmo_postgres.py`),
including append-only enforcement. The Storage adapter is tested against a
mocked Supabase Storage API. Neither has yet been run against a live Supabase
project; do that with synthetic files before giving a tester access.

`CMO_API_TOKEN` is a shared secret, not per-user identity. Reviewer names are
typed by the reviewer. Put SSO in front before any regulated or multi-customer
use; this deployment is not a validated GxP system.
