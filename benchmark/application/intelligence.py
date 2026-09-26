from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from itertools import product
from typing import Any, Callable


Provider = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ModelProvider:
    provider_id: str
    family: str
    description: str
    handler: Provider


class DeterministicModelRouter:
    """Routes inspectable analytics jobs without implying an LLM is configured."""

    def __init__(self, *, llm_configured: bool = False) -> None:
        self.llm_configured = llm_configured
        self._providers = {
            "statistics.spc": ModelProvider(
                "statistics.spc", "statistical_ml", "Control-limit and latest-point SPC", self._spc,
            ),
            "statistics.anomaly": ModelProvider(
                "statistics.anomaly", "statistical_ml", "Robust median/MAD anomaly scoring", self._anomaly,
            ),
            "optimization.doe": ModelProvider(
                "optimization.doe", "optimization", "Deterministic full-factorial experiment design", self._doe,
            ),
        }

    def route(self, request: dict[str, Any]) -> dict[str, Any]:
        capability = str(request.get("capability", ""))
        provider = self._providers.get(capability)
        if provider is None:
            raise ValueError(f"no configured provider for capability: {capability}")
        result = provider.handler(request)
        return {
            "provider_id": provider.provider_id,
            "family": provider.family,
            "deterministic": True,
            "result": result,
        }

    def status(self) -> list[dict[str, Any]]:
        return [
            {
                "provider_id": provider.provider_id,
                "family": provider.family,
                "description": provider.description,
                "configured": True,
                "deterministic": True,
            }
            for provider in self._providers.values()
        ] + [{
            "provider_id": "llm.reasoning",
            "family": "llm",
            "description": "External reasoning model supplied by the Prime Agent harness",
            "configured": self.llm_configured,
            "deterministic": False,
        }]

    @staticmethod
    def _values(request: dict[str, Any]) -> list[float]:
        values = request.get("values", [])
        if not isinstance(values, list) or not values:
            raise ValueError("values must be a non-empty list")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            raise ValueError("values must contain only numbers")
        return [float(value) for value in values]

    @classmethod
    def _spc(cls, request: dict[str, Any]) -> dict[str, Any]:
        values = cls._values(request)
        mean = statistics.fmean(values)
        sigma = statistics.stdev(values) if len(values) > 1 else 0.0
        limit_sigma = float(request.get("limit_sigma", 3.0))
        lower = mean - limit_sigma * sigma
        upper = mean + limit_sigma * sigma
        violations = [index for index, value in enumerate(values) if value < lower or value > upper]
        return {
            "count": len(values), "mean": mean, "sigma": sigma,
            "lower_control_limit": lower, "upper_control_limit": upper,
            "violations": violations, "state": "alert" if violations else "in_control",
        }

    @classmethod
    def _anomaly(cls, request: dict[str, Any]) -> dict[str, Any]:
        values = cls._values(request)
        median = statistics.median(values)
        deviations = [abs(value - median) for value in values]
        mad = statistics.median(deviations)
        threshold = float(request.get("threshold", 3.5))
        scores = [0.0 if mad == 0 else 0.6745 * (value - median) / mad for value in values]
        anomalies = [index for index, score in enumerate(scores) if abs(score) > threshold]
        return {
            "count": len(values), "median": median, "mad": mad,
            "scores": scores, "anomalies": anomalies,
            "state": "alert" if anomalies else "normal",
        }

    @staticmethod
    def _doe(request: dict[str, Any]) -> dict[str, Any]:
        factors = request.get("factors", {})
        if not isinstance(factors, dict) or not factors:
            raise ValueError("factors must be a non-empty object")
        names: list[str] = []
        levels: list[list[Any]] = []
        for name, raw_levels in factors.items():
            if not isinstance(raw_levels, list) or len(raw_levels) < 2:
                raise ValueError(f"factor {name!r} requires at least two levels")
            names.append(str(name))
            levels.append(raw_levels)
        combinations = math.prod(len(items) for items in levels)
        max_runs = int(request.get("max_runs", 32))
        if combinations > max_runs:
            raise ValueError(f"full factorial requires {combinations} runs; max_runs is {max_runs}")
        runs = [
            {"run": index, "settings": dict(zip(names, values, strict=True))}
            for index, values in enumerate(product(*levels), start=1)
        ]
        return {"design": "full_factorial", "factors": names, "run_count": len(runs), "runs": runs}


class ToolGateway:
    """Small allow-listed gateway shared by agents and HTTP callers."""

    def __init__(self, router: DeterministicModelRouter) -> None:
        self.router = router
        self._tools = {
            "spc": "statistics.spc",
            "anomaly": "statistics.anomaly",
            "doe": "optimization.doe",
        }

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        capability = self._tools.get(tool_name)
        if capability is None:
            raise ValueError(f"tool is not allow-listed: {tool_name}")
        return self.router.route({"capability": capability, **arguments})

    def status(self) -> list[dict[str, str]]:
        return [
            {"tool_name": tool_name, "capability": capability, "access": "read_compute"}
            for tool_name, capability in self._tools.items()
        ]
