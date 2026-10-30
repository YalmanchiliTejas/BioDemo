"""Relational schema for CMO delivery verification records.

Normalization rules (see decision D52):

* Every mutable fact has exactly one home row. Values that can be derived
  (run summaries, coverage, relationships, confidence, a measurement's template
  or file hash, a layout's template version, review receipts, model usage) are
  computed when read, never stored.
* Decisions and history are append-only: confirmed templates, ignore rules,
  deliveries and their files, and the shared platform ``audit`` table, which
  holds the hash-chained receipts for every CMO decision.
* JSON columns hold only immutable value objects that are never queried or
  updated piecewise (a confirmed column mapping, a source citation, a model
  decision payload, the parser report). They duplicate no column.

Every table carries ``tenant_id``; PostgreSQL enforces tenant isolation with
row-level security and the runtime role may only perform the writes listed in
``cmo_grants``.
"""
from __future__ import annotations

# Tables in dependency order. ``mutable`` lists columns the application may
# update after insert; everything else is insert-only.
TABLES: dict[str, dict] = {
    "cmo_workspaces": {"mutable": ()},
    "cmo_deliveries": {"mutable": ()},
    "cmo_delivery_files": {"mutable": ()},
    "cmo_templates": {"mutable": ()},
    "cmo_runs": {"mutable": ("configuration", "requested_configuration", "package_id", "delivery_name", "disclosure",
                             "status", "synthetic", "hosted_approved", "hosted_basis", "completed_at",
                             "runtime_seconds", "error", "human_minutes", "human_time_status", "project_id",
                             "case_id", "store_path", "ingestion", "expectations_basis", "superseded_by",
                             "carried_from_run", "carried_skipped")},
    "cmo_run_notes": {"mutable": ()},
    "cmo_run_stages": {"mutable": ("state", "duration_seconds")},
    "cmo_documents": {"mutable": ()},
    "cmo_layouts": {"mutable": ()},
    "cmo_elements": {"mutable": ()},
    "cmo_issues": {"mutable": ("status", "actor", "reason", "resolved_at", "grouped_with", "covered_by", "carried_from")},
    "cmo_measurements": {"mutable": ("evidence_id", "source", "parameter", "batch", "time_value", "value_raw",
                                     "unit_raw", "unit_declared", "value", "unit", "parser", "source_verified",
                                     "status", "extraction_confidence", "extraction_spans",
                                     "extraction_review_reasons")},
    "cmo_measurement_rules": {"mutable": ()},
    "cmo_extraction_reviews": {"mutable": ()},
    "cmo_ignore_rules": {"mutable": ()},
}
APPEND_ONLY = ("cmo_deliveries", "cmo_delivery_files", "cmo_templates", "cmo_ignore_rules")

_DEFERRED = "DEFERRABLE INITIALLY DEFERRED"

