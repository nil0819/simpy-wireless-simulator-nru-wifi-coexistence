# Rashed-Step 13.B-08-23-2026-start
"""
Step 13.B: scenario sweep that generates the training dataset for the
SINR/channel-quality prediction work (see "Project details/Step
13.txt"). Runs many varied Wi-Fi+NR-U coexistence scenarios, all
pointed at the SAME --export-packets-csv path, so
common.packet.export_packets_csv()'s existing "write header once, then
append" behavior (Step 9.D) accumulates every scenario's packets - each
carrying its own measured_sinr_db (Step 13.A) - into one combined file.

WHY model.runner.run_scenario() INSTEAD OF SHELLING OUT TO singleRun.py
PER SCENARIO: measured directly in this session - a 1-simulated-second
scenario took 120s+ wall clock via a plain `python singleRun.py ...`
subprocess (this sandbox's mounted filesystem makes every per-event
log() call in common/common.py a slow disk write - see model/
runner.py's own docstring for the full explanation and a measured
14.6x speedup figure). run_scenario() disables logging
(logging.disable(logging.CRITICAL)) before running singleRun.py's CLI
in-process, which is what makes a several-dozen-scenario sweep
tractable at all. Same 1-simulated-second scenario measured 25.8s wall
clock THIS way (still not fast - the mounted-filesystem overhead is
real, not just a logging problem - but tractable for the grid size
below).

DELIBERATELY NOT per-packet contextual columns (distance, live
interferer count) - see Step 13.txt design decision 3: the first model
(13.C) is a pure lag-based/autoregressive predictor. What THIS script
gives that model to generalize over is variation ACROSS scenarios
(distance/shadowing/mobility/interferer-count all change between
sweep points), not per-row context columns. A companion "manifest" CSV
(one row per scenario, keyed by seed) records exactly what varied, so
a later step (13.E) can join it back to the packet CSV by seed if
richer per-scenario features are ever wanted - the packet CSV's "seed"
column (Step 9.D) already makes that join possible with zero changes
to the packet CSV format itself.

Run: `python3 ml/generate_sinr_dataset.py` from the repo root (or
anywhere - paths below are resolved relative to this file, not cwd).
Re-running DELETES and regenerates both output files from scratch
(the point is a reproducible dataset from a fixed, documented grid,
not an ever-growing accumulation across unrelated runs).
"""
import csv
import os
import sys
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from model.runner import run_scenario  # noqa: E402

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PACKETS_CSV_PATH = os.path.join(_DATA_DIR, "sinr_dataset_packets.csv")
MANIFEST_CSV_PATH = os.path.join(_DATA_DIR, "sinr_dataset_manifest.csv")

# Simulated seconds per scenario. A first pass at 0.3s (measured:
# whole 24-scenario grid in 21.4s wall clock, 7250 total rows) was too
# thin for lag-window features (~300 rows/scenario average, some
# "close"/low-contention scenarios far fewer) - bumped to 2.0s, still
# only ~140-150s wall clock for the full grid at that rate.
SIM_TIME_S = 2.0

# --- Distance proxy: area size (affects inter-node/interferer
# distance) + STA/UE radius (affects the STA/UE's own distance from
# its AP/gNB) move together, so "close" means genuinely short links
# AND tightly packed interferers, "far" means the opposite - see Step
# 13.txt decision 3's note on why no explicit distance column is
# logged per packet; this is the run-level variation standing in for
# it.
DISTANCE_LEVELS = [
    {"name": "close", "area_w": 20.0, "area_h": 20.0, "sta_radius": 3.0, "ue_radius": 3.0},
    {"name": "medium", "area_w": 60.0, "area_h": 60.0, "sta_radius": 15.0, "ue_radius": 15.0},
    {"name": "far", "area_w": 150.0, "area_h": 150.0, "sta_radius": 40.0, "ue_radius": 40.0},
]

# 0.0 = disabled/deterministic path loss only; 6.0 = typical indoor
# log-normal shadowing sigma (Step 5.B's own docstring range is ~4-8).
SHADOWING_LEVELS = [0.0, 6.0]

# STA/UE walking speed - APs/gNBs (infrastructure) stay static in
# every scenario, only client devices move, matching Step 5.G's own
# typical-use framing (~1.4 m/s = walking pace).
MOBILITY_LEVELS = [False, True]

# "light" = minimal contention (1 AP, 1 gNB); "heavy" = more
# contending/interfering nodes of both technologies.
TOPOLOGY_LEVELS = [
    {"name": "light", "ap_number": 1, "gnb_number": 1},
    {"name": "heavy", "ap_number": 3, "gnb_number": 2},
]

