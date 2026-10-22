from __future__ import annotations

from typing import Any, Protocol


class CaseOrchestratorPort(Protocol):
    def start(self, case_id: str, context: dict[str, Any]) -> dict[str, Any]: ...
    def get(self, run_id: str) -> dict[str, Any] | None: ...
    def latest(self, case_id: str, tenant_id: str | None = None) -> dict[str, Any] | None: ...
    def case_state(self, case_id: str, tenant_id: str | None = None) -> dict[str, Any] | None: ...
    def catalog(self) -> list[dict[str, Any]]: ...


class ModelRouterPort(Protocol):
    def route(self, request: dict[str, Any]) -> dict[str, Any]: ...


class ToolExecutorPort(Protocol):
    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class ExtensionRegistry:
    """Intentional seams for the user-supplied agent, harness, and tools."""

    def __init__(
        self, orchestrator: CaseOrchestratorPort | None = None,
        model_router: ModelRouterPort | None = None,
        tool_executor: ToolExecutorPort | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.model_router = model_router
        self.tool_executor = tool_executor

    def status(self) -> dict[str, bool]:
        return {
            "agent_orchestrator": self.orchestrator is not None,
            "model_router": self.model_router is not None,
            "tool_executor": self.tool_executor is not None,
        }
