"""Conversation decisions are typed data, never executable solver programs."""
from typing import Any, Literal
from datetime import datetime
from pydantic import Field, PrivateAttr, model_validator
from .schemas import PipelineSpec, StrictModel

class ChatPipelineSpec(PipelineSpec):
    max_solver_calls: int = Field(default=32, ge=2, le=32, strict=True)
    max_wall_seconds: float = Field(default=30., ge=1., le=30.)

Operator = Literal['model_library_catalog','model_library_configure','model_library_import_runs','model_library_prepare','model_library_execute','model_library_read','model_library_refresh','model_library_propose_extension','physical_demo_context', 'physical_context_variant', 'physical_pipeline_prepare',
    'physical_pipeline_execute', 'physical_results_compare', 'physical_results_assess',
    'physical_analysis_review', 'physical_model_adapter_propose',
    'bioprocess_demo_case', 'bioprocess_forecast', 'cho_dataset_forecast',
    'workspace_search', 'workspace_read', 'workspace_propose_action', 'workspace_propose_rule',
    'workspace_propose_investigation']

class ConversationIn(StrictModel):
    site_id: str = Field(default='NF1', min_length=1, max_length=100)

class ConversationUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=90)
    archived: bool | None = None


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

class ReplyClaim(StrictModel):
    """One factual statement in the reply and the exact inspected words behind it."""
    text: str = Field(min_length=1, max_length=500)
    kind: Literal['observed', 'derived'] = 'observed'
    source_id: str = Field(min_length=1, max_length=300)
    quote: str = Field(min_length=1, max_length=500)

class ChatDecision(StrictModel):
    reply: str = Field(min_length=1, max_length=4000)
    questions: list[str] = Field(default_factory=list, max_length=4)
    claims: list[ReplyClaim] = Field(default_factory=list, max_length=8)
    workflow: list[WorkflowNode] = Field(default_factory=list, max_length=10)
    continue_after_workflow: bool = False
    # Steps over a per-turn cap, held back by the host (titles), offered to the user as one click.
    _held_back: list[str] = PrivateAttr(default_factory=list)

    def _hold_over_cap(self, kinds, limit, message):
        """Run the first `limit` steps of these kinds and hold the rest, instead of rejecting a sound plan.
        Refused (the old error) only when a step that would run depends on one held back."""
        capped = [n for n in self.workflow if n.task_kind in kinds]
        if len(capped) <= limit:
            return
        held = {n.node_id for n in capped[limit:]}

        def binds(value):
            if isinstance(value, dict):
                return value.get('$node') in held or any(binds(v) for v in value.values())
            return isinstance(value, list) and any(binds(v) for v in value)
        kept = [n for n in self.workflow if n.node_id not in held]
        if any(held & set(n.depends_on) or binds(n.payload) for n in kept):
            raise ValueError(message)
        self.workflow = kept
        self._held_back = [*self._held_back, *(n.title for n in capped[limit:])]

    @model_validator(mode='after')
    def clarify_or_execute(self):
        # Discovery can resolve the uncertainty behind a provisional question.
        # Numerical work and proposals still require clarification first.
        if self.questions and any(n.task_kind not in ('workspace_search', 'workspace_read') for n in self.workflow):
            raise ValueError('ask for missing information before running a workflow')
        if self.continue_after_workflow and not self.workflow:
            raise ValueError('continuation requires tool work')
        self._hold_over_cap(('physical_pipeline_execute','model_library_execute'), 3, 'at most three numerical analyses per conversational turn')
        self._hold_over_cap(('bioprocess_forecast', 'cho_dataset_forecast'), 3, 'at most three bioprocess forecasts per conversational turn')
        if sum(n.task_kind == 'physical_results_assess' for n in self.workflow) > 1:
            raise ValueError('at most one agent interpretation per conversational turn')
        return self

