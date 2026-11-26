# Q-RACE — design decisions (v1.6, 26 Nov 2026)

Project lead: Sumit Chongder. Mentee: Arpitha Rajeev. Mentee guide PDF: Q-RACE_Project_Guide_QAMP2026.pdf (current v1.5, 26 Nov 2026, 24 pages; Arpitha previously received v1.2 of 13 Nov; aligned with the deliverables PDF: 120 QPU min in phases P1-P3, HPC dataset ~150k rows, H5, AI-QEM as related work and optional baseline B7, Arpitha submits QPU jobs after lead review). Deliverables PDF: Q-RACE_Deliverables_QAMP2026.pdf (v1.1, 6 pages, 13 Nov 2026) — supersedes guide §8 and §10 where they differ.

## UPDATE 26 Nov 2026 (later): Deliverables v1.2 issued (7 pages)
- Same deliverable IDs and QPU minutes as v1.1.
- Dates: kick-off 23 Nov; CP1 Tue 15 Dec; rehearsals Sat 12 Dec / Tue 12 Jan / Sat 20 Feb; CP2 report draft Sat 9 Jan; meetings Tue + Sat.
- QAMP formats: the CP1 talk confirms the MVP and includes a team check; CP2 is a written report (3–5 pages).
- MVP box added (QPU A); QPU B (D3.2) runs only if a second Heron QPU is available.
- ISA twin added to D1.3; ISA twins used for D2.6/H3b. One row = one evaluation. F7/F8 simulation rows sealed. B3/B5/B6 scored on the oracle circuits.
- Guide v1.5 now references Deliverables v1.2.

## UPDATE 26 Nov 2026: Project Guide v1.5 (careful audit) and hardware Clifford twins (ISA twins)
- **Sent to Arpitha:** Project Guide v1.2 and Deliverables v1.1, both dated 13 Nov. Guide v1.5 (26 Nov, 24 pages) is written for her and includes a change box listing what changed since v1.2.
- **Plan of record:** Deliverables v1.1 (the lead chose it). The guide follows it, and the v2.0 plan from the 18 Nov entry is NOT used.
  - P1 before CP1: pilot 80 + oracle 16x24 = 11.6 min.
  - P2 CP1->CP2: 32.4 min.
  - P3 after freeze: 40 min.
  - Reserve 36 min.
  - Freeze tag v1.0-frozen at CP2, before any blind job.
- **Dates and meetings:**
  - Kick-off was Mon 23 Nov. Read v1.1's '17 Nov' as 23 Nov; the CP1 rehearsal is the Sat 12 Dec meeting. CP1 is Tue 15 Dec.
  - Meetings are Tue and Sat, 1 h each: 24 and 28 Nov; 1, 5, 8 and 12 Dec.
  - QAMP formats: the CP1 talk confirms the MVP; CP2 is a written report.
  - QPU use before CP1 falls in the trial period and happens only with Arpitha's agreement.
- **DECISION: hardware twins are made after transpilation (ISA twin).**
  - Steps: transpile once per layout with fractional gates off; snap only the rz angles in the ISA circuit; do not re-transpile; map observables through the layout; compute ideal values and signal observables by stabilizer simulation of the ISA twin.
  - Because rz is virtual, the twin has the same qubits, 2q gates, pulses and timing as the circuit. DD, twirling, ZNE folding and TREX are all Clifford, so the twin stays Clifford under all 24 arms.
  - The abstract D1.2 twins (twin_instance) stay for simulation and family F6.
  - To do in D1.3: implement isa_twin, with tests that layout, 2q gates and scheduled duration match. Fix the twin_instance docstring (it still says 'used for hardware probing') and docs/BENCHMARKS.md §5.
- **Data rows:** one row = one evaluation (circuit, arm, noise variant or QPU job). Observables are stored as list columns, plus mse and y. This matches '>=10k rows' (D1.5: 104 x 24 x 5 ≈ 12.5k) and '≈150k rows'.
- **Held-out leakage:**
  - F7/F8 simulation rows (≈38k) go in a sealed file that no training or tuning code reads before the freeze.
  - Stage 1 trains on F1-F6 (≈115k rows).
  - F6 twins share a fold with their F4/F5 sources.
- **Wide circuits (20-30 qubits):** F1, F2 and F6 are simulated with Pauli-twirled approximations of each regime (stabilizer method). Wide F3 is hardware-only. Each row records sim_method.
- **Equal cost:**
  - The rule is equal target shots T0.
  - TREX calibration, ZNE folding and twirling overheads are recorded via job.usage(). Main results are repeated at equal measured QPU time.
  - Average the squared errors before taking the log (Jensen).
