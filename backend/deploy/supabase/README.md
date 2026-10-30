# Hosting the platform database on Supabase

The platform and CMO delivery verification share one PostgreSQL database. The
schema is normalized (decision D52): every mutable fact has one home row,
derived values are computed when read, and decisions are append-only receipts
in the shared, hash-chained `audit` table. Every table is tenant-scoped with
row-level security, and the backend connects as the non-owner `lifesci_app`
role. Supabase's `anon` and `authenticated` roles get no access, because browsers
never query these tables.

## One-time setup

Either run the migration command:

```bash
# owner = the `postgres` session-pooler URL; runtime = lifesci_app.<ref> on the same pooler
LIFESCI_MIGRATION_DATABASE_URL='postgresql://postgres.<ref>:<db password>@<pooler-host>:5432/postgres?sslmode=require' \
LIFESCI_DATABASE_URL='postgresql://lifesci_app.<ref>:<app password>@<pooler-host>:5432/postgres?sslmode=require' \
python -m src.lifesci db-migrate
```

or paste the SQL into the Supabase SQL editor, in order:

1. `migrations/0002_lifesci_platform.sql`: first replace
   `REPLACE_WITH_APP_PASSWORD` with a new password of 16 or more characters for
   `lifesci_app`. Don't commit the edited copy.
2. `migrations/0003_cmo_records.sql`.

Both files are generated from the code (`python -m src.lifesci supabase-sql`),
and a test fails if they fall out of date. They are idempotent. They also
upgrade databases created by earlier versions, but only after confirming that
every current record equals its stored revision; otherwise they stop and change
nothing.

Then create a **private** Storage bucket named `cmo-evidence`, and set these on
the API service (never in the frontend):

```dotenv
LIFESCI_DATABASE_URL=postgresql://lifesci_app.<ref>:<app password>@<pooler-host>:5432/postgres?sslmode=require
LIFESCI_DB_MIGRATE=0
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<secret key>   # Storage only; bypasses RLS, keep server-side
CMO_STORAGE_BUCKET=cmo-evidence
CMO_API_TOKEN=<long random token>        # until real sign-in replaces the development identity
```

`CMO_DATABASE_URL` is optional. Set it only to keep CMO records in a different
database.

## Moving existing CMO records

Records saved in the old one-document-per-run layout (`cmo.sqlite`, or the
`cmo_*` tables from the retired `0001_cmo_ingestion.sql`) are copied with:

```bash
python -m src.lifesci cmo-import-legacy backend/.cache/cmo-ingestion/cmo.sqlite --tenant demo-northfield
```

The importer verifies the old hash chain before writing anything, writes each
customer's records in one transaction, re-chains the receipts in `audit`, and
reloads every run to report any difference from the original. A second run is
skipped, and the source is never modified.

## Verified so far

- Both SQL files were run twice with `psql` on a disposable PostgreSQL 16 cluster
  that had `anon`/`authenticated` roles: once on an empty database and once on
  a database in the earlier shape. The backend then ran there as `lifesci_app`.
- The upgrade ran on a copy of the local development database: the same 28
  current records, with an identical content fingerprint before and after.
- The importer ran on a copy of the local `cmo.sqlite`: 32 runs, 29 templates,
  28 ignore rules and 772 receipts, with no differences and a valid chain. One
  identical duplicate issue was merged.
- Tests cover RLS isolation, insert-only grants, append-only triggers and
  derived-value round trips (`tests/lifesci/test_postgres.py`).

None of this has yet been run against a live Supabase project. Do that with
synthetic files before giving anyone access. This deployment is not a validated
GxP system.
