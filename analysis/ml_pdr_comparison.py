# Rashed-Step 13.F-08-29-2026-start
"""
Figure: Packet Delivery Ratio, heuristic (persistence-based ARF/CQI) vs
ML-driven (SINR-predictor-based) rate adaptation, across 4 scenarios -
NR-U Static, NR-U Mobile, Wi-Fi Static, Wi-Fi Mobile - for the paper's
ML-extension performance-evaluation section.

Same "reuse already-validated numbers, just render them as a plot"
approach as analysis/occupancy_model_vs_sim.py (see that module's own
docstring for the precedent): these 8 DELIVERED/total figures are NOT
re-derived by this script. They are the exact, already fact-checked,
POST-FIX ("corrected") empirical numbers from "Project details/Step
13.txt"'s constant-link-guard-fix section (~lines 341-367) and the
matching section of "Project details/STATUS - resume context.txt"
(~lines 863-887), each aggregated over 20 seeds per scenario/mode with
--export-packets-csv ground truth (DELIVERED/DROPPED counted directly
from the packet CSV, not model/runner.py's parsed stdout stats - that
stdout metric was found mid-project to report transmission-ATTEMPT
counts, not packet-level outcome, see the same source section).

WHY HARD-CODED INSTEAD OF RE-RUN: the exact CLI scenario parameters
(gNB/AP positions, tx power, shadowing, mobility speed) ARE fully
documented and reproducible, but the exact --simulation-time/traffic-
model/seed-list used for the original 20-seed sweep is not recorded
precisely enough in project docs to guarantee a byte-identical re-run,
and re-running an undocumented 4-scenario x 2-mode x 20-seed sweep
fresh risks silently drifting from the numbers already fact-checked
and written up. Plotting the existing, already-verified totals keeps
this figure consistent with the paper's prose. If Rashed wants a fresh
from-scratch re-run instead (e.g. to also report confidence intervals
across seeds), that is a separate, larger follow-up step, not this one.

EXPECTED RESULT (already established, not discovered here): the
predictor is SAFE by construction on static/constant links (NR-U
Static and Wi-Fi Static are statistically IDENTICAL to the heuristic,
97.9% and 89.9% PDR respectively - the constant-link guard makes it
degenerate exactly to persistence there), a genuine TIE on NR-U Mobile
(69.0% vs 68.5%, within normal run-to-run variation), and a real,
reproducible WIN for the model on Wi-Fi Mobile (72.6% -> 76.0% PDR) -
the one regime where the richer, trend-aware prediction actually beats
simple last-observed persistence.

Run standalone: `python -m analysis.ml_pdr_comparison` from the repo
root (no simulator run required - plots the literal numbers above).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.plot_utils import save_bar_figure

CATEGORIES = ["NR-U Static", "NR-U Mobile", "Wi-Fi Static", "Wi-Fi Mobile"]

# (delivered, total) pairs, 20 seeds aggregated per scenario/mode - see
# module docstring for exact source lines in Project details/Step 13.txt
# and Project details/STATUS - resume context.txt.
HEURISTIC_DELIVERED_TOTAL = {
    "NR-U Static": (705, 720),
    "NR-U Mobile": (214, 310),
    "Wi-Fi Static": (943, 1049),
    "Wi-Fi Mobile": (815, 1122),
}
ML_DRIVEN_DELIVERED_TOTAL = {
    "NR-U Static": (705, 720),
    "NR-U Mobile": (204, 298),
    "Wi-Fi Static": (943, 1049),
    "Wi-Fi Mobile": (951, 1252),
}


def _pdr_pct(delivered_total):
    delivered, total = delivered_total
    return 100.0 * delivered / total


def generate():
    heuristic_pdr = [_pdr_pct(HEURISTIC_DELIVERED_TOTAL[c]) for c in CATEGORIES]
    ml_pdr = [_pdr_pct(ML_DRIVEN_DELIVERED_TOTAL[c]) for c in CATEGORIES]

    paths = save_bar_figure(
        categories=CATEGORIES,
        series={"Heuristic": heuristic_pdr, "ML-Driven": ml_pdr},
        xlabel="Scenario",
        ylabel="Packet Delivery Ratio (%)",
        output_stem="ml_pdr_comparison",
        value_fmt="{:.1f}",
    )

    return {
        "categories": CATEGORIES,
        "heuristic_pdr": heuristic_pdr,
        "ml_pdr": ml_pdr,
        "heuristic_raw": HEURISTIC_DELIVERED_TOTAL,
        "ml_raw": ML_DRIVEN_DELIVERED_TOTAL,
    }, paths


if __name__ == "__main__":
    results, paths = generate()
    print(f"{'scenario':>14} | {'Heuristic PDR':>13} {'(D/T)':>11} | {'ML-Driven PDR':>13} {'(D/T)':>11}")
    print("-" * 80)
    for c in CATEGORIES:
        hd, ht = results["heuristic_raw"][c]
        md, mt = results["ml_raw"][c]
        hp = _pdr_pct((hd, ht))
        mp = _pdr_pct((md, mt))
        print(f"{c:>14} | {hp:>12.1f}% {f'{hd}/{ht}':>11} | {mp:>12.1f}% {f'{md}/{mt}':>11}")
    print()
    print(f"Saved: {paths['pdf']}")
    print(f"Saved: {paths['jpg']}")
# Rashed-Step 13.F-08-29-2026-end
