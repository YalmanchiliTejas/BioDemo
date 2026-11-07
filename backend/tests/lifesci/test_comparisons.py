"""Comparison check on sentences from real answers (2026-11-07): catch contradictions, never cry wolf."""
import pytest

from src.lifesci.process_engineering.comparisons import check
from src.lifesci.process_engineering.grounding import check_reply

CAUGHT = [
    ('Dissolved oxygen fell steadily all run — 61 % at 01:00, 44 % at 02:00, 33 % at 03:00, 24 % at 04:00 (historian '
     'points, seq 1–4; the last three below a 30 % action level).', '44 %, 33 %, 24 %'),  # live QA triage answer
    ('DO read 33 %, below the 30 % low limit.', '33 % is not below 30 %'),
    ('Both runs, 8.1 g/L and 9.9 g/L, stayed above 9 g/L.', '8.1 g/L, 9.9 g/L'),
    ('Two of the three runs (5.2 g/L, 4.1 g/L, 3.0 g/L) were above 4.5 g/L.', '5.2 g/L, 4.1 g/L, 3 g/L'),
]
LEFT_ALONE = [  # true statements, and ambiguous wording seen in real answers
    'DO read 24 %, below the 30 % low limit.',
    'DO read 33 %, not below the 30 % low limit.',
    'DO fell 61 % → 44 % → 33 % → 24 % over 01:00–04:00, below the 30 % low limit.',
    'It fell to 46,000 cells/mL after peaking at 14,000,000 cells/mL (the highest), above 8,126,667 cells/mL.',
    'It fell from 89.25 % at 114.5 h to 6.17 % at 142 h, while every other run was still ≥ ~72–88 %.',
    'Glucose fell from 6.4 g/L to 2.0 g/L, below 2.5 g/L.',
    'Runs ended at 9.9 g/L, 8.1 g/L and 0.3 g/L; the highest, 9.9 g/L, was CHO-003-R01.',
]


@pytest.mark.parametrize('sentence, values', CAUGHT)
def test_contradicted_comparisons_are_caught(sentence, values):
    [found] = check(sentence)
    assert values in found['but']


@pytest.mark.parametrize('sentence', LEFT_ALONE)
def test_true_or_ambiguous_statements_are_left_alone(sentence):
    assert check(sentence) == []


def test_a_contradiction_marks_the_answer_and_is_always_shown():
    out = check_reply(CAUGHT[0][0], [], {'historian': '61 44 33 24 30 01:00 04:00 1 4'})
    assert out['status'] == 'contradicted' and out['contradictions'][0]['says'] == 'the last 3 below 30 %'
