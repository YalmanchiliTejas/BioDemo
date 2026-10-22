from __future__ import annotations

from typing import Any

from .models import DocumentRecord


class MongoDocumentStore:
    """MongoDB document adapter with text and metadata retrieval."""

    def __init__(self, uri: str, database: str = "biopharma", collection: str = "knowledge_documents") -> None:
        try:
            from pymongo import MongoClient
        except ImportError as exc:  # pragma: no cover - depends on optional service
            raise RuntimeError("Install the 'knowledge' extra to use MongoDB") from exc
        self._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self._client.admin.command("ping")
        self._collection = self._client[database][collection]
        self._collection.create_index("document_id", unique=True)
        self._collection.create_index([("text", "text")])
        self._collection.create_index("metadata.entity_ids")
        self._collection.create_index("metadata.event_id")
        self._collection.create_index([("metadata.tenant_id", 1), ("metadata.site_id", 1)])
        self._collection.create_index([("metadata.document_id", 1), ("metadata.revision", 1)])

    def close(self) -> None:
        self._client.close()

    def put(self, document: DocumentRecord) -> None:
        self._collection.replace_one(
            {"document_id": document.document_id},
            {
                "document_id": document.document_id,
                "text": document.text,
                "metadata": document.metadata,
                "payload": document.payload,
                "created_at": document.created_at,
            },
            upsert=True,
        )

    def search(
        self, query: str, *, entity_ids: tuple[str, ...] = (), event_ids: tuple[str, ...] = (),
        metadata_filters: dict[str, Any] | None = None, limit: int = 10
    ) -> list[DocumentRecord]:
        filters: list[dict[str, Any]] = []
        scope_filters: list[dict[str, Any]] = []
        if entity_ids:
            scope_filters.append({"metadata.entity_ids": {"$in": list(entity_ids)}})
        if event_ids:
            scope_filters.append({"metadata.event_id": {"$in": list(event_ids)}})
        if scope_filters:
            filters.append({"$or": scope_filters})
        for key, value in (metadata_filters or {}).items():
            filters.append({f"metadata.{key}": value})
        if query.strip():
            filters.append({"$text": {"$search": query}})
        mongo_filter = {"$and": filters} if filters else {}
        cursor = self._collection.find(mongo_filter)
        if query.strip():
            cursor = cursor.sort([("score", {"$meta": "textScore"})])
        else:
            cursor = cursor.sort("created_at", -1)
        return [
            DocumentRecord(
                document_id=value["document_id"], text=value["text"], metadata=value["metadata"],
                payload=value["payload"], created_at=value["created_at"],
            )
            for value in cursor.limit(limit)
        ]
