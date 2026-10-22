from __future__ import annotations

from collections.abc import Iterable
from threading import Event
from typing import Callable

from benchmark.knowledge.domain import AccessContext

from .gateway import IntegrationGateway
from .models import ConnectorCycleResult
from .ports import Connector


class ConnectorRunner:
    """Runs independent connector cycles and keeps the knowledge projections current."""

    def __init__(self, gateway: IntegrationGateway) -> None:
        self.gateway = gateway

    def run_cycle(
        self, connectors: Iterable[Connector], *, access: AccessContext,
        batch_size: int = 100,
    ) -> ConnectorCycleResult:
        completed = {}
        errors = {}
        for connector in connectors:
            try:
                completed[connector.connector_id] = self.gateway.sync(
                    connector, access=access, batch_size=batch_size,
                )
            except Exception as exc:  # connectors are isolated; the next source must still synchronize
                errors[connector.connector_id] = f"{type(exc).__name__}: {exc}"
        return ConnectorCycleResult(completed, errors)

    def run_forever(
        self, connectors: Iterable[Connector], *, access: AccessContext,
        poll_interval_seconds: float = 15, stop_event: Event | None = None,
        batch_size: int = 100, on_cycle: Callable[[ConnectorCycleResult], None] | None = None,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        stop = stop_event or Event()
        configured = tuple(connectors)
        while not stop.is_set():
            result = self.run_cycle(configured, access=access, batch_size=batch_size)
            if on_cycle is not None:
                on_cycle(result)
            stop.wait(poll_interval_seconds)
