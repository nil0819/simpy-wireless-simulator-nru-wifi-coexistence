# Rashed-Step 14.A-08-28-2026-start
"""
Figures: Wi-Fi vs. NR-U coexistence performance across channel occupancy,
throughput, delay, and fairness.

Same w=1..6 coexisting-Wi-Fi-AP sweep and clustered AP placement as
analysis/occupancy_model_vs_sim.py (via model.compare's own
_cluster_ap_positions() helper, so both of this paper's figures share one
consistent, already-validated experimental design) - but calls
model.runner.run_scenario() directly instead of going through
model.compare.compare_dtmc(), since compare_dtmc() only returns the
subset of fields it needs for its own model-vs-measured deviation report
(occupancy only) and drops the throughput/delay/fairness fields this
script also needs (see simulation.py's Step 14.A block for where those
are computed and printed).

Run standalone: `python -m analysis.wifi_nru_performance_comparison` from
the repo root, or `python analysis/wifi_nru_performance_comparison.py`.
"""
import os
import sys
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model.compare import _cluster_ap_positions
from model.runner import run_scenario
from analysis.plot_utils import save_line_figure

W_VALUES = list(range(1, 7))  # 1..6 coexisting Wi-Fi APs, gNB count fixed at 1


def _run_one(w: int, Wo: int, sim_time_s: float, seed: int, ap_cluster_radius: float,
             ap_pos: str, gnb_pos: str, sta_radius: float, ue_radius: float,
             area_w: float, area_h: float, mcot_ms: int) -> Dict:
    """
    Runs one w-AP + 1-gNB saturated scenario (same fixed-CW/clustered-
    placement convention as model.compare.compare_dtmc(), reused directly
    here rather than through compare_dtmc() itself - see module docstring
    for why) and returns model.runner.run_scenario()'s FULL result dict
    (every stdout-scraped field, not just occupancy).
    """
    ap_pos_list = _cluster_ap_positions(ap_pos, w, ap_cluster_radius)
    ap_pos_argv: List[str] = []
    for pos in ap_pos_list:
        ap_pos_argv += ["--ap-pos", pos]

    argv = [
        "--ap-number", str(w), "--gnb-number", "1",
        "-t", str(sim_time_s), "-r", "1", "--seed", str(seed),
        "--wifi-traffic-model", "saturated", "--nru-traffic-model", "saturated",
        "--area-w", str(area_w), "--area-h", str(area_h),
    ] + ap_pos_argv + [
        "--gnb-pos", gnb_pos,
        "--sta-radius", str(sta_radius), "--ue-radius", str(ue_radius),
        "--wifi_cw_min", str(Wo - 1), "--wifi_cw_max", str(Wo - 1),
        "--nru_cw_min", str(Wo - 1), "--nru_cw_max", str(Wo - 1),
        "--mcot", str(mcot_ms),
    ]
    return run_scenario(argv)


def generate(w_values=W_VALUES, sim_time_s: float = 30.0, seed: int = 1):
    results = [
        _run_one(
            w=w, Wo=32, sim_time_s=sim_time_s, seed=seed, ap_cluster_radius=2.0,
            ap_pos="0,0", gnb_pos="10,0", sta_radius=3.0, ue_radius=3.0,
            area_w=20.0, area_h=20.0, mcot_ms=6,
        )
        for w in w_values
    ]

    figures = {}

    figures["occupancy"] = save_line_figure(
        x=w_values,
        series={
            "Wi-Fi": [r["wifi_occ"] for r in results],
            "NR-U":  [r["gnb_occ"] for r in results],
        },
        xlabel="Number of coexisting Wi-Fi APs (w)",
        ylabel="Normalized channel occupancy",
        title="Wi-Fi vs. NR-U: Channel Occupancy",
        output_stem="wifi_nru_channel_occupancy",
    )

    figures["throughput"] = save_line_figure(
        x=w_values,
        series={
            "Wi-Fi": [r["wifi_throughput_mbps"] for r in results],
            "NR-U":  [r["nru_throughput_mbps"] for r in results],
        },
        xlabel="Number of coexisting Wi-Fi APs (w)",
        ylabel="Goodput throughput (Mbps)",
        title="Wi-Fi vs. NR-U: Throughput",
        output_stem="wifi_nru_throughput",
    )

    figures["delay"] = save_line_figure(
        x=w_values,
        series={
            "Wi-Fi": [r["wifi_avg_latency_us"] for r in results],
            "NR-U":  [r["nru_avg_latency_us"] for r in results],
        },
        xlabel="Number of coexisting Wi-Fi APs (w)",
        ylabel="Average packet delay (µs)",
        title="Wi-Fi vs. NR-U: Delay",
        output_stem="wifi_nru_delay",
    )

    # Fairness (simulation.py's Jain-style index over WiFi/NR-U normalized
    # occupancy) is a single JOINT metric describing how fairly the two
    # technologies share the channel, not a per-technology quantity - one
    # line, not two, unlike the three figures above.
    figures["fairness"] = save_line_figure(
        x=w_values,
        series={
            "Fairness Index": [r["fairness"] for r in results],
        },
        xlabel="Number of coexisting Wi-Fi APs (w)",
        ylabel="Jain fairness index (Wi-Fi vs. NR-U occupancy)",
        title="Wi-Fi/NR-U Coexistence Fairness",
        output_stem="wifi_nru_fairness",
    )

    return results, figures


if __name__ == "__main__":
    results, figures = generate()
    print(f"{'w':>2} | {'WiFi occ':>9} {'NRU occ':>9} | {'WiFi Mbps':>10} {'NRU Mbps':>10} | "
          f"{'WiFi us':>10} {'NRU us':>10} | {'fair':>6}")
    print("-" * 90)
    for r, w in zip(results, W_VALUES):
        wl = r["wifi_avg_latency_us"]
        nl = r["nru_avg_latency_us"]
        wl_s = f"{wl:>10.1f}" if wl is not None else f"{'N/A':>10}"
        nl_s = f"{nl:>10.1f}" if nl is not None else f"{'N/A':>10}"
        print(f"{w:>2} | {r['wifi_occ']:>9.4f} {r['gnb_occ']:>9.4f} | "
              f"{r['wifi_throughput_mbps']:>10.3f} {r['nru_throughput_mbps']:>10.3f} | "
              f"{wl_s} {nl_s} | {r['fairness']:>6.3f}")
    print()
    for name, paths in figures.items():
        print(f"[{name}] Saved: {paths['pdf']}")
        print(f"[{name}] Saved: {paths['jpg']}")
# Rashed-Step 14.A-08-28-2026-end