- **Baselines B3, B5, B6:** scored on the 24 blind oracle circuits, with no extra QPU time.
- **Arm submission:** arms of one circuit are submitted together in random order. Use one job if the API allows; otherwise consecutive jobs.
- **Other fixes in v1.5:**
  - 12 DD arms (not 6); five hypotheses; non-Clifford limit ≤16 qubits.
  - AI-QEM described as optional baseline B7, not an arm.
  - Passport example (an F7 circuit) dated after the freeze.
  - Install via requirements.lock on Python 3.11-3.12; no pip freeze.
  - Code is AI-drafted and reviewed (stated in §12.2).
  - Precedence rule: QAMP > Deliverables v1.1 > code/docs/BENCHMARKS.md > guide.

## UPDATE 25 Nov 2026: F7 Ising regimes
- F7 = Trotterized 1D Ising chain H = J sum ZZ + h_x sum X + h_z sum Z (theta = 2*coef*dt). Regimes (theta_X, theta_Z, theta_ZZ): weak (0.10,0.10,0.10), near-clifford (0.10,0.05,pi/2), chaotic (0.53,0.10,1.00) = tilted field, non-integrable, same angles as LTM AI-QEM published 2D tilted-field Ising benchmarks (cited); NEW 'transverse' (0.30, 0, 0.30) = pure TFIM near critical point (Pfeuty 1970), no RZ layer. +/-5% jitter on nonzero angles.
- F7 suite grid now interleaved by CRT (regime i mod 4, steps i mod 5, width i mod 7 -> all 140 combos once); pilot F7 now covers all 4 regimes. New pilot QPY sha256 17b4dfd911c691a03782c9d7a5dd51328dd7ac067989afd148a71b8dad1c492e (same on py3.11/3.12/3.13).
- Tests: 1,300 pass; acceptance 985 (41 settings). Guide v1.4 (25 Nov) fixes F7 wording, adds refs [24] AI-QEM angles and [25] Pfeuty.

## UPDATE 21 Nov 2026: D1.1 + D1.2 code delivered (zip q-race_D1.1-D1.2.zip; repo to be created by Arpitha at github.com/algovista-collab/q-race)
- Package `qrace` (src layout), v0.1.0, Apache-2.0. Lock: requirements/lock.txt (uv universal, py3.11-3.13): qiskit 2.6.2, qiskit-aer 0.18.4, qiskit-ibm-runtime 0.52.1, numpy 2.4/2.5, networkx, pandas 3.1, pyarrow 26, matplotlib, pytest, ruff 0.17.6. Fresh install 16-26 s. CI: ruff + tests on ubuntu/macos/windows x py3.11-3.13 + timed fresh-install job + smoke suite build/verify. HPC: env/environment.yml, env/qrace.def (Apptainer), slurm/test_and_pilot_suite.sbatch, scripts/setup_env.sh/.ps1.
- qrace.bench: families F1-F8 (gate set: Clifford + rx/ry/rz only; ZZ via cx-rz-cx; CP via rz/cx), Clifford twins (snap rotations to k*pi/2; identical 2q structure) + 'signal observables' U Z_q U^dag (ideal +/-1, lowest weight, k=4) because snapped source observables are often 0. Ideal routes: stabilizer (F1,F2,F6,twins), statevector <=20q (F4,F5,F7,F8), analytic (F3 mirror). QAOA angles gamma~U(0.15,0.5), beta~U(0.2,0.6) (avoid gamma=pi/4 zero). QPE inverse QFT applied on reversed register (sharp for exact phases). F7 regimes weak/near-clifford/chaotic (x U(0.95,1.05) jitter).
- Suites: smoke (2/family), pilot (F1-F3,F5,F6 18; F4 14; F7,F8 6 => 104 train + 12 heldout), full (80/family). Saved as circuits.qpy + manifest.json (schema 1.0, sha256). Pilot QPY sha256 prefix 48e15b86ebb75e05 (superseded on 25 Nov by 17b4dfd9...).
- Tests: 1,147 pass (acceptance test_ideal_values: 865 = 36 settings x n{4,6,8,10} x 3 seeds, circuits + twins vs statevector, atol 1e-9); coverage 97%. CLI: qrace-bench list/build/summary/verify.
- Docs: README, docs/BENCHMARKS.md (Methods-ready spec), docs/ROADMAP.md, docs/cp1/ACCEPTANCE.md (+ figure, pilot_summary.md), CONTRIBUTING, CODE_OF_CONDUCT (IBM Quantum Community CoC link), CITATION.cff, CHANGELOG, LOG.md, AI-assistance statement in README.

