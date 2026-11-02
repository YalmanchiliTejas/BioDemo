from benchmarks.interventions.followup_report import decision, interval


def record(*, stopped=False, feasible=False, mass=100.):
    return {'evaluation': {'outcome': {'stopped': stopped,
        'post_decision_feasible': feasible, 'product_mass_kg': 0. if stopped else mass,
        'post_decision': {'below_limit_h': 0. if stopped or feasible else 2.}}}}


def test_high_mass_infeasible_action_is_wrong_and_has_no_feasible_inventory():
    result = decision(record(mass=1000.), True)
    assert result['correct'] == 0
    assert result['violating_operation'] == 1
    assert result['mass_kg'] == 1000.
    assert result['feasible_mass_kg'] == 0.


def test_stopping_and_missing_submissions_cannot_inflate_success():
    assert decision(record(stopped=True), False)['correct'] == 1
    assert decision(record(stopped=True), True)['unnecessary_stop'] == 1
    assert decision(record(stopped=True), True)['correct'] == 0
    assert decision({}, False)['correct'] == 0
    assert decision({}, False)['completed'] == 0


def test_feasible_operation_and_degenerate_bootstrap():
    assert decision(record(feasible=True), True)['correct'] == 1
    assert interval([0., 0.])['interval95'] == [0., 0.]
    assert interval([1., 1.])['mean'] == 1.
