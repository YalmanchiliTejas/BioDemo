"""Mutation robustness of CMO ingestion under a confirmed template (no network)."""
import pytest

from benchmarks.cmo_ingestion.robustness import MUTATIONS, run_harness

# Name a real, unfixed defect here (strict xfail) instead of weakening a check.
KNOWN_DEFECTS = {}


@pytest.fixture(scope='module')
def report(tmp_path_factory):
    return {r['mutation']: r for r in run_harness(tmp_path_factory.mktemp('robustness'))['mutations']}


@pytest.mark.parametrize('name', [
    pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=KNOWN_DEFECTS[n])) if n in KNOWN_DEFECTS else n
    for n, spec in MUTATIONS.items() if spec[2]])
def test_mutation_never_crashes_or_silently_accepts_wrong_values(report, name):
    checks = report[name]['checks']
    for check in ('no_crash', 'no_silent_wrong_value', 'guarantee_holds', 'no_silent_omission', 'deterministic', 'zip_safety'):
        if check in checks:
            assert checks[check]['passed'], (check, checks[check]['detail'])


@pytest.mark.parametrize('name', ['header_case_change', 'huge_cell'])
def test_one_respelled_header_or_long_cell_does_not_fail_the_delivery(report, name):
    assert report[name]['checks']['delivery_survives']['passed'], report[name]['checks']['delivery_survives']


def test_header_respelling_is_unique_or_refused():
    from src.ingestion.schema import Mapping
    m = Mapping(columns={'Titer (g/L)': 'acid_feed'}, batch_column='Batch', time_column='Time (h)')
    fixed, renamed = m.respell(['BATCH', 'TIME (H)', 'TITER (G/L)'])
    assert fixed.check(['BATCH', 'TIME (H)', 'TITER (G/L)']).columns == {'TITER (G/L)': 'acid_feed'} and len(renamed) == 3
    for headers in (['BATCH', 'TIME (H)', 'TITER (G/L)', 'titer g/l'], ['BATCH', 'TIME (H)', 'Yield']):  # ambiguous, absent
        with pytest.raises(ValueError, match='absent source header'):
            m.respell(headers)[0].check(headers)
