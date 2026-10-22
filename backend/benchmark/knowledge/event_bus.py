from __future__ import annotations

import json
from datetime import datetime, timezone

from .ports import Outbox


class KafkaOutboxPublisher:
    """Publishes durable outbox messages to Kafka-compatible buses such as Redpanda."""

    def __init__(self, bootstrap_servers: str, outbox: Outbox, client_id: str = "cdmo-knowledge") -> None:
        try:
            from confluent_kafka import Producer
        except ImportError as exc:  # pragma: no cover - optional service
            raise RuntimeError("Install the 'eventbus' extra to publish to Kafka/Redpanda") from exc
        self._producer = Producer({"bootstrap.servers": bootstrap_servers, "client.id": client_id})
        self._outbox = outbox

    def publish_pending(self, limit: int = 100) -> int:
        messages = self._outbox.pending(limit)
        delivered: set[str] = set()

        def delivery(error, message, *, message_id: str) -> None:
            if error is None:
                delivered.add(message_id)

        for item in messages:
            self._producer.produce(
                item.topic,
                key=f"{item.tenant_id}:{item.aggregate_id}".encode(),
                value=json.dumps(item.payload, sort_keys=True, default=str).encode(),
                headers={"message_id": item.message_id, "tenant_id": item.tenant_id},
                on_delivery=lambda error, message, message_id=item.message_id:
                    delivery(error, message, message_id=message_id),
            )
        self._producer.flush()
        published_at = datetime.now(timezone.utc)
        for message_id in delivered:
            self._outbox.mark_published(message_id, published_at)
        return len(delivered)