## UPDATE 18 Nov 2026 (QPU plan and v2.0 dates SUPERSEDED on 26 Nov by Deliverables v1.1; QAMP definitions still valid): aligned with QAMP 2026 mentor/mentee quick-start guides; kick-off moved to Mon 23 Nov 2026
- QAMP milestone definitions: Kick-off = team communication, goals, scope. CP1 (mid-Dec) = short presentation reviewing the proposal, confirming MVP + deliverables, decide together whether to continue (period up to CP1 is a trial period). CP2 (mid-Jan) = mentee's short written report on explorations/progress. Final (end Feb) = complete MVP + demo/presentation for community showcase. Exact dates/requirements via #qamp-announcements. Use private Discord project channels; escalation @admin/#qamp-support; IBM Quantum Community Code of Conduct; QAMP is learning, not assessment; no project work before official start.
- MVP: qrace package that (1) runs a circuit under 24 arms at equal cost, (2) predicts best arm (sim-trained + hardware-corrected), (3) Reliability Passport, (4) pre-registered blind test on ONE Heron QPU vs IBM default + oracle. Research track: H5/QPU B, AI-QEM B7, paper, tutorial 2, Streamlit.
- QPU re-plan: Phase 1 (23 Nov-CP1) = 0 min (trial period). Phase 2 (CP1 -> freeze Fri 22 Jan) = 44 min: pilot 2.0, oracle 48x24 28.8, B4 3.6, adaptive 6.0, drift 3.6. Phase 3 (25 Jan - end Feb) = 40 min (blind QPU A 24 min = MVP; QPU B 16 min = research). MVP needs ~68 min; reserve 36.
- Internal dates: CP1 rehearsal Fri 11 Dec; CP2 report draft Fri 8 Jan, final Tue 12 Jan; freeze Fri 22 Jan (after CP2); dress rehearsal Fri 19 Feb.
- Files: Deliverables PDF v2.0 (6 pages), Project Guide v1.3 (21 pages), both 18 Nov 2026.

## UPDATE 10 Nov 2026: resources and checkpoints (supersedes older QPU/sim numbers below)
- Resources: mentee has ~120 min IBM QPU time (her account; lead reviews every job manifest); lead has institute HPC. Confirm at kick-off: total vs per-period, expiry, which QPUs (2 Heron-class needed for H5); HPC scheduler/quota/containers.
- QAMP dates (provisional): proposal 15 Nov 2026; kick-off 17 Nov; CP1 mid-Dec (internal deadline Fri 11 Dec); CP2 mid-Jan 2027 (internal Mon 11 Jan; model freeze); Final showcase end Feb 2027 (dress rehearsal Fri 19 Feb). User wrote 'Feb 2026' — assumed 2027.
- Sim on HPC: 640 circuits (80/family) x 24 arms x 10 noise variants (A-E + drift twins) ~ 150k rows; non-Clifford <=16q; Clifford/mirror <=30q.
- QPU plan (1.5 s/eval assumption; 3,360 evals; 84 min used, 36 min reserve): P1 pilot 80 + oracle 16x24 (11.6 min). P2 oracle 32x24, B4 6x24, adaptive 60x~4, drift 144 (32.4 min; cum 44). P3 blind QPU A: 48 circuits x ~8 (Q-RACE + B0,B1,B2,B4) + oracle 24x24; QPU B: oracle 16x24 + 32x~8 (40 min; cum 84). Cut cross-device oracle first if over budget, never the blind test.
- New H5: cross-device transfer (adapted on QPU A, keeps advantage on QPU B with twin probes only).
- Deliverables: CP1 D1.1-D1.8 (repo/CI, benchmarks+twins, 24-arm adapter, features, noise regimes + pilot dataset >=10k rows, QPU pilot + 16-circuit oracle, first H1 heatmap, related-work v1 + prereg v0). CP2 D2.1-D2.8 (QRD v1 ~150k + data card, 48-circuit oracle + drift, baselines, Stage 1 with CIs, Stages 2-3 tuned, twin fidelity, freeze tag v1.0-frozen + prereg, passport v1 + paper skeleton). Final D3.1-D3.8 (blind QPU A, cross-device QPU B, H1-H5 stats + 8 figures, v1.0 release + Zenodo DOI, 2 tutorials, paper draft for arXiv, 10-min talk + 2-min demo with pre-recorded QPU results, community write-up).

