"""D1.3 checks on a fake Heron backend (Project Guide §13.5, item 2).

* All 24 arms run a 4-qubit GHZ circuit on FakeMarrakesh.
* TREX (M1) and TREX + ZNE (M2) change the estimates relative to no mitigation (M0).
* Equal cost: counting every shot the simulator actually runs, all arms spend the same
  budget (exactly, or less than one randomization per variant short).
* L-na never scores worse than L-std on ESP.
"""

import numpy as np
import pytest
import qiskit_aer.primitives as aer_primitives
from qiskit.primitives.containers.sampler_pub import SamplerPub
from qiskit_ibm_runtime.fake_provider import FakeMarrakesh

from qrace.arms import ARMS, T0_SHOTS, ZNE_NOISE_FACTORS, Arm, shot_plan
from qrace.bench import make_instance
from qrace.run import count_bases, esp, run_arm, transpile_for_arm

BACKEND = FakeMarrakesh()
GHZ = make_instance("F1", n=4, index=0, variant="ghz")


@pytest.mark.parametrize("arm", ARMS, ids=lambda a: a.id)
def test_every_arm_runs(arm):
    """All 24 arms run and give one finite estimate per observable, close enough to show the mapping is right."""
    evs = run_arm(GHZ.circuit, GHZ.observables, arm, BACKEND)
    assert evs.shape == (len(GHZ.observables),)
    assert np.all(np.isfinite(evs))
    # GHZ ideals are [1, 1, 1, 1, 0]; a wrong qubit mapping would give values near 0.
    assert np.all(evs[:4] > 0.5), evs


def test_mitigation_changes_results():
    """M1 and M2 give different estimates from M0, so the options really take effect."""
    m0, m1, m2 = (
        run_arm(GHZ.circuit, GHZ.observables, Arm.from_id(f"L-std|S0|{m}"), BACKEND) for m in ("M0", "M1", "M2")
    )
    assert not np.allclose(m0, m1)
    assert not np.allclose(m0, m2)


@pytest.fixture
def shot_counter(monkeypatch):
    """Count every shot the local simulator executes (main circuits and TREX calibration)."""
    counted = []
    original = aer_primitives.SamplerV2.run

    def counting_run(self, pubs, shots=None, **kwargs):
        for pub in pubs:
            p = SamplerPub.coerce(pub, shots)
            n_bindings = int(np.prod(p.parameter_values.shape)) if p.parameter_values.shape else 1
            counted.append(p.shots * n_bindings)
        return original(self, pubs, shots=shots, **kwargs)

    monkeypatch.setattr(aer_primitives.SamplerV2, "run", counting_run)
    return counted


@pytest.mark.parametrize("arm", [a for a in ARMS if a.layout == "L-std"], ids=lambda a: a.id)
def test_equal_cost_in_executed_shots(arm, shot_counter):
    """The shots actually executed match the plan, and no arm exceeds the budget."""
    n_bases = count_bases(GHZ.observables)
    run_arm(GHZ.circuit, GHZ.observables, arm, BACKEND)
    executed = sum(shot_counter)
    plan = shot_plan(arm, n_bases)
    assert executed == plan.total_shots
    budget = n_bases * T0_SHOTS
    n_factors = len(ZNE_NOISE_FACTORS) if arm.uses_zne else 1
    assert budget - n_factors * n_bases * 64 < executed <= budget


@pytest.mark.parametrize("family,n,params", [("F1", 4, {"variant": "ghz"}), ("F4", 6, {"p": 1})])
def test_l_na_is_never_worse_than_l_std(family, n, params):
    inst = make_instance(family, n=n, index=0, **params)
    std = transpile_for_arm(inst.circuit, Arm.from_id("L-std|S0|M0"), BACKEND)
    na = transpile_for_arm(inst.circuit, Arm.from_id("L-na|S0|M0"), BACKEND)
    assert esp(na, BACKEND.target) >= esp(std, BACKEND.target)
