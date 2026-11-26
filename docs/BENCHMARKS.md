# Benchmark specification (deliverable D1.2)

This document specifies the Q-RACE benchmark suite precisely enough to be
re-implemented from scratch. It is written to serve as the basis of the
"Benchmarks" subsection of the Methods section of the paper. The reference
implementation is `src/qrace/bench/`.

## 1. Design requirements

1. **Exact ground truth.** Every observable of every circuit has a noise-free
   expectation value that is known exactly (to floating-point precision), so the
   error of any execution strategy can be measured on real hardware.
2. **Structure-preserving Clifford twin.** Every circuit is built only from
   Clifford gates and single-qubit rotations `rx`, `ry`, `rz`. Rounding each
   rotation angle to the nearest multiple of π/2 therefore yields a Clifford
   circuit with identical two-qubit structure (the *Clifford twin*), whose ideal
   values are exact at any width (§5).
3. **Determinism.** Every random choice is derived from a SHA-256 hash of
   `(base_seed, family, variant, n, tag, index)`. The same arguments produce
   byte-identical QPY files across runs, platforms and Python 3.11–3.13
   (verified in `docs/cp1/ACCEPTANCE.md`).
4. **Held-out families.** F7 and F8 are never used for training or hardware
   calibration; they exist for the pre-registered blind test.
5. **Estimator-style circuits.** Circuits contain no measurements and act on
   `|0…0⟩`; observables are Pauli strings evaluated by an Estimator primitive.

## 2. Conventions

* Pauli labels use Qiskit's little-endian order: the right-most character acts
  on qubit 0 (`"IIIZ"` is Z on qubit 0).
* `exp(-i θ/2 Z_a Z_b)` is always implemented as `CX(a,b) · RZ(θ)_b · CX(a,b)`,
  and a controlled phase `CP(θ)` as `RZ(θ/2)_c · CX · RZ(−θ/2)_t · CX · RZ(θ/2)_t`
  (equal up to a global phase). This keeps the twin's two-qubit structure
  identical to the source.
* A *brickwork layer* `ℓ` acts on pairs `(i, i+1)` for `i = ℓ mod 2, ℓ mod 2 + 2, …`.
* Instance identifiers have the form
  `F<k>-<variant>-n<qubits>[-<tag>]-s<index>`, e.g. `F4-qaoa-p2-n08-s0003`.

## 3. Families

| Code | Family | Qubits | Parameters (grid) | Observables | Ideal value | Split |
|---|---|---|---|---|---|---|
| F1 | GHZ and graph states | 4–30 | variant ∈ {ghz, graph} | GHZ: 3 random `Z_iZ_j` (+1), `X^⊗n` (+1), one `Z_i` (0). Graph: 4 stabilizers `K_v` (+1), one product `K_uK_v` over an edge (+1), one `Z_i` (0) | stabilizer | train |
| F2 | Random Clifford brickwork | 4–30 | depth ∈ {2, 4, 6, 8} | `U Z_q U†` for 2 random q, `U Z_iZ_{i+1} U†` (±1), one random weight-2 Pauli (usually 0) | stabilizer | train |
| F3 | Mirror circuits | 4–30 | depth ∈ {2, 4, 8} | `Z` on 2 single qubits, 2 pairs, and all qubits (±1) | analytic | train |
| F4 | QAOA MaxCut, random 3-regular graphs | 4–16 (even) | p ∈ {1, 2} | `Z_uZ_v` on every edge | state vector | train |
| F5 | Hardware-efficient ansatz | 4–16 | reps ∈ {1, 2, 3} | 3 × `Z_i`, 3 × `Z_iZ_{i+1}`, 1 × `X_i` | state vector | train |
| F6 | Clifford twins of F4/F5 structures | 4–30 | source ∈ {F4 (p=1,2), F5 (reps=1,2,3)} | source observables + 4 signal observables (§5) | stabilizer | train |
| F7 | Trotterized Ising chain: tilted field, plus the pure transverse-field (TFIM) special case | 4–16 | regime ∈ {weak, near-clifford, chaotic, transverse}, steps ∈ {1, 2, 4, 6, 8} | every `Z_i` (magnetisation) + 3 × `Z_iZ_{i+1}` | state vector | **held out** |
| F8 | Quantum phase estimation | 4–12 | exact ∈ {true, false} | `Z` on each counting qubit and on the target | state vector | **held out** |

