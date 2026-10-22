from __future__ import annotations

from .models import AuthorizedAction, SourceRecord, SyncResult
from .ports import CheckpointStore, Connector, WritableConnector
from benchmark.knowledge.digital_thread import DigitalThread
from benchmark.knowledge.domain import AccessContext


class IntegrationGateway:
    """Checkpoint-driven ingress and authorized system-of-record action loop."""

    def __init__(self, digital_thread: DigitalThread, checkpoints: CheckpointStore) -> None:
        self.digital_thread = digital_thread
        self.checkpoints = checkpoints

    def sync(
        self, connector: Connector, *, access: AccessContext, batch_size: int = 100,
        max_batches: int = 100,
    ) -> SyncResult:
        initial = self.checkpoints.get_checkpoint(access.tenant_id, connector.connector_id)
        checkpoint = initial
        ingested = 0
        batches = 0
        while batches < max_batches:
            batch = connector.pull(checkpoint, batch_size)
            if batch.has_more and batch.next_checkpoint == checkpoint:
                raise RuntimeError(f"connector {connector.connector_id} did not advance its checkpoint")
            for record in batch.records:
                self._ingest(record, connector, access)
                ingested += 1
            # Commit only after every record in the page has reached immutable evidence
            # and all knowledge projections. A retry before this point is idempotent.
            self.checkpoints.commit_checkpoint(access.tenant_id, connector.connector_id, batch.next_checkpoint)
            checkpoint = batch.next_checkpoint
            batches += 1
            if not batch.has_more:
                break
        return SyncResult(connector.connector_id, ingested, batches, initial, checkpoint)

    def execute_authorized(
        self, connector: WritableConnector, action: AuthorizedAction, *, access: AccessContext,
    ) -> SourceRecord:
        if action.tenant_id != access.tenant_id:
            raise PermissionError("cross-tenant actions are not allowed")
        if action.requested_by != access.actor_id:
            raise PermissionError("the authenticated actor must match requested_by")
        if not action.approved_by or not action.approval_ids:
            raise PermissionError("authorized writes require recorded human approvals")
        if action.source_system != connector.source_system:
            raise ValueError("action source system does not match connector")
        acknowledgement = connector.write(action)
        self._ingest(acknowledgement, connector, access)
        return acknowledgement

    def _ingest(self, record: SourceRecord, connector: Connector, access: AccessContext) -> None:
        if record.source_system != connector.source_system:
            raise ValueError("connector emitted a record for a different source system")
        payload = {
            **record.payload,
            "timestamp": record.occurred_at.isoformat(),
            "source_record_id": record.source_record_id,
        }
        self.digital_thread.ingest_raw_event(
            payload, access=access, source_system=record.source_system,
            site_id=record.site_id, classification=record.classification,
        )
