"""Per-turn caps hold back extra steps instead of rejecting a sound plan.

Regression: "chart all six batches" planned six forecasts; the cap rejected it, the model's repair (three now,
"shall I run the rest?") was rejected by the no-questions-while-working rule, and the turn ended "stuck".
"""
import pytest

from src.lifesci.process_engineering.conversation import EngineeringConversationService
from src.lifesci.process_engineering.conversation_schemas import ChatDecision

BATCHES = ['CHO-001-R01', 'CHO-001-R02', 'CHO-002-R01', 'CHO-002-R02', 'CHO-003-R01', 'CHO-003-R02']


def forecast(batch, **extra):
    return {'node_id': 'f_' + batch.lower().replace('-', '_'), 'task_kind': 'cho_dataset_forecast',
            'title': f'Monod forecast overlay for {batch}', 'depends_on': [],
            'payload': {'batch': batch, 'cutoff_h': 72, 'dataset_id': 'cmo-verified-delivery:abc'}, **extra}


def decision(workflow, **extra):
    return {'reply': 'Charting the forecasts.', 'workflow': workflow, 'continue_after_workflow': True, **extra}


def test_six_forecasts_run_three_and_hold_three_in_order():
    d = ChatDecision.model_validate(decision([forecast(b) for b in BATCHES]))
    assert [n.payload['batch'] for n in d.workflow] == BATCHES[:3]
    assert d._held_back == [f'Monod forecast overlay for {b}' for b in BATCHES[3:]]
    assert 'held_back' not in d.model_dump()  # host state, not part of the model's contract


def test_three_or_fewer_are_untouched():
    d = ChatDecision.model_validate(decision([forecast(b) for b in BATCHES[:3]]))
    assert len(d.workflow) == 3 and d._held_back == []


def test_a_step_depending_on_a_held_back_one_is_still_refused():
    nodes = [forecast(b) for b in BATCHES[:4]]
    nodes.append({'node_id': 'compare', 'task_kind': 'workspace_read', 'title': 'Read the fourth forecast',
                  'depends_on': ['f_cho_002_r02'], 'payload': {}})
    with pytest.raises(ValueError, match='at most three bioprocess forecasts'):
        ChatDecision.model_validate(decision(nodes))


def test_questions_alongside_numerical_work_are_still_refused():
    with pytest.raises(ValueError, match='ask for missing information'):
        ChatDecision.model_validate(decision([forecast(BATCHES[0])], questions=['Which cutoff?']))


def test_planner_validation_accepts_the_trimmed_plan():
    EngineeringConversationService._validate_decision(decision([forecast(b) for b in BATCHES]))
