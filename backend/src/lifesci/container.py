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
from .gateway import AnthropicProvider, ModalProvider, ModelGateway, OpenAIProvider, Router, default_registry
from .gateway.providers import modal_settings
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
    runtime: Any = field(init=False)
    connectors: Any = field(init=False)
    procedures: Any = field(init=False)
    execution: Any = field(init=False)
    lab: Any = field(init=False)
    network: Any = field(init=False)
    transfers: Any = field(init=False)
    cases: Any = field(init=False)
    packages: Any = field(init=False)
    artifacts: Any = field(init=False)
    flows: Any = field(init=False)
    remote_sessions: Any = field(init=False)
    media_providers: dict[str, Any] = field(default_factory=dict)
    partners: Any = field(init=False)
    process_models: Any = field(init=False)
    bioprocess: Any = field(init=False)
    engineering_conversations: Any = field(init=False)
    fermentation: Any = field(init=False)
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
        from .procedures import ProcedureService
        from .execution import ExecutionService
        from .lab import LabService
        from .network import NetworkService, TransferService
        from .quality import CaseService, PackageService, ArtifactService
        self.procedures = ProcedureService(s, self.identity, self.actions, self.evidence)
        self.execution = ExecutionService(s, self.identity, self.ownership, self.procedures, self.signatures, self.evidence)
        self.lab = LabService(s, self.identity, self.ownership, self.procedures)
        self.network = NetworkService(s, self.identity)
        self.transfers = TransferService(s, self.identity)
        self.cases = CaseService(s, self.identity)
        self.packages = PackageService(s, self.identity, self.evidence, self.signatures)
        self.artifacts = ArtifactService(s, self.identity, self.evidence)
        registry = default_registry()
        from .gateway.configuration import configure_engineering_llms
        bindings = configure_engineering_llms(registry, os.environ)
        providers = self.providers if self.providers is not None else self._env_providers()
        self.gateway = ModelGateway(s, self.identity, registry, providers,
                                    router=Router(registry, allow_unqualified=self.allow_unqualified, task_profile_bindings=bindings))
        from .lyophilization.service import ProcessModelService, register_handlers
        self.process_models = ProcessModelService(self)
        register_handlers(self.gateway)
        try:
            from . import science
            science.register_handlers(self.gateway)
        except (ImportError, AttributeError):
            pass
        from .runtime import Runtime
        self.runtime = Runtime(self)
        from .connectors import ConnectorService
        self.connectors = ConnectorService(self)
        from .flows import FlowService
        self.flows = FlowService(self)
        from .bioprocess.service import BioprocessService
        self.bioprocess = BioprocessService(self)
        from .process_engineering.conversation import EngineeringConversationService
        self.engineering_conversations = EngineeringConversationService(self)
        from .fermentation.service import FermentationService
        self.fermentation = FermentationService(self)
        from .collab import RemoteSessionService
        from .media import configured_media
        from .network import PartnerService
        self.partners = PartnerService(s, self.identity, self.evidence)
        self.media_providers.update(configured_media())
        self.remote_sessions = RemoteSessionService(s, self.identity, self.media_providers)

    @staticmethod
    def _env_providers() -> dict[str, Any]:
        out: dict[str, Any] = {}
        if os.environ.get("ANTHROPIC_API_KEY"):
            out["anthropic"] = AnthropicProvider()
        if os.environ.get("OPENAI_API_KEY"):
            out["openai"] = OpenAIProvider()
        if all(modal_settings()):
            out["modal"] = ModalProvider()
        return out

    @classmethod
    def from_env(cls) -> "Platform":
        migrate = os.environ.get("LIFESCI_DB_MIGRATE", "1").strip().lower() not in {"0", "false", "no"}
        return cls(RecordStore(os.environ.get("LIFESCI_DATABASE_URL", ":memory:"), migrate=migrate),
                   allow_unqualified=os.environ.get("LIFESCI_ALLOW_UNQUALIFIED_ROUTES") == "1")

    def extend_api(self, app: Any, ctx_dep: Any, idempotent: Any) -> None:
        from .suite_api import install_suite_api
        install_suite_api(self, app, ctx_dep, idempotent)
        from .lyophilization.api import install_process_api
        install_process_api(self, app, ctx_dep, idempotent)
        from .process_engineering.api import install_analysis_api
        install_analysis_api(self, app, ctx_dep, idempotent)
        from .fermentation.api import install_fermentation_api
        install_fermentation_api(self, app, ctx_dep, idempotent)
        for extension in self.api_extensions:
            extension(self, app, ctx_dep, idempotent)