WorkspaceKind = Literal['case', 'evidence', 'batch', 'sample', 'procedure_instance', 'claim',
    'proposal', 'physical_analysis_context', 'physical_model_dataset', 'physical_model_checkpoint', 'physical_interval_calibration', 'physical_analysis_result', 'process_simulation', 'engineering_chat_turn', 'deviation_signal', 'specification']

class WorkspaceSearch(StrictModel):
    """mode=search: records by kind and query. mode=links: records sharing an identifier with record_id (record_kind
    optional: omit it for an identifier such as a batch, lot or equipment ID). mode=similar_cases: closed cases similar
    to case_id and/or the query text."""
    mode: Literal['search', 'links', 'similar_cases'] = 'search'
    kinds: list[WorkspaceKind] = Field(default_factory=list, max_length=20)
    query: str = Field(default='', max_length=200)
    limit: int = Field(default=20, ge=1, le=50)
    record_kind: WorkspaceKind | None = None
    record_id: str | None = Field(default=None, max_length=300)
    case_id: str | None = Field(default=None, max_length=300)
    include_open: bool = False
    site_id: str | None = Field(default=None, max_length=100, description='Optional; must be this conversation\'s site.')

    @model_validator(mode='after')
    def mode_inputs(self):
        if self.mode == 'links' and not self.record_id:
            raise ValueError('links needs record_id')
        if self.mode == 'similar_cases' and not (self.case_id or self.query.strip()):
            raise ValueError('similar_cases needs case_id or query')
        return self

class WorkspaceRead(StrictModel):
    kind: WorkspaceKind
    record_id: str = Field(min_length=1, max_length=300)
    revision: int = Field(ge=1)
    offset: int = Field(default=0, ge=0, le=1000000)
    max_chars: int = Field(default=24000, ge=1000, le=24000)

class SourceRef(StrictModel):
    kind: WorkspaceKind
    id: str = Field(min_length=1, max_length=300)
    revision: int = Field(ge=1)
    site_id: str | None = None

class WorkspaceProposal(StrictModel):
    target_system: str = Field(min_length=1, max_length=100)
    operation: Literal['request_retest', 'place_hold', 'create_work_order', 'reschedule_batch', 'submit_deviation']
    target_id: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)
    basis: list[SourceRef] = Field(min_length=1, max_length=10)
    rationale: str = Field(min_length=10, max_length=2000)
    expected_result: str = Field(min_length=10, max_length=1000)
    follow_up_measure: str = Field(min_length=5, max_length=1000)
    constraints: list[str] = Field(default_factory=list, max_length=10)

class WorkspaceRuleProposal(StrictModel):
    """A standing instruction the user stated in this turn, saved as a PROPOSED rule only."""
    text: str = Field(min_length=3, max_length=2000)
    scope: Literal['user', 'site', 'org'] = 'user'
    # The user's own words, copied exactly from this turn's message: rules come from the user, never from sources.
    user_quote: str = Field(min_length=3, max_length=2000)

class WorkspaceInvestigationProposal(StrictModel):
    """A full multi-agent investigation the user asked for, saved as a PROPOSAL; only a person can start it."""
    objective: str = Field(min_length=3, max_length=2000)
    case_id: str | None = Field(default=None, max_length=160)
    rationale: str = Field(default='', max_length=1000)
    # The user's own words from this turn: an investigation spends budget, so it must come from the user.
    user_quote: str = Field(min_length=3, max_length=2000)

class WatchIn(StrictModel):
    enabled: bool
    expected_revision: int = Field(ge=1)
    objective: str = Field(default='', max_length=2000)
    kinds: list[Literal['case', 'evidence', 'batch', 'sample']] = Field(default_factory=lambda: ['case'])
    max_runs: int = Field(default=3, ge=1, le=10)
    every_minutes: int | None = Field(default=None, ge=15, le=10080)
    # Count limits bound inference admissions, not unknown Modal monetary billing.
    acknowledge_inference: bool = False

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
