-- Apply using a migration identity; runtime identities must not own tables.
CREATE TABLE IF NOT EXISTS cloud_jobs (
    id text PRIMARY KEY, tenant text NOT NULL, project text NOT NULL,
    actor text NOT NULL, idempotency_key text NOT NULL, request_hash text NOT NULL,
    request jsonb NOT NULL, state text NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued','running','succeeded','failed','cancelled')),
    attempt integer NOT NULL DEFAULT 0, fence text, task_arn text, launch_manifest jsonb,
    deadline double precision, created double precision NOT NULL,
    updated double precision NOT NULL, result_key text, result_version text, error_code text,
    UNIQUE (tenant, project, idempotency_key)
);
CREATE INDEX IF NOT EXISTS cloud_jobs_pending ON cloud_jobs (state, created);
CREATE TABLE IF NOT EXISTS cloud_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred double precision NOT NULL, tenant text NOT NULL, project text NOT NULL,
    actor text NOT NULL, action text NOT NULL, object_id text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'
);
-- No prompts, document contents, bearer tokens or provider errors in audit rows.
CREATE OR REPLACE FUNCTION cloud_audit_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Audit history is append only'; END $$;
DROP TRIGGER IF EXISTS cloud_audit_no_mutation ON cloud_audit;
CREATE TRIGGER cloud_audit_no_mutation BEFORE UPDATE OR DELETE ON cloud_audit
FOR EACH ROW EXECUTE FUNCTION cloud_audit_immutable();