CMO_DDL = f"""
CREATE TABLE IF NOT EXISTS cmo_workspaces (
  tenant_id TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, name));

CREATE TABLE IF NOT EXISTS cmo_deliveries (
  tenant_id TEXT NOT NULL, id TEXT NOT NULL, cmo TEXT NOT NULL, name TEXT, created_at TEXT NOT NULL,
  dataset TEXT, condition TEXT, synthetic BOOLEAN, disclosure TEXT,
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, cmo) REFERENCES cmo_workspaces (tenant_id, name));

CREATE TABLE IF NOT EXISTS cmo_delivery_files (
  tenant_id TEXT NOT NULL, delivery_id TEXT NOT NULL, position INTEGER NOT NULL, path TEXT NOT NULL,
  size_bytes BIGINT NOT NULL, sha256 TEXT NOT NULL,
  PRIMARY KEY (tenant_id, delivery_id, path), UNIQUE (tenant_id, delivery_id, position),
  FOREIGN KEY (tenant_id, delivery_id) REFERENCES cmo_deliveries (tenant_id, id));

CREATE TABLE IF NOT EXISTS cmo_templates (
  tenant_id TEXT NOT NULL, id TEXT NOT NULL, cmo TEXT NOT NULL, fingerprint TEXT NOT NULL, kind TEXT NOT NULL,
  version INTEGER NOT NULL, mapping TEXT NOT NULL, headers TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL,
  origin TEXT NOT NULL,
  PRIMARY KEY (tenant_id, id), UNIQUE (tenant_id, cmo, fingerprint, version),
  FOREIGN KEY (tenant_id, cmo) REFERENCES cmo_workspaces (tenant_id, name));
CREATE INDEX IF NOT EXISTS cmo_templates_kind ON cmo_templates (tenant_id, cmo, kind);

CREATE TABLE IF NOT EXISTS cmo_runs (
  tenant_id TEXT NOT NULL, id TEXT NOT NULL, cmo TEXT NOT NULL, configuration TEXT NOT NULL,
  requested_configuration TEXT, package_id TEXT, delivery_name TEXT, disclosure TEXT, status TEXT NOT NULL,
  synthetic BOOLEAN NOT NULL, hosted_approved BOOLEAN NOT NULL, hosted_basis TEXT, started_at TEXT NOT NULL,
  completed_at TEXT, runtime_seconds DOUBLE PRECISION, error TEXT, human_minutes DOUBLE PRECISION,
  human_time_status TEXT, project_id TEXT, case_id TEXT, store_path TEXT, ingestion TEXT, expectations_basis TEXT,
  superseded_by TEXT, carried_from_run TEXT, carried_skipped TEXT, elements_recorded BOOLEAN NOT NULL,
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, cmo) REFERENCES cmo_workspaces (tenant_id, name),
  FOREIGN KEY (tenant_id, superseded_by) REFERENCES cmo_runs (tenant_id, id) {_DEFERRED},
  FOREIGN KEY (tenant_id, carried_from_run) REFERENCES cmo_runs (tenant_id, id) {_DEFERRED});
CREATE INDEX IF NOT EXISTS cmo_runs_cmo ON cmo_runs (tenant_id, cmo, started_at);

CREATE TABLE IF NOT EXISTS cmo_run_notes (
  tenant_id TEXT NOT NULL, run_id TEXT NOT NULL, kind TEXT NOT NULL, position INTEGER NOT NULL, note TEXT NOT NULL,
  PRIMARY KEY (tenant_id, run_id, kind, position),
  FOREIGN KEY (tenant_id, run_id) REFERENCES cmo_runs (tenant_id, id) {_DEFERRED});

CREATE TABLE IF NOT EXISTS cmo_run_stages (
  tenant_id TEXT NOT NULL, run_id TEXT NOT NULL, position INTEGER NOT NULL, stage TEXT NOT NULL, state TEXT NOT NULL,
  elapsed_seconds DOUBLE PRECISION NOT NULL, duration_seconds DOUBLE PRECISION,
  PRIMARY KEY (tenant_id, run_id, position),
  FOREIGN KEY (tenant_id, run_id) REFERENCES cmo_runs (tenant_id, id) {_DEFERRED});

CREATE TABLE IF NOT EXISTS cmo_documents (
  tenant_id TEXT NOT NULL, run_id TEXT NOT NULL, source_id TEXT NOT NULL, position INTEGER NOT NULL,
  path TEXT NOT NULL, doc_type TEXT NOT NULL, classification_method TEXT, classification_evidence TEXT,
  sha256 TEXT NOT NULL, extraction_status TEXT,
  PRIMARY KEY (tenant_id, run_id, source_id), UNIQUE (tenant_id, run_id, path),
  FOREIGN KEY (tenant_id, run_id) REFERENCES cmo_runs (tenant_id, id) {_DEFERRED});

CREATE TABLE IF NOT EXISTS cmo_layouts (
  tenant_id TEXT NOT NULL, run_id TEXT NOT NULL, fingerprint TEXT NOT NULL, position INTEGER NOT NULL,
  sheet TEXT, headers TEXT NOT NULL, mapping TEXT NOT NULL, decisions TEXT NOT NULL, template_id TEXT,
  based_on TEXT, example_source_id TEXT NOT NULL, records INTEGER,
  PRIMARY KEY (tenant_id, run_id, fingerprint),
  FOREIGN KEY (tenant_id, run_id, example_source_id) REFERENCES cmo_documents (tenant_id, run_id, source_id) {_DEFERRED},
  FOREIGN KEY (tenant_id, template_id) REFERENCES cmo_templates (tenant_id, id));

CREATE TABLE IF NOT EXISTS cmo_elements (
  tenant_id TEXT NOT NULL, run_id TEXT NOT NULL, id TEXT NOT NULL, position INTEGER NOT NULL,
  source_id TEXT NOT NULL, sheet TEXT, source_column TEXT, source_row INTEGER, page INTEGER, state TEXT NOT NULL,
  PRIMARY KEY (tenant_id, run_id, id),
  FOREIGN KEY (tenant_id, run_id, source_id) REFERENCES cmo_documents (tenant_id, run_id, source_id) {_DEFERRED});

CREATE TABLE IF NOT EXISTS cmo_issues (
  tenant_id TEXT NOT NULL, run_id TEXT NOT NULL, id TEXT NOT NULL, position INTEGER NOT NULL,
  rule_code TEXT NOT NULL, status TEXT NOT NULL, context TEXT NOT NULL, actor TEXT, reason TEXT, resolved_at TEXT,
  grouped_with TEXT, covered_by TEXT, carried_from TEXT,
  PRIMARY KEY (tenant_id, run_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES cmo_runs (tenant_id, id) {_DEFERRED});

CREATE TABLE IF NOT EXISTS cmo_measurements (
  tenant_id TEXT NOT NULL, run_id TEXT NOT NULL, id TEXT NOT NULL, position INTEGER NOT NULL,
  evidence_id TEXT NOT NULL, source_id TEXT NOT NULL, source TEXT NOT NULL, parameter TEXT NOT NULL,
  batch TEXT NOT NULL, time_value TEXT NOT NULL, value_raw TEXT, unit_raw TEXT, unit_declared TEXT,
  value DOUBLE PRECISION, unit TEXT NOT NULL, fingerprint TEXT NOT NULL, parser TEXT,
  source_verified BOOLEAN NOT NULL, status TEXT NOT NULL, extraction_confidence TEXT,
  extraction_spans TEXT, extraction_review_reasons TEXT, supersedes TEXT,
  PRIMARY KEY (tenant_id, run_id, id),
  FOREIGN KEY (tenant_id, run_id, source_id) REFERENCES cmo_documents (tenant_id, run_id, source_id) {_DEFERRED},
  FOREIGN KEY (tenant_id, run_id, fingerprint) REFERENCES cmo_layouts (tenant_id, run_id, fingerprint) {_DEFERRED},
  FOREIGN KEY (tenant_id, run_id, supersedes) REFERENCES cmo_measurements (tenant_id, run_id, id) {_DEFERRED});

CREATE TABLE IF NOT EXISTS cmo_measurement_rules (
  tenant_id TEXT NOT NULL, run_id TEXT NOT NULL, measurement_id TEXT NOT NULL, rule_code TEXT NOT NULL,
  PRIMARY KEY (tenant_id, run_id, measurement_id, rule_code),
  FOREIGN KEY (tenant_id, run_id, measurement_id) REFERENCES cmo_measurements (tenant_id, run_id, id) {_DEFERRED});

CREATE TABLE IF NOT EXISTS cmo_extraction_reviews (
  tenant_id TEXT NOT NULL, run_id TEXT NOT NULL, position INTEGER NOT NULL, source_id TEXT NOT NULL,
  review TEXT NOT NULL,
  PRIMARY KEY (tenant_id, run_id, position),
  FOREIGN KEY (tenant_id, run_id, source_id) REFERENCES cmo_documents (tenant_id, run_id, source_id) {_DEFERRED});

CREATE TABLE IF NOT EXISTS cmo_ignore_rules (
  tenant_id TEXT NOT NULL, id TEXT NOT NULL, cmo TEXT NOT NULL, pattern TEXT NOT NULL, actor TEXT NOT NULL,
  reason TEXT NOT NULL, at TEXT NOT NULL, run_id TEXT, issue_id TEXT,
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, cmo) REFERENCES cmo_workspaces (tenant_id, name),
  FOREIGN KEY (tenant_id, run_id) REFERENCES cmo_runs (tenant_id, id) {_DEFERRED},
  FOREIGN KEY (tenant_id, run_id, issue_id) REFERENCES cmo_issues (tenant_id, run_id, id) {_DEFERRED});
CREATE INDEX IF NOT EXISTS cmo_ignore_rules_cmo ON cmo_ignore_rules (tenant_id, cmo);
"""

