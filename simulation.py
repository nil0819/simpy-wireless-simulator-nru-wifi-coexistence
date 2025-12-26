from common import *
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
        nr_ues_per_gnb: int = 1
        # Rashed-Step 1.D_1-12-26-2025-end
):
    random.seed(seed)
    environment = simpy.Environment()
    channel = Channel(
        simpy.PreemptiveResource(environment, capacity=1),
        simpy.Resource(environment, capacity=1),
        number_of_stations,
        number_of_gnb,
        backoffs,
        airtime_data,
        airtime_control,
        airtime_data_NR,
        airtime_control_NR
    )

    

    # Rashed-Step 1.D_2-12-26-2025-start
    wifi_aps = []
    wifi_stas = []

    for i in range(1, number_of_stations + 1):
        ap_name = f"AP {i}"
        ap_pos = rand_pos(area_w, area_h)

        stas_for_ap = []
        for k in range(1, wifi_stas_per_ap + 1):
            sta = WiFiSTA(
                name=f"STA {i}-{k}",
                pos=rand_pos_near(ap_pos, radius=10.0),
                ap_name=ap_name
            )
            stas_for_ap.append(sta)
            wifi_stas.append(sta)
    ap = WiFi(
        environment,
        ap_name,
        channel,
        ap_pos,
        stas_for_ap,
        config
    )
    wifi_aps.append(ap)
    # Rashed-Step 1.D_2-12-26-2025-end

    # Rashed-Step 1.D_3-12-26-2025-start
    gnbs = []
    ues = []
    for i in range(1, number_of_gnb + 1):
        gnb_name = f"Gnb {i}"
        gnb_pos = rand_pos(area_w, area_h)

        ues_for_gnb = []
        for k in range(1, nr_ues_per_gnb + 1):
            ue = NrUE(
                name=f"UE {i}-{k}",
                pos=rand_pos_near(gnb_pos, radius=15.0),
                gnb_name=gnb_name
            )
            ues_for_gnb.append(ue)
            ues.append(ue)
    g = Gnb(
        environment,
        gnb_name,
        channel,
        gnb_pos,
        ues_for_gnb,
        configNr
    )
    gnbs.append(g)
    # Rashed-Step 1.D_3-12-26-2025-end

    # Rashed-Step 1.E-12-26-2025-start
    print("=== Wi-Fi Topology ===")
    for ap in wifi_aps:
        print(ap.name, ap.pos)
        for sta in ap.sta_list:
            print("  ", sta.name, sta.pos, "d=", dist(ap.pos, sta.pos))

    print("=== NR-U Topology ===")
    for gnb in gnbs:
        print(gnb.name, gnb.pos)
        for ue in gnb.ue_list:
            print("  ", ue.name, ue.pos, "d=", dist(gnb.pos, ue.pos))
    # Rashed-Step 1.E-12-26-2025-end




    # is_wifi_rogue = 0 if rogue_wifi else 1

    # print(is_wifi_rogue)

    if is_rogue_wifi:
        print(is_rogue_wifi)
        print("Rogue WiFi")
        config = ConfigRoguesWiFi()
    else:
        print(is_rogue_wifi)
        print("Benign WiFi")
        config = Config()

    config_nr = Config_NR()
    
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
        
        

    # environment.run(until=simulation_time * 1000000) 10^6 milisekundy
    environment.run(until=simulation_time * 1000000)

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

    for i in range(1, number_of_stations + 1):
        channel_occupancy_time += channel.airtime_data["Station {}".format(i)] + channel.airtime_control[
            "Station {}".format(i)]
        channel_efficiency += channel.airtime_data["Station {}".format(i)]

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

    fairness = (normalized_channel_occupancy_time_all**2) / (2 *
                                                             (normalized_channel_occupancy_time**2 + normalized_channel_occupancy_time_NR**2))

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
        


