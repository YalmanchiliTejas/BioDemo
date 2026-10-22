from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from benchmark.application.execution import IntegrationActionWriter
from benchmark.application.models import ActionProposal, ApprovalDecision, ProposalStatus, RiskLevel
from benchmark.integration import (
    AuthorizedAction, ConnectorRunner, InMemoryCheckpointStore, IntegrationGateway, JsonlConnector, SourceRecord,
    connectors_from_settings,
)
from benchmark.integration.models import PullBatch
from benchmark.knowledge.digital_thread import DigitalThread
from benchmark.knowledge.domain import AccessContext
from benchmark.knowledge.evidence import FileEvidenceStore
from benchmark.knowledge.memory import (
    InMemoryCaseStore, InMemoryDocumentStore, InMemoryGraphStore, InMemoryOutbox,
)
from benchmark.knowledge.service import KnowledgeBase


class WritableTestConnector:
    connector_id = "qms-actions"
    source_system = "QMS"

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        return PullBatch((), checkpoint)

    def write(self, action: AuthorizedAction) -> SourceRecord:
        return SourceRecord(
            f"QMS-ACK-{action.action_id}", "QMS", action.approved_at,
            {"event_type": "action_accepted", "action_id": action.action_id,
             "target_id": action.target_id, "status": "accepted",
             "entities": [{"entity_id": action.target_id, "entity_type": "deviation"}]},
            action.site_id,
        )


class IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.graph = InMemoryGraphStore()
        self.documents = InMemoryDocumentStore()
        self.thread = DigitalThread(
            KnowledgeBase(self.graph, self.documents), FileEvidenceStore(Path(self.temp.name) / "evidence"),
            InMemoryCaseStore(), InMemoryOutbox(),
        )
        self.checkpoints = InMemoryCheckpointStore()
        self.gateway = IntegrationGateway(self.thread, self.checkpoints)
        self.access = AccessContext("SPONSOR-A", "qa-01", ("SITE-01",), ("qa",), ("internal",))
        self.now = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_jsonl_connector_backfill_checkpoints_and_updates_knowledge(self) -> None:
        path = Path(self.temp.name) / "events.jsonl"
        path.write_text("".join(json.dumps({
            "timestamp": self.now.isoformat(), "event_type": "sample_reported",
            "source_record_id": f"LIMS-{index}",
            "entities": [{"entity_id": "BATCH-01", "entity_type": "batch"}],
        }) + "\n" for index in range(3)))
        connector = JsonlConnector("lims-backfill", "LIMS", path, site_id="SITE-01")

        result = self.gateway.sync(connector, access=self.access, batch_size=2)
        repeated = self.gateway.sync(connector, access=self.access, batch_size=2)

        self.assertEqual(result.records_ingested, 3)
        self.assertEqual(result.batches_processed, 2)
        self.assertEqual(result.final_checkpoint, "3")
        self.assertEqual(repeated.records_ingested, 0)
        self.assertEqual(len(self.graph.events), 3)
        context = self.thread.knowledge.context(
            "sample", entity_ids=["BATCH-01"], access=self.access,
        )
        self.assertEqual(len(context.events), 3)

        cycle = ConnectorRunner(self.gateway).run_cycle([connector], access=self.access)
        self.assertEqual(cycle.completed[connector.connector_id].records_ingested, 0)
        self.assertEqual(cycle.errors, {})

    def test_authorized_write_ingests_only_source_acknowledgement(self) -> None:
        connector = WritableTestConnector()
        action = AuthorizedAction(
            "ACT-01", "SPONSOR-A", "QMS", "close_deviation", "DEV-01", {"reason": "approved"},
            "qa-01", ("sponsor-qa",), self.now, "SITE-01", ("APR-01",),
        )
        acknowledgement = self.gateway.execute_authorized(connector, action, access=self.access)

        self.assertEqual(acknowledgement.source_record_id, "QMS-ACK-ACT-01")
        self.assertEqual(len(self.graph.events), 1)
        event = next(iter(self.graph.events.values()))
        self.assertEqual(event.attributes["source_record_id"], "QMS-ACK-ACT-01")
        self.assertEqual(event.source, "QMS")

    def test_write_without_recorded_approval_is_rejected(self) -> None:
        action = AuthorizedAction(
            "ACT-02", "SPONSOR-A", "QMS", "close_deviation", "DEV-01", {},
            "qa-01", (), self.now,
        )
        with self.assertRaises(PermissionError):
            self.gateway.execute_authorized(WritableTestConnector(), action, access=self.access)

    def test_application_writer_routes_approved_proposal_to_named_system(self) -> None:
        proposal = ActionProposal(
            "ACT-03", "SPONSOR-A", "CASE-01", "close_deviation", "DEV-01",
            {"source_system": "QMS"}, "msat-01", "Approved evidence package",
            "SITE-01", RiskLevel.HIGH, ("qa",), ProposalStatus.APPROVED,
            (ApprovalDecision("APR-03", "qa-01", "qa", "approved", "QA closure"),),
            self.now, self.now,
        )
        executor = AccessContext(
            "SPONSOR-A", "gateway-01", ("SITE-01",), ("system_executor",), ("internal",),
        )
        receipt = IntegrationActionWriter(
            self.gateway, {"qms": WritableTestConnector()},
        ).write(proposal, executor)
        self.assertEqual(receipt, "QMS-ACK-ACT-03")
        self.assertEqual(len(self.graph.events), 1)

    def test_connector_catalog_builds_only_configured_systems(self) -> None:
        connectors = connectors_from_settings({
            "MES_BASE_URL": "https://mes.example.test",
            "MES_API_TOKEN": "secret",
            "MES_SITE_ID": "SITE-01",
            "LIMS_BASE_URL": "https://lims.example.test",
            "LIMS_WRITE_PATH": "none",
        })
        self.assertEqual(set(connectors), {"mes", "lims"})
        self.assertEqual(connectors["mes"].config.headers["Authorization"], "Bearer secret")
        self.assertIsNone(connectors["lims"].config.write_path)


if __name__ == "__main__":
    unittest.main()
