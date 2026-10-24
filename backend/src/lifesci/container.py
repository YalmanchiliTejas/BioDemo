"""Composition root: wires store, identity, gateway and domain services once per process.

Configuration (all optional):
  LIFESCI_DATABASE_URL     sqlite:///path or postgresql://... (default: in-memory sqlite)
  LIFESCI_ALLOW_UNQUALIFIED_ROUTES=1  development only: allow evaluated-route fallback (results flagged)
  ANTHROPIC_API_KEY / OPENAI_API_KEY  enable the corresponding provider adapters
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from .actions import ActionService
from .assurance import AssuranceService
from .evidence import EvidenceService
from .gateway import AnthropicProvider, ModelGateway, OpenAIProvider, Router, default_registry
from .identity import IdentityService
from .missions import MissionService
from .ownership import OwnershipRegistry
from .records import SignatureService
from .store import RecordStore
from .workqueue import WorkQueue


@dataclass
class Platform:
    store: RecordStore
    identity: IdentityService = field(init=False)
    ownership: OwnershipRegistry = field(init=False)
    evidence: EvidenceService = field(init=False)
    signatures: SignatureService = field(init=False)
    actions: ActionService = field(init=False)
    missions: MissionService = field(init=False)
    gateway: ModelGateway = field(init=False)
    assurance: AssuranceService = field(init=False)
    queue: WorkQueue = field(init=False)
    allow_unqualified: bool = False
    providers: dict[str, Any] | None = None
    api_extensions: list[Callable[..., None]] = field(default_factory=list)

    def __post_init__(self) -> None:
        s = self.store
        self.identity = IdentityService(s)
        self.ownership = OwnershipRegistry(s)
        self.evidence = EvidenceService(s, self.identity)
        self.signatures = SignatureService(s, self.identity)
        self.actions = ActionService(s, self.identity, self.ownership)
        self.missions = MissionService(s, self.identity)
        self.assurance = AssuranceService(s, self.identity)
        self.queue = WorkQueue(s)
        registry = default_registry()
        providers = self.providers if self.providers is not None else self._env_providers()
        self.gateway = ModelGateway(s, self.identity, registry, providers,
                                    router=Router(registry, allow_unqualified=self.allow_unqualified))
        try:
            from . import science
            science.register_handlers(self.gateway)
        except (ImportError, AttributeError):
            pass

    @staticmethod
    def _env_providers() -> dict[str, Any]:
        out: dict[str, Any] = {}
        if os.environ.get("ANTHROPIC_API_KEY"):
            out["anthropic"] = AnthropicProvider()
        if os.environ.get("OPENAI_API_KEY"):
            out["openai"] = OpenAIProvider()
        return out

    @classmethod
    def from_env(cls) -> "Platform":
        return cls(RecordStore(os.environ.get("LIFESCI_DATABASE_URL", ":memory:")),
                   allow_unqualified=os.environ.get("LIFESCI_ALLOW_UNQUALIFIED_ROUTES") == "1")

    def extend_api(self, app: Any, ctx_dep: Any, idempotent: Any) -> None:
        for extension in self.api_extensions:
            extension(self, app, ctx_dep, idempotent)
