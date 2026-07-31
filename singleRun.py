import click
import sys

from simulation import *


# Rashed-Step 5.A-02-06-2026-start
def parse_pos_list(raw_values, label: str):
    """Parse a tuple of 'x,y' strings (from a repeatable click option) into
    a list of (float, float) tuples. Raises click.BadParameter on malformed
    input so the CLI fails fast with a clear message instead of a raw
    ValueError/IndexError deep in simulation.py."""
    positions = []
    for raw in raw_values:
        parts = raw.split(",")
        if len(parts) != 2:
            raise click.BadParameter(
                f"{label} must be given as 'x,y' (got: {raw!r})"
            )
        try:
            x, y = float(parts[0]), float(parts[1])
        except ValueError:
            raise click.BadParameter(
                f"{label} coordinates must be numeric (got: {raw!r})"
            )
        positions.append((x, y))
    return positions
# Rashed-Step 5.A-02-06-2026-end


@click.command()
@click.option("-r", "--runs", "runs", default=10, help="Number of simulation runs")
@click.option("--seed", "seed", default=1, help="Seed for simulation")
@click.option(
    "--ap-number",
    "ap_number",
    type=int,
    required=True,
    help="Number of Wi-Fi stations",
)
@click.option(
    "--gnb-number",
    "gnb_number",
    type=int,
    required=True,
    help="Number of NR-U gNBs",
)
@click.option(
    "-t",
    "--simulation-time",
    "simulation_time",
    default=100.0,
    help="Duration of the simulation per stations number in s",
)
@click.option("--wifi_cw_min", "wifi_cw_min", default=15, help="Size of Wi-Fi cw min")
@click.option("--wifi_cw_max", "wifi_cw_max", default=63, help="Size of Wi-Fi cw max")
@click.option("--nru_cw_min", "nru_cw_min", default=15, help="Size of NR-U cw min")
@click.option("--nru_cw_max", "nru_cw_max", default=63, help="Size of NR-U cw max")
@click.option(
    "--wifi_r_limit", "wifi_r_limit", default=7, help="Number of failed transmissions in a row",
)
@click.option("-m", "--mcs-value", "mcs_value", default=7, help="Value of mcs")
@click.option("-syn_slot", "--synchronization_slot_duration", default=1000, help="Synchronization slot length in mikrosecounds")
@click.option("-max_des", "--max_sync_slot_desync", default=1000, help="Max value of gNB desynchronization")
@click.option("-min_des", "--min_sync_slot_desync", default=0, help="Min value of gNB desynchronization")
@click.option("-nru_obser_slots", "--nru_observation_slot", default=3, help="amount of observation slots for NR_U")
@click.option("--mcot", default=6, help="Max channel occupancy time for NR-U (ms)")
@click.option("--rogue","rogue_wifi",default=False,help="Presence of rogue Wi-Fi AP(True/False)")
# Rashed-Step 5.A-02-06-2026-start
@click.option("--area-w", "area_w", type=float, default=50.0, help="Deployment area width (m) used for randomly placed devices")
@click.option("--area-h", "area_h", type=float, default=50.0, help="Deployment area height (m) used for randomly placed devices")
@click.option("--ap-pos", "ap_pos", type=str, multiple=True, help="Explicit AP position as 'x,y' (repeatable, e.g. --ap-pos 0,0 --ap-pos 50,0). Matched in order to AP 1, AP 2, ...; any AP beyond the number given falls back to a random position within --area-w/--area-h.")
@click.option("--gnb-pos", "gnb_pos", type=str, multiple=True, help="Explicit gNB position as 'x,y' (repeatable). Matched in order to Gnb 1, Gnb 2, ...; same random fallback as --ap-pos.")
@click.option("--sta-radius", "sta_radius", type=float, default=10.0, help="Radius (m) around its AP within which an associated Wi-Fi STA is randomly placed")
@click.option("--ue-radius", "ue_radius", type=float, default=15.0, help="Radius (m) around its gNB within which an associated NR-U UE is randomly placed")
# Rashed-Step 5.A-02-06-2026-end
# Rashed-Step 5.B-02-06-2026-start
@click.option("--shadowing-sigma-db", "shadowing_sigma_db", type=float, default=0.0, help="Log-normal shadow fading std dev in dB, applied on top of the deterministic path loss (0 = disabled/deterministic, matches pre-Step-5.B behavior; typical indoor value ~4-8)")
# Rashed-Step 5.B-02-06-2026-end
# Rashed-Step 5.C-02-06-2026-start
@click.option("--wifi-bandwidth-mhz", "wifi_bandwidth_mhz", type=float, default=20.0, help="Wi-Fi channel bandwidth (MHz), used to derive the SINR noise floor")
@click.option("--wifi-noise-figure-db", "wifi_noise_figure_db", type=float, default=7.0, help="Wi-Fi receiver noise figure (dB), used to derive the SINR noise floor")
@click.option("--nru-bandwidth-mhz", "nru_bandwidth_mhz", type=float, default=20.0, help="NR-U channel bandwidth (MHz), used to derive the SINR noise floor")
@click.option("--nru-noise-figure-db", "nru_noise_figure_db", type=float, default=7.0, help="NR-U receiver noise figure (dB), used to derive the SINR noise floor")
# Rashed-Step 5.C-02-06-2026-end
# Rashed-Step 5.D-02-06-2026-start
@click.option("--nru-mcs", "nru_mcs", type=int, default=4, help="NR-U MCS index (0-7), drives the required-SINR threshold via NRU_MCS_SINR_THRESHOLDS_DB. Note: unlike Wi-Fi's -m/--mcs-value, this does NOT affect NR-U transmission duration (still mcot-based).")
@click.option("--wifi-sinr-thr-db-override", "wifi_sinr_thr_db_override", type=float, default=None, help="Force a flat Wi-Fi SINR success threshold (dB) instead of the per-MCS table lookup")
@click.option("--nru-sinr-thr-db-override", "nru_sinr_thr_db_override", type=float, default=None, help="Force a flat NR-U SINR success threshold (dB) instead of the per-MCS table lookup")
# Rashed-Step 5.D-02-06-2026-end
# Rashed-Step 5.E-02-06-2026-start
@click.option("--wifi-freq-ghz", "wifi_freq_ghz", type=float, default=5.18, help="Wi-Fi center frequency (GHz). Default matches --nru-freq-ghz's default (full co-channel overlap, same as before Step 5.E). Set them apart to model adjacent/non-overlapping channels.")
@click.option("--nru-freq-ghz", "nru_freq_ghz", type=float, default=5.18, help="NR-U center frequency (GHz). See --wifi-freq-ghz.")
# Rashed-Step 5.E-02-06-2026-end
# Rashed-Step 5.F-02-06-2026-start
@click.option("--wifi-tx-power-dbm", "wifi_tx_power_dbm", type=float, default=20.0, help="Wi-Fi tx power (dBm), treated as EIRP directly (no separate antenna-gain model). Checked at startup against the FCC U-NII EIRP cap for --wifi-freq-ghz (warning only, not clamped/enforced). Default (20.0) matches wifi.Config.tx_power_dbm's pre-existing class default - regression-safe.")
@click.option("--nru-tx-power-dbm", "nru_tx_power_dbm", type=float, default=23.0, help="NR-U tx power (dBm). See --wifi-tx-power-dbm. Default (23.0) matches nru.Config_NR.tx_power_dbm's pre-existing class default - regression-safe (NOT the same default as --wifi-tx-power-dbm, intentionally, to match each config's own prior constant).")
# Rashed-Step 5.F-02-06-2026-end