# Unique, clearly-out-of-the-way seed range so this sweep's rows can
# never collide with a seed used by some earlier/unrelated
# --export-packets-csv run someone might append into the same file by
# mistake.
SEED_BASE = 20000


def build_grid():
    """Cartesian product of every level list above -> one dict per
    scenario, each with a unique seed assigned in a fixed, reproducible
    order (distance outer loop, then shadowing, then mobility, then
    topology - order doesn't affect the simulation itself, just makes
    the manifest's seed assignment deterministic across reruns)."""
    grid = []
    seed = SEED_BASE
    for dist in DISTANCE_LEVELS:
        for shadow in SHADOWING_LEVELS:
            for mobility in MOBILITY_LEVELS:
                for topo in TOPOLOGY_LEVELS:
                    grid.append({
                        "seed": seed,
                        "distance": dist["name"],
                        "area_w": dist["area_w"],
                        "area_h": dist["area_h"],
                        "sta_radius": dist["sta_radius"],
                        "ue_radius": dist["ue_radius"],
                        "shadowing_sigma_db": shadow,
                        "mobility": mobility,
                        "topology": topo["name"],
                        "ap_number": topo["ap_number"],
                        "gnb_number": topo["gnb_number"],
                    })
                    seed += 1
    return grid


def scenario_argv(scenario: dict) -> list:
    argv = [
        # -r/--runs defaults to 10 in singleRun.py - MUST be pinned to 1
        # here, or each "scenario" silently becomes 10 internal repeats
        # with seed+0..seed+9, blowing the manifest's one-seed-per-
        # scenario assumption and creating overlapping seed ranges
        # between adjacent scenarios (caught by a smoke test before the
        # real sweep ran - see Step 13.txt/STATUS for the writeup).
        "-r", "1",
        "--ap-number", str(scenario["ap_number"]),
        "--gnb-number", str(scenario["gnb_number"]),
        "-t", str(SIM_TIME_S),
        "--seed", str(scenario["seed"]),
        "--area-w", str(scenario["area_w"]),
        "--area-h", str(scenario["area_h"]),
        "--sta-radius", str(scenario["sta_radius"]),
        "--ue-radius", str(scenario["ue_radius"]),
        "--shadowing-sigma-db", str(scenario["shadowing_sigma_db"]),
        "--export-packets-csv", PACKETS_CSV_PATH,
    ]
    if scenario["mobility"]:
        argv += [
            "--sta-mobility-speed-mps", "1.4",
            "--ue-mobility-speed-mps", "1.4",
        ]
    return argv


def main():
    os.makedirs(_DATA_DIR, exist_ok=True)
    for path in (PACKETS_CSV_PATH, MANIFEST_CSV_PATH):
        if os.path.exists(path):
            os.remove(path)

    grid = build_grid()
    print(f"Running {len(grid)} scenarios, {SIM_TIME_S}s simulated time each...")

    manifest_rows = []
    t0 = time.time()
    for i, scenario in enumerate(grid, start=1):
        t_scenario = time.time()
        run_scenario(scenario_argv(scenario))
        elapsed = time.time() - t_scenario
        manifest_rows.append({**scenario, "wall_clock_s": round(elapsed, 2)})
        print(
            f"  [{i}/{len(grid)}] seed={scenario['seed']} "
            f"distance={scenario['distance']} shadowing={scenario['shadowing_sigma_db']} "
            f"mobility={scenario['mobility']} topology={scenario['topology']} "
            f"-> {elapsed:.1f}s"
        )

    with open(MANIFEST_CSV_PATH, "w", newline="") as f:
        fieldnames = list(manifest_rows[0].keys())
        writer = csv.writer(f)
        writer.writerow(fieldnames)
        for row in manifest_rows:
            writer.writerow([row[k] for k in fieldnames])

    total_elapsed = time.time() - t0
    with open(PACKETS_CSV_PATH) as f:
        total_rows = sum(1 for _ in f) - 1  # minus header

    print(f"\nDone in {total_elapsed:.1f}s wall clock.")
    print(f"{len(grid)} scenarios -> {total_rows} packet rows in {PACKETS_CSV_PATH}")
    print(f"Manifest ({len(grid)} rows) written to {MANIFEST_CSV_PATH}")


if __name__ == "__main__":
    main()
# Rashed-Step 13.B-08-23-2026-end
