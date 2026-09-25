from __future__ import annotations


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self.checkpoints: dict[tuple[str, str], str | None] = {}

    def get_checkpoint(self, tenant_id: str, connector_id: str) -> str | None:
        return self.checkpoints.get((tenant_id, connector_id))

    def commit_checkpoint(self, tenant_id: str, connector_id: str, checkpoint: str | None) -> None:
        self.checkpoints[(tenant_id, connector_id)] = checkpoint
