"""Benchmark circuit families F1-F8.

Every generator is a pure function of its arguments: the same ``(n, index,
base_seed, params)`` always produces the same circuit, observables and ideal
values on every platform. All circuits are measurement-free, act on
``|0...0>``, and are built only from Clifford gates plus ``rx``/``ry``/``rz``
rotations, so that each has a structure-preserving Clifford twin
(:func:`qrace.bench.twins.clifford_twin`).

=====  ===========================================  ======  ============  ========
Code   Family                                       Qubits  Ideal value   Split
=====  ===========================================  ======  ============  ========
F1     GHZ and graph states                         4-30    stabilizer    train
F2     Random Clifford brickwork                    4-30    stabilizer    train
F3     Mirror circuits                              4-30    analytic      train
F4     QAOA MaxCut on random 3-regular graphs       4-16    statevector   train
F5     Hardware-efficient ansatz (random angles)    4-16    statevector   train
F6     Clifford twins of F4 and F5 structures       4-30    stabilizer    train
F7     Trotterized Ising chain (tilted + TFIM)      4-16    statevector   heldout
F8     Quantum phase estimation (QFT-based)         4-12    statevector   heldout
=====  ===========================================  ======  ============  ========

Observables are Pauli labels in Qiskit's little-endian convention (the right-most
character acts on qubit 0). See ``docs/BENCHMARKS.md`` for the full specification.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import networkx as nx
import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Clifford, Pauli, random_clifford

from .core import BenchmarkInstance, derive_seed
from .ideal import compute_ideal
from .twins import clifford_twin, signal_observables

__all__ = [
    "DEFAULT_BASE_SEED",
    "FAMILIES",
    "ISING_REGIMES",
    "FamilyInfo",
    "make_instance",
    "pauli_label",
    "twin_instance",
]

DEFAULT_BASE_SEED = 2026


# --------------------------------------------------------------------------- helpers


def pauli_label(n: int, factors: dict[int, str]) -> str:
    """Pauli label of length ``n`` with ``factors[q]`` on qubit ``q`` (little-endian)."""
    chars = ["I"] * n
    for q, p in factors.items():
        if not 0 <= q < n:
            raise ValueError(f"qubit {q} out of range for n={n}")
        chars[n - 1 - q] = p
    return "".join(chars)


def _strip_phase(p: Pauli) -> str:
    return Pauli((p.z, p.x)).to_label()


def _dedupe(labels: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for label in labels:
        if label not in seen and set(label) != {"I"}:
            seen.add(label)
            out.append(label)
    return out


def _zz_rotation(qc: QuantumCircuit, theta: float, a: int, b: int) -> None:
    """exp(-i theta/2 Z_a Z_b) as CX . RZ(theta) . CX (keeps the twin structure exact)."""
    qc.cx(a, b)
    qc.rz(theta, b)
    qc.cx(a, b)


def _controlled_phase(qc: QuantumCircuit, theta: float, c: int, t: int) -> None:
    """Controlled-phase CP(theta), up to a global phase, from RZ and CX only."""
    qc.rz(theta / 2, c)
    qc.cx(c, t)
    qc.rz(-theta / 2, t)
    qc.cx(c, t)
    qc.rz(theta / 2, t)


def _brickwork_pairs(n: int, layer: int) -> list[tuple[int, int]]:
    start = layer % 2
    return [(i, i + 1) for i in range(start, n - 1, 2)]


def _random_3_regular(n: int, rng: np.random.Generator) -> list[tuple[int, int]]:
    if n < 4 or n % 2:
        raise ValueError("3-regular graphs need an even number of nodes >= 4")
    graph = nx.random_regular_graph(3, n, seed=int(rng.integers(2**31 - 1)))
    return sorted(tuple(sorted(e)) for e in graph.edges())


def _haar_angles(rng: np.random.Generator) -> tuple[float, float, float]:
    """Euler angles (rz, ry, rz) of a Haar-random single-qubit unitary."""
    return (
        float(rng.uniform(0, 2 * np.pi)),
        float(np.arccos(1 - 2 * rng.uniform())),
        float(rng.uniform(0, 2 * np.pi)),
    )


def _pick(rng: np.random.Generator, seq: list[Any], k: int) -> list[Any]:
    k = min(k, len(seq))
    idx = rng.choice(len(seq), size=k, replace=False)
    return [seq[i] for i in sorted(idx)]


# --------------------------------------------------------------------------- F1


def _f1(n: int, rng: np.random.Generator, variant: str) -> tuple[QuantumCircuit, list[str], dict]:
    qc = QuantumCircuit(n)
    if variant == "ghz":
        qc.h(0)
        for i in range(n - 1):
            qc.cx(i, i + 1)
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
        obs = [pauli_label(n, {i: "Z", j: "Z"}) for i, j in _pick(rng, pairs, 3)]
        obs.append("X" * n)  # GHZ parity, ideal +1
        obs.append(pauli_label(n, {int(rng.integers(n)): "Z"}))  # ideal 0
        return qc, obs, {"graph": "chain"}
    if variant == "graph":
        if n % 2 == 0:
            edges, kind = _random_3_regular(n, rng), "3-regular"
        else:
            edges, kind = [(i, (i + 1) % n) for i in range(n)], "ring"
        qc.h(range(n))
        for a, b in edges:
            qc.cz(a, b)
        nbrs: dict[int, set[int]] = {v: set() for v in range(n)}
        for a, b in edges:
            nbrs[a].add(b)
            nbrs[b].add(a)

        def stabilizer(v: int) -> str:
            return pauli_label(n, {v: "X", **{u: "Z" for u in nbrs[v]}})

        verts = _pick(rng, list(range(n)), 4)
        obs = [stabilizer(v) for v in verts]
        a, b = edges[int(rng.integers(len(edges)))]
        obs.append(_strip_phase(Pauli(stabilizer(a)).compose(Pauli(stabilizer(b)))))
        obs.append(pauli_label(n, {int(rng.integers(n)): "Z"}))  # ideal 0
        return qc, obs, {"graph": kind, "edges": [list(e) for e in edges]}
    raise ValueError(f"unknown F1 variant {variant!r}")


# --------------------------------------------------------------------------- F2


def _f2(n: int, rng: np.random.Generator, depth: int) -> tuple[QuantumCircuit, list[str], dict]:
    qc = QuantumCircuit(n)
    for layer in range(depth):
        pairs = _brickwork_pairs(n, layer)
        covered = {q for p in pairs for q in p}
        for a, b in pairs:
            block = random_clifford(2, seed=int(rng.integers(2**31 - 1))).to_circuit()
            qc.compose(block, qubits=[a, b], inplace=True)
        for q in range(n):
            if q not in covered:
                block = random_clifford(1, seed=int(rng.integers(2**31 - 1))).to_circuit()
                qc.compose(block, qubits=[q], inplace=True)
    cliff = Clifford(qc)
    # Heisenberg-evolved Z-type stabilizers of |0..0>: ideal value +/-1 by construction.
    zs = [pauli_label(n, {int(q): "Z"}) for q in _pick(rng, list(range(n)), 2)]
    i = int(rng.integers(n - 1))
    zs.append(pauli_label(n, {i: "Z", i + 1: "Z"}))
    obs = [_strip_phase(Pauli(z).evolve(cliff, frame="s")) for z in zs]
    # One random weight-2 Pauli (ideal value typically 0) for diversity.
    q1, q2 = _pick(rng, list(range(n)), 2)
    obs.append(pauli_label(n, {q1: str(rng.choice(list("XYZ"))), q2: str(rng.choice(list("XYZ")))}))
    return qc, obs, {"depth": depth}


# --------------------------------------------------------------------------- F3


def _f3(n: int, rng: np.random.Generator, depth: int) -> tuple[QuantumCircuit, list[str], dict, np.ndarray]:
    forward = QuantumCircuit(n)
    for layer in range(depth):
        for q in range(n):
            a, b, c = _haar_angles(rng)
            forward.rz(a, q)
            forward.ry(b, q)
            forward.rz(c, q)
        for a, b in _brickwork_pairs(n, layer):
            forward.cz(a, b)
    bits = [int(x) for x in rng.integers(0, 2, size=n)]
    qc = QuantumCircuit(n)
    qc.compose(forward, inplace=True)
    qc.barrier()  # stops the transpiler from cancelling U against U^dagger
    qc.compose(forward.inverse(), inplace=True)
    qc.barrier()
    for q, bit in enumerate(bits):
        if bit:
            qc.x(q)
    supports = [[int(q)] for q in _pick(rng, list(range(n)), 2)]
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    supports += [list(p) for p in _pick(rng, pairs, 2)]
    supports.append(list(range(n)))
    obs, ideal = [], []
    for s in supports:
        label = pauli_label(n, {q: "Z" for q in s})
        if label not in obs:
            obs.append(label)
            ideal.append((-1.0) ** sum(bits[q] for q in s))
    return qc, obs, {"depth": depth, "bitstring": bits}, np.array(ideal)


# --------------------------------------------------------------------------- F4


def _f4(n: int, rng: np.random.Generator, p: int) -> tuple[QuantumCircuit, list[str], dict]:
    edges = _random_3_regular(n, rng)
    # Cost layer exp(-i gamma Z_a Z_b) per edge, mixer exp(-i beta X). Angles are drawn
    # around the p=1 MaxCut optimum on 3-regular graphs in this convention
    # (gamma ~ 0.31, beta ~ pi/8) and away from gamma = pi/4, where cos(2 gamma) = 0
    # makes every edge correlation vanish; the observables therefore carry signal.
    gammas = [float(g) for g in rng.uniform(0.15, 0.5, size=p)]
    betas = [float(b) for b in rng.uniform(0.2, 0.6, size=p)]
    qc = QuantumCircuit(n)
    qc.h(range(n))
    for gamma, beta in zip(gammas, betas, strict=True):
        for a, b in edges:
            _zz_rotation(qc, 2 * gamma, a, b)
        for q in range(n):
            qc.rx(2 * beta, q)
    obs = [pauli_label(n, {a: "Z", b: "Z"}) for a, b in edges]
    return qc, obs, {"p": p, "gammas": gammas, "betas": betas, "edges": [list(e) for e in edges]}


# --------------------------------------------------------------------------- F5


def _f5(n: int, rng: np.random.Generator, reps: int) -> tuple[QuantumCircuit, list[str], dict]:
    qc = QuantumCircuit(n)

    def rotation_layer() -> None:
        for q in range(n):
            qc.ry(float(rng.uniform(0, 2 * np.pi)), q)
            qc.rz(float(rng.uniform(0, 2 * np.pi)), q)

    for _ in range(reps):
        rotation_layer()
        for q in range(n - 1):
            qc.cx(q, q + 1)
    rotation_layer()
    obs = [pauli_label(n, {int(q): "Z"}) for q in _pick(rng, list(range(n)), 3)]
    obs += [pauli_label(n, {int(i): "Z", int(i) + 1: "Z"}) for i in _pick(rng, list(range(n - 1)), 3)]
    obs.append(pauli_label(n, {int(rng.integers(n)): "X"}))
    return qc, obs, {"reps": reps, "entanglement": "linear"}


# --------------------------------------------------------------------------- F7


#: Per-step angles (theta_X, theta_Z, theta_ZZ) of the Ising regimes. One Trotter step is
#: exp(-i theta_ZZ/2 sum Z_i Z_{i+1}) followed by RX(theta_X) and RZ(theta_Z) on every qubit,
#: i.e. a first-order step of H = J sum Z_i Z_{i+1} + h_x sum X_i + h_z sum Z_i with
#: theta_ZZ = 2 J dt, theta_X = 2 h_x dt, theta_Z = 2 h_z dt.
#:
#: * "weak", "near-clifford", "chaotic": tilted field (h_z != 0), non-integrable. Their base
#:   angles match the tilted-field Ising benchmarks published for LTM's AI-QEM Qiskit
#:   Function (IBM Quantum documentation, accessed 12 Nov 2026), for direct comparison.
#: * "transverse": pure transverse-field Ising model (h_z = 0), which in 1D is exactly
#:   solvable (Pfeuty, Ann. Phys. 57, 79, 1970); theta_X = theta_ZZ puts it near the
#:   critical point h_x = J. Included as the integrable special case.
ISING_REGIMES: dict[str, tuple[float, float, float]] = {
    "weak": (0.10, 0.10, 0.10),
    "near-clifford": (0.10, 0.05, float(np.pi / 2)),
    "chaotic": (0.53, 0.10, 1.00),
    "transverse": (0.30, 0.00, 0.30),
}


def _f7(n: int, rng: np.random.Generator, regime: str, steps: int) -> tuple[QuantumCircuit, list[str], dict]:
    base = ISING_REGIMES[regime]
    jitter = rng.uniform(0.95, 1.05, size=3)  # +/-5 % so instances differ within a regime
    tx, tz, tzz = (float(v) for v in np.array(base) * jitter)
    qc = QuantumCircuit(n)
    for _ in range(steps):
        for parity in (0, 1):
            for a, b in _brickwork_pairs(n, parity):
                _zz_rotation(qc, tzz, a, b)
        for q in range(n):
            qc.rx(tx, q)
            if tz != 0.0:  # pure transverse-field regime has no longitudinal term
                qc.rz(tz, q)
    obs = [pauli_label(n, {q: "Z"}) for q in range(n)]  # magnetisation = mean of these
    obs += [pauli_label(n, {int(i): "Z", int(i) + 1: "Z"}) for i in _pick(rng, list(range(n - 1)), 3)]
    return qc, obs, {"regime": regime, "steps": steps, "theta_x": tx, "theta_z": tz, "theta_zz": tzz}


# --------------------------------------------------------------------------- F8


def _f8(n: int, rng: np.random.Generator, exact: bool) -> tuple[QuantumCircuit, list[str], dict]:
    m = n - 1  # counting qubits 0..m-1, target qubit m
    if exact:
        k = int(rng.integers(0, 2**m))
        phase = k / 2**m
    else:
        phase = float(rng.uniform(0, 1))
    qc = QuantumCircuit(n)
    qc.x(m)  # eigenstate |1> of the phase gate P(2 pi phase)
    for j in range(m):
        qc.h(j)
    for j in range(m):
        _controlled_phase(qc, 2 * np.pi * phase * 2**j, j, m)
    qft = QuantumCircuit(m)
    for j in reversed(range(m)):
        qft.h(j)
        for k2 in reversed(range(j)):
            _controlled_phase(qft, np.pi / 2 ** (j - k2), k2, j)
    # Inverse QFT without explicit SWAPs: the QFT built above omits the final bit
    # reversal, so its inverse is applied on the reversed register. For an exactly
    # representable phase the counting register ends in a computational basis state.
    qc.compose(qft.inverse(), qubits=list(reversed(range(m))), inplace=True)
    obs = [pauli_label(n, {q: "Z"}) for q in range(m)] + [pauli_label(n, {m: "Z"})]
    return qc, obs, {"phase": phase, "counting_qubits": m, "exact": exact}


# --------------------------------------------------------------------------- registry


@dataclass(frozen=True)
class FamilyInfo:
    code: str
    title: str
    split: str
    ideal_method: str
    min_qubits: int
    max_qubits: int
    even_only: bool = False


FAMILIES: dict[str, FamilyInfo] = {
    "F1": FamilyInfo("F1", "GHZ and graph states", "train", "stabilizer", 4, 30),
    "F2": FamilyInfo("F2", "Random Clifford brickwork", "train", "stabilizer", 4, 30),
    "F3": FamilyInfo("F3", "Mirror circuits", "train", "analytic", 4, 30),
    "F4": FamilyInfo("F4", "QAOA MaxCut, 3-regular graphs", "train", "statevector", 4, 16, True),
    "F5": FamilyInfo("F5", "Hardware-efficient ansatz", "train", "statevector", 4, 16),
    "F6": FamilyInfo("F6", "Clifford twins of F4/F5", "train", "stabilizer", 4, 30),
    "F7": FamilyInfo("F7", "Trotterized Ising (tilted + TFIM)", "heldout", "statevector", 4, 16),
    "F8": FamilyInfo("F8", "Quantum phase estimation", "heldout", "statevector", 4, 12),
}


def _variant_and_tag(family: str, params: dict[str, Any]) -> tuple[str, str]:
    if family == "F1":
        return params["variant"], ""
    if family == "F2":
        return "clifford", f"d{params['depth']}"
    if family == "F3":
        return "mirror", f"d{params['depth']}"
    if family == "F4":
        return f"qaoa-p{params['p']}", ""
    if family == "F5":
        return f"hea-r{params['reps']}", ""
    if family == "F6":
        src = params["source"]
        tag = f"p{params['p']}" if src == "F4" else f"r{params['reps']}"
        return f"twin-{'qaoa' if src == 'F4' else 'hea'}-{tag}", ""
    if family == "F7":
        return f"ising-{params['regime']}", f"t{params['steps']}"
    if family == "F8":
        return f"qpe-{'exact' if params['exact'] else 'inexact'}", ""
    raise KeyError(family)


def _make_id(family: str, variant: str, n: int, tag: str, index: int) -> str:
    parts = [family, variant, f"n{n:02d}"] + ([tag] if tag else []) + [f"s{index:04d}"]
    return "-".join(parts)


def _structure_builders() -> dict[str, Callable[..., Any]]:
    return {"F1": _f1, "F2": _f2, "F3": _f3, "F4": _f4, "F5": _f5, "F7": _f7, "F8": _f8}


def make_instance(
    family: str,
    n: int,
    index: int = 0,
    base_seed: int = DEFAULT_BASE_SEED,
    **params: Any,
) -> BenchmarkInstance:
    """Generate one benchmark instance.

    Parameters
    ----------
    family:
        ``"F1"`` ... ``"F8"``.
    n:
        Number of qubits.
    index:
        Instance index within the suite; part of the identifier and of the seed.
    base_seed:
        Global seed of the suite.
    **params:
        Family parameters:
        F1 ``variant`` in {"ghz", "graph"};
        F2 ``depth``; F3 ``depth``; F4 ``p``; F5 ``reps``;
        F6 ``source`` in {"F4", "F5"} plus that family's parameter (``p`` or ``reps``);
        F7 ``regime`` in :data:`ISING_REGIMES` (three tilted-field regimes and
        ``"transverse"``) and ``steps``; F8 ``exact`` (bool).
    """
    if family not in FAMILIES:
        raise KeyError(f"unknown family {family!r}")
    info = FAMILIES[family]
    if not info.min_qubits <= n <= info.max_qubits:
        raise ValueError(f"{family} supports {info.min_qubits}-{info.max_qubits} qubits, got {n}")
    variant, tag = _variant_and_tag(family, params)
    circuit_id = _make_id(family, variant, n, tag, index)
    builders = _structure_builders()
    twin_of = None

    if family == "F6":
        source = params["source"]
        src_params = {"p": params["p"]} if source == "F4" else {"reps": params["reps"]}
        src_variant, src_tag = _variant_and_tag(source, src_params)
        seed = derive_seed(base_seed, source, src_variant, n, src_tag, index)
        qc, obs, gen_params = builders[source](n, np.random.default_rng(seed), **src_params)
        twin_of = _make_id(source, src_variant, n, src_tag, index)
        qc = clifford_twin(qc)
        obs = list(obs) + signal_observables(qc, k=4)
        gen_params = {"source": source, **src_params, "source_params": gen_params}
        ideal_vals = None
    else:
        seed = derive_seed(base_seed, family, variant, n, tag, index)
        rng = np.random.default_rng(seed)
        kwargs = {k: v for k, v in params.items() if k != "variant"}
        if family == "F1":
            kwargs = {"variant": params["variant"]}
        out = builders[family](n, rng, **kwargs)
        if family == "F3":
            qc, obs, gen_params, ideal_vals = out
        else:
            qc, obs, gen_params = out
            ideal_vals = None

    obs = _dedupe(obs)
    if info.ideal_method == "analytic":
        assert ideal_vals is not None
        method = "analytic"
    else:
        ideal_vals, method = compute_ideal(qc, obs, method=info.ideal_method)
    qc.metadata = {"circuit_id": circuit_id, "family": family, "variant": variant}
    return BenchmarkInstance(
        circuit_id=circuit_id,
        family=family,
        variant=variant,
        circuit=qc,
        observables=obs,
        ideal=ideal_vals,
        ideal_method=method,
        split=info.split,
        seed=seed,
        params={**params, **gen_params, "base_seed": base_seed, "index": index},
        twin_of=twin_of,
    )


def twin_instance(instance: BenchmarkInstance) -> BenchmarkInstance:
    """Clifford twin of any instance, with exact stabilizer ideal values.

    Used for hardware probing (Stage 3). The twin keeps the source observables and
    adds up to four signal-bearing observables (:func:`~qrace.bench.twins.signal_observables`).
    It inherits the source's split, so the twins of held-out circuits stay held out.
    """
    qc = clifford_twin(instance.circuit, name=f"{instance.circuit_id}-twin")
    observables = _dedupe(list(instance.observables) + signal_observables(qc, k=4))
    ideal_vals, method = compute_ideal(qc, observables, method="stabilizer")
    qc.metadata = {"circuit_id": f"{instance.circuit_id}-twin", "family": instance.family}
    return BenchmarkInstance(
        circuit_id=f"{instance.circuit_id}-twin",
        family=instance.family,
        variant=f"{instance.variant}-twin",
        circuit=qc,
        observables=observables,
        ideal=ideal_vals,
        ideal_method=method,
        split=instance.split,
        seed=instance.seed,
        params=dict(instance.params),
        twin_of=instance.circuit_id,
    )
