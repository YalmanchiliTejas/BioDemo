"""Operational role skills (LS-005, LS-024).

A role skill is a scoped bundle of task kinds, tools, artifacts and proposal
operations for one of the named operational roles. It is not a separate
always-on agent (D12). When an agent works for a person, its effective scope is
the intersection of the skill, the person's current permissions and the agent
role: a skill can narrow authority but can never widen it, and consequential
actions stay with humans.
"""

from __future__ import annotations

from dataclasses import dataclass

from .identity import CONSEQUENTIAL_ACTIONS, DEFAULT_ROLE_POLICY, AccessContext, IdentityService


@dataclass(frozen=True)
class RoleSkill:
    role: str
    title: str
    task_kinds: frozenset[str]
    tools: frozenset[str]
    artifacts: frozenset[str]
    may_propose: frozenset[str]
    scenario: str


def _s(*items: str) -> frozenset[str]:
    return frozenset(items)


SKILLS: dict[str, RoleSkill] = {s.role: s for s in [
    RoleSkill("operator", "Operator", _s("short_summary", "query_rewrite", "field_extraction"),
              _s("execution.perform_step", "execution.submit_offline_draft", "lab.register_sample"),
              _s("step_observation", "shift_note"), _s("request_retest", "place_hold"),
              "Explain the current step's limits and log an out-of-limit observation as an exception."),
    RoleSkill("qa", "Quality", _s("form_draft", "short_summary", "conflicting_evidence_synthesis", "comparison_explanation"),
              _s("quality.build_package", "quality.claim_view", "execution.review_by_exception"),
              _s("deviation_form", "qa_review_package", "capa_draft"),
              _s("submit_deviation", "approve_capa", "close_deviation", "quarantine_lot"),
              "Assemble a QA review package with cited fields, open gaps and review-by-exception coverage."),
    RoleSkill("msat", "MSAT", _s("comparison_explanation", "investigation_planning", "optimization_reasoning", "statistics"),
              _s("science.compare_cohorts", "science.detect_emerging_concern", "science.control_chart"),
              _s("process_trend_report", "improvement_recommendation"), _s("change_recipe_parameter"),
              "Detect an emerging drift before deviation and propose a constrained, evidence-linked adjustment."),
    RoleSkill("supervisor", "Supervisor", _s("short_summary", "task_decomposition", "notification_draft"),
              _s("network.site_view", "workqueue.metrics"), _s("shift_summary", "handoff"),
              _s("reschedule_batch", "send_notification"),
              "Prepare the shift handoff: open exceptions, pending decisions, overdue tasks."),
    RoleSkill("engineering", "Engineering", _s("comparison_explanation", "investigation_planning", "statistics"),
              _s("science.oee", "execution.prepare_maintenance"), _s("equipment_assessment"),
              _s("create_work_order"), "Compare equipment OEE and propose an engineering investigation."),
    RoleSkill("maintenance", "Maintenance", _s("short_summary", "field_extraction"),
              _s("execution.prepare_maintenance"), _s("work_order_draft"), _s("create_work_order"),
              "Prepare a work order from fault history, manuals and spares; expose missing qualification."),
    RoleSkill("supply_chain", "Supply Chain", _s("short_summary", "comparison_explanation"),
              _s("integrations.erp_reconcile", "network.propose_schedule"), _s("material_risk_report"),
              _s("reserve_material", "reschedule_batch"),
              "Reconcile ERP lots/expiry against the campaign and flag material risk."),
    RoleSkill("manufacturing_systems", "Manufacturing Systems", _s("field_extraction", "short_summary"),
              _s("integrations.preview_mapping", "integrations.matrix"), _s("connector_config_draft"), _s(),
              "Preview a connector mapping and report unmapped fields and gaps."),
    RoleSkill("quality_systems", "Quality Systems", _s("short_summary", "form_draft"),
              _s("assurance.qualification_trace", "assurance.export"), _s("qualification_trace"), _s("publish_procedure"),
              "Trace intended-use requirements to executed test evidence."),
]}


@dataclass(frozen=True)
class EffectiveScope:
    role: str
    task_kinds: frozenset[str]
    tools: frozenset[str]
    may_propose: frozenset[str]
    actions: frozenset[str]
    denied: tuple[str, ...]


def effective_scope(skill_role: str, person: AccessContext, *, as_agent: bool = True) -> EffectiveScope:
    """Intersection of skill and the person's current role policy. Never exceeds the person."""
    skill = SKILLS.get(skill_role)
    if skill is None:
        raise KeyError(f"unknown role skill {skill_role}")
    denied = []
    if skill_role not in person.roles:
        # a person may only invoke skills for roles they currently hold
        return EffectiveScope(skill_role, frozenset(), frozenset(), frozenset(), frozenset(),
                              (f"{person.actor_id} does not hold role {skill_role}",))
    person_actions: set[str] = set()
    for role in person.roles:
        for actions in DEFAULT_ROLE_POLICY.get(role, {}).values():
            person_actions |= actions
    actions = frozenset(person_actions)
    if as_agent:
        actions = actions - CONSEQUENTIAL_ACTIONS
        denied.append("consequential actions require the person, not the agent")
    may_propose = skill.may_propose if "propose" in actions else frozenset()
    return EffectiveScope(skill_role, skill.task_kinds, skill.tools, may_propose, actions, tuple(denied))


def agent_context_for(person: AccessContext, identity: IdentityService) -> AccessContext:
    """Delegated agent context: person's site scope, agent role only, linked to the delegating person.

    A person with no current roles delegates nothing: the agent gets no roles (an empty site list
    must never turn a revoked person into a tenant-wide agent).
    """
    roles = frozenset({"agent"}) if person.roles else frozenset()
    return AccessContext(person.tenant_id, f"agent:{person.actor_id}", "agent", roles,
                         person.site_ids, None, delegated_from=person.actor_id,
                         authorization_version=person.authorization_version)
