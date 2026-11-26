"""Benchmark suites: deterministic collections of instances, with save/load and verification."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import platform
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import qiskit
from qiskit import qpy

from .. import __version__
from .core import BenchmarkInstance
from .families import DEFAULT_BASE_SEED, FAMILIES, ISING_REGIMES, make_instance
from .ideal import reference_expectations

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "SUITE_SPECS",
    "SuiteSpec",
    "build_suite",
    "load_suite",
    "save_suite",
    "summarize",
    "verify_suite",
]

MANIFEST_SCHEMA_VERSION = "1.0"

_EVEN = lambda ws: [w for w in ws if w % 2 == 0]  # noqa: E731


def _grid(family: str, widths: Sequence[int]) -> list[tuple[int, dict[str, Any]]]:
    """Cartesian grid (width, params) for one family, in a fixed order."""
    if family == "F1":
        return [(n, {"variant": v}) for v, n in itertools.product(("ghz", "graph"), widths)]
    if family == "F2":
        return [(n, {"depth": d}) for d, n in itertools.product((2, 4, 6, 8), widths)]
    if family == "F3":
        return [(n, {"depth": d}) for d, n in itertools.product((2, 4, 8), widths)]
    if family == "F4":
        return [(n, {"p": p}) for p, n in itertools.product((1, 2), _EVEN(widths))]
    if family == "F5":
        return [(n, {"reps": r}) for r, n in itertools.product((1, 2, 3), widths)]
    if family == "F6":
        qaoa = [(n, {"source": "F4", "p": p}) for p, n in itertools.product((1, 2), _EVEN(widths))]
        hea = [(n, {"source": "F5", "reps": r}) for r, n in itertools.product((1, 2, 3), widths)]
        return [x for pair in itertools.zip_longest(qaoa, hea) for x in pair if x is not None]
    if family == "F7":
        regimes, steps = list(ISING_REGIMES), (1, 2, 4, 6, 8)
        sizes = (len(regimes), len(steps), len(widths))
        if all(math.gcd(a, b) == 1 for a, b in itertools.combinations(sizes, 2)):
            # Pairwise-coprime sizes: index i -> (i mod 4, i mod 5, i mod 7) visits every
            # combination exactly once (Chinese remainder theorem) and cycles through all
            # regimes, step counts and widths from the very first instances.
            return [
                (
                    widths[i % len(widths)],
                    {"regime": regimes[i % len(regimes)], "steps": steps[i % len(steps)]},
                )
                for i in range(math.prod(sizes))
            ]
        return [
            (n, {"regime": reg, "steps": s})
            for s, n, reg in itertools.product(steps, widths, regimes)  # regime varies fastest
        ]
    if family == "F8":
        return [(n, {"exact": e}) for e, n in itertools.product((True, False), widths)]
    raise KeyError(family)


@dataclass(frozen=True)
class SuiteSpec:
    """How many instances of each family to build, and at which widths."""

    name: str
    per_family: dict[str, int]
    widths: dict[str, tuple[int, ...]]
    base_seed: int = DEFAULT_BASE_SEED

    def grid(self, family: str) -> list[tuple[int, dict[str, Any]]]:
        info = FAMILIES[family]
        widths = [w for w in self.widths[family] if info.min_qubits <= w <= info.max_qubits]
        return _grid(family, widths)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "per_family": dict(self.per_family),
            "widths": {k: list(v) for k, v in self.widths.items()},
            "base_seed": self.base_seed,
        }


_WIDE = (4, 6, 8, 10, 12, 16, 20, 24, 30)
_MID = (4, 6, 8, 10, 12, 14, 16)
_SMALL = (4, 6, 8, 10, 12)
_W = {"F1": _WIDE, "F2": _WIDE, "F3": _WIDE, "F4": _MID, "F5": _MID, "F6": _WIDE, "F7": _MID, "F8": _SMALL}

#: Named suites. ``smoke`` is for CI, ``pilot`` for the Checkpoint-1 pilot dataset,
#: ``full`` for the Phase-2 dataset (80 instances per family, 640 circuits).
SUITE_SPECS: dict[str, SuiteSpec] = {
    "smoke": SuiteSpec(
        "smoke",
        dict.fromkeys(FAMILIES, 2),
        dict.fromkeys(FAMILIES, (4, 6)),
    ),
    "pilot": SuiteSpec(
        "pilot",
        {"F1": 18, "F2": 18, "F3": 18, "F4": 14, "F5": 18, "F6": 18, "F7": 6, "F8": 6},
        _W,
    ),
    "full": SuiteSpec("full", dict.fromkeys(FAMILIES, 80), _W),
}


def build_suite(spec: SuiteSpec | str, families: Iterable[str] | None = None) -> list[BenchmarkInstance]:
    """Build every instance of ``spec`` deterministically.

    Instance ``i`` of a family uses grid point ``i mod len(grid)`` (width and
    parameters) and index ``i``, so repeated grid points get fresh seeds.
    """
    if isinstance(spec, str):
        spec = SUITE_SPECS[spec]
    chosen = list(families) if families is not None else list(spec.per_family)
    instances = []
    for family in chosen:
        grid = spec.grid(family)
        for i in range(spec.per_family[family]):
            n, params = grid[i % len(grid)]
            instances.append(make_instance(family, n, index=i, base_seed=spec.base_seed, **params))
    ids = [inst.circuit_id for inst in instances]
    if len(set(ids)) != len(ids):  # pragma: no cover - guarded by construction
        raise RuntimeError("duplicate circuit identifiers in suite")
    return instances


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def save_suite(
    instances: Sequence[BenchmarkInstance],
    out_dir: str | Path,
    spec: SuiteSpec | None = None,
) -> Path:
    """Write ``circuits.qpy`` and ``manifest.json`` to ``out_dir`` and return the manifest path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    qpy_path = out / "circuits.qpy"
    with qpy_path.open("wb") as fh:
        qpy.dump([inst.circuit for inst in instances], fh)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "software": {
            "qrace": __version__,
            "qiskit": qiskit.__version__,
            "numpy": np.__version__,
            "python": platform.python_version(),
        },
        "spec": spec.to_dict() if spec else None,
        "qpy_file": qpy_path.name,
        "qpy_sha256": _sha256(qpy_path),
        "n_instances": len(instances),
        "instances": [{**inst.to_record(), "qpy_index": i} for i, inst in enumerate(instances)],
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest_path


