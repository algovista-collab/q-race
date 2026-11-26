"""D1.3 checks: GHZ-4 runs through the L-std arms on FakeMarrakesh, and mitigation changes results.

Project Guide §13.5, item 2: run a 4-qubit GHZ circuit through the arms on a fake Heron
backend and check that M1 and M2 really change the estimates relative to M0.
L-na arms are added once the layout picker exists.
"""

import numpy as np
import pytest
from qiskit_ibm_runtime.fake_provider import FakeMarrakesh

from qrace.arms import ARMS, Arm
from qrace.bench import make_instance
from qrace.run import run_arm

BACKEND = FakeMarrakesh()
GHZ = make_instance("F1", n=4, index=0, variant="ghz")


@pytest.mark.parametrize("arm", [a for a in ARMS if a.layout == "L-std"], ids=lambda a: a.id)
def test_l_std_arms_run(arm):
    """Every L-std arm runs and returns one finite estimate per observable."""
    evs = run_arm(GHZ.circuit, GHZ.observables, arm, BACKEND)
    assert evs.shape == (len(GHZ.observables),)
    assert np.all(np.isfinite(evs))


def test_mitigation_changes_results():
    """TREX (M1) and TREX + ZNE (M2) give different estimates from no mitigation (M0)."""
    m0 = run_arm(GHZ.circuit, GHZ.observables, Arm.from_id("L-std|S0|M0"), BACKEND)
    m1 = run_arm(GHZ.circuit, GHZ.observables, Arm.from_id("L-std|S0|M1"), BACKEND)
    m2 = run_arm(GHZ.circuit, GHZ.observables, Arm.from_id("L-std|S0|M2"), BACKEND)
    assert not np.allclose(m0, m1)
    assert not np.allclose(m0, m2)