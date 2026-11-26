"""Read-only discovery must not be blocked by an accompanying clarification."""
import pytest
from pydantic import ValidationError

from src.lifesci.process_engineering.conversation_schemas import ChatDecision


def test_clarification_allows_safe_workspace_discovery():
    decision = ChatDecision.model_validate({'reply': 'I will check the existing records first.',
        'questions': ['Which measurement did you mean?'], 'continue_after_workflow': True,
        'workflow': [{'node_id': 'search', 'title': 'Find measurement sources',
            'task_kind': 'workspace_search', 'payload': {'kinds': ['evidence']}}]})
    assert decision.workflow[0].task_kind == 'workspace_search'
    assert decision.continue_after_workflow


def test_clarification_still_blocks_consequential_or_numerical_work():
    for operation in ('workspace_propose_action', 'physical_pipeline_execute', 'physical_demo_context'):
        with pytest.raises(ValidationError, match='ask for missing information'):
            ChatDecision.model_validate({'reply': 'I still need information.', 'questions': ['Which batch?'],
                'workflow': [{'node_id': 'work', 'title': 'Perform requested work', 'task_kind': operation}]})
