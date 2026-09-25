from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from .models import DocumentRecord


class FastEmbedProvider:
    """Local open-source embeddings; no document content leaves the deployment."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover - optional service
            raise RuntimeError("Install the 'semantic' extra to enable embeddings") from exc
        self._model = TextEmbedding(model_name=model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]


class QdrantSemanticIndex:
    """Vector index carrying enough metadata to enforce tenant filters at query time."""

    def __init__(
        self, url: str, collection: str = "knowledge_documents", *,
        embeddings: FastEmbedProvider | None = None, vector_size: int = 384,
    ) -> None:
        try:
            from qdrant_client import QdrantClient, models
        except ImportError as exc:  # pragma: no cover - optional service
            raise RuntimeError("Install the 'semantic' extra to use Qdrant") from exc
        self._client = QdrantClient(url=url)
        self._models = models
        self._collection = collection
        self._embeddings = embeddings or FastEmbedProvider()
        if not self._client.collection_exists(collection):
            self._client.create_collection(
                collection, vectors_config=models.VectorParams(
                    size=vector_size, distance=models.Distance.COSINE,
                ),
            )

    def index(self, document: DocumentRecord) -> None:
        vector = self._embeddings.embed([document.text])[0]
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, document.document_id))
        self._client.upsert(self._collection, points=[self._models.PointStruct(
            id=point_id, vector=vector,
            payload={
                "document_id": document.document_id, "text": document.text,
                "metadata": document.metadata, "payload": document.payload,
                "created_at": document.created_at.isoformat(),
            },
        )])

    def search(
        self, query: str, *, metadata_filters: dict[str, Any] | None = None, limit: int = 10
    ) -> list[DocumentRecord]:
        conditions = [
            self._models.FieldCondition(key=f"metadata.{key}", match=self._models.MatchValue(value=value))
            for key, value in (metadata_filters or {}).items()
        ]
        response = self._client.query_points(
            collection_name=self._collection, query=self._embeddings.embed([query])[0],
            query_filter=self._models.Filter(must=conditions) if conditions else None,
            limit=limit, with_payload=True,
        )
        return [DocumentRecord(
            document_id=point.payload["document_id"], text=point.payload["text"],
            metadata=point.payload["metadata"], payload=point.payload["payload"],
            created_at=datetime.fromisoformat(point.payload["created_at"]),
        ) for point in response.points]
