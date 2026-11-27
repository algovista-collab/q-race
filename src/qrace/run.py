"""Run one (circuit, arm) evaluation on a simulator or on hardware (D1.3).

Contents:
    transpile_for_arm   apply the arm's layout: L-std (preset) or L-na (best of K by calibration)
    isa_twin            the Clifford twin for hardware probes, made from the transpiled circuit
    run_arm             transpile, configure the Estimator for the arm, run, return estimates
    SubsetBackend, compact, active_qubits, count_bases, esp: helpers

Why compaction: in local mode the client-side Estimator measures every qubit of the
backend, so a 156-qubit fake backend (e.g. FakeMarrakesh) cannot be simulated directly,
even for a 4-qubit circuit ("a circuit requires more memory than max_memory_mb").
We transpile on the full chip (so the layout sees the whole calibration), then simulate on
a SubsetBackend holding only the qubits in use, with their gate errors, durations, readout
errors and T1/T2 copied unchanged. On real hardware no compaction is done.

Fractional gates must be off (Project Guide §4): the transpiled circuit may contain only
cz, rz, sx, x (plus delay, barrier, measure, reset). ``isa_twin`` refuses anything else.
"""

from __future__ import annotations

import math

import rustworkx as rx
from qiskit import QuantumCircuit
from qiskit.circuit.library import RZGate
from qiskit.providers import BackendV2, Options
from qiskit.quantum_info import SparsePauliOp
from qiskit.transpiler import InstructionProperties, Target, generate_preset_pass_manager

from qrace.arms import Arm, configure
from qrace.bench.twins import snap_angle

SEED_TRANSPILER = 7
LNA_CANDIDATES = 10  # K: number of candidate layouts L-na compares (decision for the lead)
LNA_MAX_MAPPINGS = 2000  # how many perfect placements to pre-screen before picking the top K

#: Instructions an ISA twin may contain besides rz (all Clifford or non-unitary).
ISA_TWIN_ALLOWED = frozenset({"cz", "sx", "x", "id", "delay", "barrier", "measure", "reset"})


class TwinError(ValueError):
    """Raised when a transpiled circuit contains a gate an ISA twin cannot handle."""


# --------------------------------------------------------------------------- simulation helpers


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


def is_simulator(backend: BackendV2) -> bool:
    """True for fake backends, AerSimulator and SubsetBackend; False for real QPUs."""
    from qiskit_aer import AerSimulator
    from qiskit_ibm_runtime.fake_provider.fake_backend import FakeBackendV2

    return isinstance(backend, (FakeBackendV2, AerSimulator, SubsetBackend))


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


def count_bases(labels: list[str]) -> int:
    """Number of measurement bases the Estimator needs for these observables.

    Observables that commute qubit by qubit (e.g. IIZZ and ZIII) share one basis;
    XXXX needs another. Needed for equal-cost shot accounting.
    """
    return len(SparsePauliOp(labels).group_commuting(qubit_wise=True))


# --------------------------------------------------------------------------- layouts


def _neg_log_success(error: float | None) -> float:
    """-log(1 - error); infinite for broken elements (error >= 1), 0 if no error is known."""
    if not error:
        return 0.0
    return math.inf if error >= 1.0 else -math.log1p(-error)


def esp(isa: QuantumCircuit, target: Target) -> float:
    """Estimated success probability: product of (1 - error) over all gates and measured qubits.

    Measurement errors are counted on the qubits holding the circuit's virtual qubits.
    """
    cost = 0.0
    for ins in isa.data:
        name = ins.operation.name
        if name not in target.operation_names:
            continue
        qargs = tuple(isa.find_bit(q).index for q in ins.qubits)
        props = target[name].get(qargs)
        cost += _neg_log_success(props.error if props is not None else None)
    for q in isa.layout.final_index_layout():
        props = target["measure"].get((q,))
        cost += _neg_log_success(props.error if props is not None else None)
    return math.exp(-cost)


def _interaction_graph(circuit: QuantumCircuit) -> rx.PyGraph:
    """Undirected graph of which virtual qubits share a two-qubit gate."""
    g = rx.PyGraph()
    g.add_nodes_from(range(circuit.num_qubits))
    for ins in circuit.data:
        if len(ins.qubits) == 2:
            a, b = (circuit.find_bit(q).index for q in ins.qubits)
            if not g.has_edge(a, b):
                g.add_edge(a, b, None)
    return g


def _quick_score(mapping: dict[int, int], circuit_graph: rx.PyGraph, target: Target) -> float:
    """Cheap pre-screen of a placement (virtual -> physical): sum of -log(1 - error)
    over the two-qubit links and readouts it would use. Lower is better."""
    score = 0.0
    for a, b in circuit_graph.edge_list():
        pa, pb = mapping[a], mapping[b]
        props = target["cz"].get((pa, pb)) or target["cz"].get((pb, pa))
        score += _neg_log_success(props.error if props is not None else None)
    for p in mapping.values():
        props = target["measure"].get((p,))
        score += _neg_log_success(props.error if props is not None else None)
    return score


