"""D1.3: the 24 arms, their options, and the equal-cost shot plan."""

import pytest

from qrace.arms import ARMS, T0_SHOTS, ZNE_NOISE_FACTORS, Arm, configure, shot_plan


def test_there_are_24_unique_arms():
    assert len(ARMS) == 24
    assert len({a.id for a in ARMS}) == 24


def test_id_round_trip():
    for arm in ARMS:
        assert Arm.from_id(arm.id) == arm


def test_invalid_arm_is_rejected():
    with pytest.raises(ValueError):
        Arm("L-std", "S9", "M0")


@pytest.mark.parametrize("n_bases", [1, 2, 3, 5])
def test_shot_plan_never_exceeds_and_nearly_fills_the_budget(n_bases):
    """Every arm spends at most n_bases * T0, and falls short by less than one randomization per variant."""
    budget = n_bases * T0_SHOTS
    for arm in ARMS:
        plan = shot_plan(arm, n_bases)
        assert plan.total_shots <= budget
        if arm.is_twirled:
            n_factors = len(ZNE_NOISE_FACTORS) if arm.uses_zne else 1
            assert budget - plan.total_shots < n_factors * n_bases * plan.shots_per_randomization
        else:
            assert plan.total_shots == budget


def test_configure_sets_options():
    """Every option name exists in the installed Estimator and gets the arm's value."""
    from qiskit_ibm_runtime import Estimator
    from qiskit_ibm_runtime.fake_provider import FakeMarrakesh

    backend = FakeMarrakesh()
    for arm in ARMS:
        o = configure(Estimator(mode=backend), arm, n_bases=2).options
        plan = shot_plan(arm, 2)
        assert o.resilience_level == 0
        assert o.dynamical_decoupling.enable == arm.uses_dd
        assert o.twirling.enable_gates == arm.uses_gate_twirling
        assert o.resilience.measure_mitigation == arm.uses_trex
        assert o.resilience.zne_mitigation == arm.uses_zne
        assert o.default_shots == plan.default_shots
        if arm.is_twirled:
            assert o.twirling.num_randomizations == plan.num_randomizations
