"""Policy-enforced model/tool gateway (LS-055, LS-057, LS-058, LS-066, LS-067, LS-080).

Routing order: deterministic code (C0) -> cheapest *qualified* model tier
(M1 small, M2 balanced, M3 frontier). Qualification is per task kind and is
granted only by a recorded evaluation. Unknown task kinds never default to the
cheapest model. Budgets are reserved before a call and reconciled afterwards;
exhaustion pauses with progress rather than lowering controls.
"""

from .registry import ModelProfile, TaskPolicy, ModelRegistry, default_registry  # noqa: F401
from .router import Router, RouteDecision, RoutingError  # noqa: F401
from .budget import BudgetLedger, BudgetExceeded  # noqa: F401
from .providers import Provider, ProviderError, FakeProvider, AnthropicProvider, OpenAIProvider  # noqa: F401
from .gateway import ModelGateway, TaskRequest, TaskResult  # noqa: F401
