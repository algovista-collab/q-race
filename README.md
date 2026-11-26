# Q-RACE: Quantum Reliability-Aware Compilation & Execution

No single way of running a quantum circuit is best for every circuit. Q-RACE learns which
combination of qubit layout, error suppression and error mitigation gives a specific circuit
the lowest error on an IBM Quantum processor, under a strict QPU-time budget.

Part of the Qiskit Advocate Mentorship Program (QAMP) 2026.

Mentee: Arpitha Rajeev · 

Project lead and mentor: Sumit Tapas Chongder (QIC Centre, IIT Jodhpur).

## Install

Requires Python 3.11 or 3.12.

```bash
git clone https://github.com/algovista-collab/q-race.git
cd q-race
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pip install -r requirements.lock   # exact pinned versions (recommended)
pytest -q
```

## Repository layout

```
qrace/     the package
tests/     pytest tests; nothing merges without a test
```

## Licence

Apache-2.0.
