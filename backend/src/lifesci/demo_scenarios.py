"""Fake but realistic scenarios each demo persona works through, on the seeded synthetic data.

`look_for` is shown to the visitor as "What a good answer should do": honest framing of what we are testing,
never a claim that the assistant gets it right.
"""
from __future__ import annotations

PERSONAS = ('process_engineer', 'msat', 'qa', 'executive')

SCENARIOS: tuple[dict, ...] = (
    {'scenario_id': 'pe-model-library', 'persona': 'process_engineer', 'title': 'Run a pharmaceutical process model',
     'situation': 'A synthetic jacketed batch reactor makes a desired product and a competing impurity. Explore what the physical model predicts.',
     'prompt': 'Use the pharmaceutical model library to find the existing SYNTHETIC chemical.parallel_batch configuration at NF1 and run a bounded simulation. Show desired-product yield, impurity and temperature with their units, assumptions and source lineage. Explain what the model calculates and which uncertain kinetic terms support optional neural adaptation. Do not train on the configuration alone.',
     'look_for': ['Executes the existing solver and cites its saved result', 'Distinguishes conversion from desired-product yield',
                  'Keeps conservation equations intact and explains the data needed for hybrid training']},
    {'scenario_id': 'msat-model-library', 'persona': 'msat', 'title': 'Screen oxygen transfer before a site transfer',
     'situation': 'A synthetic fermentation transport configuration is available. Use it to identify what must be characterized at a receiving site.',
     'prompt': 'Find the existing SYNTHETIC fermentation.oxygen_transfer configuration at NF1 in the pharmaceutical model library and run a bounded simulation. Explain the oxygen-transfer and equipment predictions in their native units, inspect the assumptions, and propose targeted receiving-site characterization. Say what data are needed for source-to-receiver hybrid adaptation and independent interval calibration. Do not claim organism yield, product quality or transfer readiness from a transport calculation.',
     'look_for': ['Runs the fermentation transport model with evidence lineage', 'Names receiving-equipment and measurement gaps',
                  'Separates conditional predictions from calibrated transfer conclusions']},
    {'scenario_id': 'qa-model-library', 'persona': 'qa', 'title': 'Review the evidence behind a model prediction',
     'situation': 'An engineer wants to use a synthetic reaction prediction in a transfer review. Check what the result can actually support.',
     'prompt': 'Use the existing SYNTHETIC chemical.parallel_batch configuration at NF1 in the pharmaceutical model library to run a bounded simulation, then prepare a QA review of the result. Inspect model version, assumptions, evidence, units, desired-product yield and impurity. Identify missing quality attributes and independent calibration evidence. Explain why this synthetic result cannot establish release suitability, calibrated risk probabilities or yield noninferiority.',
     'look_for': ['Cites an executed result and its versioned inputs', 'Withholds conclusions for unpredicted quality attributes',
                  'Separates model review from approval and manufacturing release']},
    {'scenario_id': 'exec-model-library', 'persona': 'executive', 'title': 'Turn a process prediction into a next decision',
     'situation': 'You need to decide what evidence to fund before considering a process transfer, using a synthetic reaction example.',
     'prompt': 'Run the existing SYNTHETIC chemical.parallel_batch configuration at NF1 using the pharmaceutical model library. Give a short leadership brief: what the calculated desired-product yield and impurity mean, what remains unknown, and which characterization measurements would most help a receiving-site transfer decision. Link the saved result and distinguish predictions from validated outcomes. Do not infer commercial savings or recommend manufacturing approval from synthetic data.',
     'look_for': ['Summarizes actual calculated results with their sources', 'Gives concrete next measurements and review owners as proposals',
                  'States scientific gaps without inventing validated accuracy or savings']},
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
     'prompt': 'What would you check in the CHO run data (the verified CMO delivery) before we transfer this CHO process to a new site with a larger bioreactor?',
     'look_for': ['Names concrete characterization gaps', 'Separates evidence from assumptions']},
    {'scenario_id': 'msat-pre-transfer', 'persona': 'msat', 'title': 'Pre-transfer check: 10 L to 100 L',
     'situation': 'A SYNTHETIC reaction step runs well in a 10 L reactor and is moving to 100 L. The receiving site offers two '
                  'vessels: option A as specified, and option B with a larger jacket whose heat transfer coefficient has not '
                  'been measured yet. Before anyone books a batch, find out which vessel can run the recipe and keep the yield.',
     'prompt': 'In the pharmaceutical model library, the SYNTHETIC chemical.parallel_batch configuration is our 10 L sending '
               'reactor; the two "receiving 100 L reactor" configurations are the options at the receiving site. Run a '
               'pre-transfer check (assess_transfer) from the sending reactor to each option, against desired-product yield '
               '>= 0.85 and impurity <= 0.08 (fractions). For option B, the jacket heat transfer coefficient is not measured: '
               'use 245 to 455 W/(m2 K) as an engineering assumption (vendor value +-30 %). Tell me which option can run the '
               'recipe, what equipment shortfall you see, how confident each verdict is, and the one measurement to do next.',
     'look_for': ['Catches that option A cannot remove the reaction heat before running a batch',
                  'Labels each verdict by its basis: model-based over stated tolerances, not calibrated',
                  'Names one targeted next measurement (the receiving jacket U) instead of a full batch']},
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
    {'scenario_id': 'exec-transfer', 'persona': 'executive', 'title': 'Which receiving vessel do we commit to?',
     'situation': 'A SYNTHETIC reaction step is scaling from 10 L to 100 L. Two receiving vessels are on the table and the '
                  'team wants a decision before booking an engineering batch.',
     'prompt': 'Use the pharmaceutical model library pre-transfer check (assess_transfer) to compare the SYNTHETIC 10 L sending '
               'reactor (chemical.parallel_batch) with the two "receiving 100 L reactor" options, against yield >= 0.85 and '
               'impurity <= 0.08 (fractions); option B\'s jacket U is unmeasured, assume 245 to 455 W/(m2 K). Give me a short '
               'brief: which option to pursue, what it would have cost to find out on a batch, what is still uncertain, and '
               'the next step. Do not claim validated results from synthetic data.',
     'look_for': ['Leads with a decision and its basis', 'Separates model-based findings from validated outcomes',
                  'Proposes a cheap next measurement rather than a batch']},
    {'scenario_id': 'exec-cmo', 'persona': 'executive', 'title': 'How reliable is our CMO?',
     'situation': 'Leadership is reviewing the CMO relationship.',
     'prompt': 'How reliable has our CMO\'s data been, and what has gone wrong?',
     'look_for': ['Based on the deliveries and signals, not opinion', 'Says what it cannot judge']},
)


def for_persona(persona: str) -> list[dict]:
    return [dict(s) for s in SCENARIOS if s['persona'] == persona]


def get(scenario_id: str) -> dict | None:
    return next((dict(s) for s in SCENARIOS if s['scenario_id'] == scenario_id), None)