## Team (v1.1)
- ONE mentee + lead. Mentee builds all qrace modules, runs simulations, models, evaluation, passports, tutorials. Lead: hypotheses/pre-registration, holds IBM Quantum credentials and submits every QPU job, co-designs Stages 2-3 and statistics, reviews PRs, leads paper.
- ~10-12 mentee hours/week. Weekly 45-min 1:1 (Mon), PR review (Thu), biweekly literature watch, two-hour 'stuck' rule, LOG.md.
- Scope tiers. Must: F1-F5 + held-out F7, Clifford twins, regimes A/B/E, 24 arms, Stages 1-3, B0-B4, B6, oracle, H1-H4, 3 QPU windows. Should: F6, F8, regimes C/D + drift, SHAP, passport card, tutorial 1. Could: Streamlit, AI-routing arms, tutorial 2, extra oracle circuits.

## Core
- RQ: can a sim-trained model + few hardware probes pick a (layout, suppression, mitigation) arm close to the exhaustive oracle, using far less QPU time?
- Target: y = log10 MSE over observables with exactly known ideal values, at EQUAL QPU cost T0 (ZNE arms get 1/3 shots per noise factor).
- Arms (24): Layout {L-std (opt-3 preset), L-na (best of K by calibration score)} x Suppression {S0, S1 DD XY4, S2 gate+measure twirl, S3 DD+twirl} x Mitigation {M0, M1 TREX, M2 TREX+ZNE (1,3,5; exponential)}. PEC/PEA excluded; AI routing optional.
- Clifford-twin probing: probe hardware on the circuit with angles snapped to Clifford values (same layout/gates/timing; ideal value via stabilizer sim).
- Learning: Stage 1 LightGBM ensemble on sim (mu, sigma); Stage 2 ridge residual on ~300 HW rows; Stage 3 confidence-bound elimination with <= b twin probes.

## Benchmarks
F1 GHZ/graph, F2 random Clifford, F3 mirror, F4 QAOA (<=12q), F5 HEA-VQE (<=12q), F6 Clifford twins — train. F7 Trotter TFIM, F8 QFT-style — held out until blind test. ~40 instances/family (~320 circuits).

## Simulation
Noise regimes A (calibration-faithful), B (coherent CZ over-rotation + ZZ), C (readout x3), D (T1/T2 x0.5 + idle drift), E (heterogeneous hot spots) + drift variants. ~38k rows, est. 30–40 CPU-h, ~8-10 h wall-clock on one 4-core laptop (verify Week 2).

## Platform facts (checked Nov 2026)
- Open Plan: up to 10 min per rolling 28-day window; no session mode.
- qiskit-ibm-runtime 0.50 (24 Sep 2026): client-side Estimator/Sampler; EstimatorV2/SamplerV2 deprecated; local mode applies same mitigation as hardware. 0.51 released 22 Oct 2026. Min Qiskit 2.3.
- PEA/PEC need separate noise-learning job with client-side Estimator.

## QPU plan (assumes 1.5 QPU-s per evaluation; rescale after pilot)
W1 (wk3): pilot 30 + oracle 10 circuits x 24 + repeats 24. W2 (wk7): B4 device calibration 96 + adaptive 30 circuits (~120) + 3 oracle (72). W3 (wk11): frozen blind test on 24 held-out circuits + baselines B0,B1,B2,B4 + oracle on 6.

## Hypotheses
H1 heterogeneity; H2 predictability; H3 sim-to-real correction (+H3b twin fidelity); H4 efficiency at equal total QPU time. Baselines B0 raw, B1 IBM default (TREX), B2 max mitigation, B3 physics/ESP heuristic, B4 device-level calibration (Mitiq-style), B5 random, B6 sim-only, oracle.

## Closest prior work (position against)
MQT Predictor (arXiv:2310.06889), Mitiq Calibrator, QuEst (2210.16724), Mapomatic (PRX Quantum 2023), GADD learned DD (2604.18734), CMAB-ZNE (2608.06426), GSC-QEMit (2604.24551), Liao et al. Nat. Mach. Intell. 2024, Chongder 2608.28535 (motivation).
- LTM AI-QEM (IBM Qiskit Function, beta, Premium/Flex/On-prem only; docs read 12 Nov 2026): GCN-Transformer predicts a per-Pauli correction factor zeta from circuit, topology, observable and calibration features; mitigated <P> = noisy <P> / zeta; zero extra QPU time vs Estimator; Heron only; mitigates only if |<O>noisy| >= 0.1; trained on random circuits with simulated ideal values; vendor benchmarks: mirror 30-40q, Clifford 50-100q, Trotter TFI Ising 28-96q, 81-96% 'accuracy' (relative error). It is a mitigator (ML replaces ZNE/PEC), NOT a strategy selector; it does not choose layout/DD/twirling or compare techniques. Position: cite in related-work table; consider as an extra blind-test baseline/arm if the mentee's plan gives Functions access (cost = same as M0).
