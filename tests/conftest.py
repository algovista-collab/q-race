"""Shared test fixtures and parameter grids."""

from __future__ import annotations

# (family, params): every parameter value used by the suite grids (qrace.bench.suite).
FAMILY_CASES = (
    [("F1", {"variant": v}) for v in ("ghz", "graph")]
    + [("F2", {"depth": d}) for d in (2, 4, 6, 8)]
    + [("F3", {"depth": d}) for d in (2, 4, 8)]
    + [("F4", {"p": p}) for p in (1, 2)]
    + [("F5", {"reps": r}) for r in (1, 2, 3)]
    + [("F6", {"source": "F4", "p": p}) for p in (1, 2)]
    + [("F6", {"source": "F5", "reps": r}) for r in (1, 2, 3)]
    + [
        ("F7", {"regime": reg, "steps": st})
        for reg in ("weak", "near-clifford", "chaotic", "transverse")
        for st in (1, 2, 4, 6, 8)
    ]
    + [("F8", {"exact": e}) for e in (True, False)]
)

#: Widths used for the D1.2 acceptance test (state-vector reference for n <= 10).
SMALL_WIDTHS = (4, 6, 8, 10)

#: Instance indices (seeds) per (family, params, width).
INDICES = (0, 1, 2)


def case_id(case: tuple[str, dict]) -> str:
    family, params = case
    return family + "-" + "-".join(f"{k}={v}" for k, v in params.items())
