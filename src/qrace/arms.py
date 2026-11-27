"""The 24 arms and the equal-cost rule; the only place execution options are set (D1.3).

An arm = one layout x one suppression x one mitigation (Project Guide §7.2, §13.4):
    Layout:      L-std (preset pass manager, opt. level 3) | L-na (noise-aware, best of K)
    Suppression: S0 none | S1 DD (XY4) | S2 gate + measure twirling | S3 DD + twirling
    Mitigation:  M0 none | M1 TREX | M2 TREX + ZNE (noise factors 1, 3, 5; exponential fit)

Equal cost (Project Guide §6, §7.2)
-----------------------------------
Every arm of a circuit spends the same total number of shots, T0_SHOTS per measurement
basis, counting everything the Estimator runs:

* main circuits, for every measurement basis and every ZNE noise factor, and
* TREX's extra measurement-calibration circuits.

Left on "auto", the Estimator spends more on mitigated arms (measured 2026-11-26 on
GHZ-4: M1 +50 %, M2 +20 % versus M0), because TREX calibration shots come on top and
"auto" rounds shot counts up. So every twirled arm gets explicit settings (see
``shot_plan``): a fixed number of shots per randomization, a fixed number of TREX
calibration randomizations, and the number of randomizations that makes the total fit
the budget. Shots come in whole randomizations, so a total can fall short of the budget
by less than one randomization per basis and noise factor (at most ~3 % for ZNE with two
bases), and it never exceeds it.

DECISION FOR THE LEAD: this counts TREX calibration shots inside T0. The alternative is
to equalise QPU-seconds measured with ``job.usage()`` on hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

LAYOUTS = ("L-std", "L-na")
SUPPRESSIONS = ("S0", "S1", "S2", "S3")
MITIGATIONS = ("M0", "M1", "M2")

T0_SHOTS = 4096  # equal-cost budget per measurement basis; reset after the Phase-1 pilot
ZNE_NOISE_FACTORS = (1, 3, 5)
SHOTS_PER_RANDOMIZATION = 64  # shots per random twirl; the unit in which twirled shots are spent
TREX_CALIBRATION_RANDOMIZATIONS = 16  # TREX calibration costs 16 x 64 = 1,024 shots per circuit


@dataclass(frozen=True)
class Arm:
    """One execution strategy: a layout, a suppression and a mitigation choice."""

    layout: str
    supp: str
    mitig: str

    def __post_init__(self):
        if self.layout not in LAYOUTS or self.supp not in SUPPRESSIONS or self.mitig not in MITIGATIONS:
            raise ValueError(f"invalid arm: {self.layout}|{self.supp}|{self.mitig}")

    @property
    def id(self) -> str:
        """Text name used in dataset rows, e.g. ``"L-na|S2|M1"``."""
        return f"{self.layout}|{self.supp}|{self.mitig}"

    @classmethod
    def from_id(cls, arm_id: str) -> Arm:
        """Parse ``"L-na|S2|M1"`` back into an Arm."""
        return cls(*arm_id.split("|"))

    @property
    def uses_dd(self) -> bool:
        return self.supp in ("S1", "S3")

    @property
    def uses_gate_twirling(self) -> bool:
        return self.supp in ("S2", "S3")

    @property
    def uses_trex(self) -> bool:
        return self.mitig in ("M1", "M2")

    @property
    def uses_zne(self) -> bool:
        return self.mitig == "M2"

    @property
    def is_twirled(self) -> bool:
        """True if the Estimator randomizes circuits (gate twirling, or measurement twirling for TREX)."""
        return self.uses_gate_twirling or self.uses_trex


ARMS = tuple(Arm(lay, s, m) for lay, s, m in product(LAYOUTS, SUPPRESSIONS, MITIGATIONS))


@dataclass(frozen=True)
class ShotPlan:
    """How an arm spends its budget on a circuit with ``n_bases`` measurement bases."""

    default_shots: int  # shots per circuit variant (per basis and noise factor)
    num_randomizations: int | None  # random twirls per variant; None if not twirled
    shots_per_randomization: int | None
    trex_randomizations: int | None  # TREX calibration twirls; None without TREX
    total_shots: int  # everything the Estimator runs for this circuit


def shot_plan(arm: Arm, n_bases: int = 1) -> ShotPlan:
    """Equal-cost shot settings for ``arm`` on a circuit with ``n_bases`` measurement bases.

    The budget is ``n_bases * T0_SHOTS``. See the module docstring for the rule.
    """
    if n_bases < 1:
        raise ValueError("n_bases must be >= 1")
    budget = n_bases * T0_SHOTS
    if not arm.is_twirled:
        return ShotPlan(T0_SHOTS, None, None, None, budget)

    s = SHOTS_PER_RANDOMIZATION
    n_factors = len(ZNE_NOISE_FACTORS) if arm.uses_zne else 1
    calibration = TREX_CALIBRATION_RANDOMIZATIONS * s if arm.uses_trex else 0
    r = (budget - calibration) // (n_factors * n_bases * s)
    if r < 1:
        raise ValueError(f"T0_SHOTS={T0_SHOTS} is too small for arm {arm.id}")
    total = n_factors * n_bases * r * s + calibration
    trex = TREX_CALIBRATION_RANDOMIZATIONS if arm.uses_trex else None
    return ShotPlan(r * s, r, s, trex, total)


def configure(est, arm: Arm, n_bases: int = 1, seed_simulator: int | None = None):
    """Set every Estimator option for this arm explicitly and return the Estimator.

    Args:
        est: a client-side ``qiskit_ibm_runtime.Estimator``.
        arm: one of the 24 arms. (The layout is applied at transpile time, not here.)
        n_bases: number of measurement bases of the circuit's observables (equal cost).
        seed_simulator: fixes the simulator's randomness so results are repeatable.
    """
    o = est.options
    o.resilience_level = 0  # start clean: no hidden default mitigation

    o.dynamical_decoupling.enable = arm.uses_dd
    if arm.uses_dd:
        o.dynamical_decoupling.sequence_type = "XY4"

    o.twirling.enable_gates = arm.uses_gate_twirling
    o.twirling.enable_measure = arm.uses_gate_twirling or arm.uses_trex  # TREX needs measurement twirling

    o.resilience.measure_mitigation = arm.uses_trex
    o.resilience.zne_mitigation = arm.uses_zne
    if arm.uses_zne:
        o.resilience.zne.noise_factors = ZNE_NOISE_FACTORS
        o.resilience.zne.extrapolator = "exponential"

    plan = shot_plan(arm, n_bases)
    o.default_shots = plan.default_shots
    if arm.is_twirled:
        o.twirling.num_randomizations = plan.num_randomizations
        o.twirling.shots_per_randomization = plan.shots_per_randomization
    if arm.uses_trex:
        o.resilience.measure_noise_learning.num_randomizations = plan.trex_randomizations

    if seed_simulator is not None:
        o.simulator.seed_simulator = seed_simulator
    return est
