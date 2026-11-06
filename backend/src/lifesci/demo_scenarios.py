"""Fake but realistic scenarios each demo persona works through, on the seeded synthetic data.

`look_for` is shown to the visitor as "What a good answer should do": honest framing of what we are testing,
never a claim that the assistant gets it right.
"""
from __future__ import annotations

PERSONAS = ('process_engineer', 'msat', 'qa', 'executive')

SCENARIOS: tuple[dict, ...] = (
    {'scenario_id': 'pe-do-drop', 'persona': 'process_engineer', 'title': 'Dissolved oxygen dropped in B-117',
     'situation': 'Overnight, dissolved oxygen in batch B-117 on bioreactor BR-07 fell below the 30 % limit. '
                  'A signal is open and the shift wants to know why before the next feed.',
     'prompt': 'DO fell below 30 % in batch B-117 on BR-07. What do we know, what could explain it, and what should I check next?',
     'look_for': ['Cites the signal and the readings behind it', 'Separates what was observed from hypotheses',
                  'Uses linked records (equipment, lot, earlier cases)', 'Proposes specific next checks, not a conclusion']},
    {'scenario_id': 'pe-forecast', 'persona': 'process_engineer', 'title': 'Forecast growth for a running batch',
     'situation': 'Run CHO-003-R01 is at 72 h. You want to know where viable cell density and glucose are heading.',
     'prompt': 'Forecast viable cell density and glucose for CHO-003-R01 from 72 h, and show how well the model did on the other runs.',
     'look_for': ['Fits only on the verified delivery', 'Reports holdout error next to the forecast',
                  'States the model\'s known weakness and limits']},
    {'scenario_id': 'pe-compare', 'persona': 'process_engineer', 'title': 'Compare viability across runs',
     'situation': 'Six runs from the September CMO delivery. One of them may be behaving differently.',
     'prompt': 'Compare viability across the six runs in the September delivery. Which run stands out, and when?',
     'look_for': ['Names the run and time point with sources', 'Does not over-interpret small differences']},
    {'scenario_id': 'msat-outlier', 'persona': 'msat', 'title': 'Is this delivery trustworthy?',
     'situation': 'Your CMO sent its September data. Before you use it, you want to know which runs look unlike the others '
                  'and whether the data itself can be trusted.',
     'prompt': 'Which runs in the September delivery look unlike the others, and is there anything about the data itself I should not trust?',
     'look_for': ['Distinguishes process differences from data-quality problems', 'Points to the source rows']},
    {'scenario_id': 'msat-transfer', 'persona': 'msat', 'title': 'Before transferring to a new site',
     'situation': 'This CHO process is moving to a receiving site with a larger bioreactor.',
     'prompt': 'What would you check in this data before we transfer the process to a new site with a larger bioreactor?',
     'look_for': ['Names concrete characterization gaps', 'Separates evidence from assumptions']},
    {'scenario_id': 'msat-precedent', 'persona': 'msat', 'title': 'Have we seen this before?',
     'situation': 'Foaming and low DO again on BR-07.',
     'prompt': 'Have we seen foaming or low DO on BR-07 before? What did we conclude then?',
     'look_for': ['Finds the closed cases', 'Says they are similar, not proven applicable']},
    {'scenario_id': 'qa-triage', 'persona': 'qa', 'title': 'Critical deviation arrived overnight',
     'situation': 'A critical deviation, DEV-31, was recorded in the QMS overnight for batch B-117. '
                  'You need to triage it and decide whether to open a case.',
     'prompt': 'A critical QMS deviation, DEV-31, arrived overnight. Triage it: what happened, what evidence do we have, and should I open a case?',
     'look_for': ['Summarises the signal and its source record', 'Lists missing evidence',
                  'Leaves the decision to open a case to you']},
    {'scenario_id': 'qa-similar', 'persona': 'qa', 'title': 'Find similar closed cases',
     'situation': 'You suspect DEV-31 resembles something investigated before.',
     'prompt': 'Find closed cases similar to DEV-31 and tell me what their root causes and CAPAs were.',
     'look_for': ['Cites the closed cases and their closures', 'Labels them as similar, not established as applicable']},
    {'scenario_id': 'qa-package', 'persona': 'qa', 'title': 'Prepare the QA review',
     'situation': 'DEV-31 needs to go to QA review.',
     'prompt': 'What would QA need to review DEV-31? List the evidence, gaps and proposed next steps with owners.',
     'look_for': ['Separates observations, hypotheses and unknowns', 'Proposes owners for next steps']},
    {'scenario_id': 'exec-attention', 'persona': 'executive', 'title': 'What needs my attention this week?',
     'situation': 'You have five minutes before the operations review.',
     'prompt': 'What needs my attention this week across deviations, signals and our CMO deliveries?',
     'look_for': ['Short, prioritised answer', 'Every item links to its record']},
    {'scenario_id': 'exec-risk', 'persona': 'executive', 'title': 'Highest-risk open deviations',
     'situation': 'You want to know which open deviations carry the most risk and who owns them.',
     'prompt': 'Which open deviations are highest risk, and who owns them?',
     'look_for': ['Explains why each is ranked as it is', 'Names owners and status']},
    {'scenario_id': 'exec-cmo', 'persona': 'executive', 'title': 'How reliable is our CMO?',
     'situation': 'Leadership is reviewing the CMO relationship.',
     'prompt': 'How reliable has our CMO\'s data been, and what has gone wrong?',
     'look_for': ['Based on the deliveries and signals, not opinion', 'Says what it cannot judge']},
)


def for_persona(persona: str) -> list[dict]:
    return [dict(s) for s in SCENARIOS if s['persona'] == persona]


def get(scenario_id: str) -> dict | None:
    return next((dict(s) for s in SCENARIOS if s['scenario_id'] == scenario_id), None)
