import pytest

from qrace.arms import ARMS, T0_SHOTS, Arm, configure


def test_there_are_24_unique_arms():
    assert len(ARMS) == 24
    assert len({a.id for a in ARMS}) == 24


def test_id_round_trip():
    for arm in ARMS:
        assert Arm.from_id(arm.id) == arm


def test_invalid_arm_is_rejected():
    with pytest.raises(ValueError):
        Arm("L-std", "S9", "M0")


def test_configure_sets_options():
    from qiskit_ibm_runtime import Estimator
    from qiskit_ibm_runtime.fake_provider import FakeMarrakesh

    backend = FakeMarrakesh()
    for arm in ARMS:
        o = configure(Estimator(mode=backend), arm).options
        assert o.resilience_level == 0
        assert o.dynamical_decoupling.enable == (arm.supp in ("S1", "S3"))
        assert o.resilience.zne_mitigation == (arm.mitig == "M2")
        expected = T0_SHOTS // 3 if arm.mitig == "M2" else T0_SHOTS
        assert o.default_shots == expected