import click
import sys

from simulation import *


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
@click.option("--rogue", "rogue_wifi", default=False, help="Presence of rogue Wi-Fi AP(True/False)")
@click.option("-n_t_p", "nru_transmission_prob", default=100, help="Transmission probability of NR-U. Helps to show the attack probability. attack probability= (100-trasmission probability)/100")
@click.option("-nru_rs_prob","nru_reservation_signal_prob", default=0, help="Reservatiom signal probability for NR-U in hybrid RS and gap-based approach. We are trying to keep it less than 50%")
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
        nru_transmission_prob: int,
        nru_reservation_signal_prob: int
):
    backoffs = {key: {ap_number: 0} for key in range(wifi_cw_max + 1)}
    airtime_data = {"Station {}".format(i): 0 for i in range(1, ap_number + 1)}
    airtime_control = {"Station {}".format(
        i): 0 for i in range(1, ap_number + 1)}
    airtime_data_NR = {"Gnb {}".format(i): 0 for i in range(1, gnb_number + 1)}
    airtime_control_NR = {"Gnb {}".format(
        i): 0 for i in range(1, gnb_number + 1)}
    

    for i in range(0, runs):
        curr_seed = seed + i
        print("before simulation")
        run_simulation(ap_number, gnb_number, curr_seed, simulation_time,
                       Config(1472, wifi_cw_min, wifi_cw_max,
                              wifi_r_limit, mcs_value),
                       Config_NR(16, 9, synchronization_slot_duration, max_sync_slot_desync,
                                 min_sync_slot_desync,  nru_observation_slot, nru_cw_min, nru_cw_max, mcot),
                       backoffs, airtime_data, airtime_control, airtime_data_NR, airtime_control_NR, rogue_wifi,nru_transmission_prob,nru_reservation_signal_prob)


if __name__ == "__main__":
    single_run()
