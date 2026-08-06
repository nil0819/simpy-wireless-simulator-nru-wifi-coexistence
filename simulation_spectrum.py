# Rashed-Step 7.B-08-05-2026-start
"""
Standalone entry point for the spectrum-analyzer scenario (Step 7.B) -
demonstrates the "spectrum analyzer" use case of Step 7.A's
generic.generic_device.GenericWirelessDevice by dropping one or more
passive sniffer nodes into a REAL WiFi + NR-U coexistence topology
(the same wifi.WiFi/nru.Gnb classes simulation.py already uses and
Step 6 already verified) and periodically sampling the channel with
sniff().

Deliberately kept separate from simulation.py's run_simulation(),
mirroring the "standalone first" pattern used for licensed NR in Step
6.B/simulation_nr.py - confirmed with Rashed via AskUserQuestion for
this sub-step too: zero changes to the already-verified
singleRun.py/simulation.py, own small script instead.

Unlike simulation_nr.py (which duplicates its own rand_pos_near rather
than import anything WiFi/NR-U related, since licensed NR needs none
of it), THIS scenario's whole point is sensing real WiFi/NR-U traffic,
so it directly reuses wifi.WiFi/wifi.sta.WiFiSTA/nru.Gnb/nru.ue.NrUE -
the exact same topology-building building blocks simulation.py uses,
just assembled in this file's own loop (so we keep a handle on the
constructed Channel/nodes to attach sniffers to and drive with one
shared environment.run()).

Sniffing is done via periodic SAMPLING (sniff() called every
sniff_interval_us), not by reading Channel's internal bookkeeping
directly - this is deliberate: a real spectrum analyzer/energy
detector doesn't have privileged access to "ground truth" airtime
counters, it only ever gets point-in-time energy readings. Per-tech
duty cycle is therefore an estimate (samples where that tech was
visible / total samples), same as a real spectrum analyzer would
report, and gets more accurate as sniff_interval_us shrinks (samples
more often) at the cost of more simulated events.
"""

import random
import simpy
from typing import List, Optional
from dataclasses import dataclass, field

from common.common import Pos, rand_pos, dist
from common.common_phy import WaypointMobility
from channel.channel import Channel
from wifi.wifi import WiFi, Config as WifiConfig
from wifi.sta import WiFiSTA
from nru.nru import Gnb, Config_NR
from nru.ue import NrUE
from generic.generic_device import Config_Generic, GenericWirelessDevice, SpectrumSnapshot


def rand_pos_near(center: Pos, radius: float) -> Pos:
    import math
    angle = random.uniform(0, 2 * math.pi)
    r = radius * math.sqrt(random.random())
    return (center[0] + r * math.cos(angle), center[1] + r * math.sin(angle))


@dataclass
class SnifferReport:
    name: str
    pos: Pos
    samples: int = 0
    busy_wideband_samples: int = 0
    busy_inband_samples: int = 0
    energy_sum_dbm_mw: float = 0.0  # accumulated in mW, converted to a mean dBm at the end
    energy_min_dbm: float = float("inf")
    energy_max_dbm: float = float("-inf")
    # tech label -> number of samples where at least one active tx of
    # that tech was visible to this sniffer
    tech_visible_samples: dict = field(default_factory=dict)


def _sniffer_process(env, dev: GenericWirelessDevice, report: SnifferReport,
                      sniff_interval_us: float, sim_duration_us: float):
    from common.common_phy import dbm_to_mw, mw_to_dbm
    while env.now < sim_duration_us:
        snap: SpectrumSnapshot = dev.sniff()
        report.samples += 1
        if snap.is_busy_wideband:
            report.busy_wideband_samples += 1
        if snap.is_busy_inband:
            report.busy_inband_samples += 1

        if snap.wideband_energy_dbm != float("-inf"):
            report.energy_sum_dbm_mw += dbm_to_mw(snap.wideband_energy_dbm)
            report.energy_min_dbm = min(report.energy_min_dbm, snap.wideband_energy_dbm)
            report.energy_max_dbm = max(report.energy_max_dbm, snap.wideband_energy_dbm)

        seen_techs = {v.tech for v in snap.visible_txs}
        for tech in seen_techs:
            report.tech_visible_samples[tech] = report.tech_visible_samples.get(tech, 0) + 1

        yield env.timeout(sniff_interval_us)


