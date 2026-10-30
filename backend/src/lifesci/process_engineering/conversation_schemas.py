"""Conversation decisions are typed data, never executable solver programs."""
from typing import Any, Literal
from datetime import datetime
from pydantic import Field, model_validator
from .schemas import PipelineSpec, StrictModel

class ChatPipelineSpec(PipelineSpec):
    max_solver_calls: int = Field(default=32, ge=2, le=32, strict=True)
    max_wall_seconds: float = Field(default=30., ge=1., le=30.)

Operator = Literal['physical_demo_context', 'physical_context_variant', 'physical_pipeline_prepare',
    'physical_pipeline_execute', 'physical_results_compare', 'physical_results_assess',
    'physical_analysis_review', 'physical_model_adapter_propose',
    'bioprocess_demo_case', 'bioprocess_forecast', 'cho_dataset_forecast']

class ConversationIn(StrictModel):
    site_id: str = Field(default='NF1', min_length=1, max_length=100)

class DisplayContext(StrictModel):
    """Untrusted user-supplied display content, distinct from authorized sources."""
    kind: Literal['text', 'chart']
    label: str = Field(min_length=1, max_length=300)
    page_path: str = Field(pattern=r'^/[^\r\n]*$', max_length=500)
    captured_at: datetime
    content: str = Field(min_length=1, max_length=120000)

class MessageIn(StrictModel):
    text: str = Field(min_length=1, max_length=4000)
    expected_revision: int = Field(ge=1)
    enable_demo: bool = False
    source_ids: list[str] = Field(default_factory=list, max_length=5)
    # Verified CMO delivery datasets published as platform evidence (cmo-verified-delivery:<run>).
    dataset_ids: list[str] = Field(default_factory=list, max_length=5)
    display_context: DisplayContext | None = None

class WorkflowNode(StrictModel):
    node_id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,49}$')
    task_kind: Operator
    title: str = Field(min_length=3, max_length=160)
    depends_on: list[str] = Field(default_factory=list, max_length=10)
    payload: dict[str, Any] = Field(default_factory=dict)

class ChatDecision(StrictModel):
    reply: str = Field(min_length=1, max_length=4000)
    questions: list[str] = Field(default_factory=list, max_length=4)
    workflow: list[WorkflowNode] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def clarify_or_execute(self):
        if self.questions and self.workflow:
            raise ValueError('ask for missing information before running a workflow')
        if sum(n.task_kind == 'physical_pipeline_execute' for n in self.workflow) > 3:
            raise ValueError('at most three numerical analyses per conversational turn')
        if sum(n.task_kind in ('bioprocess_forecast', 'cho_dataset_forecast') for n in self.workflow) > 3:
            raise ValueError('at most three bioprocess forecasts per conversational turn')
        if sum(n.task_kind == 'physical_results_assess' for n in self.workflow) > 1:
            raise ValueError('at most one agent interpretation per conversational turn')
        return self

class DemoInputs(StrictModel):
    audience: Literal['technology_transfer', 'cdmo_operation'] = 'technology_transfer'

class Knot(StrictModel):
    time_h: float = Field(ge=0, le=96)
    shelf_temperature_c: float = Field(ge=-60, le=40)
    chamber_pressure_pa: float = Field(ge=1, le=100)

class Variant(StrictModel):
    source_id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=3, max_length=160)
    rationale: str = Field(min_length=8, max_length=2000)
    load_vials: int | None = Field(default=None, ge=100, le=11000, strict=True)
    schedule: list[Knot] | None = Field(default=None, min_length=1, max_length=20)
    vapor_capacity_kg_h: float | None = Field(default=None, ge=.1, le=2.)

class PlanId(StrictModel):
    plan_id: str = Field(min_length=1, max_length=100)

class ResultId(StrictModel):
    result_id: str = Field(min_length=1, max_length=100)

class Compare(StrictModel):
    result_ids: list[str] = Field(min_length=2, max_length=3)

CASE_ID = r'^NC-[0-9a-f]{12}$'

class DemoCase(StrictModel):
    case_id: str = Field(pattern=CASE_ID)

class BioForecast(StrictModel):
    # The demo case id, or the id of a bioprocess_case record loaded earlier in this conversation.
    case_id: str = Field(pattern=r'^(NC-[0-9a-f]{12}|biop_[0-9A-Z]{26})$')
    actions: list[str] = Field(min_length=1, max_length=11)
    rationale: str = Field(min_length=8, max_length=2000)

class ChoForecast(StrictModel):
    dataset_id: str = Field(min_length=1, max_length=200)
    batch: str = Field(min_length=1, max_length=100)
    cutoff_h: float = Field(default=72., ge=12., le=110.)
    rationale: str = Field(min_length=8, max_length=2000)
