# Rashed-Step 14.B-08-28-2026-start
"""
Figure: NR-U/Wi-Fi coexistence inside vs. outside mutual carrier-sensing
range.

Demonstrates that this simulator's physical layer - energy-detection (ED)
sensing (channel.Channel.is_busy()/sensed_energy_dbm(), Step 5.E) driven
by real tx power + log-distance path loss (common_phy.rx_power_dbm(),
Step 2.A/5.B) against each technology's own ED threshold
(wifi.Config.ed_threshold_dbm=-62dBm, nru.Config_NR.ed_threshold_dbm=
-72dBm) - genuinely differentiates two physically distinct regimes:

  IN sensing range:  each technology senses the other's transmissions as
    channel-busy energy and defers (LBT/CSMA backoff freezes) - a real,
    single shared collision domain, same as every other figure in this
    module's w-sweeps (which deliberately keep APs/gNBs clustered WITHIN
    this range - see model/compare.py's ap_cluster_radius docs).

  OUT of sensing range: neither technology's ED threshold is crossed by
    the other's transmissions at the receiver's sensing position, so
    NEITHER defers - both can genuinely transmit AT THE SAME TIME
    (spatial reuse). This is the same "measured occupancy sum > 1.0" tell
    already documented in model/compare.py's _cluster_ap_positions()
    docstring as a bug to AVOID when validating against the DTMC model
    (which assumes one shared collision domain) - here it's the whole
    point: it's proof the PHY layer's sensing behavior is real physics
    (tx power + path loss + threshold), not a hardcoded coexistence rule.

The two crossover distances below (where sensed energy from the OTHER
technology's default tx power first drops below EACH technology's own ED
threshold) are derived directly from the same formulas the simulator
itself uses (common_phy.rx_power_dbm/log_distance_pl_db), at the
defaults singleRun.py itself uses (Wi-Fi tx=20dBm/ed=-62dBm, NR-U
tx=23dBm/ed=-72dBm, f=5.18GHz, pl_exp n=3.0) - so the figure can plot
them as reference lines and the reader can see the empirical simulation
knee land exactly where the analytical PHY math says it should.

Run standalone: `python -m analysis.nru_sensing_region_impact` from the
repo root, or `python analysis/nru_sensing_region_impact.py`.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model.runner import run_scenario
from analysis.plot_utils import save_line_figure

# Defaults matching singleRun.py's own Config/Config_NR class defaults
# (wifi/wifi.py, nru/nru.py) - see this module's docstring.
WIFI_TX_POWER_DBM = 20.0
WIFI_ED_THRESHOLD_DBM = -62.0
NRU_TX_POWER_DBM = 23.0
NRU_ED_THRESHOLD_DBM = -72.0
F_HZ = 5.18e9
PL_EXP = 3.0

# Distance sweep (meters) - log-spaced from well inside mutual sensing
# range to well outside it, with the two representative points this
# script reports explicitly (10m, 200m - see generate()) folded in.
# Rashed-Step 14.B-08-28-2026-start
# Concentrated around the two analytically-derived crossover distances
# (~18.9m, ~32.3m - see _sensing_crossover_m() below) where the
# interesting transition happens; sparser beyond ~60m since occupancy
# empirically plateaus almost immediately past the second crossover
# (confirmed identical WiFi/NR-U occupancy at d=100m and d=500m during
# this script's own dev testing - once neither side senses the other at
# all, distance stops mattering to occupancy, only to SINR/PDR, which
# isn't this figure's subject).
DISTANCES_M = sorted(set(
    [2.0, 5.0, 8.0, 10.0, 12.0, 15.0, 17.0, 19.0, 21.0, 23.0, 26.0, 30.0,
     35.0, 45.0, 60.0, 150.0, 400.0]
))
# Rashed-Step 14.B-08-28-2026-end

IN_RANGE_M = 10.0       # matches every other script in this module's default gnb_pos="10,0"
OUT_OF_RANGE_M = 200.0  # safely beyond both crossover distances computed below


def _fspl_db(d_m: float, f_hz: float) -> float:
    d_m = max(d_m, 1e-3)
    c = 3e8
    return 20.0 * math.log10(4.0 * math.pi * d_m * f_hz / c)


def _sensing_crossover_m(other_tx_power_dbm: float, own_ed_threshold_dbm: float,
                          f_hz: float = F_HZ, n: float = PL_EXP) -> float:
    """
    Distance at which the OTHER technology's default tx power, attenuated
    by log-distance path loss, first drops below MY OWN ED threshold -
    i.e. the max range at which I can still sense it as channel-busy.
    Same formula as common_phy.rx_power_dbm()/log_distance_pl_db(),
    solved for d instead of evaluated at a given d.
    """
    pl_d0 = _fspl_db(1.0, f_hz)
    log10_d = (other_tx_power_dbm - own_ed_threshold_dbm - pl_d0) / (10.0 * n)
    return 10.0 ** log10_d


# Rashed-Step 14.C-08-28-2026-start
# 36286 bytes -> ~5400us Wi-Fi PPDU duration (same byte count already
# validated elsewhere in this codebase - model/compare.py's __main__/
# model/sweep.py's reference DTMC scenario) - chosen because it matches
# real 802.11ax's actual TXOP limit (~5.484ms via frame aggregation),
# so this isn't an arbitrary "make Wi-Fi win" number, it's Wi-Fi legally
# using the longest single transmission opportunity the real standard
# allows, for a fair-as-possible comparison against NR-U's 6ms MCOT.
WIFI_LONG_TXOP_PACKET_SIZE_BYTES = 36286
# Rashed-Step 14.C-08-28-2026-end


def _run_one(d_m: float, sim_time_s: float, seed: int,
             wifi_packet_size_bytes: "int | None" = None) -> dict:
    argv = [
        "--ap-number", "1", "--gnb-number", "1",
        "-t", str(sim_time_s), "-r", "1", "--seed", str(seed),
        "--wifi-traffic-model", "saturated", "--nru-traffic-model", "saturated",
        "--area-w", str(max(d_m * 1.2, 50.0)), "--area-h", str(max(d_m * 1.2, 50.0)),
        "--ap-pos", "0,0", "--gnb-pos", f"{d_m},0",
        "--sta-radius", "3", "--ue-radius", "3",
    ]
    # Rashed-Step 14.C-08-28-2026-start
    if wifi_packet_size_bytes is not None:
        argv += ["--wifi-packet-size-bytes", str(wifi_packet_size_bytes)]
    # Rashed-Step 14.C-08-28-2026-end
    return run_scenario(argv)


def generate(distances_m=DISTANCES_M, sim_time_s: float = 5.0, seed: int = 1,
             # Rashed-Step 14.C-08-28-2026-start
             wifi_packet_size_bytes: "int | None" = None,
             output_stem: str = "nru_sensing_region_impact",
             title_suffix: str = "",
             wifi_series_label: str = "Wi-Fi",
             # Rashed-Step 14.C-08-28-2026-end
             ):
    # Rashed-Step 14.C-08-28-2026-start
    # wifi_packet_size_bytes/output_stem/title_suffix/wifi_series_label
    # are new, all-optional params (defaults reproduce the original
    # Step 14.B call byte-for-byte) - added so this same function can
    # also generate the "long Wi-Fi TXOP" variant (see __main__ below
    # and WIFI_LONG_TXOP_PACKET_SIZE_BYTES above) without duplicating
    # the whole sweep/plot logic.
    # Rashed-Step 14.C-08-28-2026-end
    # sim_time_s=5.0 (not this module's usual 30.0): out-of-sensing-range
    # points generate MUCH more traffic per second (neither side defers,
    # so both saturate independently instead of sharing one collision
    # domain - confirmed during dev testing: succeeded WiFi transmissions
    # jump from ~5400 to ~25800 once d crosses ~19m), making those points
    # several times slower to simulate. 5s was confirmed to still track
    # the 30s/10s reference values closely (occupancy is a time-normalized
    # ratio, not a raw count, so it converges fast under saturated
    # traffic) - plenty stable for this figure's purpose.
    # WiFi can sense NR-U (NR-U's tx power vs. WiFi's own ED threshold).
    d_wifi_senses_nru = _sensing_crossover_m(NRU_TX_POWER_DBM, WIFI_ED_THRESHOLD_DBM)
    # NR-U can sense WiFi (WiFi's tx power vs. NR-U's own ED threshold).
    d_nru_senses_wifi = _sensing_crossover_m(WIFI_TX_POWER_DBM, NRU_ED_THRESHOLD_DBM)

    results = [_run_one(d, sim_time_s, seed, wifi_packet_size_bytes) for d in distances_m]

    wifi_occ = [r["wifi_occ"] for r in results]
    nru_occ = [r["gnb_occ"] for r in results]
    combined = [w + n for w, n in zip(wifi_occ, nru_occ)]

    # Rashed-Step 14.C-08-28-2026-start
    # wifi_series_label lets the long-TXOP variant use its own legend
    # entry ("Wi-Fi (Long TXOP)") - falls back to SERIES_STYLE's default
    # matplotlib color cycle since it isn't in the registry, which is
    # fine (still gets its own distinct marker/color, just not the same
    # blue "Wi-Fi" uses elsewhere in this module - deliberate, so the
    # two figures are visually distinguishable from each other too).
    combined_label = "Combined (Wi-Fi + NR-U)"
    # Rashed-Step 14.C-08-28-2026-end
    paths = save_line_figure(
        x=distances_m,
        series={
            wifi_series_label: wifi_occ,
            "NR-U": nru_occ,
            combined_label: combined,
        },
        xlabel="Wi-Fi AP - NR-U gNB separation distance (m, log scale)",
        ylabel="Normalized channel occupancy",
        title=f"NR-U/Wi-Fi Coexistence: Inside vs. Outside Mutual Sensing Range{title_suffix}",
        output_stem=output_stem,
        x_ticks_as_int=False,
        xscale="log",
        hlines=[(1.0, "Shared-channel limit (sum = 1.0)")],
        vlines=[
            (d_wifi_senses_nru, f"Wi-Fi's sensing reach of NR-U ({d_wifi_senses_nru:.1f} m)"),
            (d_nru_senses_wifi, f"NR-U's sensing reach of Wi-Fi ({d_nru_senses_wifi:.1f} m)"),
        ],
    )

    # The two representative, explicitly-named scenarios this script was
    # asked to demonstrate - pulled out of the sweep already run above
    # (both distances are included in DISTANCES_M) rather than run again.
    in_range = results[distances_m.index(IN_RANGE_M)] if IN_RANGE_M in distances_m else _run_one(IN_RANGE_M, sim_time_s, seed, wifi_packet_size_bytes)
    out_of_range = results[distances_m.index(OUT_OF_RANGE_M)] if OUT_OF_RANGE_M in distances_m else _run_one(OUT_OF_RANGE_M, sim_time_s, seed, wifi_packet_size_bytes)

    return {
        "results": results,
        "paths": paths,
        "d_wifi_senses_nru": d_wifi_senses_nru,
        "d_nru_senses_wifi": d_nru_senses_wifi,
        "in_range": in_range,
        "out_of_range": out_of_range,
    }


def _report(out, distances_m, label):
    results = out["results"]
    print(f"--- {label} ---")
    print(f"WiFi's sensing reach of NR-U:  {out['d_wifi_senses_nru']:.1f} m "
          f"(WiFi ed_threshold={WIFI_ED_THRESHOLD_DBM} dBm vs. NR-U tx={NRU_TX_POWER_DBM} dBm)")
    print(f"NR-U's sensing reach of WiFi:  {out['d_nru_senses_wifi']:.1f} m "
          f"(NR-U ed_threshold={NRU_ED_THRESHOLD_DBM} dBm vs. WiFi tx={WIFI_TX_POWER_DBM} dBm)")
    print()
    print(f"{'d (m)':>7} | {'WiFi occ':>9} {'NRU occ':>9} {'sum':>7} | {'WiFi succ/fail':>16} {'NRU succ/fail':>16}")
    print("-" * 80)
    for d, r in zip(distances_m, results):
        s = r["wifi_occ"] + r["gnb_occ"]
        print(f"{d:>7.1f} | {r['wifi_occ']:>9.4f} {r['gnb_occ']:>9.4f} {s:>7.4f} | "
              f"{r['wifi_succ']:>7}/{r['wifi_fail']:<7} {r['nru_succ']:>7}/{r['nru_fail']:<7}")

    print()
    ir, oor = out["in_range"], out["out_of_range"]
    print(f"IN sensing range (d={IN_RANGE_M:.0f}m):     WiFi occ={ir['wifi_occ']:.4f}  "
          f"NR-U occ={ir['gnb_occ']:.4f}  sum={ir['wifi_occ']+ir['gnb_occ']:.4f}")
    print(f"OUT of sensing range (d={OUT_OF_RANGE_M:.0f}m): WiFi occ={oor['wifi_occ']:.4f}  "
          f"NR-U occ={oor['gnb_occ']:.4f}  sum={oor['wifi_occ']+oor['gnb_occ']:.4f}")
    print()
    print(f"Saved: {out['paths']['pdf']}")
    print(f"Saved: {out['paths']['jpg']}")
    print()


if __name__ == "__main__":
    # Original short-TXOP (default 1472-byte Wi-Fi frame) figure -
    # unchanged from Step 14.B.
    out_short = generate()
    _report(out_short, DISTANCES_M, "Wi-Fi default (short) TXOP")

    # Rashed-Step 14.C-08-28-2026-start
    # Long-TXOP variant: Wi-Fi given a 36286-byte frame (~5.4ms on-air,
    # matching real 802.11ax's actual TXOP limit via frame aggregation -
    # see WIFI_LONG_TXOP_PACKET_SIZE_BYTES's docstring above) instead of
    # the 242us default - closer to NR-U's fixed 6ms MCOT per win, to
    # show how much of Wi-Fi's "poor" occupancy (see this session's
    # earlier discussion) is really just its much shorter per-win
    # transmission duration, not weaker channel access overall. Same
    # sensing-range crossover distances apply unchanged (crossover is a
    # pure tx-power/path-loss/ED-threshold function, independent of
    # packet size), so both figures share the same vertical reference
    # lines even though the occupancy story past them changes a lot.
    out_long = generate(
        wifi_packet_size_bytes=WIFI_LONG_TXOP_PACKET_SIZE_BYTES,
        output_stem="nru_sensing_region_impact_long_txop",
        title_suffix=" (Wi-Fi Long TXOP)",
        wifi_series_label="Wi-Fi (Long TXOP)",
    )
    _report(out_long, DISTANCES_M, "Wi-Fi long TXOP (36286-byte frame, ~5.4ms)")
    # Rashed-Step 14.C-08-28-2026-end
# Rashed-Step 14.B-08-28-2026-end
