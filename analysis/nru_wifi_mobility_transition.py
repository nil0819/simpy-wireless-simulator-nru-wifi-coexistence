# Rashed-Step 14.D-08-28-2026-start
"""
Figure: Wi-Fi/NR-U channel occupancy over time as NR-U moves from
outside Wi-Fi's sensing region into it.

Scenario: one static Wi-Fi AP+STA at the origin, one NR-U gNB (with its
UE rigidly following it, see common.common_phy.RelativeMobility) that
starts 100m away (safely outside BOTH analytically-derived sensing
crossovers from Step 14.B - 18.9m/32.3m) and moves in a straight line to
10m (safely inside both) over the first TRANSITION_DURATION_S=100
seconds of a TOTAL_DURATION_S=200 second run, then holds there for the
second 100 seconds. The gNB-UE offset (0,3) never changes, so their own
link quality is unaffected by the gNB's movement toward Wi-Fi - only the
Wi-Fi/NR-U sensing relationship changes.

Expected result (same physics already proven in Step 14.B/14.C, now
shown unfolding over TIME instead of over a static distance sweep):
combined occupancy should sit above 1.0 while the gNB is still outside
sensing range (each side gets exclusive access, real concurrent
transmission), then drop to <=1.0 once it crosses into range and the two
start genuinely contending via the SAME CSMA/LBT logic that already
exists - no new MAC-layer behavior anywhere, only the geometry changes.

HOW THE OCCUPANCY TIME SERIES IS BUILT (the "lighter option" agreed on
2026-08-28, instead of adding timestamped event logging to channel.py's
core airtime accounting): occupancy today is only ever a single scalar
computed once at the end of a run (channel.airtime_data/_control dicts
just accumulate microseconds with no timestamp attached) - there is no
existing machinery to bin it by time. Rather than touch channel.py's
airtime bookkeeping (used everywhere, real regression risk), this script
reconstructs a DATA-airtime-only, success-only occupancy time series
directly from each DELIVERED Packet's delivered_at timestamp (already
recorded, Step 8.A) plus each technology's KNOWN, deterministic
per-transmission duration in this scenario (rate adaptation is off, so
neither duration varies packet-to-packet):
  - Wi-Fi: 242us (the default 1472-byte/MCS7 PPDU duration, the same
    reference value already used throughout this project - see
    model/compare.py's own __main__).
  - NR-U: 6000us (mcot=6 default, ALWAYS this value regardless of
    payload size - nru.py's transmission_time is purely mcot-based).
This is the same "goodput" philosophy Step 14.A's throughput figures
already use (only delivered packets count) - narrower than the
aggregate "occupancy" metric used in 14.A/14.B/14.C (which also
includes ACK/control-frame airtime via separate, scattered call sites
not centralized enough to timestamp this way), but internally consistent
with it and zero new risk to the simulator's core accounting.

WHY THE RUN IS SPLIT INTO CHUNKS INSTEAD OF ONE CONTINUOUS 200s CALL:
purely a wall-clock-time constraint on how this script gets EXECUTED
during development/regeneration (a single 200s run of this traffic mix
was measured to take several minutes wall-clock, too long for one
non-interactive command), NOT a physics simplification - contention/
occupancy in this simulator has no state that depends on distance
HISTORY (CW/backoff resets stochastically regardless of prior distance,
NR-U's mcot doesn't either), so splicing several genuinely-continuous
sub-runs' packet timelines end-to-end (each chunk's gNB starts exactly
where the previous chunk's gNB ended, following the SAME overall linear
trajectory, just computed chunk-by-chunk) is statistically equivalent to
one uninterrupted run. The only real difference from a single run: CW/
backoff/queue state resets at each chunk boundary instead of carrying
over continuously - negligible under saturated traffic over a 200s
timeline binned into 5s windows.

Run standalone: `python -m analysis.nru_wifi_mobility_transition` from
the repo root (builds the full combined CSV + figure from chunk CSVs
already present in analysis/generated/_mobility_chunks/ - use
run_all_chunks() to (re)generate those first, see __main__ below).

# Rashed-Step 14.D.1-08-29-2026-start
LONG-TXOP WI-FI VARIANT (added 2026-08-29, additive - default behavior
above is byte-identical when wifi_packet_size_bytes is left at None
everywhere): same follow-up question as Step 14.C, now asked of this
time-series experiment instead of the static distance sweep - what does
the transition look like if Wi-Fi is given a comparably long TXOP
(36286-byte frame via aggregation, matching real 802.11ax's ~5.4ms TXOP
limit, WIFI_LONG_TXOP_PACKET_SIZE_BYTES/WIFI_LONG_TXOP_FRAME_DURATION_US
below - the exact 5400us duration confirmed directly via
Times(payload=36286, mcs=7).get_ppdu_frame_time(), not assumed) instead
of its ~242us single-frame default? Every function below now takes
optional wifi_packet_size_bytes/wifi_frame_duration_us/chunks_dir/
combined_csv/output_stem/title_suffix/wifi_series_label params (all
default to the original short-TXOP behavior) so the SAME chunking/
reconstruction/binning logic produces a second, independent figure
instead of duplicating it - mirrors exactly how Step 14.C extended
nru_sensing_region_impact.py.
# Rashed-Step 14.D.1-08-29-2026-end
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model.runner import run_scenario
from analysis.plot_utils import save_line_figure

TOTAL_DURATION_S = 200.0
TRANSITION_DURATION_S = 100.0
START_DIST_M = 100.0
END_DIST_M = 10.0
UE_OFFSET = (0.0, 3.0)
CHUNK_DURATION_S = 25.0
BIN_DURATION_S = 5.0

WIFI_FRAME_DURATION_US = 242.0   # default 1472-byte/MCS7 PPDU - see module docstring
NRU_MCOT_US = 6000.0             # mcot=6 default, payload-independent

# Rashed-Step 14.D.1-08-29-2026-start
WIFI_LONG_TXOP_PACKET_SIZE_BYTES = 36286   # matches Step 14.C / model/compare.py's DTMC scenario
WIFI_LONG_TXOP_FRAME_DURATION_US = 5400.0  # Times(payload=36286, mcs=7).get_ppdu_frame_time(), confirmed exact
# Rashed-Step 14.D.1-08-29-2026-end

CHUNKS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated", "_mobility_chunks")
os.makedirs(CHUNKS_DIR, exist_ok=True)
COMBINED_CSV = os.path.join(CHUNKS_DIR, "combined_packets.csv")

# Rashed-Step 14.D.1-08-29-2026-start
CHUNKS_DIR_LONG_TXOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated", "_mobility_chunks_long_txop")
os.makedirs(CHUNKS_DIR_LONG_TXOP, exist_ok=True)
COMBINED_CSV_LONG_TXOP = os.path.join(CHUNKS_DIR_LONG_TXOP, "combined_packets.csv")
# Rashed-Step 14.D.1-08-29-2026-end


def _dist_at(t_s: float) -> float:
    """Ground-truth gNB-AP distance at global time t_s, per the SAME
    linear trajectory the simulator's own LinearMobility would produce
    in one continuous run (100m -> 10m over the first 100s, then static)."""
    if t_s >= TRANSITION_DURATION_S:
        return END_DIST_M
    frac = t_s / TRANSITION_DURATION_S
    return START_DIST_M + frac * (END_DIST_M - START_DIST_M)


def run_chunk(chunk_index: int, seed: int = 1,
              wifi_packet_size_bytes: "int | None" = None,
              chunks_dir: str = CHUNKS_DIR) -> str:
    """
    Runs one CHUNK_DURATION_S-second sub-scenario continuing the overall
    trajectory (gNB moves from its distance at this chunk's start time to
    its distance at this chunk's end time, over exactly this chunk's
    duration - byte-identical slope to the full 100s/100m->10m move),
    exports its packets to a per-chunk CSV, and returns that CSV's path.
    """
    chunk_start_t = chunk_index * CHUNK_DURATION_S
    chunk_end_t = chunk_start_t + CHUNK_DURATION_S
    d_start = _dist_at(chunk_start_t)
    d_end = _dist_at(chunk_end_t)

    chunk_csv = os.path.join(chunks_dir, f"chunk_{chunk_index:02d}.csv")
    if os.path.exists(chunk_csv):
        os.remove(chunk_csv)  # export_packets_csv() appends - start clean each regeneration

    argv = [
        "--ap-number", "1", "--gnb-number", "1",
        "-t", str(CHUNK_DURATION_S), "-r", "1", "--seed", str(seed + chunk_index),
        "--wifi-traffic-model", "saturated", "--nru-traffic-model", "saturated",
        "--area-w", "250", "--area-h", "250",
        "--ap-pos", "0,0", "--gnb-pos", f"{d_start},0",
        "--sta-radius", "3",
        "--gnb-mobility-linear-target", f"{d_end},0",
        "--gnb-mobility-linear-duration-s", str(CHUNK_DURATION_S),
        "--ue-follow-gnb-offset", f"{UE_OFFSET[0]},{UE_OFFSET[1]}",
        "--export-packets-csv", chunk_csv,
    ]
    if wifi_packet_size_bytes is not None:
        argv += ["--wifi-packet-size-bytes", str(wifi_packet_size_bytes)]
    run_scenario(argv)
    return chunk_csv


def merge_chunks_into_combined(n_chunks: int, chunks_dir: str = CHUNKS_DIR,
                                combined_csv: str = COMBINED_CSV) -> str:
    """
    Reads every chunk_NN.csv, shifts each chunk's created_at_us/
    delivered_at_us by that chunk's global start-time offset (so
    "delivered_at_us" becomes a coordinate in the FULL 200s timeline,
    not each chunk's own 0..25s-relative one), and writes one combined
    CSV with the same PACKET_CSV_HEADER-compatible layout, filtered down
    to just the columns this script actually needs.
    """
    if os.path.exists(combined_csv):
        os.remove(combined_csv)

    with open(combined_csv, "w", newline="") as out_f:
        writer = csv.writer(out_f)
        writer.writerow(["technology", "status", "delivered_at_us"])
        for i in range(n_chunks):
            chunk_csv = os.path.join(chunks_dir, f"chunk_{i:02d}.csv")
            offset_us = (i * CHUNK_DURATION_S) * 1e6
            with open(chunk_csv, newline="") as in_f:
                reader = csv.DictReader(in_f)
                for row in reader:
                    if row["status"] != "DELIVERED" or row["delivered_at_us"] == "":
                        continue
                    global_delivered_at = float(row["delivered_at_us"]) + offset_us
                    writer.writerow([row["technology"], row["status"], global_delivered_at])
    return combined_csv


def run_all_chunks(seed: int = 1, wifi_packet_size_bytes: "int | None" = None,
                    chunks_dir: str = CHUNKS_DIR) -> int:
    n_chunks = int(TOTAL_DURATION_S / CHUNK_DURATION_S)
    for i in range(n_chunks):
        run_chunk(i, seed=seed, wifi_packet_size_bytes=wifi_packet_size_bytes, chunks_dir=chunks_dir)
    return n_chunks


def compute_occupancy_time_series(combined_csv: str = COMBINED_CSV,
                                   wifi_frame_duration_us: float = WIFI_FRAME_DURATION_US):
    n_bins = int(TOTAL_DURATION_S / BIN_DURATION_S)
    bin_us = BIN_DURATION_S * 1e6
    wifi_us_per_bin = [0.0] * n_bins
    nru_us_per_bin = [0.0] * n_bins

    with open(combined_csv, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t_us = float(row["delivered_at_us"])
            b = int(t_us // bin_us)
            if b < 0 or b >= n_bins:
                continue
            if row["technology"] == "WiFi":
                wifi_us_per_bin[b] += wifi_frame_duration_us
            elif row["technology"] == "NRU":
                nru_us_per_bin[b] += NRU_MCOT_US

    bin_centers_s = [(i + 0.5) * BIN_DURATION_S for i in range(n_bins)]
    wifi_occ = [us / bin_us for us in wifi_us_per_bin]
    nru_occ = [us / bin_us for us in nru_us_per_bin]
    combined = [w + n for w, n in zip(wifi_occ, nru_occ)]
    return bin_centers_s, wifi_occ, nru_occ, combined


def generate(combined_csv: str = COMBINED_CSV,
             wifi_frame_duration_us: float = WIFI_FRAME_DURATION_US,
             output_stem: str = "nru_wifi_mobility_transition",
             title_suffix: str = "",
             wifi_series_label: str = "Wi-Fi"):
    bin_centers_s, wifi_occ, nru_occ, combined = compute_occupancy_time_series(
        combined_csv=combined_csv, wifi_frame_duration_us=wifi_frame_duration_us)

    paths = save_line_figure(
        x=bin_centers_s,
        series={
            wifi_series_label: wifi_occ,
            "NR-U": nru_occ,
            "Combined (Wi-Fi + NR-U)": combined,
        },
        xlabel="Simulated time (s)",
        ylabel="Data-airtime occupancy (5s bins)",
        title=f"NR-U/Wi-Fi Coexistence: Occupancy as NR-U Enters Wi-Fi's Sensing Region{title_suffix}",
        output_stem=output_stem,
        x_ticks_as_int=False,
        hlines=[(1.0, "Shared-channel limit (sum = 1.0)")],
        vlines=[(TRANSITION_DURATION_S, f"NR-U reaches {END_DIST_M:.0f}m (t={TRANSITION_DURATION_S:.0f}s)")],
    )
    return bin_centers_s, wifi_occ, nru_occ, combined, paths


def _print_report(bin_centers_s, wifi_occ, nru_occ, combined, paths, label):
    print(f"--- {label} ---")
    print(f"{'t (s)':>7} | {'WiFi occ':>9} {'NRU occ':>9} {'sum':>7}")
    print("-" * 40)
    for t, w, n, s in zip(bin_centers_s, wifi_occ, nru_occ, combined):
        print(f"{t:>7.1f} | {w:>9.4f} {n:>9.4f} {s:>7.4f}")
    print()
    print(f"Saved: {paths['pdf']}")
    print(f"Saved: {paths['jpg']}")
    print()


if __name__ == "__main__":
    if not os.path.exists(COMBINED_CSV):
        n_chunks = run_all_chunks()
        merge_chunks_into_combined(n_chunks)
    result = generate()
    _print_report(*result, label="short-TXOP Wi-Fi (default, 242us)")

    # Rashed-Step 14.D.1-08-29-2026-start
    if not os.path.exists(COMBINED_CSV_LONG_TXOP):
        n_chunks = run_all_chunks(
            wifi_packet_size_bytes=WIFI_LONG_TXOP_PACKET_SIZE_BYTES,
            chunks_dir=CHUNKS_DIR_LONG_TXOP,
        )
        merge_chunks_into_combined(n_chunks, chunks_dir=CHUNKS_DIR_LONG_TXOP,
                                    combined_csv=COMBINED_CSV_LONG_TXOP)
    result_long = generate(
        combined_csv=COMBINED_CSV_LONG_TXOP,
        wifi_frame_duration_us=WIFI_LONG_TXOP_FRAME_DURATION_US,
        output_stem="nru_wifi_mobility_transition_long_txop",
        title_suffix=" (Long Wi-Fi TXOP)",
        wifi_series_label="Wi-Fi (Long TXOP)",
    )
    _print_report(*result_long, label="long-TXOP Wi-Fi (5.4ms via 36286-byte frame)")
    # Rashed-Step 14.D.1-08-29-2026-end
# Rashed-Step 14.D-08-28-2026-end
