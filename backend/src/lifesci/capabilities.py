"""Capability packs for the one manufacturing assistant.

There is a single agent: one conversation, memory, rule set and permission model. A pack is only the
tools and instructions it is shown for a task, chosen from the request, the person's roles and the
attached context. Packs never change what the person is allowed to do; the host still enforces that.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pack:
    id: str
    description: str
    operators: tuple[str, ...]
    instructions: str
    keywords: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()


CORE = Pack('core', 'Find and read authorized records; follow identifiers; propose standing rules.',
            ('workspace_search', 'workspace_read', 'workspace_propose_rule', 'workspace_propose_action'),
            'Search and read before asking. Follow identifier links (workspace_search mode=links) for any batch, lot, '
            'equipment, material or deviation ID.')

PHYSICAL = ('physical_demo_context', 'physical_context_variant', 'physical_pipeline_prepare', 'physical_pipeline_execute',
            'physical_results_compare', 'physical_results_assess', 'physical_analysis_review', 'physical_model_adapter_propose')
LIBRARY = ('model_library_catalog','model_library_configure','model_library_import_runs','model_library_prepare','model_library_execute','model_library_read','model_library_refresh','model_library_propose_extension')
BIOPROCESS = ('bioprocess_demo_case', 'bioprocess_forecast', 'cho_dataset_forecast')

PACKS = (
    Pack('quality', 'Deviations, signals, investigations, CAPA and QA review.',
         ('workspace_propose_investigation',),
         'For deviation signals (kind deviation_signal) report what fired (rule, value, limit, spec version), the subject, '
         'linked batches/lots/equipment, similar closed cases (mode=similar_cases) and missing evidence. A signal is not a '
         'deviation: propose opening a case, a multi-agent investigation or an evidence request; never conclude a root cause.',
         ('deviation', 'signal', 'capa', 'investigat', 'root cause', 'oos', 'out of spec', 'excursion', 'nonconform',
          'audit', 'quality', 'qa ', 'triage', 'case'), ('qa', 'supervisor')),
    Pack('process', 'Process data, trends, mechanistic and bioprocess models, scale-up and technology transfer (MSAT, engineering).',
         PHYSICAL + BIOPROCESS + LIBRARY,
         'Choose registered models with rationale; distinguish published values, measurements and assumptions.',
         ('model', 'simulat', 'forecast', 'transfer', 'scale', 'lyophil', 'freeze', 'ferment', 'cho', 'titer', 'trend',
          'pharmaceutical', 'hybrid', 'crystall', 'tablet', 'sensitivity', 'uncertainty', 'kla', 'drying', 'bioreactor', 'what if', 'scenario'), ('msat', 'engineering')),
    Pack('operations', 'SOP steps, execution status, shift handoffs (operator, supervisor).',
         (), 'Read procedure_instance records for step status, limits and exceptions; summarise open signals for a handoff. '
         'Guidance only: never record, sign or execute a step.',
         ('sop', 'procedure', 'step', 'shift', 'handoff', 'hand-off', 'operator', 'execution', 'batch record'), ('operator', 'supervisor')),
    Pack('materials', 'Material lots, suppliers, shortages and reconciliation (supply chain).',
         (), 'Use identifier links to connect lots to batches and suppliers; report quantity, expiry or status mismatches '
         'from source records without inferring causes.',
         ('lot', 'material', 'supplier', 'shortage', 'inventory', 'expiry', 'coa', 'raw material'), ()),
    Pack('equipment', 'Equipment history, maintenance and recurring issues.',
         (), 'Collect the equipment\'s batches, signals and cases through identifier links; separate recurrence from coincidence.',
         ('equipment', 'maintenance', 'reactor', 'pump', 'calibrat', 'valve', 'sensor', 'probe'), ()),
)
BY_ID = {p.id: p for p in PACKS}


def select(text: str, roles=(), *, has_process_context: bool = False, has_signal: bool = False) -> list[str]:
    """Pack ids for one request. Core always; if nothing specific matches, every pack (never hide tools by guessing)."""
    lowered = f' {text.lower()} '
    chosen = [p.id for p in PACKS if any(k in lowered for k in p.keywords) or set(roles) & set(p.roles)]
    if has_process_context and 'process' not in chosen:
        chosen.append('process')
    if has_signal and 'quality' not in chosen:
        chosen.append('quality')
    return ['core', *(chosen or [p.id for p in PACKS])]


def operators(pack_ids) -> set[str]:
    return set(CORE.operators).union(*(BY_ID[i].operators for i in pack_ids if i in BY_ID))


def describe(pack_ids) -> list[dict]:
    return [{'id': p.id, 'description': p.description, 'instructions': p.instructions}
            for p in (CORE, *(BY_ID[i] for i in pack_ids if i in BY_ID))]
