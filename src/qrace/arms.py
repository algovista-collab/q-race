"""The 24 arms and the equal-cost rule; the only place execution options are set (D1.3).

An arm = one layout x one suppression x one mitigation (Project Guide §7.2, §13.4):
    Layout:      L-std (preset pass manager, opt. level 3) | L-na (noise-aware)
    Suppression: S0 none | S1 DD (XY4) | S2 gate + measure twirling | S3 DD + twirling
    Mitigation:  M0 none | M1 TREX | M2 TREX + ZNE (noise factors 1, 3, 5; exponential fit)
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

LAYOUTS = ("L-std", "L-na")
SUPPRESSIONS = ("S0", "S1", "S2", "S3")
MITIGATIONS = ("M0", "M1", "M2")

T0_SHOTS = 4096  # equal-cost budget; reset after the Phase-1 pilot
ZNE_NOISE_FACTORS = (1, 3, 5)


@dataclass(frozen=True)
class Arm:
    layout: str
    supp: str
    mitig: str

    def __post_init__(self):
        if self.layout not in LAYOUTS or self.supp not in SUPPRESSIONS or self.mitig not in MITIGATIONS:
            raise ValueError(f"invalid arm: {self.layout}|{self.supp}|{self.mitig}")

    @property
    def id(self) -> str:
        return f"{self.layout}|{self.supp}|{self.mitig}"

    @classmethod
    def from_id(cls, arm_id: str) -> Arm:
        return cls(*arm_id.split("|"))


ARMS = tuple(Arm(lay, s, m) for lay, s, m in product(LAYOUTS, SUPPRESSIONS, MITIGATIONS))


def configure(est, arm: Arm, seed_simulator: int | None = None):
    """Set every Estimator option for this arm explicitly and return the Estimator."""
    o = est.options
    o.resilience_level = 0  # start clean: no hidden default mitigation

    o.dynamical_decoupling.enable = arm.supp in ("S1", "S3")
    if arm.supp in ("S1", "S3"):
        o.dynamical_decoupling.sequence_type = "XY4"

    o.twirling.enable_gates = arm.supp in ("S2", "S3")
    o.twirling.enable_measure = arm.supp in ("S2", "S3") or arm.mitig != "M0"

    o.resilience.measure_mitigation = arm.mitig in ("M1", "M2")  # TREX
    o.resilience.zne_mitigation = arm.mitig == "M2"
    if arm.mitig == "M2":
        o.resilience.zne.noise_factors = ZNE_NOISE_FACTORS
        o.resilience.zne.extrapolator = "exponential"

    o.default_shots = T0_SHOTS // (len(ZNE_NOISE_FACTORS) if arm.mitig == "M2" else 1)

    if seed_simulator is not None:
        o.simulator.seed_simulator = seed_simulator  # makes simulations repeatable
    return est