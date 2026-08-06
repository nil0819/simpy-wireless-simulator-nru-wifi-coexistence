# Rashed-Step 7.B-08-05-2026-start
# Standalone CLI for the spectrum-analyzer scenario (simulation_spectrum.py)
# - separate from singleRun.py (WiFi/NR-U coexistence) and singleRunNR.py
# (licensed NR), per the confirmed "standalone first" scope for Step 7.B.
# Run e.g.:
#   python singleRunSpectrum.py --ap-number 2 --gnb-number 1 --sniffer-number 2 -t 1

import click

from simulation_spectrum import run_simulation_spectrum
from wifi.wifi import Config as WifiConfig
from nru.nru import Config_NR
from generic.generic_device import Config_Generic
from simulation_nr import parse_pos_list_nr as parse_pos_list  # reused verbatim, see that file's docstring


@click.command()
@click.option("-r", "--runs", "runs", default=1, help="Number of simulation runs")
@click.option("--seed", "seed", default=1, help="Seed for simulation")
@click.option("--ap-number", "ap_number", type=int, required=True, help="Number of Wi-Fi APs generating traffic")
@click.option("--gnb-number", "gnb_number", type=int, required=True, help="Number of NR-U gNBs generating traffic")
@click.option("--sniffer-number", "sniffer_number", type=int, default=1, help="Number of spectrum-analyzer sniffer nodes")
@click.option("-t", "--simulation-time", "simulation_time", default=1.0, help="Duration of the simulation in s")
@click.option("--area-w", "area_w", type=float, default=50.0, help="Deployment area width (m)")
@click.option("--area-h", "area_h", type=float, default=50.0, help="Deployment area height (m)")
@click.option("--sta-radius", "sta_radius", type=float, default=10.0, help="Radius (m) around its AP within which a Wi-Fi STA is placed")
@click.option("--ue-radius", "ue_radius", type=float, default=15.0, help="Radius (m) around its gNB within which an NR-U UE is placed")
@click.option("--sniffer-pos", "sniffer_pos", type=str, multiple=True, help="Explicit sniffer position 'x,y' (repeatable)")
@click.option("--sniff-interval-us", "sniff_interval_us", type=float, default=50.0, help="How often (us) each sniffer samples the channel")
@click.option("--sniffer-ed-threshold-dbm", "sniffer_ed_threshold_dbm", type=float, default=-62.0, help="Energy-detect threshold (dBm) sniffers use for their busy/idle read")
@click.option("--sniffer-bandwidth-mhz", "sniffer_bandwidth_mhz", type=float, default=20.0, help="Sniffer's own in-band channel width (MHz) - only affects the in-band (not wideband) reading")
@click.option("--sniffer-freq-ghz", "sniffer_freq_ghz", type=float, default=5.18, help="Sniffer's own in-band center frequency (GHz) - only affects the in-band (not wideband) reading")
@click.option("--wifi_cw_min", "wifi_cw_min", default=15, help="Size of Wi-Fi cw min")
@click.option("--wifi_cw_max", "wifi_cw_max", default=63, help="Size of Wi-Fi cw max")
@click.option("--nru_cw_min", "nru_cw_min", default=15, help="Size of NR-U cw min")
@click.option("--nru_cw_max", "nru_cw_max", default=63, help="Size of NR-U cw max")
@click.option("--mcot", "mcot", default=6, help="Max channel occupancy time for NR-U (ms)")
@click.option("-syn_slot", "--synchronization_slot_duration", "synchronization_slot_duration", default=1000, help="Synchronization slot length in microseconds")
def single_run_spectrum(
        runs, seed, ap_number, gnb_number, sniffer_number, simulation_time,
        area_w, area_h, sta_radius, ue_radius,
        sniffer_pos, sniff_interval_us, sniffer_ed_threshold_dbm,
        sniffer_bandwidth_mhz, sniffer_freq_ghz,
        wifi_cw_min, wifi_cw_max, nru_cw_min, nru_cw_max, mcot, synchronization_slot_duration,
):
    sniffer_positions = parse_pos_list(sniffer_pos, "--sniffer-pos") if sniffer_pos else None

    wifi_config = WifiConfig(cw_min=wifi_cw_min, cw_max=wifi_cw_max)
    configNr = Config_NR(
        cw_min=nru_cw_min, cw_max=nru_cw_max, mcot=mcot,
        synchronization_slot_duration=synchronization_slot_duration,
    )
    sniffer_config = Config_Generic(
        f_hz=sniffer_freq_ghz * 1e9,
        bandwidth_mhz=sniffer_bandwidth_mhz,
        ed_threshold_dbm=sniffer_ed_threshold_dbm,
        tech_label="SNIFFER",
    )

    for i in range(runs):
        curr_seed = seed + i
        run_simulation_spectrum(
            ap_number, gnb_number, sniffer_number, curr_seed, simulation_time,
            wifi_config, configNr, sniffer_config,
            area_w=area_w, area_h=area_h,
            sta_radius=sta_radius, ue_radius=ue_radius,
            sniffer_positions=sniffer_positions,
            sniff_interval_us=sniff_interval_us,
        )


if __name__ == "__main__":
    single_run_spectrum()
# Rashed-Step 7.B-08-05-2026-end
