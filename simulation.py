from common.common import *
from nru.ue import NrUE
from wifi.wifi import *
from nru.nru import *
from channel.channel import *
from attacker.roguewificad import *
# from roguewifiselfbackoff import *
# from roguewifijammer import *
# Rashed-Step 1.D_2-12-26-2025-start
from wifi.sta import *
# Rashed-Step 1.D_2-12-26-2025-end
# Rashed-Step 5.A-02-06-2026-start
from typing import Optional
# Rashed-Step 5.A-02-06-2026-end
# Rashed-Step 5.F-02-06-2026-start
from common.common_phy import check_eirp_compliance
# Rashed-Step 5.F-02-06-2026-end
# Rashed-Step 5.G-02-06-2026-start
from common.common_phy import WaypointMobility
# Rashed-Step 5.G-02-06-2026-end


# Rashed-Step 1.D_2-12-26-2025-start
def rand_pos_near(center:Pos, radius:float) -> Pos:
    angle = random.uniform(0, 2*math.pi)
    r = radius * math.sqrt(random.random())
    return (center[0] + r*math.cos(angle), center[1] + r*math.sin(angle))
# Rashed-Step 1.D_2-12-26-2025-end



def run_simulation(
        number_of_stations: int,
        number_of_gnb: int,
        seed: int,
        simulation_time: int,
        config: Config,
        configNr: Config_NR,
        backoffs: Dict[int, Dict[int, int]],
        airtime_data: Dict[str, int],
        airtime_control: Dict[str, int],
        airtime_data_NR: Dict[str, int],
        airtime_control_NR: Dict[str, int],
        is_rogue_wifi: bool,
        # Rashed-Step 1.D_1-12-26-2025-start
        area_w: float = 50.0,
        area_h: float = 50.0,
        wifi_stas_per_ap: int = 1,
        nr_ues_per_gnb: int = 1,
        # Rashed-Step 1.D_1-12-26-2025-end
        # Rashed-Step 5.A-02-06-2026-start
        # Explicit device placement. Matched by order to AP 1, AP 2, ... /
        # Gnb 1, Gnb 2, ... ; any AP/gNB beyond len(ap_positions) /
        # len(gnb_positions) still falls back to rand_pos(area_w, area_h).
        ap_positions: Optional[List[Pos]] = None,
        gnb_positions: Optional[List[Pos]] = None,
        sta_radius: float = 10.0,
        ue_radius: float = 15.0,
        # Rashed-Step 5.A-02-06-2026-end
        # Rashed-Step 5.B-02-06-2026-start
        # 0.0 = shadowing disabled (deterministic path loss only, same as
        # before Step 5.B). Typical indoor log-normal shadowing sigma is
        # ~4-8 dB.
        shadowing_sigma_db: float = 0.0,
        # Rashed-Step 5.B-02-06-2026-end
        # Rashed-Step 5.G-02-06-2026-start
        # 0.0 (default, for every one of these) = that node type never
        # moves - common_phy.WaypointMobility is only constructed for a
        # node type when its speed is > 0, so a run with all four at 0.0
        # is byte-identical to every pre-5.G run (no WaypointMobility
        # objects exist at all, current_pos() just returns the static
        # pos it always did). Mobile nodes roam within the same
        # [0,area_w] x [0,area_h] box used for random initial placement.
        ap_mobility_speed_mps: float = 0.0,
        gnb_mobility_speed_mps: float = 0.0,
        sta_mobility_speed_mps: float = 0.0,
        ue_mobility_speed_mps: float = 0.0,
        mobility_pause_s: float = 0.0,
        # Rashed-Step 5.G-02-06-2026-end
        # Rashed-Step 8.B-08-06-2026-start
        # None (default, for both) = TrafficConfig(mode="saturated"),
        # byte-identical to every pre-Step-8.B run - see
        # wifi.WiFi/nru.Gnb's own traffic_config param docs.
        wifi_traffic_config: Optional[TrafficConfig] = None,
        nru_traffic_config: Optional[TrafficConfig] = None,
        # Rashed-Step 8.B-08-06-2026-end
):
    random.seed(seed)
    environment = simpy.Environment()

    # Rashed-Step pre_5.D-02-06-2026-start
    # BUGFIX: is_rogue_wifi used to only be checked *after* the topology
    # loop had already built every AP as benign WiFi (the reassigned
    # `config` was never used to construct anything), so --rogue True never
    # actually spawned an attacker. Decide the WiFi config up front and use
    # it inside the AP-building loop below.
    if is_rogue_wifi:
        wifi_config = ConfigRoguesWiFi()
    else:
        wifi_config = config
    # Rashed-Step pre_5.D-02-06-2026-end
    # Rashed-Step 3.F-01-13-2026-start
    # channel = Channel(
    #     simpy.PreemptiveResource(environment, capacity=1),
    #     simpy.Resource(environment, capacity=1),
    #     number_of_stations,
    #     number_of_gnb,
    #     backoffs,
    #     airtime_data,
    #     airtime_control,
    #     airtime_data_NR,
    #     airtime_control_NR
    # )
    channel = Channel(
        simpy.PriorityResource(environment, capacity=1),  # <-- change this
        simpy.Resource(environment, capacity=1),
        number_of_stations,
        number_of_gnb,
        backoffs,
        airtime_data,
        airtime_control,
        airtime_data_NR,
        airtime_control_NR,
        # Rashed-Step 5.B-02-06-2026-start
        shadowing_sigma_db=shadowing_sigma_db
        # Rashed-Step 5.B-02-06-2026-end
    )

    # Rashed-Step 3.F-01-13-2026-end

    

    # Rashed-Step 1.D_2-12-26-2025-start
    # Rashed-Step pre_5.A-02-06-2026-start
    # BUGFIX: ap = WiFi(...) / wifi_aps.append(ap) used to sit outside this
    # for-loop (same indent as the loop itself), so only the AP built on the
    # loop's LAST iteration was ever instantiated regardless of
    # number_of_stations. Moved inside the loop so every AP (and its STA
    # list) actually gets created.
    # Rashed-Step pre_5.A-02-06-2026-end
    wifi_aps = []
    wifi_stas = []

    for i in range(1, number_of_stations + 1):
        ap_name = f"AP {i}"
        # Rashed-Step 5.A-02-06-2026-start
        if ap_positions is not None and i - 1 < len(ap_positions):
            ap_pos = ap_positions[i - 1]
        else:
            ap_pos = rand_pos(area_w, area_h)
        # Rashed-Step 5.A-02-06-2026-end

        # Rashed-Step 5.G-02-06-2026-start
        ap_mobility = None
        if ap_mobility_speed_mps > 0.0:
            ap_mobility = WaypointMobility(environment, area_w, area_h,
                                            ap_mobility_speed_mps, mobility_pause_s, ap_pos)
        # Rashed-Step 5.G-02-06-2026-end

        stas_for_ap = []
        for k in range(1, wifi_stas_per_ap + 1):
            sta_pos = rand_pos_near(ap_pos, radius=sta_radius)
            # Rashed-Step 5.G-02-06-2026-start
            sta_mobility = None
            if sta_mobility_speed_mps > 0.0:
                sta_mobility = WaypointMobility(environment, area_w, area_h,
                                                 sta_mobility_speed_mps, mobility_pause_s, sta_pos)
            # Rashed-Step 5.G-02-06-2026-end
            sta = WiFiSTA(
                name=f"STA {i}-{k}",
                # Rashed-Step 5.A-02-06-2026-start
                pos=sta_pos,
                # Rashed-Step 5.A-02-06-2026-end
                ap_name=ap_name,
                # Rashed-Step 5.G-02-06-2026-start
                mobility=sta_mobility
                # Rashed-Step 5.G-02-06-2026-end
            )
            stas_for_ap.append(sta)
            wifi_stas.append(sta)

        # Rashed-Step pre_5.A-02-06-2026-start
        # Rashed-Step pre_5.D-02-06-2026-start
        if is_rogue_wifi:
            # Rashed-Step 5.G-02-06-2026-start
            # NOT given mobility - attack-path changes are out of scope
            # per current instructions (roguewificad.py is left alone
            # elsewhere in Step 5 for the same reason).
            # Rashed-Step 5.G-02-06-2026-end
            ap = RogueWiFiCAD(
                environment,
                ap_name,
                channel,
                ap_pos,
                wifi_config
            )
        else:
            ap = WiFi(
                environment,
                ap_name,
                channel,
                ap_pos,
                stas_for_ap,
                wifi_config,
                # Rashed-Step 5.G-02-06-2026-start
                mobility=ap_mobility,
                # Rashed-Step 5.G-02-06-2026-end
                # Rashed-Step 8.B-08-06-2026-start
                traffic_config=wifi_traffic_config
                # Rashed-Step 8.B-08-06-2026-end
            )
        # Rashed-Step pre_5.D-02-06-2026-end
        wifi_aps.append(ap)
        # Rashed-Step pre_5.A-02-06-2026-end
    # Rashed-Step 1.D_2-12-26-2025-end

    # Rashed-Step 1.D_3-12-26-2025-start
    # Rashed-Step pre_5.A-02-06-2026-start
    # BUGFIX: same issue as above for gNBs - g = Gnb(...) / gnbs.append(g)
    # moved inside the loop.
    # Rashed-Step pre_5.A-02-06-2026-end
    gnbs = []
    ues = []
    for i in range(1, number_of_gnb + 1):
        gnb_name = f"Gnb {i}"
        # Rashed-Step 5.A-02-06-2026-start
        if gnb_positions is not None and i - 1 < len(gnb_positions):
            gnb_pos = gnb_positions[i - 1]
        else:
            gnb_pos = rand_pos(area_w, area_h)
        # Rashed-Step 5.A-02-06-2026-end

        # Rashed-Step 5.G-02-06-2026-start
        gnb_mobility = None
        if gnb_mobility_speed_mps > 0.0:
            gnb_mobility = WaypointMobility(environment, area_w, area_h,
                                             gnb_mobility_speed_mps, mobility_pause_s, gnb_pos)
        # Rashed-Step 5.G-02-06-2026-end

        ues_for_gnb = []
        for k in range(1, nr_ues_per_gnb + 1):
            ue_pos = rand_pos_near(gnb_pos, radius=ue_radius)
            # Rashed-Step 5.G-02-06-2026-start
            ue_mobility = None
            if ue_mobility_speed_mps > 0.0:
                ue_mobility = WaypointMobility(environment, area_w, area_h,
                                                ue_mobility_speed_mps, mobility_pause_s, ue_pos)
            # Rashed-Step 5.G-02-06-2026-end
            ue = NrUE(
                name=f"UE {i}-{k}",
                # Rashed-Step 5.A-02-06-2026-start
                pos=ue_pos,
                # Rashed-Step 5.A-02-06-2026-end
                gnb_name=gnb_name,
                # Rashed-Step 5.G-02-06-2026-start
                mobility=ue_mobility
                # Rashed-Step 5.G-02-06-2026-end
            )
            ues_for_gnb.append(ue)
            ues.append(ue)

        # Rashed-Step pre_5.A-02-06-2026-start
        g = Gnb(
            environment,
            gnb_name,
            channel,
            gnb_pos,
            ues_for_gnb,
            configNr,
            # Rashed-Step 5.G-02-06-2026-start
            mobility=gnb_mobility,
            # Rashed-Step 5.G-02-06-2026-end
            # Rashed-Step 8.B-08-06-2026-start
            traffic_config=nru_traffic_config
            # Rashed-Step 8.B-08-06-2026-end
        )
        gnbs.append(g)
        # Rashed-Step pre_5.A-02-06-2026-end
    # Rashed-Step 1.D_3-12-26-2025-end

    # Rashed-Step 1.E-12-26-2025-start
    print("=== Wi-Fi Topology ===")
    for ap in wifi_aps:
        print(ap.name, ap.pos)
        # Rashed-Step pre_5.D-02-06-2026-start
        # BUGFIX: RogueWiFiCAD has no sta_list (an attacker has no
        # legitimate associated STA), so this crashed with AttributeError
        # whenever --rogue True was used. Guard with getattr.
        for sta in getattr(ap, "sta_list", []):
            print("  ", sta.name, sta.pos, "d=", dist(ap.pos, sta.pos))
        # Rashed-Step pre_5.D-02-06-2026-end

    print("=== NR-U Topology ===")
    for gnb in gnbs:
        print(gnb.name, gnb.pos)
        for ue in gnb.ue_list:
            print("  ", ue.name, ue.pos, "d=", dist(gnb.pos, ue.pos))
    # Rashed-Step 1.E-12-26-2025-end

    # Rashed-Step pre_5.D-02-06-2026-start
    # BUGFIX: this used to reassign `config` to a fresh ConfigRoguesWiFi()/
    # Config() *after* the AP loop had already built every AP with the
    # original `config` argument, so it never affected which class/config
    # got instantiated. AP construction above now uses wifi_config (decided
    # before the loop); reuse it here for the reporting/log lines instead of
    # building a second, disconnected config object.
    print(is_rogue_wifi)
    print("Rogue WiFi" if is_rogue_wifi else "Benign WiFi")
    config = wifi_config
    # Rashed-Step pre_5.D-02-06-2026-end

    # Rashed-Step 5.F-02-06-2026-start
    # Informational-only regulatory EIRP check (does not clamp/raise) -
    # see common_phy.check_eirp_compliance() for the U-NII band table and
    # the simplifications involved (tx_power_dbm treated as EIRP directly,
    # no separate antenna-gain field). Checked once per run against each
    # tech's configured frequency, not per-AP/gNB, since every WiFi AP
    # shares wifi_config and every gNB shares configNr in this CLI.
    if number_of_stations != 0:
        check_eirp_compliance("WiFi", wifi_config.tx_power_dbm, wifi_config.f_ghz)
    if number_of_gnb != 0:
        check_eirp_compliance("NR-U", configNr.tx_power_dbm, configNr.f_ghz)
    # Rashed-Step 5.F-02-06-2026-end

    # Rashed-Step 6.E-08-05-2026-start
    # BUGFIX: this used to be `config_nr = Config_NR()` - a fresh, always-
    # default Config_NR object, disconnected from `configNr` (the real
    # config actually used to build the Gnb objects below, populated from
    # CLI flags like --nru_cw_min/--nru_cw_max). It was only ever read for
    # the "CW_MIN=/CW_MAX=" diagnostic print further down, so that print
    # always showed 15/63 regardless of the real --nru_cw_min/--nru_cw_max
    # values passed in - misleading, though the real simulation logic
    # (which uses configNr throughout) was never affected. Found during
    # Step 6.D/6.E regression testing. Point the print at the real object.
    config_nr = configNr
    # Rashed-Step 6.E-08-05-2026-end

    # Rashed-Step 1.E-12-26-2025-start
    # for i in range(1, number_of_stations + 1):
    #     if is_rogue_wifi:
    #         print("Rogue WiFi")
    #         #RogueWiFiCAD(environment, "Station {}".format(i), channel, config)
    #         #RogueWiFiSelfBackoff(environment, "Station {}".format(i), channel, config)
    #         #RogueWiFiJammer(environment, "Station {}".format(i), channel, config)
    #     else:
    #         print("Benign WiFi")
    #         WiFi(environment, "Station {}".format(i), channel, config)
    # Rashed-Step 1.E-12-26-2025-end

        
    # Rashed-Step 1.E-12-26-2025-start
    # for i in range(1, number_of_gnb + 1):
    #     # Gnb(environment, "Gnb {}".format(i), channel, config_nr)
    #     Gnb(environment, "Gnb {}".format(i), channel, configNr)
    # Rashed-Step 1.E-12-26-2025-end

    # Rashed-Step 3.F-12-26-2025-start
    # print("APs: ", [ap.name for ap in wifi_aps])
    # print("GNBs: ", [g.name for g in gnbs])
    # Rashed-Step 3.F-12-26-2025-end

    # environment.run(until=simulation_time * 1000000) 10^6 milisekundy
    environment.run(until=simulation_time * 1000000)

    # Rashed-Step 6.E-08-05-2026-start
    # BUGFIX: this "WiFi airtime data:.../NRU airtime ctrl:" debug print
    # block used to sit BEFORE environment.run() (i.e. before the
    # simulation actually executed), so it always printed all-zero
    # airtime/succ/fail regardless of what really happened - misleading
    # debug output (channel.airtime_data etc. are only ever populated as
    # a side effect of the simulation running). Moved here, right after
    # environment.run(), so it reflects real post-simulation state.
    # Found during Step 6.D/6.E regression testing.
    print("WiFi airtime data:", sum(channel.airtime_data.values()))
    print("WiFi airtime ctrl:", sum(channel.airtime_control.values()))
    print("NRU airtime data:", sum(channel.airtime_data_NR.values()))
    print("NRU airtime ctrl:", sum(channel.airtime_control_NR.values()))
    print("succ WiFi:", channel.succeeded_transmissions, "fail WiFi:", channel.failed_transmissions)
    print("succ NRU:", channel.succeeded_transmissions_NR, "fail NRU:", channel.failed_transmissions_NR)
    # Rashed-Step 6.E-08-05-2026-end

    if number_of_stations != 0:
        if(channel.failed_transmissions + channel.succeeded_transmissions) != 0:
            p_coll = "{:.4f}".format(
                channel.failed_transmissions / (channel.failed_transmissions + channel.succeeded_transmissions))
        else:
            p_coll = 0
    else:
        p_coll = 0

    if number_of_gnb != 0:
        if (channel.failed_transmissions_NR + channel.succeeded_transmissions_NR) != 0:
            p_coll_NR = "{:.4f}".format(
                channel.failed_transmissions_NR / (
                        channel.failed_transmissions_NR + channel.succeeded_transmissions_NR))
        else:
            p_coll_NR = 0
    else:
        p_coll_NR = 0

    # DETAILED OUTPUTS:

    print(
        f"SEED = {seed} N_stations:={number_of_stations}  CW_MIN = {config.cw_min} CW_MAX = {config.cw_max}  PCOLL: {p_coll} THR:"
        f" {(channel.bytes_sent * 8) / (simulation_time * 100000)} "
        f"FAILED_TRANSMISSIONS: {channel.failed_transmissions}"
        f" SUCCEEDED_TRANSMISSION {channel.succeeded_transmissions}"
    )

    print('stats for GNB ------------------')

    print(
        f"SEED = {seed} N_gnbs={number_of_gnb} CW_MIN = {config_nr.cw_min} CW_MAX = {config_nr.cw_max}  PCOLL: {p_coll_NR} "
        f"FAILED_TRANSMISSIONS: {channel.failed_transmissions_NR}"
        f" SUCCEEDED_TRANSMISSION {channel.succeeded_transmissions_NR}"
    )

    print('airtimes summary: Wifi, NR ---- 1)data, 2)control')

    print(channel.airtime_data)
    print(channel.airtime_control)
    print(channel.airtime_data_NR)
    print(channel.airtime_control_NR)

    print("sumarizing airtime --------------")
    channel_occupancy_time = 0
    channel_efficiency = 0
    channel_occupancy_time_NR = 0
    channel_efficiency_NR = 0
    time = simulation_time * 1000000  # DEBUG

    # nodes = number_of_stations + number_of_gnb

    # Rashed-Step pre_5.B-02-06-2026-start
    # BUGFIX: this used to read channel.airtime_data["Station {i}"], but
    # WiFi.__init__ registers airtime under the AP's real name ("AP {i}"),
    # so these lookups always hit the initial 0 and WiFi occupancy/
    # efficiency printed as 0.0 even when frames succeeded. Fixed to use
    # the same naming scheme WiFi actually registers under.
    # Rashed-Step pre_5.B-02-06-2026-end
    for i in range(1, number_of_stations + 1):
        channel_occupancy_time += channel.airtime_data["AP {}".format(i)] + channel.airtime_control[
            "AP {}".format(i)]
        channel_efficiency += channel.airtime_data["AP {}".format(i)]

    for i in range(1, number_of_gnb + 1):
        channel_occupancy_time_NR += channel.airtime_data_NR["Gnb {}".format(i)] + channel.airtime_control_NR[
            "Gnb {}".format(i)]
        channel_efficiency_NR += channel.airtime_data_NR["Gnb {}".format(i)]

    normalized_channel_occupancy_time = channel_occupancy_time / time
    normalized_channel_efficiency = channel_efficiency / time
    print(f'Wifi occupancy (Normalized): {normalized_channel_occupancy_time}')
    print(f'Wifi efficieny (Normalized): {normalized_channel_efficiency}')

    normalized_channel_occupancy_time_NR = channel_occupancy_time_NR / time
    normalized_channel_efficiency_NR = channel_efficiency_NR / time
    print(
        f'Gnb occupancy (Normalized): {normalized_channel_occupancy_time_NR}')
    print(f'Gnb efficieny (Normalized): {normalized_channel_efficiency_NR}')

    normalized_channel_occupancy_time_all = (
        channel_occupancy_time + channel_occupancy_time_NR) / time
    normalized_channel_efficiency_all = (
        channel_efficiency + channel_efficiency_NR) / time
    print(f'All occupancy: {normalized_channel_occupancy_time_all}')
    print(f'All efficieny: {normalized_channel_efficiency_all}')

    print(
        f"SEED = {seed} N_stations:={number_of_stations} N_gNB:={number_of_gnb}  CW_MIN = {config.cw_min} CW_MAX = {config.cw_max} "
        f"WiFi pcol:={p_coll} WiFi cot:={normalized_channel_occupancy_time} WiFi eff:={normalized_channel_efficiency} "
        f"gNB pcol:={p_coll_NR} gNB cot:={normalized_channel_occupancy_time_NR} gNB eff:={normalized_channel_efficiency_NR} "
        f" all cot:={normalized_channel_occupancy_time_all} all eff:={normalized_channel_efficiency_all}"
    )
    print(
        f" Wifi succ: {channel.succeeded_transmissions} fail: {channel.failed_transmissions}")
    print(
        f" NR succ: {channel.succeeded_transmissions_NR} fail: {channel.failed_transmissions_NR}")

    # Rashed-Step 3.F-01-12-2026-start

    #fairness_den = 2 * (normalized_channel_occupancy_time_wifi**2 + normalized_channel_occupancy_time_nru**2)

    fairness = (normalized_channel_occupancy_time_all**2) / (2 * (normalized_channel_occupancy_time**2 + normalized_channel_occupancy_time_NR**2)) if (normalized_channel_occupancy_time or normalized_channel_occupancy_time_NR) else 0.0
    # Rashed-Step 3.F-01-12-2026-end
    print(f'fairness: {fairness}')
    joint = fairness * normalized_channel_occupancy_time_all
    print(f'joint: {joint}')

    write_header = True
    if os.path.isfile(output_csv):
        write_header = False
    with open(output_csv, mode='a', newline="") as result_file:
        result_adder = csv.writer(
            result_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)

        if write_header:
            result_adder.writerow(
                ['Seed,WiFi,Gnb,ChannelOccupancyWiFi,ChannelEfficiencyWiFi,PcolWifi,ChannelOccupancyNR,ChannelEfficiencyNR,PcolNR,ChannelOccupancyAll,ChannelEfficiencyAll'])

        result_adder.writerow(
            [seed, config.cw_max, fairness, number_of_stations, number_of_gnb, normalized_channel_occupancy_time, normalized_channel_efficiency,
             p_coll,
             normalized_channel_occupancy_time_NR, normalized_channel_efficiency_NR, p_coll_NR,
             normalized_channel_occupancy_time_all, normalized_channel_efficiency_all])
        


