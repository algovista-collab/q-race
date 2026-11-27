"""D1.3: the ISA twin keeps the layout, two-qubit gates and duration of its source (Project Guide §4).

Also: the twin is Clifford, only rz angles change, and gates an ISA twin cannot handle
(e.g. fractional rx/rzz) are refused.
"""

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Clifford
from qiskit_ibm_runtime.fake_provider import FakeMarrakesh

from qrace.arms import Arm
from qrace.bench import make_instance
from qrace.run import TwinError, isa_twin, transpile_for_arm

BACKEND = FakeMarrakesh()
CASES = [
    ("F4", 8, {"p": 2}),
    ("F5", 6, {"reps": 2}),
    ("F7", 8, {"regime": "chaotic", "steps": 2}),
    ("F8", 6, {"exact": False}),
]


def _non_rz_instructions(circuit):
    """Every instruction except rz, as (name, physical qubits): the physical pulses."""
    return [
        (ins.operation.name, tuple(circuit.find_bit(q).index for q in ins.qubits))
        for ins in circuit.data
        if ins.operation.name != "rz"
    ]


@pytest.fixture(params=[(c, layout) for c in CASES for layout in ("L-std", "L-na")], ids=lambda p: f"{p[0][0]}-{p[1]}")
def source_and_twin(request):
    (family, n, params), layout = request.param
    inst = make_instance(family, n=n, index=0, **params)
    isa = transpile_for_arm(inst.circuit, Arm(layout, "S0", "M0"), BACKEND)
    return isa, isa_twin(isa)


def test_same_layout(source_and_twin):
    isa, twin = source_and_twin
    assert twin.layout.initial_index_layout() == isa.layout.initial_index_layout()
    assert twin.layout.final_index_layout() == isa.layout.final_index_layout()


def test_same_two_qubit_gates_and_pulses(source_and_twin):
    isa, twin = source_and_twin
    assert twin.count_ops().get("cz", 0) == isa.count_ops().get("cz", 0) > 0
    assert _non_rz_instructions(twin) == _non_rz_instructions(isa)


def test_same_duration(source_and_twin):
    isa, twin = source_and_twin
    assert twin.estimate_duration(BACKEND.target) == isa.estimate_duration(BACKEND.target)


def test_twin_is_clifford_with_snapped_angles(source_and_twin):
    _, twin = source_and_twin
    Clifford(twin)  # raises if any gate is not Clifford
    for ins in twin.data:
        if ins.operation.name == "rz":
            k = float(ins.operation.params[0]) / (np.pi / 2)
            assert abs(k - round(k)) < 1e-9


def test_fractional_gates_are_refused():
    qc = QuantumCircuit(1)
    qc.rx(0.3, 0)
    with pytest.raises(TwinError):
        isa_twin(qc)
