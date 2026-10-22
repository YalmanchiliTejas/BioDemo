from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from benchmark.knowledge.digital_thread import DigitalThread
from benchmark.knowledge.domain import (
    AccessContext, ApprovalRecord, CaseRecord, ControlledDocument, DecisionRecord,
    DocumentRevision, DocumentStatus, EntityRef, HumanTask,
)
from benchmark.knowledge.evidence import FileEvidenceStore
from benchmark.knowledge.memory import (
    InMemoryCaseStore, InMemoryDocumentStore, InMemoryGraphStore, InMemoryOutbox,
)
from benchmark.knowledge.service import KnowledgeBase


class DigitalThreadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.graph = InMemoryGraphStore()
        self.documents = InMemoryDocumentStore()
        self.cases = InMemoryCaseStore()
        self.outbox = InMemoryOutbox()
        self.evidence = FileEvidenceStore(Path(self.temp.name))
        self.thread = DigitalThread(
            KnowledgeBase(self.graph, self.documents), self.evidence, self.cases, self.outbox,
        )
        self.access = AccessContext(
            "SPONSOR-A", "qa-01", ("SITE-01",), ("qa",), ("internal", "confidential"),
        )
        self.now = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_evidence_first_ingestion_is_tenant_scoped_and_citable(self) -> None:
        event = self.thread.ingest_raw_event({
            "timestamp": self.now.isoformat(), "source_record_id": "MES-100",
            "event_type": "batch_started", "information_available": ["BATCH-01"],
        }, access=self.access, source_system="MES", site_id="SITE-01")

        context = self.thread.knowledge.context(
            "batch started", entity_ids=["BATCH-01"], access=self.access,
            at=self.now + timedelta(minutes=1),
        )
        self.assertEqual(event.tenant_id, "SPONSOR-A")
        self.assertEqual(len(self.evidence.records), 1)
        self.assertEqual(context.events[0].evidence_id, context.citations[0].evidence_id)
        self.assertTrue(context.citations[0].source_uri.startswith("file://"))
        self.assertEqual(self.outbox.pending()[0].topic, "knowledge.event.normalized")

        other = AccessContext("SPONSOR-B", "qa-02", clearances=("internal",))
        self.assertEqual(
            self.thread.knowledge.context("batch", entity_ids=["BATCH-01"], access=other).events,
            (),
        )

    def test_document_lineage_case_tasks_and_decision_provenance(self) -> None:
        document = ControlledDocument(
            "SOP-001", "SPONSOR-A", "SOP", "Bioreactor alarm response", "msat-01",
            ("SITE-01",), ("PRODUCT-01",),
        )
        revision = DocumentRevision(
            "SOP-001:A", "SOP-001", "A", DocumentStatus.APPROVED,
            "", self.now, ("qa-01",),
        )
        revision = self.thread.ingest_controlled_document(
            document, revision, b"SOP content",
            extracted_text="Hold batch after critical pH alarm", access=self.access,
        )
        case = CaseRecord(
            "CASE-01", "SPONSOR-A", "deviation", "pH excursion", "qa-01", "SITE-01",
            entity_refs=(EntityRef("BATCH-01", "batch"),),
        )
        self.thread.open_case(case, access=self.access)
        self.thread.assign_task(
            HumanTask("TASK-01", case.case_id, case.tenant_id, "review", "Review trend", "MSAT"),
            access=self.access,
        )
        approval = ApprovalRecord("APR-01", "qa-01", "QA", "approved", self.now, "batch disposition")
        decision = DecisionRecord(
            "DEC-01", "SPONSOR-A", case.case_id, "Hold batch", "Critical pH alarm",
            "Batch held pending investigation", self.now, "qa-01", "SITE-01",
            (revision.evidence_id,), (revision.revision_id,), (EntityRef("BATCH-01", "batch"),),
            (approval,),
        )
        self.thread.record_decision(decision, access=self.access)

        relationships = self.graph.domain_relationships
        self.assertIn(("SPONSOR-A", revision.revision_id, "REVISION_OF", document.document_id), relationships)
        self.assertIn(("SPONSOR-A", decision.decision_id, "BASED_ON", revision.evidence_id), relationships)
        self.assertIn(("SPONSOR-A", decision.decision_id, "FOLLOWED_PROCEDURE", revision.revision_id), relationships)
        self.assertEqual(self.cases.tasks_for_case(case.case_id, case.tenant_id)[0].task_id, "TASK-01")

        context = self.thread.knowledge.context(
            "critical pH alarm", entity_ids=["PRODUCT-01"], access=self.access,
            at=self.now + timedelta(minutes=1),
        )
        self.assertEqual(context.documents[0].metadata["revision"], "A")
        self.assertEqual(context.citations[0].revision, "A")

    def test_draft_documents_and_cross_tenant_writes_are_blocked(self) -> None:
        document = ControlledDocument("SOP-2", "SPONSOR-B", "SOP", "Secret", "owner")
        revision = DocumentRevision("SOP-2:A", "SOP-2", "A", DocumentStatus.DRAFT, "evd-x", self.now)
        with self.assertRaises(PermissionError):
            self.thread.publish_document(document, revision, extracted_text="secret", access=self.access)

    def test_context_uses_procedure_revision_effective_at_requested_time(self) -> None:
        document = ControlledDocument(
            "SOP-3", "SPONSOR-A", "SOP", "Alarm response", "owner",
            ("SITE-01",), ("PRODUCT-01",),
        )
        first = DocumentRevision(
            "SOP-3:A", "SOP-3", "A", DocumentStatus.APPROVED, "evd-a", self.now,
            ("qa-01",),
        )
        second = DocumentRevision(
            "SOP-3:B", "SOP-3", "B", DocumentStatus.APPROVED, "evd-b",
            self.now + timedelta(hours=5), ("qa-01",), supersedes_revision_id="SOP-3:A",
        )
        self.thread.publish_document(document, first, extracted_text="Inspect alarm", access=self.access)
        self.thread.publish_document(document, second, extracted_text="Hold batch after alarm", access=self.access)

        early = self.thread.knowledge.context(
            "alarm", entity_ids=["PRODUCT-01"], access=self.access,
            at=self.now + timedelta(hours=1),
        )
        late = self.thread.knowledge.context(
            "alarm", entity_ids=["PRODUCT-01"], access=self.access,
            at=self.now + timedelta(hours=6),
        )
        self.assertEqual(early.documents[0].metadata["revision"], "A")
        self.assertEqual(late.documents[0].metadata["revision"], "B")


if __name__ == "__main__":
    unittest.main()
