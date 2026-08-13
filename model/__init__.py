# Rashed-Step pre_11.C-08-13-2026-start
"""
model/ - analytical mathematical models used to evaluate this simulator's
output, separate from the simulator itself (wifi/, nru/, channel/, ...).

Every function in this package is PURE MATH (no SimPy, no randomness beyond
what a caller explicitly asks for) - it answers "what does published theory
predict for these parameters", so it can be checked against a real
`singleRun.py`/`simulation.run_simulation()` run to see how closely this
simulator's PHY-augmented behavior tracks the idealized combinatorial models
the wireless-networking literature usually validates against.

Modules:
  bianchi.py  - G. Bianchi, "Performance Analysis of the IEEE 802.11
                Distributed Coordination Function," IEEE JSAC, 2000.
                Wi-Fi-only DCF saturation throughput / collision-probability
                model. Validated against this simulator in Step 6.A (see
                "Project details/Step 6.txt").
  dtmc.py     - M. Rahman & M. Hossain, "Channel Access Deterrence Attack:
                An Attack Against Spectrum Coexistence Between NR-U and
                Wi-Fi in the 5GHz Band," IEEE INFOCOM 2025 - benign-scenario
                (attack probability pa=0) Discrete-Time Markov Chain model
                for NR-U/Wi-Fi channel occupancy (paper's eq. 1-20).
                Validated against this simulator in Step 6.D and again in
                Step pre_11.C (see "Project details/Step 6.txt" and
                "Project details/Step pre_11.txt").
  runner.py   - runs a real singleRun.py scenario in-process (fast: disables
                the per-event log file so a long run doesn't take hours -
                see runner.py's own docstring) and parses its printed
                stats back into a dict. Used by compare.py so the
                comparison harness is always checking against an ACTUAL
                simulator run, not a stale hand-copied number.
  compare.py  - high-level compare_bianchi()/compare_dtmc() - run the
                simulator via runner.py, run the matching model with the
                same parameters, and report measured-vs-model deviation.

None of this package is imported by wifi.py/nru.py/simulation.py/
singleRun.py - it is a standalone evaluation toolkit, not part of the
simulator's own runtime.
"""
# Rashed-Step pre_11.C-08-13-2026-end
