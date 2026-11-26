"""Properties of the benchmark generators F1-F8."""

from __future__ import annotations

import numpy as np
import pytest

from qrace.bench import FAMILIES, make_instance, pauli_label
from qrace.bench.ideal import CLIFFORD_GATES, NON_UNITARY_IGNORED, ROTATION_GATES

from conftest import FAMILY_CASES, case_id

ALLOWED = CLIFFORD_GATES | ROTATION_GATES | NON_UNITARY_IGNORED


@pytest.mark.parametrize("case", FAMILY_CASES, ids=case_id)
def test_deterministic(case):
    family, params = case
    a = make_instance(family, 6, index=3, **params)
    b = make_instance(family, 6, index=3, **params)
    assert a.circuit_id == b.circuit_id
    assert a.circuit == b.circuit
    assert a.observables == b.observables
    np.testing.assert_array_equal(a.ideal, b.ideal)


@pytest.mark.parametrize("case", FAMILY_CASES, ids=case_id)
def test_index_changes_instance(case):
    family, params = case
    if family == "F1" and params["variant"] == "ghz":
        pytest.skip("GHZ circuit is fixed; only its observables vary")
    a = make_instance(family, 8, index=0, **params)
    b = make_instance(family, 8, index=1, **params)
    assert a.circuit_id != b.circuit_id
    assert a.seed != b.seed
    assert a.circuit != b.circuit or a.observables != b.observables


@pytest.mark.parametrize("case", FAMILY_CASES, ids=case_id)
def test_gate_set_and_no_measurements(case):
    family, params = case
    inst = make_instance(family, 6, index=0, **params)
    names = set(inst.circuit.count_ops())
    assert names <= ALLOWED, names - ALLOWED
    assert inst.circuit.num_clbits == 0


@pytest.mark.parametrize("case", FAMILY_CASES, ids=case_id)
def test_metadata_and_split(case):
    family, params = case
    inst = make_instance(family, 6, index=0, **params)
    assert inst.family == family
    assert inst.split == FAMILIES[family].split
    assert inst.split == ("heldout" if family in ("F7", "F8") else "train")
    assert inst.circuit.name == inst.circuit_id
    assert inst.circuit_id.startswith(family + "-")
    assert np.all(np.abs(inst.ideal) <= 1 + 1e-12)
    record = inst.to_record()
    assert record["n_qubits"] == 6 and len(record["ideal"]) == len(record["observables"])


def test_width_limits():
    with pytest.raises(ValueError):
        make_instance("F4", 18, p=1)
    with pytest.raises(ValueError):
        make_instance("F4", 7, p=1)  # 3-regular graphs need even n
    with pytest.raises(ValueError):
        make_instance("F8", 13, exact=True)
    with pytest.raises(KeyError):
        make_instance("F9", 4)


def test_pauli_label_little_endian():
    assert pauli_label(4, {0: "Z"}) == "IIIZ"
    assert pauli_label(4, {3: "X", 1: "Y"}) == "XIYI"


def test_ghz_parity_and_correlations():
    inst = make_instance("F1", 8, variant="ghz")
    values = dict(zip(inst.observables, inst.ideal, strict=True))
    assert values["X" * 8] == 1.0
    assert sorted(set(np.round(inst.ideal, 12))) <= [0.0, 1.0]


def test_graph_state_stabilizers_are_plus_one():
    inst = make_instance("F1", 10, index=2, variant="graph")
    assert np.all(inst.ideal[:-1] == 1.0)  # last observable is a single Z (ideal 0)
    assert inst.ideal[-1] == 0.0


def test_clifford_brickwork_evolved_stabilizers():
    inst = make_instance("F2", 10, index=0, depth=6)
    assert np.all(np.abs(inst.ideal[:3]) == 1.0)


def test_mirror_has_barriers_and_analytic_values():
    inst = make_instance("F3", 12, index=0, depth=4)
    assert inst.circuit.count_ops()["barrier"] == 2
    assert inst.ideal_method == "analytic"
    assert set(np.abs(inst.ideal)) == {1.0}


def test_qpe_exact_phase_is_sharp():
    for index in range(5):
        inst = make_instance("F8", 8, index=index, exact=True)
        assert set(np.abs(np.round(inst.ideal, 9))) == {1.0}


def test_qaoa_has_signal():
    inst = make_instance("F4", 10, index=0, p=1)
    assert np.mean(np.abs(inst.ideal)) > 0.05


def test_f6_twin_links_to_source_id():
    twin = make_instance("F6", 8, index=4, source="F4", p=1)
    source = make_instance("F4", 8, index=4, p=1)
    assert twin.twin_of == source.circuit_id
    assert twin.observables[: len(source.observables)] == source.observables


def test_transverse_field_regime_is_pure_tfim():
    n, steps = 8, 4
    inst = make_instance("F7", n, index=0, regime="transverse", steps=steps)
    assert inst.params["theta_z"] == 0.0
    # Every RZ belongs to a CX-RZ-CX ZZ rotation (one per bond per step): no Z field.
    assert inst.circuit.count_ops()["rz"] == steps * (n - 1)
    assert inst.circuit.count_ops()["rx"] == steps * n


def test_tilted_regimes_have_longitudinal_field():
    for regime in ("weak", "near-clifford", "chaotic"):
        inst = make_instance("F7", 6, index=0, regime=regime, steps=2)
        assert inst.params["theta_z"] > 0.0