def load_suite(in_dir: str | Path, verify_checksum: bool = True) -> list[BenchmarkInstance]:
    """Load a suite written by :func:`save_suite`."""
    src = Path(in_dir)
    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"unsupported manifest schema {manifest.get('schema_version')!r}")
    qpy_path = src / manifest["qpy_file"]
    if verify_checksum and _sha256(qpy_path) != manifest["qpy_sha256"]:
        raise ValueError(f"checksum mismatch for {qpy_path}")
    with qpy_path.open("rb") as fh:
        circuits = qpy.load(fh)
    out = []
    for rec in manifest["instances"]:
        out.append(
            BenchmarkInstance(
                circuit_id=rec["circuit_id"],
                family=rec["family"],
                variant=rec["variant"],
                circuit=circuits[rec["qpy_index"]],
                observables=rec["observables"],
                ideal=np.array(rec["ideal"]),
                ideal_method=rec["ideal_method"],
                split=rec["split"],
                seed=rec["seed"],
                params=rec["params"],
                twin_of=rec["twin_of"],
            )
        )
    return out


def verify_suite(
    instances: Sequence[BenchmarkInstance],
    max_qubits: int = 10,
    atol: float = 1e-9,
) -> dict[str, Any]:
    """Re-check stored ideal values against a dense state vector for ``n <= max_qubits``.

    Returns a report with the number of checked instances and observables and the
    largest absolute deviation. ``report["passed"]`` is ``True`` when every deviation
    is below ``atol``.
    """
    checked = n_obs = 0
    worst = 0.0
    worst_id = None
    for inst in instances:
        if inst.n_qubits > max_qubits:
            continue
        ref = reference_expectations(inst.circuit, inst.observables)
        dev = float(np.max(np.abs(ref - inst.ideal)))
        checked += 1
        n_obs += len(inst.observables)
        if dev > worst:
            worst, worst_id = dev, inst.circuit_id
    return {
        "checked_instances": checked,
        "checked_observables": n_obs,
        "max_abs_deviation": worst,
        "worst_instance": worst_id,
        "atol": atol,
        "passed": worst <= atol,
    }


def summarize(instances: Sequence[BenchmarkInstance]) -> list[dict[str, Any]]:
    """One row per family: counts, widths, two-qubit gate counts and ideal-value method."""
    rows = []
    for family in sorted({inst.family for inst in instances}):
        group = [inst for inst in instances if inst.family == family]
        widths = [inst.n_qubits for inst in group]
        n2q = [inst.stats["n_2q"] for inst in group]
        n_obs = [len(inst.observables) for inst in group]
        rows.append(
            {
                "family": family,
                "title": FAMILIES[family].title,
                "instances": len(group),
                "qubits": f"{min(widths)}-{max(widths)}",
                "two_qubit_gates": f"{min(n2q)}-{max(n2q)}",
                "observables": sum(n_obs),
                "ideal_method": ",".join(sorted({inst.ideal_method for inst in group})),
                "split": ",".join(sorted({inst.split for inst in group})),
            }
        )
    return rows