### Construction details

**F1 GHZ.** `H(0)` then `CX(i, i+1)` for `i = 0 … n−2`.
**F1 graph.** `H` on all qubits, then `CZ` on every edge of a random 3-regular
graph (even n; `networkx.random_regular_graph`) or a ring (odd n). Stabilizer
`K_v = X_v ∏_{u∈N(v)} Z_u`.

**F2.** For each of `depth` brickwork layers, a uniformly random two-qubit
Clifford (`qiskit.quantum_info.random_clifford`) on every pair, and a random
single-qubit Clifford on any unpaired qubit. Observables are Heisenberg images
`U P U†` of Z-type stabilizers `P` of `|0…0⟩`, so their ideal values are ±1 by
construction.

**F3 (mirror circuits, after Proctor et al. 2022, simplified).** `depth` layers,
each with a Haar-random single-qubit unitary per qubit (Euler angles
`RZ·RY·RZ`) followed by brickwork `CZ`s; then a barrier, the exact inverse of
those layers, a barrier, and `X` on a random bit string `b`. The ideal output is
`|b⟩`, so `⟨Z_S⟩ = (−1)^{Σ_{i∈S} b_i}`. The barriers stop the transpiler from
cancelling `U` against `U†`.

**F4.** `H` on all qubits; for each of `p` layers, `exp(−iγ Z_uZ_v)` on every edge
then `RX(2β)` on every qubit. Angles γ ~ U(0.15, 0.5) and β ~ U(0.2, 0.6) are drawn
around the p = 1 optimum for 3-regular MaxCut in this convention and away from
γ = π/4, where every edge correlation vanishes.

**F5.** `reps` blocks of (`RY(θ)`, `RZ(φ)` on every qubit; linear `CX` chain),
followed by a final rotation layer; all angles ~ U(0, 2π).

**F6.** The F4 or F5 circuit with the same `(n, index)` seed, converted to its
Clifford twin (§5). `twin_of` records the identifier of that source structure.

**F7.** First-order Trotterization of the Ising chain with open boundaries,

  H = J Σᵢ ZᵢZᵢ₊₁ + hₓ Σᵢ Xᵢ + h_z Σᵢ Zᵢ,

with per-step angles θ_ZZ = 2J·dt, θ_X = 2hₓ·dt, θ_Z = 2h_z·dt. Each of the `steps`
Trotter steps applies `exp(−i θ_ZZ/2 ZᵢZᵢ₊₁)` on even then odd bonds, then `RX(θ_X)`
and (if θ_Z ≠ 0) `RZ(θ_Z)` on every qubit. Base angles `(θ_X, θ_Z, θ_ZZ)`:

| Regime | θ_X | θ_Z | θ_ZZ | Model |
|---|---|---|---|---|
| weak | 0.10 | 0.10 | 0.10 | tilted field (non-integrable) |
| near-clifford | 0.10 | 0.05 | π/2 | tilted field (non-integrable) |
| chaotic | 0.53 | 0.10 | 1.00 | tilted field (non-integrable) |
| transverse | 0.30 | 0 | 0.30 | transverse-field Ising (TFIM), near the critical point hₓ = J |

Each nonzero angle is multiplied by an independent factor ~ U(0.95, 1.05) so that
instances differ within a regime (θ_Z stays exactly 0 in the transverse regime).

*Why a tilted field.* The tilted-field chain (h_z ≠ 0) is non-integrable and
therefore a generic test workload. The three tilted regimes use the same base angles
as the tilted-field Ising benchmarks published for the LTM AI-QEM Qiskit Function
[1], which allows a direct comparison with that method. The **transverse** regime
is the h_z = 0 special case, the transverse-field Ising model, which in one
dimension is exactly solvable by mapping to free fermions [2]; it is included so the
blind test also covers the integrable limit.

The F7 suite grid interleaves regimes, step counts and widths (with the 7-width
grid, instance i uses regime i mod 4, step count i mod 5 and width i mod 7; the
pairwise-coprime sizes visit all 140 combinations exactly once), so even small suites contain every regime.

