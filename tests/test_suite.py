"""Suite construction, persistence and verification."""

from __future__ import annotations

import json
from collections import Counter

import numpy as np
import pytest

from qrace.bench import SUITE_SPECS, build_suite, load_suite, save_suite, summarize, verify_suite


@pytest.fixture(scope="module")
def smoke():
    return build_suite("smoke")


def test_smoke_counts_and_ids(smoke):
    counts = Counter(inst.family for inst in smoke)
    assert counts == {f"F{i}": 2 for i in range(1, 9)}
    ids = [inst.circuit_id for inst in smoke]
    assert len(ids) == len(set(ids))


def test_pilot_composition():
    suite = build_suite("pilot")
    train = [i for i in suite if i.split == "train"]
    heldout = [i for i in suite if i.split == "heldout"]
    assert len(train) == 104
    assert {i.family for i in heldout} == {"F7", "F8"}
    assert {i.family for i in train} == {"F1", "F2", "F3", "F4", "F5", "F6"}
    assert max(i.n_qubits for i in suite if i.family in ("F1", "F2", "F3", "F6")) == 30


def test_build_is_deterministic():
    a = build_suite("smoke")
    b = build_suite("smoke")
    assert [x.circuit for x in a] == [x.circuit for x in b]


def test_save_load_roundtrip(tmp_path, smoke):
    manifest = save_suite(smoke, tmp_path, spec=SUITE_SPECS["smoke"])
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["n_instances"] == len(smoke)
    assert data["software"]["qiskit"]
    loaded = load_suite(tmp_path)
    assert [x.circuit_id for x in loaded] == [x.circuit_id for x in smoke]
    for a, b in zip(smoke, loaded, strict=True):
        assert a.circuit == b.circuit
        assert a.observables == b.observables
        np.testing.assert_array_equal(a.ideal, b.ideal)


def test_checksum_detects_tampering(tmp_path, smoke):
    save_suite(smoke, tmp_path)
    with (tmp_path / "circuits.qpy").open("ab") as fh:
        fh.write(b"tamper")
    with pytest.raises(ValueError, match="checksum"):
        load_suite(tmp_path)


def test_verify_and_summary(smoke):
    report = verify_suite(smoke, max_qubits=10)
    assert report["passed"]
    assert report["checked_instances"] == len(smoke)
    rows = summarize(smoke)
    assert [r["family"] for r in rows] == [f"F{i}" for i in range(1, 9)]


def test_f7_grid_covers_every_regime_early():
    pilot = [i for i in build_suite("pilot") if i.family == "F7"]
    assert {i.params["regime"] for i in pilot} == {"weak", "near-clifford", "chaotic", "transverse"}
    assert len({i.params["steps"] for i in pilot}) == 5
    full = SUITE_SPECS["full"].grid("F7")
    assert len(full) == len({(n, p["regime"], p["steps"]) for n, p in full})  # no repeats
