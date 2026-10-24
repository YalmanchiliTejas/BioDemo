"""Model profiles, task policies and evaluation-gated qualification.

Prices are a dated, versioned calculation input, not a commitment. The default
registry lists candidate models per tier for two providers; none is qualified
for any task until an evaluation record is attached (LS-067).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

TIERS = ("C0", "M1", "M2", "M3")
TIER_RANK = {t: i for i, t in enumerate(TIERS)}
RISK_CLASSES = ("low", "moderate", "high", "critical")


@dataclass(frozen=True)
class ModelProfile:
    profile_id: str
    provider: str
    model: str
    tier: str
    input_per_mtok: float
    output_per_mtok: float
    cached_input_per_mtok: float
    max_context: int = 200_000
    supports_tools: bool = True
    regions: tuple[str, ...] = ("us",)
    price_source: str = ""
    price_retrieved: str = ""
    version: str = "1"

    def cost(self, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
        uncached = max(input_tokens - cached_tokens, 0)
        return (uncached * self.input_per_mtok + cached_tokens * self.cached_input_per_mtok
                + output_tokens * self.output_per_mtok) / 1_000_000


@dataclass(frozen=True)
class TaskPolicy:
    """Application-owned policy per task kind. Models may suggest labels but cannot lower these."""
    task_kind: str
    risk: str
    min_tier: str
    description: str = ""
    deterministic: bool = False           # handled by registered code, never a model
    requires_human_review: bool = False
    max_output_tokens: int = 2_000
    max_repairs: int = 1
    allow_escalation: bool = True
    output_schema: dict[str, Any] | None = None  # required keys / types for validation


@dataclass(frozen=True)
class Qualification:
    task_kind: str
    profile_id: str
    eval_id: str
    passed: bool
    metrics: dict[str, float]
    thresholds: dict[str, float]
    impact_scope: str
    policy_version: str


@dataclass
class ModelRegistry:
    profiles: dict[str, ModelProfile] = field(default_factory=dict)
    policies: dict[str, TaskPolicy] = field(default_factory=dict)
    qualifications: dict[tuple[str, str], Qualification] = field(default_factory=dict)
    version: int = 1

    def add_profile(self, profile: ModelProfile) -> None:
        if profile.tier not in TIERS[1:]:
            raise ValueError("model profiles must be tier M1, M2 or M3")
        self.profiles[profile.profile_id] = profile
        self.version += 1

    def add_policy(self, policy: TaskPolicy) -> None:
        if policy.risk not in RISK_CLASSES or policy.min_tier not in TIERS:
            raise ValueError("invalid risk or tier")
        self.policies[policy.task_kind] = policy
        self.version += 1

    def qualify(self, q: Qualification) -> None:
        """Activate a profile for a task kind only with a passing, threshold-checked evaluation."""
        if q.profile_id not in self.profiles:
            raise KeyError(q.profile_id)
        if q.task_kind not in self.policies:
            raise KeyError(q.task_kind)
        if not q.eval_id or not q.impact_scope:
            raise ValueError("qualification requires an evaluation id and impact scope")
        failing = {k: v for k, v in q.thresholds.items() if q.metrics.get(k, float("-inf")) < v}
        if not q.passed or failing:
            raise ValueError(f"evaluation {q.eval_id} does not meet thresholds: {failing or 'marked failed'}")
        policy = self.policies[q.task_kind]
        if TIER_RANK[self.profiles[q.profile_id].tier] < TIER_RANK[policy.min_tier]:
            raise ValueError(f"{q.profile_id} is below the minimum tier {policy.min_tier} for {q.task_kind}")
        self.qualifications[(q.task_kind, q.profile_id)] = q
        self.version += 1

    def suspend(self, task_kind: str, profile_id: str) -> None:
        """Drift monitoring can suspend a qualification (LS-089); approved past work is untouched."""
        self.qualifications.pop((task_kind, profile_id), None)
        self.version += 1

    def qualified_profiles(self, task_kind: str) -> list[ModelProfile]:
        return [self.profiles[p] for (t, p) in self.qualifications if t == task_kind and p in self.profiles]

    def reprice(self, profile_id: str, **prices: float) -> None:
        self.profiles[profile_id] = replace(self.profiles[profile_id], **prices)
        self.version += 1


_ANTHROPIC = "Anthropic model catalog via OpenCode models tool"
_OPENAI = "https://developers.openai.com/api/docs/pricing (docs/product/life-sciences-platform/model-routing.md)"


def default_profiles() -> list[ModelProfile]:
    return [
        ModelProfile("anthropic-haiku", "anthropic", "claude-haiku-5-5", "M1", 0.10, 0.50, 0.01,
                     price_source=_ANTHROPIC, price_retrieved="2026-10-23"),
        ModelProfile("anthropic-sonnet", "anthropic", "claude-sonnet-5-5", "M2", 2.00, 10.00, 0.10,
                     price_source=_ANTHROPIC, price_retrieved="2026-10-23"),
        ModelProfile("anthropic-opus", "anthropic", "claude-opus-5-5", "M3", 4.00, 20.00, 0.20,
                     price_source=_ANTHROPIC, price_retrieved="2026-10-23"),
        ModelProfile("openai-luna", "openai", "gpt-6-luna", "M1", 0.10, 0.50, 0.01,
                     price_source=_OPENAI, price_retrieved="2026-10-23"),
        ModelProfile("openai-sol", "openai", "gpt-6.1-sol", "M2", 2.00, 10.00, 0.10,
                     price_source=_OPENAI, price_retrieved="2026-10-23"),
        ModelProfile("openai-astra", "openai", "gpt-6-astra", "M3", 10.00, 50.00, 1.00,
                     price_source=_OPENAI, price_retrieved="2026-10-23"),
    ]


def default_policies() -> list[TaskPolicy]:
    """Task taxonomy from model-routing.md. min_tier is the floor; qualification decides the actual route."""
    P = TaskPolicy
    return [
        # C0 — deterministic only
        P("unit_conversion", "high", "C0", deterministic=True),
        P("limit_check", "critical", "C0", deterministic=True),
        P("authorization", "critical", "C0", deterministic=True),
        P("procedure_sequencing", "critical", "C0", deterministic=True),
        P("statistics", "high", "C0", deterministic=True),
        # M1 — small, schema-checked
        P("document_classification", "low", "M1", output_schema={"category": "str", "evidence_span": "str"}),
        P("field_extraction", "moderate", "M1", output_schema={"fields": "list"}),
        P("short_summary", "low", "M1", output_schema={"summary": "str", "source_refs": "list"}),
        P("query_rewrite", "low", "M1", output_schema={"query": "str"}),
        P("notification_draft", "low", "M1", output_schema={"subject": "str", "body": "str"}),
        # M2 — balanced
        P("form_draft", "moderate", "M2", requires_human_review=True, output_schema={"fields": "list"}),
        P("procedure_interpretation", "high", "M2", requires_human_review=True, output_schema={"steps": "list"}),
        P("comparison_explanation", "moderate", "M2", output_schema={"explanation": "str", "source_refs": "list"}),
        P("task_decomposition", "moderate", "M2", output_schema={"tasks": "list"}),
        # M3 — frontier
        P("investigation_planning", "high", "M3", requires_human_review=True, max_output_tokens=6_000),
        P("conflicting_evidence_synthesis", "high", "M3", requires_human_review=True, max_output_tokens=6_000),
        P("optimization_reasoning", "high", "M3", requires_human_review=True, max_output_tokens=6_000),
    ]


def default_registry() -> ModelRegistry:
    reg = ModelRegistry()
    for p in default_profiles():
        reg.add_profile(p)
    for t in default_policies():
        reg.add_policy(t)
    return reg