**F8.** `m = n − 1` counting qubits and one target qubit prepared in `|1⟩`.
Hadamards on the counting register, controlled phases `CP(2π φ 2^j)` from
counting qubit `j` to the target, then the inverse QFT. `exact = true` draws
`φ = k/2^m` (sharp output, `⟨Z⟩ = ±1`); `exact = false` draws `φ ~ U(0, 1)`.

## 4. Ideal values

| Route | Used for | Method | Cost |
|---|---|---|---|
| `stabilizer` | F1, F2, F6, all twins | circuit → `Clifford` tableau → `StabilizerState.expectation_value` | polynomial; 30 qubits in milliseconds |
| `statevector` | F4, F5, F7, F8 | dense `Statevector` (limit 20 qubits) | 2^n memory |
| `analytic` | F3 | closed form from the mirror bit string | O(1) |

**Validation (D1.2 acceptance).** `tests/test_ideal_values.py` regenerates every
family at every parameter value used by the suite grids (41 settings) at 4, 6, 8
and 10 qubits with three seeds (985 tests) and checks every stored ideal value, and
every twin's ideal value, against an independent dense state-vector calculation to
an absolute tolerance of 10⁻⁹. `qrace-bench verify`
repeats the check on any saved suite.

## 5. Clifford twins

`clifford_twin(circuit)` copies every instruction and replaces each `rx`, `ry`,
`rz` angle θ with `π/2 · round(2θ/π) mod 2π`. All two-qubit gates, barriers and
the instruction order are unchanged (tested via `two_qubit_structure`).

Snapping often drives the source observables to an ideal value of 0, which
carries no information about error reduction. Each twin therefore also carries up
to four **signal observables**: `U Z_q U†` for the qubits `q` giving the lowest
Pauli weight, with ideal value ±1 by construction. Twins of held-out circuits
inherit the held-out split.

## 6. Named suites

| Suite | Purpose | Instances |
|---|---|---|
| `smoke` | CI | 2 per family at 4–6 qubits (16) |
| `pilot` | Checkpoint-1 pilot dataset | F1–F3, F5, F6: 18 each; F4: 14; F7, F8: 6 each (104 train + 12 held-out) |
| `full` | Phase-2 dataset | 80 per family (640) |

Instance `i` of a family uses grid point `i mod |grid|` and index `i`, so grid
points that repeat get fresh seeds. Suites are saved as `circuits.qpy` plus
`manifest.json` (schema 1.0: every instance's identifier, parameters, seed,
observables, ideal values, structural statistics, software versions and the
SHA-256 checksum of the QPY file).

## 7. Known limitations

* Non-Clifford families stop at 16 qubits (12 for F8) so that exact ideal values
  remain cheap; wider non-Clifford circuits would need tensor-network or Pauli-
  propagation methods.
* F3 is a simplified mirror-circuit construction (no random Pauli layers between
  halves); its role here is an exactly-known, structurally rich workload.
* Observables are single Pauli strings; composite observables (e.g. the average
  magnetisation of F7) are linear combinations computed downstream.

## 8. References

1. LTM, "AI-QEM by LTM," IBM Quantum Documentation (Qiskit Functions),
   https://quantum.cloud.ibm.com/docs/en/functions/ltm-ai-qem (accessed 12 Nov 2026).
   Benchmark section: Trotterized 2D tilted-field Ising simulations in the regimes
   small angle (θ_X, θ_Z, θ_ZZ) = (0.1, 0.1, 0.1), near-Clifford (0.1, 0.05, 1.5708)
   and chaotic (0.53, 0.1, 1.0). Q-RACE uses the same angles on a 1D chain.
2. P. Pfeuty, "The one-dimensional Ising model with a transverse field,"
   Annals of Physics 57, 79–90 (1970).
3. T. Proctor et al., "Measuring the capabilities of quantum computers,"
   Nature Physics 18, 75–79 (2022). (Mirror circuits, F3.)
4. P. Czarnik, A. Arrasmith, P. J. Coles, L. Cincio, "Error mitigation with
   Clifford quantum-circuit data," Quantum 5, 592 (2021). (Clifford twins.)
