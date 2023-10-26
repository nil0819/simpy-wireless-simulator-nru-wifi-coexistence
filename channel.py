from common import *
from wifi import *
from nru import *


@dataclass
class Channel:
    # lock for the stations with the longest frame to transmit
    tx_queue: simpy.PreemptiveResource
    # channel lock (locked when there is ongoing transmission)
    tx_lock: simpy.Resource
    n_of_stations: int  # number of transmitting stations in the channel
    n_of_eNB: int
    backoffs: Dict[int, Dict[int, int]]
    airtime_data: Dict[str, int]
    airtime_control: Dict[str, int]
    airtime_data_NR: Dict[str, int]
    airtime_control_NR: Dict[str, int]
    # transmitting stations in the channel
    tx_list: List[WiFi] = field(default_factory=list)
    back_off_list: List[WiFi] = field(default_factory=list)  # stations in backoff phase
    # transmitting stations in the channel
    tx_list_NR: List[Gnb] = field(default_factory=list)
    back_off_list_NR: List[Gnb] = field(default_factory=list)  # stations in backoff phase
    # problem list of station objects, what if we have 2 different station objects???

    failed_transmissions: int = 0  # total failed transmissions
    succeeded_transmissions: int = 0  # total succeeded transmissions
    bytes_sent: int = 0  # total bytes sent
    failed_transmissions_NR: int = 0  # total failed transmissions
    succeeded_transmissions_NR: int = 0  # total succeeded transmissions
    
    # NR-U gnb victim attack probability
    nru_transmission_probability: int = 100

    # channel access delay calculation
    nru_channel_access_delays_log: Dict[int, int] = field(default_factory=dict)

    #NR-U minislot specific busy count log
    nru_minislot_busy_log: Dict[int, int] = field(default_factory=dict)
    minislot_log_start_time:int = 0
    

    