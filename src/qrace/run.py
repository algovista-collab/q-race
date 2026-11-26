"""Run one (circuit, arm) evaluation on a simulator or on hardware (D1.3).

Contents:
    SubsetBackend   a simulation-only copy of a backend with only some of its qubits
    active_qubits   which physical qubits a transpiled circuit actually uses
    compact         move a transpiled circuit and its observables onto a SubsetBackend
    run_arm         transpile, configure the Estimator for one arm, run, return estimates

Why compaction: in local mode the client-side Estimator measures every qubit of the
backend, so a 156-qubit fake backend (e.g. FakeMarrakesh) cannot be simulated directly,
even for a 4-qubit circuit ("a circuit requires more memory than max_memory_mb").
We therefore transpile on the full chip (so the layout still sees the whole
calibration), then simulate on a SubsetBackend holding only the qubits in use, with
their gate errors, durations, readout errors and T1/T2 copied unchanged. On real
hardware no compaction is needed.

Status: L-std layout only. Still to do in D1.3: L-na layout picker, isa_twin,
equal-cost shot accounting.
"""

from __future__ import annotations

from qiskit import QuantumCircuit
from qiskit.providers import BackendV2, Options
from qiskit.quantum_info import SparsePauliOp
from qiskit.transpiler import InstructionProperties, Target, generate_preset_pass_manager

from qrace.arms import Arm, configure


class SubsetBackend(BackendV2):
    """A simulation-only copy of `parent` containing only the physical qubits in `qubits`.

    Parent qubit qubits[i] becomes qubit i here. Gate errors, durations,
    readout errors and T1/T2 are copied, so the noise on those qubits is unchanged.
    """

    def __init__(self, parent: BackendV2, qubits: list[int]):
        super().__init__(name=f"{parent.name}_subset")
        self.parent_qubits = list(qubits)
        self.qubit_map = {q: i for i, q in enumerate(qubits)}  # e.g. {12: 0, 13: 1, 18: 2, 19: 3}

        pt = parent.target
        target = Target(
            num_qubits=len(qubits),
            dt=pt.dt,
            granularity=pt.granularity,
            min_length=pt.min_length,
            pulse_alignment=pt.pulse_alignment,
            acquire_alignment=pt.acquire_alignment,
            qubit_properties=[pt.qubit_properties[q] for q in qubits],  # T1, T2
        )
        for name in pt.operation_names:
            op = pt.operation_from_name(name)
            props = pt[name]
            if props is None or None in props:  # instructions that apply to every qubit
                target.add_instruction(op, name=name)
                continue
            new = {}
            for qargs, p in props.items():
                if all(q in self.qubit_map for q in qargs):  # keep only gates on our qubits
                    key = tuple(self.qubit_map[q] for q in qargs)
                    new[key] = None if p is None else InstructionProperties(duration=p.duration, error=p.error)
            if new:
                target.add_instruction(op, new, name=name)
        self._target = target

    @property
    def target(self):
        """The reduced Target: only the kept qubits, with their copied calibration."""
        return self._target

    @property
    def max_circuits(self):
        """No limit on circuits per job (required by BackendV2)."""
        return None

    @classmethod
    def _default_options(cls):
        """No run options (required by BackendV2)."""
        return Options()

    def run(self, *args, **kwargs):
        """Not supported: this backend is only for local simulation via the Estimator."""
        raise NotImplementedError("SubsetBackend is only for local simulation via the Estimator")


def active_qubits(isa: QuantumCircuit) -> list[int]:
    """Return the physical qubits a transpiled circuit actually uses, sorted.

    A transpiled circuit is written on the whole chip (e.g. 156 qubits), but only a
    few are touched by gates. Qubits holding the circuit's virtual qubits are always
    included, even if idle, so that every observable can be mapped.
    """
    used = {isa.find_bit(q).index for ins in isa.data for q in ins.qubits}
    used |= set(isa.layout.final_index_layout())
    return sorted(used)


def compact(isa: QuantumCircuit, labels: list[str], parent: BackendV2):
    """Move a transpiled circuit and its observables onto a SubsetBackend.

    Args:
        isa: circuit transpiled for ``parent`` (written on all of its qubits).
        labels: Pauli observables on the circuit's virtual qubits, e.g. ``"IIZZ"``.
        parent: the full backend the circuit was transpiled for.

    Returns:
        ``(small_circuit, observables, subset_backend)``: the same circuit renumbered
        onto only the active qubits, the observables mapped to those qubits, and a
        backend with the parent's calibration for them.
    """
    sub = SubsetBackend(parent, active_qubits(isa))
    m = sub.qubit_map
    small = QuantumCircuit(len(m), isa.num_clbits, global_phase=isa.global_phase)
    for ins in isa.data:
        small.append(
            ins.operation,
            [small.qubits[m[isa.find_bit(q).index]] for q in ins.qubits],
            [small.clbits[isa.find_bit(c).index] for c in ins.clbits],
        )
    positions = [m[p] for p in isa.layout.final_index_layout()]
    obs = [SparsePauliOp(lab).apply_layout(positions, num_qubits=len(m)) for lab in labels]
    return small, obs, sub


def run_arm(circuit: QuantumCircuit, labels: list[str], arm: Arm, backend: BackendV2, seed: int = 1):
    """Run one (circuit, arm) evaluation on a simulated backend and return the estimates.

    Args:
        circuit: abstract benchmark circuit (before transpilation).
        labels: its observables as Pauli labels.
        arm: which of the 24 arms to use.
        backend: a fake backend, e.g. ``FakeMarrakesh()``.
        seed: simulator seed, so results are repeatable.

    Returns:
        One estimated expectation value per observable (numpy array).

    Raises:
        NotImplementedError: for L-na arms (layout picker still to be built in D1.3).
    """
    from qiskit_ibm_runtime import Estimator

    if arm.layout != "L-std":
        raise NotImplementedError("L-na layout: still to do in D1.3")
    pm = generate_preset_pass_manager(optimization_level=3, backend=backend, seed_transpiler=7)
    isa = pm.run(circuit)
    small, obs, sub = compact(isa, labels, backend)
    est = configure(Estimator(mode=sub), arm, seed_simulator=seed)
    return est.run([(small, obs)]).result()[0].data.evs