CMO_SQLITE_DDL = CMO_DDL + "".join(
    f"CREATE TRIGGER IF NOT EXISTS {t}_no_update BEFORE UPDATE ON {t} BEGIN SELECT RAISE(ABORT, 'append only'); END;\n"
    f"CREATE TRIGGER IF NOT EXISTS {t}_no_delete BEFORE DELETE ON {t} BEGIN SELECT RAISE(ABORT, 'append only'); END;\n"
    for t in APPEND_ONLY)

# Tables from the retired one-document-per-run schema (0001_cmo_ingestion.sql)
# share names with the normalized ones but have no tenant_id. They are renamed to
# legacy_<name>, never dropped, so `cmo-import-legacy` can copy their records.
LEGACY_TABLES = ("cmo_runs", "cmo_templates", "cmo_ignore_rules", "cmo_deliveries", "cmo_events")
CMO_PG_SET_ASIDE_LEGACY = """
DO $$ DECLARE t text; c text; old text; BEGIN
  FOREACH t IN ARRAY ARRAY[""" + ",".join(f"'{t}'" for t in LEGACY_TABLES) + """] LOOP
    IF to_regclass(format('%I', t)) IS NOT NULL AND NOT EXISTS (
         SELECT 1 FROM information_schema.columns
         WHERE table_schema = current_schema() AND table_name = t AND column_name = 'tenant_id') THEN
      IF to_regclass(format('%I', 'legacy_' || t)) IS NOT NULL THEN
        RAISE EXCEPTION 'both % and legacy_% exist; resolve by hand before migrating', t, t;
      END IF;
      old := 'legacy_' || t;
      EXECUTE format('ALTER TABLE %I RENAME TO %I', t, old);
      -- Constraint and index names are schema-wide; free them for the new tables.
      FOR c IN SELECT conname FROM pg_constraint WHERE conrelid = old::regclass AND conname NOT LIKE 'legacy\\_%' LOOP
        EXECUTE format('ALTER TABLE %I RENAME CONSTRAINT %I TO %I', old, c, 'legacy_' || c);
      END LOOP;
      FOR c IN SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() AND tablename = old
                 AND indexname NOT LIKE 'legacy\\_%' LOOP
        EXECUTE format('ALTER INDEX %I RENAME TO %I', c, 'legacy_' || c);
      END LOOP;
    END IF;
  END LOOP;
END $$;
"""

