-- CMO ingestion system of record for hosted deployments (Supabase PostgreSQL).
-- Apply once with the Supabase SQL editor or `psql "$SUPABASE_DB_URL" -f ...`.
-- Idempotent. The API connects server-side with CMO_DATABASE_URL; browsers
-- never query these tables directly, so RLS is enabled with no policies and
-- the public anon/authenticated roles have no access.

create table if not exists cmo_runs (
  id text primary key,
  cmo text not null,
  config text not null,
  result text not null,
  created timestamptz not null default now(),
  updated timestamptz not null default now()
);
create index if not exists cmo_runs_cmo_idx on cmo_runs (cmo, created);

create table if not exists cmo_templates (
  id text primary key,
  cmo text not null,
  fingerprint text not null,
  kind text not null,
  version integer not null,
  mapping text not null,
  headers text not null,
  actor text not null,
  at text not null,
  origin text not null,
  unique (cmo, fingerprint, version)
);
create index if not exists cmo_templates_kind_idx on cmo_templates (cmo, kind);

create table if not exists cmo_ignore_rules (
  id text primary key,
  cmo text not null,
  pattern text not null,
  actor text not null,
  reason text not null,
  at text not null,
  run_id text
);
create index if not exists cmo_ignore_rules_cmo_idx on cmo_ignore_rules (cmo);

create table if not exists cmo_deliveries (
  id text primary key,
  item text not null,
  created timestamptz not null default now()
);

create table if not exists cmo_events (
  seq bigserial primary key,
  payload text not null,
  prev_hash text not null,
  hash text not null,
  created timestamptz not null default now()
);

create or replace function cmo_append_only() returns trigger language plpgsql as $$
begin
  raise exception 'append only: % on %', tg_op, tg_table_name;
end $$;

do $$
declare t text;
begin
  foreach t in array array['cmo_templates','cmo_ignore_rules','cmo_events'] loop
    execute format('drop trigger if exists %I_append_only on %I', t, t);
    execute format('create trigger %I_append_only before update or delete or truncate on %I for each statement execute function cmo_append_only()', t, t);
  end loop;
end $$;

alter table cmo_runs enable row level security;
alter table cmo_templates enable row level security;
alter table cmo_ignore_rules enable row level security;
alter table cmo_deliveries enable row level security;
alter table cmo_events enable row level security;

-- Supabase-specific roles; skipped on plain PostgreSQL.
do $$
declare r text;
begin
  foreach r in array array['anon','authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on cmo_runs, cmo_templates, cmo_ignore_rules, cmo_deliveries, cmo_events from %I', r);
      execute format('revoke all on sequence cmo_events_seq_seq from %I', r);
    end if;
  end loop;
end $$;
