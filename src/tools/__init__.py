from .analyze_trend import analyze_trend
from .base import ToolBudgetExceeded, ToolContext, ToolRegistry
from .compare_batches import compare_batches
from .create_investigation_task import create_investigation_task
from .get_batch_context import get_batch_context
from .get_evidence import get_evidence
from .request_new_evidence import request_new_evidence
from .search_factory_data import search_factory_data


RUNTIME_TOOLS = {
    "search_factory_data": search_factory_data,
    "get_batch_context": get_batch_context,
    "compare_batches": compare_batches,
    "analyze_trend": analyze_trend,
    "get_evidence": get_evidence,
    "request_new_evidence": request_new_evidence,
    "create_investigation_task": create_investigation_task,
}


def build_tool_registry(*, max_calls: int = 24) -> ToolRegistry:
    return ToolRegistry(RUNTIME_TOOLS, max_calls=max_calls)


__all__ = ["RUNTIME_TOOLS", "ToolBudgetExceeded", "ToolContext", "ToolRegistry", "build_tool_registry"]