CMO_PG_DDL = CMO_PG_SET_ASIDE_LEGACY + CMO_DDL + """
CREATE OR REPLACE FUNCTION cmo_append_only() RETURNS trigger LANGUAGE plpgsql AS
$$ BEGIN RAISE EXCEPTION 'append only: % on %', TG_OP, TG_TABLE_NAME; END $$;
""" + "".join(
    f"DROP TRIGGER IF EXISTS {t}_append_only ON {t};\n"
    f"CREATE TRIGGER {t}_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON {t} "
    f"FOR EACH STATEMENT EXECUTE FUNCTION cmo_append_only();\n"
    for t in APPEND_ONLY)

CMO_PG_POLICIES = """
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY[""" + ",".join(f"'{t}'" for t in TABLES) + """] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.tenant_id'', true)) '
                   'WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true))', t);
  END LOOP;
END $$;
"""


def cmo_grants(role: str) -> list[str]:
    insert_only = [t for t, spec in TABLES.items() if not spec["mutable"]]
    updatable = [t for t, spec in TABLES.items() if spec["mutable"]]
    return [f'GRANT SELECT, INSERT ON {", ".join(insert_only)} TO "{role}"',
            f'GRANT SELECT, INSERT, UPDATE ON {", ".join(updatable)} TO "{role}"']
