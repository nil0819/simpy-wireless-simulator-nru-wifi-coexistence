from common.common import *
# from wifi.wifi import *
# from nru.nru import *

# Rashed-Step 3.B-01-12-2026-start
from dataclasses import dataclass
import simpy
import math
from common.common_phy import rx_power_dbm, dbm_to_mw, mw_to_dbm, Pos
from typing import Optional, List
from typing import Any, List
# Rashed-Step 3.B-01-12-2026-end


# Rashed-Step 3.B-01-12-2026-start
@dataclass
class ActiveTx:
    tx_id: str
    tx_pos: Pos
    # Rashed-Step 3.F-01-13-2026-start
    tx_start: int
    # Rashed-Step 3.F-01-13-2026-end
    tx_power_dbm: float
    f_hz: float
    pl_exp: float
    t_end: int
    tech: str  # "WiFi" or "NRU"
# Rashed-Step 3.B-01-12-2026-end


@dataclass()
class Channel:
    # lock for the stations with the longest frame to transmit
    tx_queue: simpy.PreemptiveResource
    # channel lock (locked when there is ongoing transmission)
    tx_lock: simpy.Resource
    n_of_stations: int  # number of transmitting stations in the channel
    n_of_gNB: int
    backoffs: Dict[int, Dict[int, int]]
    airtime_data: Dict[str, int]
    airtime_control: Dict[str, int]
    airtime_data_NR: Dict[str, int]
    airtime_control_NR: Dict[str, int]
    # transmitting stations in the channel
    tx_list: List[Any] = field(default_factory=list)
    back_off_list: List[Any] = field(
        default_factory=list)  # stations in backoff phase
    # transmitting stations in the channel
    tx_list_NR: List[Any] = field(default_factory=list)
    back_off_list_NR: List[Any] = field(
        default_factory=list)  # stations in backoff phase
    # problem list of station objects, what if we 2 differenet station objects???

    failed_transmissions: int = 0  # total failed transmissions
    succeeded_transmissions: int = 0  # total succeeded transmissions
    bytes_sent: int = 0  # total bytes sent
    failed_transmissions_NR: int = 0  # total failed transmissions
    succeeded_transmissions_NR: int = 0  # total succeeded transmissions


    # Rashed-Step 3.B-01-12-2026-start
    active_txs: List[ActiveTx] = field(default_factory=list)
    state_changed: simpy.Event = field(init=False)
    env: simpy.Environment = field(init=False)
    # Rashed-Step 3.B-01-12-2026-end

     # Rashed-Step 3.B-01-12-2026-start
    def __post_init__(self):
            self.env = self.tx_lock._env
            self.state_changed = self.env.event()


    def _pulse_state_changed(self):
        # Rashed-Step 3.F-12-26-2025-start
        #print(self.env.now, "STATE_CHANGED PULSE", len(self.active_txs))
        # Rashed-Step 3.F-12-26-2025-end
        
        if not self.state_changed.triggered:
            self.state_changed.succeed()
        self.state_changed = self.env.event()


    def register_tx(self, tx: ActiveTx):
         self.active_txs.append(tx)
         self._pulse_state_changed()

    # Rashed-Step 3.F-01-13-2026-start
    def unregister_tx(self, tx: ActiveTx):
         if tx in self.active_txs:
              self.active_txs.remove(tx)

              dur = max(0, tx.t_end - tx.tx_start)

              if tx.tech == "WiFi":
                   self.airtime_data[tx.tx_id] = self.airtime_data.get(tx.tx_id, 0) + dur

              elif tx.tech == "NRU":
                    self.airtime_data_NR[tx.tx_id] = self.airtime_data_NR.get(tx.tx_id, 0) + dur
              self._pulse_state_changed()
        #  if tx in self.active_txs:
        #      self.active_txs.remove(tx)
        #      self._pulse_state_changed()

    # Rashed-Step 3.F-01-13-2026-end

    # Rashed-Step 3.B-01-12-2026-end


    # Rashed-Step 3.C-01-12-2026-start
    def sensed_energy_dbm(self, sense_pos: Pos, exclude_tx_id: Optional[str] = None) -> float:
        total_mw = 0.0
        now = self.env.now

        expired = [t for t in self.active_txs if t.t_end <= now]

        # Rashed-Step 3.F-01-13-2026-start
        # for t in expired:
        #     self.active_txs.remove(t)
        self.active_txs = [t for t in self.active_txs if t.t_end > now]

        # Rashed-Step 3.F-01-13-2026-end
        
        for tx in self.active_txs:
             if exclude_tx_id is not None and tx.tx_id == exclude_tx_id:
                  continue
             d = dist(tx.tx_pos, sense_pos)
             pr = rx_power_dbm(tx.tx_power_dbm, d, tx.f_hz, n = tx.pl_exp)
             total_mw += dbm_to_mw(pr)

        if total_mw == 0.0:
            return -math.inf
        
        return mw_to_dbm(total_mw)
    

    def is_busy(self, sense_pos: Pos, ed_threshold_dbm: float, exclude_tx_id: Optional[str] = None) -> bool:
        return self.sensed_energy_dbm(sense_pos, exclude_tx_id) >= ed_threshold_dbm
            
        
    # Rashed-Step 3.C-01-12-2026-end
