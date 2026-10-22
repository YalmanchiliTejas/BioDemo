from __future__ import annotations

import os

from .digital_thread import DigitalThread
from .evidence import S3EvidenceStore
from .extraction import OpenDocumentExtractor
from .mongodb import MongoDocumentStore
from .neo4j import Neo4jGraphStore
from .postgres import PostgresWorkflowStore
from .semantic import QdrantSemanticIndex
from .service import KnowledgeBase


def knowledge_base_from_env(*, semantic: bool = False) -> KnowledgeBase:
    """Build production adapters from environment variables."""
    graph = Neo4jGraphStore(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        os.getenv("NEO4J_USERNAME", "neo4j"),
        os.getenv("NEO4J_PASSWORD", "biopharma-dev"),
        os.getenv("NEO4J_DATABASE", "neo4j"),
    )
    documents = MongoDocumentStore(
        os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
        os.getenv("MONGODB_DATABASE", "biopharma"),
    )
    semantic_index = QdrantSemanticIndex(
        os.getenv("QDRANT_URL", "http://localhost:6333")
    ) if semantic else None
    return KnowledgeBase(graph, documents, semantic_index)


def digital_thread_from_env(*, semantic: bool = False) -> DigitalThread:
    knowledge = knowledge_base_from_env(semantic=semantic)
    workflow = PostgresWorkflowStore(os.getenv(
        "POSTGRES_DSN", "postgresql://biopharma:biopharma-dev@localhost:5432/biopharma"
    ))
    evidence = S3EvidenceStore(
        os.getenv("EVIDENCE_BUCKET", "cdmo-evidence"),
        endpoint_url=os.getenv("S3_ENDPOINT_URL", "http://localhost:9000"),
        region=os.getenv("AWS_REGION", "us-east-1"),
    )
    return DigitalThread(knowledge, evidence, workflow, workflow, extractor=OpenDocumentExtractor())


def integration_gateway_from_env(*, semantic: bool = False):
    from benchmark.integration.gateway import IntegrationGateway

    thread = digital_thread_from_env(semantic=semantic)
    return IntegrationGateway(thread, thread.cases)
