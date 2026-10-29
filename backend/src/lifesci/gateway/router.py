"""Route selection. Enforced in code; model output never lowers risk or authority."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .registry import TIER_RANK, ModelProfile, ModelRegistry, TaskPolicy


class RoutingError(Exception):
    pass


@dataclass(frozen=True)
class RouteDecision:
    task_kind: str
    tier: str
    profile: ModelProfile | None
    reason: str
    policy_version: int
    escalation_chain: tuple[str, ...] = ()
    unqualified: bool = False  # no evaluated route; result must be treated as unreviewed draft
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {"task_kind": self.task_kind, "tier": self.tier,
                "profile_id": self.profile.profile_id if self.profile else None,
                "model": self.profile.model if self.profile else None, "reason": self.reason,
                "policy_version": self.policy_version, "escalation_chain": list(self.escalation_chain),
                "unqualified": self.unqualified, "notes": list(self.notes),
                "provider": self.profile.provider if self.profile else None,
                "profile_version": self.profile.version if self.profile else None,
                "cost_basis": {"classification": self.profile.price_source, "input_usd_per_mtok": self.profile.input_per_mtok,
                    "output_usd_per_mtok": self.profile.output_per_mtok, "cached_input_usd_per_mtok": self.profile.cached_input_per_mtok,
                    "note": "Profile-based estimate, not a reconciled provider invoice."} if self.profile else None}


class Router:
    def __init__(self, registry: ModelRegistry, *, allow_unqualified: bool = False,
                 provider_allowlist: set[str] | None = None, region: str | None = None,
                 task_profile_bindings: dict[str, str] | None = None) -> None:
        self.registry = registry
        self.allow_unqualified = allow_unqualified  # development only; marks results unqualified
        self.provider_allowlist = provider_allowlist
        self.region = region
        self.task_profile_bindings = task_profile_bindings or {}

    def _eligible(self, profiles: list[ModelProfile], policy: TaskPolicy, needs_tools: bool,
                  context_tokens: int, unavailable: set[str]) -> list[ModelProfile]:
        out = []
        for p in profiles:
            binding = self.task_profile_bindings.get(policy.task_kind)
            if binding is not None and p.profile_id != binding:
                continue
            if TIER_RANK[p.tier] < TIER_RANK[policy.min_tier]:
                continue
            if self.provider_allowlist is not None and p.provider not in self.provider_allowlist:
                continue
            if self.region and self.region not in p.regions:
                continue
            if needs_tools and not p.supports_tools:
                continue
            if context_tokens > p.max_context or p.profile_id in unavailable:
                continue
            out.append(p)
        return out

    def route(self, task_kind: str, *, ambiguity: str | None = None, needs_tools: bool = False,
              context_tokens: int = 0, unavailable: set[str] | None = None,
              suggested_risk: str | None = None) -> RouteDecision:
        unavailable = unavailable or set()
        policy = self.registry.policies.get(task_kind)
        if policy is None:
            # Unknown task classes are unqualified: conservative frontier route or human clarification.
            frontier = [p for p in self.registry.profiles.values() if p.tier == "M3" and p.profile_id not in unavailable]
            if not frontier or not self.allow_unqualified:
                raise RoutingError(f"unknown task kind {task_kind}; register a TaskPolicy or request clarification")
            pick = min(frontier, key=lambda p: p.output_per_mtok)
            return RouteDecision(task_kind, "M3", pick, "unknown task kind: conservative frontier route",
                                 self.registry.version, unqualified=True)
        notes = []
        if suggested_risk and suggested_risk != policy.risk:
            notes.append(f"model-suggested risk {suggested_risk} ignored; policy risk is {policy.risk}")
        if policy.deterministic:
            return RouteDecision(task_kind, "C0", None, "deterministic handler required by policy",
                                 self.registry.version, notes=tuple(notes))
        qualified = self._eligible(self.registry.qualified_profiles(task_kind), policy, needs_tools,
                                   context_tokens, unavailable)
        floor = policy.min_tier
        if ambiguity == "high" and TIER_RANK[floor] < TIER_RANK["M3"] and policy.risk in ("high", "critical"):
            # Do not spend first on a predictably unsuitable small model for ambiguous consequential work.
            qualified = [p for p in qualified if p.tier == "M3"] or qualified
            notes.append("high ambiguity on consequential task: prefer frontier qualified route")
        if qualified:
            ordered = sorted(qualified, key=lambda p: (TIER_RANK[p.tier], p.cost(2000, 500)))
            chain = tuple(p.profile_id for p in ordered[1:]) if policy.allow_escalation else ()
            return RouteDecision(task_kind, ordered[0].tier, ordered[0],
                                 f"cheapest evaluated route meeting floor {floor}", self.registry.version,
                                 escalation_chain=chain, notes=tuple(notes))
        if not self.allow_unqualified:
            raise RoutingError(f"no qualified, available model for {task_kind} (floor {floor}); "
                               "record an evaluation before enabling this route")
        candidates = self._eligible(list(self.registry.profiles.values()), policy, needs_tools,
                                    context_tokens, unavailable)
        # Unqualified dev route: never below the policy floor; prefer the floor tier itself.
        candidates = sorted(candidates, key=lambda p: (TIER_RANK[p.tier], p.cost(2000, 500)))
        if not candidates:
            raise RoutingError(f"no available model at or above {floor} for {task_kind}")
        chain = tuple(p.profile_id for p in candidates[1:] if TIER_RANK[p.tier] > TIER_RANK[candidates[0].tier])
        return RouteDecision(task_kind, candidates[0].tier, candidates[0],
                             f"UNQUALIFIED development route at floor {floor}", self.registry.version,
                             escalation_chain=chain, unqualified=True, notes=tuple(notes))
