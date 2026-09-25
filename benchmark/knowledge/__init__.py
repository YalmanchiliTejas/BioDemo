"""Dynamic knowledge base for event, rule, and document context."""

from .digital_thread import DigitalThread
from .domain import (
    AccessContext, CanonicalEvent, ControlledDocument, DecisionRecord, DocumentRevision, DocumentSection,
    DomainEntity,
)
from .memory import (
    InMemoryCaseStore, InMemoryDocumentStore, InMemoryGraphStore, InMemoryOutbox,
)
from .models import Citation, ContextBundle, DocumentRecord, KnowledgeEvent, KnowledgeRule
from .service import KnowledgeBase

__all__ = [
    "ContextBundle",
    "Citation",
    "AccessContext",
    "CanonicalEvent",
    "ControlledDocument",
    "DecisionRecord",
    "DigitalThread",
    "DocumentRevision",
    "DocumentSection",
    "DomainEntity",
    "DocumentRecord",
    "InMemoryDocumentStore",
    "InMemoryGraphStore",
    "InMemoryCaseStore",
    "InMemoryOutbox",
    "KnowledgeBase",
    "KnowledgeEvent",
    "KnowledgeRule",
]