def run_simulation_spectrum(
        number_of_stations: int,
        number_of_gnb: int,
        number_of_sniffers: int,
        seed: int,
        simulation_time: float,
        wifi_config: WifiConfig,
        configNr: Config_NR,
        sniffer_config: Config_Generic,
        area_w: float = 50.0,
        area_h: float = 50.0,
        wifi_stas_per_ap: int = 1,
        nr_ues_per_gnb: int = 1,
        sta_radius: float = 10.0,
        ue_radius: float = 15.0,
        sniffer_positions: Optional[List[Pos]] = None,
        sniff_interval_us: float = 50.0,
):
    random.seed(seed)
    environment = simpy.Environment()

    # wifi.WiFi.generate_new_back_off_slots() indexes channel.backoffs
    # [drawn_slot][n_of_stations] unconditionally (a diagnostic
    # histogram of drawn backoff values, same as singleRun.py's own
    # topology builder pre-populates) - has to exist for every possible
    # drawn slot up to cw_max before any WiFi AP starts, or the first
    # backoff draw raises a KeyError.
    backoffs = {key: {number_of_stations: 0} for key in range(wifi_config.cw_max + 1)}

    channel = Channel(
        simpy.PriorityResource(environment, capacity=1),
        simpy.Resource(environment, capacity=1),
        number_of_stations,
        number_of_gnb,
        backoffs,
        {},  # airtime_data
        {},  # airtime_control
        {},  # airtime_data_NR
        {},  # airtime_control_NR
    )

    # --- WiFi topology (same pattern as simulation.py's AP/STA loop) ---
    wifi_aps = []
    for i in range(1, number_of_stations + 1):
        ap_name = f"AP {i}"
        ap_pos = rand_pos(area_w, area_h)
        stas_for_ap = []
        for k in range(1, wifi_stas_per_ap + 1):
            sta = WiFiSTA(name=f"STA {i}-{k}", pos=rand_pos_near(ap_pos, radius=sta_radius), ap_name=ap_name)
            stas_for_ap.append(sta)
        ap = WiFi(environment, ap_name, channel, ap_pos, stas_for_ap, wifi_config)
        wifi_aps.append(ap)

    # --- NR-U topology (same pattern as simulation.py's gNB/UE loop) ---
    gnbs = []
    for i in range(1, number_of_gnb + 1):
        gnb_name = f"Gnb {i}"
        gnb_pos = rand_pos(area_w, area_h)
        ues_for_gnb = []
        for k in range(1, nr_ues_per_gnb + 1):
            ue = NrUE(name=f"UE {i}-{k}", pos=rand_pos_near(gnb_pos, radius=ue_radius), gnb_name=gnb_name)
            ues_for_gnb.append(ue)
        g = Gnb(environment, gnb_name, channel, gnb_pos, ues_for_gnb, configNr)
        gnbs.append(g)

    # --- Spectrum-analyzer sniffers (Step 7.A's GenericWirelessDevice) ---
    sim_duration_us = simulation_time * 1_000_000
    sniffers: List[GenericWirelessDevice] = []
    reports: List[SnifferReport] = []
    for i in range(1, number_of_sniffers + 1):
        name = f"SNIFFER {i}"
        if sniffer_positions is not None and i - 1 < len(sniffer_positions):
            pos = sniffer_positions[i - 1]
        else:
            pos = rand_pos(area_w, area_h)
        dev = GenericWirelessDevice(environment, name, channel, sniffer_config, pos)
        sniffers.append(dev)
        report = SnifferReport(name=name, pos=pos)
        reports.append(report)
        environment.process(_sniffer_process(environment, dev, report, sniff_interval_us, sim_duration_us))

    print("=== Spectrum-Analyzer Scenario Topology ===")
    print("Wi-Fi:")
    for ap in wifi_aps:
        print(" ", ap.name, ap.pos)
        for sta in ap.sta_list:
            print("   ", sta.name, sta.pos, "d=", dist(ap.pos, sta.pos))
    print("NR-U:")
    for g in gnbs:
        print(" ", g.name, g.pos)
        for ue in g.ue_list:
            print("   ", ue.name, ue.pos, "d=", dist(g.pos, ue.pos))
    print("Sniffers:")
    for dev in sniffers:
        print(" ", dev.name, dev.current_pos())

    environment.run(until=sim_duration_us)

    print("\n=== Spectrum-Analyzer Results ===")
    from common.common_phy import mw_to_dbm
    for report in reports:
        wb_frac = report.busy_wideband_samples / report.samples if report.samples else 0.0
        ib_frac = report.busy_inband_samples / report.samples if report.samples else 0.0
        mean_dbm = (
            mw_to_dbm(report.energy_sum_dbm_mw / report.samples)
            if report.samples and report.energy_sum_dbm_mw > 0 else float("-inf")
        )
        print(f"{report.name} @ {report.pos}: samples={report.samples} "
              f"wideband_busy_fraction={wb_frac:.4f} inband_busy_fraction={ib_frac:.4f} "
              f"mean_energy_dbm={mean_dbm:.1f} "
              f"(min={report.energy_min_dbm if report.energy_min_dbm != float('inf') else float('nan'):.1f} "
              f"max={report.energy_max_dbm if report.energy_max_dbm != float('-inf') else float('nan'):.1f})")
        if report.tech_visible_samples:
            print("  per-tech duty cycle (fraction of samples where at least one tx of that tech was visible):")
            for tech, cnt in sorted(report.tech_visible_samples.items()):
                print(f"    {tech}: {cnt / report.samples:.4f}")
        else:
            print("  (no transmissions of any technology were ever visible to this sniffer)")

    return reports
# Rashed-Step 7.B-08-05-2026-end
