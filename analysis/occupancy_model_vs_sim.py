# Rashed-Step 14.A-08-28-2026-start
"""
Figure: Wi-Fi/NR-U channel-occupancy prediction, DTMC model vs simulator.

Reuses model/sweep.py's sweep_dtmc_by_w() unchanged - the exact w=1..6
reference scenario (Wo=32, ng=55, Twp=5400us/36286-byte Wi-Fi frame,
Tmcot=6000us, 30s runs, ap_cluster_radius=2.0) already validated in this
project's Step 6.C/pre_11.C model-validation work - so this figure's
numbers are the SAME ones already reported in Project details/Step
pre_11.txt and STATUS - resume context.txt, just rendered as a plot
instead of a printed table.

Run standalone: `python -m analysis.occupancy_model_vs_sim` from the repo
root, or `python analysis/occupancy_model_vs_sim.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model.sweep import sweep_dtmc_by_w
from analysis.plot_utils import save_line_figure

W_VALUES = list(range(1, 7))  # 1..6 coexisting Wi-Fi APs, gNB count fixed at 1


def generate(w_values=W_VALUES, sim_time_s: float = 30.0, seed: int = 1):
    results = sweep_dtmc_by_w(
        w_values=w_values, Wo=32, ng=55, Twp_us=5400.0, Tmcot_us=6000.0,
        sim_time_s=sim_time_s, seed=seed, ap_cluster_radius=2.0,
        wifi_packet_size_bytes=36286,
    )

    series = {
        "Wi-Fi (Model)":     [r["model_Cw"] for r in results],
        "Wi-Fi (Simulated)": [r["measured_Cw"] for r in results],
        "NR-U (Model)":      [r["model_Cn"] for r in results],
        "NR-U (Simulated)":  [r["measured_Cn"] for r in results],
    }

    paths = save_line_figure(
        x=w_values,
        series=series,
        xlabel="Number of coexisting Wi-Fi APs (w)",
        ylabel="Normalized channel occupancy",
        title="Wi-Fi/NR-U Channel Occupancy: DTMC Model vs. Simulation",
        output_stem="occupancy_model_vs_simulation",
    )
    return results, paths


if __name__ == "__main__":
    results, paths = generate()
    print(f"{'w':>2} | {'model Cw':>9} {'sim Cw':>9} | {'model Cn':>9} {'sim Cn':>9}")
    print("-" * 55)
    for r in results:
        print(f"{r['w']:>2} | {r['model_Cw']:>9.4f} {r['measured_Cw']:>9.4f} | "
              f"{r['model_Cn']:>9.4f} {r['measured_Cn']:>9.4f}")
    print()
    print(f"Saved: {paths['pdf']}")
    print(f"Saved: {paths['jpg']}")
# Rashed-Step 14.A-08-28-2026-end
