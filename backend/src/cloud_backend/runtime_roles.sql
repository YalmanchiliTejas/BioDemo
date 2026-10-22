-- Run once as migration administrator; set LOGIN passwords separately via \password.
-- Runtime services must never use the owner/superuser connection string.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cloud_api') THEN
    CREATE ROLE cloud_api LOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cloud_dispatcher') THEN
    CREATE ROLE cloud_dispatcher LOGIN;
  END IF;
END $$;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO cloud_api, cloud_dispatcher;
GRANT SELECT, INSERT ON cloud_jobs TO cloud_api;
GRANT UPDATE (state, updated) ON cloud_jobs TO cloud_api;
GRANT SELECT, UPDATE ON cloud_jobs TO cloud_dispatcher;
GRANT SELECT, INSERT ON cloud_audit TO cloud_api;
GRANT INSERT ON cloud_audit TO cloud_dispatcher;
GRANT USAGE ON SEQUENCE cloud_audit_id_seq TO cloud_api, cloud_dispatcher;