def single_run(
        runs: int,
        seed: int,
        ap_number: int,
        gnb_number: int,
        simulation_time: int,
        wifi_cw_min: int,
        wifi_cw_max: int,
        wifi_r_limit: int,
        mcs_value: int,

        nru_cw_min: int,
        nru_cw_max: int,
        synchronization_slot_duration: int,
        max_sync_slot_desync: int,
        min_sync_slot_desync: int,
        nru_observation_slot: int,
        mcot: int,
        rogue_wifi: bool,
        # Rashed-Step 5.A-02-06-2026-start
        area_w: float,
        area_h: float,
        ap_pos: tuple,
        gnb_pos: tuple,
        sta_radius: float,
        ue_radius: float,
        # Rashed-Step 5.A-02-06-2026-end
        # Rashed-Step 5.B-02-06-2026-start
        shadowing_sigma_db: float,
        # Rashed-Step 5.B-02-06-2026-end
        # Rashed-Step 5.C-02-06-2026-start
        wifi_bandwidth_mhz: float,
        wifi_noise_figure_db: float,
        nru_bandwidth_mhz: float,
        nru_noise_figure_db: float,
        # Rashed-Step 5.C-02-06-2026-end
        # Rashed-Step 5.D-02-06-2026-start
        nru_mcs: int,
        wifi_sinr_thr_db_override: float,
        nru_sinr_thr_db_override: float,
        # Rashed-Step 5.D-02-06-2026-end
        # Rashed-Step 5.E-02-06-2026-start
        wifi_freq_ghz: float,
        nru_freq_ghz: float,
        # Rashed-Step 5.E-02-06-2026-end
        # Rashed-Step 5.F-02-06-2026-start
        wifi_tx_power_dbm: float,
        nru_tx_power_dbm: float
        # Rashed-Step 5.F-02-06-2026-end
):
    backoffs = {key: {ap_number: 0} for key in range(wifi_cw_max + 1)}
    airtime_data = {"Station {}".format(i): 0 for i in range(1, ap_number + 1)}
    airtime_control = {"Station {}".format(i): 0 for i in range(1, ap_number + 1)}
    airtime_data_NR = {"Gnb {}".format(i): 0 for i in range(1, gnb_number + 1)}
    airtime_control_NR = {"Gnb {}".format(i): 0 for i in range(1, gnb_number + 1)}

    # Rashed-Step 5.A-02-06-2026-start
    ap_positions = parse_pos_list(ap_pos, "--ap-pos") if ap_pos else None
    gnb_positions = parse_pos_list(gnb_pos, "--gnb-pos") if gnb_pos else None
    # Rashed-Step 5.A-02-06-2026-end

    for i in range(0, runs):
        curr_seed = seed + i
        print("before simulation")
        run_simulation(ap_number, gnb_number, curr_seed, simulation_time,
                       # Rashed-Step 5.C-02-06-2026-start
                       Config(1472, wifi_cw_min, wifi_cw_max, wifi_r_limit, mcs_value,
                              bandwidth_mhz=wifi_bandwidth_mhz, noise_figure_db=wifi_noise_figure_db,
                              # Rashed-Step 5.D-02-06-2026-start
                              wifi_sinr_thr_db_override=wifi_sinr_thr_db_override,
                              # Rashed-Step 5.D-02-06-2026-end
                              # Rashed-Step 5.E-02-06-2026-start
                              f_ghz=wifi_freq_ghz * 1e9,
                              # Rashed-Step 5.E-02-06-2026-end
                              # Rashed-Step 5.F-02-06-2026-start
                              tx_power_dbm=wifi_tx_power_dbm
                              # Rashed-Step 5.F-02-06-2026-end
                              ),
                       Config_NR(16, 9, synchronization_slot_duration, max_sync_slot_desync, min_sync_slot_desync,  nru_observation_slot, nru_cw_min, nru_cw_max, mcot,
                                 bandwidth_mhz=nru_bandwidth_mhz, noise_figure_db=nru_noise_figure_db,
                                 # Rashed-Step 5.D-02-06-2026-start
                                 mcs=nru_mcs, nru_sinr_thr_db_override=nru_sinr_thr_db_override,
                                 # Rashed-Step 5.D-02-06-2026-end
                                 # Rashed-Step 5.E-02-06-2026-start
                                 f_ghz=nru_freq_ghz * 1e9,
                                 # Rashed-Step 5.E-02-06-2026-end
                                 # Rashed-Step 5.F-02-06-2026-start
                                 tx_power_dbm=nru_tx_power_dbm
                                 # Rashed-Step 5.F-02-06-2026-end
                                 ),
                       # Rashed-Step 5.C-02-06-2026-end
                       backoffs, airtime_data, airtime_control, airtime_data_NR, airtime_control_NR, rogue_wifi,
                       # Rashed-Step 5.A-02-06-2026-start
                       area_w=area_w, area_h=area_h,
                       ap_positions=ap_positions, gnb_positions=gnb_positions,
                       sta_radius=sta_radius, ue_radius=ue_radius,
                       # Rashed-Step 5.A-02-06-2026-end
                       # Rashed-Step 5.B-02-06-2026-start
                       shadowing_sigma_db=shadowing_sigma_db
                       # Rashed-Step 5.B-02-06-2026-end
                       )





if __name__ == "__main__":
    single_run()