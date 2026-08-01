# Rashed-Step 6.B-07-31-2026-start
# Standalone CLI for the licensed 5G NR scenario (simulation_nr.py) -
# separate from singleRun.py (WiFi/NR-U coexistence) per the confirmed
# "standalone first" scope for Step 6.B. Run e.g.:
#   python singleRunNR.py --gnb-number 2 --ues-per-gnb 6 -t 1 --scheduler proportional_fair

import click

from simulation_nr import run_simulation_licensed_nr, parse_pos_list_nr
from nr.nr import Config_NRL


@click.command()
@click.option("-r", "--runs", "runs", default=1, help="Number of simulation runs")
@click.option("--seed", "seed", default=1, help="Seed for simulation")
@click.option("--gnb-number", "gnb_number", type=int, required=True, help="Number of licensed-NR gNBs")
@click.option("--ues-per-gnb", "ues_per_gnb", type=int, default=4, help="Number of UEs associated to each gNB")
@click.option("-t", "--simulation-time", "simulation_time", default=1.0, help="Duration of the simulation in s")
@click.option("--area-w", "area_w", type=float, default=200.0, help="Deployment area width (m)")
@click.option("--area-h", "area_h", type=float, default=200.0, help="Deployment area height (m)")
@click.option("--gnb-pos", "gnb_pos", type=str, multiple=True, help="Explicit gNB position 'x,y' (repeatable)")
@click.option("--ue-radius", "ue_radius", type=float, default=200.0, help="Radius (m) around its gNB within which a UE is randomly placed")
@click.option("--numerology", "numerology", type=int, default=1, help="NR numerology index mu (0=15kHz SCS, 1=30kHz, 2=60kHz, 3=120kHz)")
@click.option("--bandwidth-mhz", "bandwidth_mhz", type=float, default=100.0, help="Channel bandwidth (MHz), drives resource-block count")
@click.option("--scheduler", "scheduler", type=click.Choice(["round_robin", "proportional_fair"]), default="round_robin", help="Per-slot RB scheduler")
@click.option("--tx-power-dbm", "tx_power_dbm", type=float, default=30.0, help="gNB downlink tx power (dBm EIRP)")
@click.option("--f-ghz", "f_ghz", type=float, default=3.5, help="Carrier frequency (GHz) - default 3.5 GHz matches 3GPP band n78")
@click.option("--noise-figure-db", "noise_figure_db", type=float, default=7.0, help="UE receiver noise figure (dB)")
@click.option("--gnb-mobility-speed-mps", "gnb_mobility_speed_mps", type=float, default=0.0, help="gNB roaming speed (m/s), 0=static")
@click.option("--ue-mobility-speed-mps", "ue_mobility_speed_mps", type=float, default=0.0, help="UE walking speed (m/s), 0=static")
@click.option("--mobility-pause-s", "mobility_pause_s", type=float, default=0.0, help="Dwell time (s) at each waypoint if mobility is enabled")
def single_run_nr(
        runs, seed, gnb_number, ues_per_gnb, simulation_time,
        area_w, area_h, gnb_pos, ue_radius,
        numerology, bandwidth_mhz, scheduler, tx_power_dbm, f_ghz, noise_figure_db,
        gnb_mobility_speed_mps, ue_mobility_speed_mps, mobility_pause_s,
):
    gnb_positions = parse_pos_list_nr(gnb_pos, "--gnb-pos") if gnb_pos else None

    config = Config_NRL(
        numerology=numerology,
        bandwidth_mhz=bandwidth_mhz,
        scheduler=scheduler,
        tx_power_dbm=tx_power_dbm,
        f_ghz=f_ghz * 1e9,
        noise_figure_db=noise_figure_db,
    )

    for i in range(runs):
        curr_seed = seed + i
        run_simulation_licensed_nr(
            gnb_number, curr_seed, simulation_time, config,
            area_w=area_w, area_h=area_h,
            gnb_positions=gnb_positions, ue_radius=ue_radius,
            nr_ues_per_gnb=ues_per_gnb,
            gnb_mobility_speed_mps=gnb_mobility_speed_mps,
            ue_mobility_speed_mps=ue_mobility_speed_mps,
            mobility_pause_s=mobility_pause_s,
        )


if __name__ == "__main__":
    single_run_nr()
# Rashed-Step 6.B-07-31-2026-end
