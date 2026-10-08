from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable

from src.data.temporal_store import TemporalSession
from src.state.blackboard import Blackboard


ToolHandler = Callable[["ToolContext", dict[str, Any]], dict[str, Any]]


@dataclass
class ToolContext:
    session: TemporalSession
    blackboard: Blackboard


class ToolBudgetExceeded(RuntimeError):
    pass


class ToolRegistry:
    def __init__(self, handlers: dict[str, ToolHandler], *, max_calls: int = 24) -> None:
        self.handlers = dict(handlers)
        self.max_calls = max_calls
        self.calls = 0
        self.call_log: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self.handlers))

    def execute(self, name: str, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self.handlers:
            raise ValueError(f"tool is not registered: {name}")
        with self._lock:
            if self.calls >= self.max_calls:
                raise ToolBudgetExceeded(f"tool-call budget exhausted at {self.max_calls}")
            self.calls += 1
        result = self.handlers[name](context, arguments)
        with self._lock:
            self.call_log.append({"tool": name, "arguments": arguments, "evidence_ids": result.get("evidence_ids", [])})
        return result