def _candidate_layouts(circuit: QuantumCircuit, backend: BackendV2, k: int) -> list[list[int]]:
    """Up to k initial layouts (physical qubit for each virtual qubit), best-scored first.

    Mapomatic-style: find placements where every two-qubit gate lands on a physical link
    (no SWAPs), pre-screen them by calibration, keep the best k. Circuits that fit no
    placement (e.g. QAOA on 3-regular graphs, which heavy-hex cannot embed) get an empty
    list, and the caller falls back to K routing seeds.
    """
    circuit_graph = _interaction_graph(circuit)
    coupling = backend.coupling_map.graph.to_undirected(multigraph=False)
    scored = []
    mappings = rx.vf2_mapping(coupling, circuit_graph, subgraph=True, induced=False, id_order=False)
    for i, m in enumerate(mappings):
        if i >= LNA_MAX_MAPPINGS:
            break
        v2p = {v: p for p, v in m.items()}
        if len(v2p) == circuit.num_qubits:
            score = _quick_score(v2p, circuit_graph, backend.target)
            if math.isfinite(score):  # skip placements that use a broken link or readout
                scored.append((score, [v2p[v] for v in range(circuit.num_qubits)]))
    scored.sort(key=lambda t: t[0])
    return [layout for _, layout in scored[:k]]


def transpile_for_arm(circuit: QuantumCircuit, arm: Arm, backend: BackendV2, k: int = LNA_CANDIDATES) -> QuantumCircuit:
    """Transpile an abstract circuit for the arm's layout choice.

    L-std: IBM's preset pass manager at optimization level 3 (already partly noise-aware).
    L-na:  best of K candidate layouts by ESP on the current calibration (Project Guide §7.2).
           Candidates are the K best perfect placements (no SWAPs), or, if the circuit
           fits none, K routing seeds; the L-std result is always one more candidate, so
           L-na never scores worse than the default. Each is transpiled at level 3; the
           highest ESP wins.
    """
    default = generate_preset_pass_manager(optimization_level=3, backend=backend, seed_transpiler=SEED_TRANSPILER).run(
        circuit
    )
    if arm.layout == "L-std":
        return default

    layouts = _candidate_layouts(circuit, backend, k)
    if layouts:
        candidates = [
            generate_preset_pass_manager(
                optimization_level=3, backend=backend, initial_layout=layout, seed_transpiler=SEED_TRANSPILER
            ).run(circuit)
            for layout in layouts
        ]
    else:
        candidates = [
            generate_preset_pass_manager(
                optimization_level=3, backend=backend, layout_method="sabre", seed_transpiler=seed
            ).run(circuit)
            for seed in range(k)
        ]
    candidates.append(default)
    return max(candidates, key=lambda isa: esp(isa, backend.target))


# --------------------------------------------------------------------------- ISA twin


def isa_twin(isa: QuantumCircuit) -> QuantumCircuit:
    """Clifford twin for hardware probes, made from a transpiled (ISA) circuit (Project Guide §4).

    Every rz angle is rounded to the nearest multiple of pi/2; nothing else changes and the
    twin is never transpiled again. On IBM hardware rz is virtual (no pulse, no time), so the
    twin keeps the source's physical qubits, two-qubit gates, pulses and duration.

    Raises:
        TwinError: if the circuit contains any gate other than rz, cz, sx, x (plus delay,
            barrier, measure, reset), e.g. fractional rx or rzz gates. Switch those off.
    """
    twin = isa.copy()
    for i, ins in enumerate(twin.data):
        name = ins.operation.name
        if name == "rz":
            twin.data[i] = ins.replace(operation=RZGate(snap_angle(float(ins.operation.params[0]))))
        elif name not in ISA_TWIN_ALLOWED:
            raise TwinError(f"cannot twin {name!r}: only rz, cz, sx, x allowed (switch fractional gates off)")
    return twin


# --------------------------------------------------------------------------- running


def run_arm(circuit: QuantumCircuit, labels: list[str], arm: Arm, backend: BackendV2, seed: int = 1):
    """Run one (circuit, arm) evaluation and return the estimates.

    Transpiles with the arm's layout on the full backend; on a simulator, compacts to the
    active qubits; configures the client-side Estimator for the arm (equal-cost shots);
    runs it. On real hardware the transpiled circuit is sent as it is.

    Args:
        circuit: abstract benchmark circuit (before transpilation).
        labels: its observables as Pauli labels.
        arm: which of the 24 arms to use.
        backend: a fake backend (e.g. ``FakeMarrakesh()``) or a real IBM backend.
        seed: simulator seed, so simulation results are repeatable (ignored on hardware).

    Returns:
        One estimated expectation value per observable (numpy array).
    """
    from qiskit_ibm_runtime import Estimator

    isa = transpile_for_arm(circuit, arm, backend)
    n_bases = count_bases(labels)
    if is_simulator(backend):
        run_circuit, obs, mode = compact(isa, labels, backend)
        est = configure(Estimator(mode=mode), arm, n_bases=n_bases, seed_simulator=seed)
    else:
        run_circuit = isa
        obs = [SparsePauliOp(lab).apply_layout(isa.layout) for lab in labels]
        est = configure(Estimator(mode=backend), arm, n_bases=n_bases)
    return est.run([(run_circuit, obs)]).result()[0].data.evs
