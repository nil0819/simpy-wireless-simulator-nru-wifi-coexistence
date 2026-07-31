from common.common import *
# from wifi.wifi import *
# from nru.nru import *

# Rashed-Step 3.B-01-12-2026-start
from dataclasses import dataclass
import simpy
import math
from common.common_phy import rx_power_dbm, dbm_to_mw, mw_to_dbm, Pos, sample_shadow_db, thermal_noise_dbm
from typing import Optional, List
from typing import Any, List, Tuple
# Rashed-Step 3.B-01-12-2026-end


# Rashed-Step 3.B-01-12-2026-start
@dataclass
class ActiveTx:
    tx_id: str
    tx_pos: Pos
    # Rashed-Step 3.F-01-13-2026-start
    tx_start: int
    # Rashed-Step 3.F-01-13-2026-end
    # Rashed-Step 4.B_1-01-20-2026-start
    rx_pos: Pos 
    # Rashed-Step 4.B_1-01-20-2026-end
    tx_power_dbm: float
    f_hz: float
    pl_exp: float
    t_end: int
    tech: str  # "WiFi" or "NRU"
    # Rashed-Step 5.C-02-06-2026-start
    # Receiver-side noise params for this link, used to derive the SINR
    # noise floor (see common_phy.thermal_noise_dbm). Defaults (20 MHz,
    # 7 dB NF -> ~-94 dBm) match the old hardcoded constant, so any code
    # constructing ActiveTx without passing these (e.g. the standalone
    # test/*.py files) is unaffected.
    bandwidth_mhz: float = 20.0
    noise_figure_db: float = 7.0
    # Rashed-Step 5.C-02-06-2026-end
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

    # Rashed-Step 5.B-02-06-2026-start
    # 0.0 = shadowing disabled (default - deterministic path loss only,
    # matches pre-Step-5.B behavior bit-for-bit). Typical indoor log-normal
    # shadowing sigma is ~4-8 dB.
    shadowing_sigma_db: float = 0.0
    # One stable shadow draw per (transmitter, receiver position) pair,
    # cached for the life of the run - "once per link", not re-rolled every
    # transmission. Keyed by rx_pos rather than a receiver id since that's
    # what's already available everywhere shadow_db() is called from.
    shadow_cache: Dict[Tuple[str, Pos], float] = field(default_factory=dict)
    # Rashed-Step 5.B-02-06-2026-end

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
    # Rashed-Step 5.1-02-06-2026-start
    # BUGFIX: this was one of TWO places adding to airtime_data/
    # airtime_data_NR on every successful transmission - wifi.py's
    # sent_completed(), nru.py's send_transmission() post-block, and
    # attacker/roguewificad.py's sent_completed() each did it a second
    # time (leftover from before this method existed), so every success
    # was counted twice and occupancy/efficiency were ~2x inflated (could
    # even exceed 1.0 for a single node, which is physically impossible).
    # This is now the single source of truth: success is passed in and
    # airtime is only recorded when the transmission actually succeeded.
    def unregister_tx(self, tx: ActiveTx, success: bool = True):
    # Rashed-Step 5.1-02-06-2026-end
         if tx in self.active_txs:
              self.active_txs.remove(tx)

              dur = max(0, tx.t_end - tx.tx_start)

              # Rashed-Step 5.1-02-06-2026-start
              if success:
                  if tx.tech == "WiFi":
                       self.airtime_data[tx.tx_id] = self.airtime_data.get(tx.tx_id, 0) + dur

                  elif tx.tech == "NRU":
                        self.airtime_data_NR[tx.tx_id] = self.airtime_data_NR.get(tx.tx_id, 0) + dur
              # Rashed-Step 5.1-02-06-2026-end
              self._pulse_state_changed()
        #  if tx in self.active_txs:
        #      self.active_txs.remove(tx)
        #      self._pulse_state_changed()

    # Rashed-Step 3.F-01-13-2026-end

    # Rashed-Step 3.B-01-12-2026-end


    # Rashed-Step 5.B-02-06-2026-start
    def shadow_db(self, tx_id: str, rx_pos: Pos) -> float:
        """
        Stable log-normal shadow-fading value for the (tx_id, rx_pos) link,
        sampled once and cached for the rest of the run. Returns 0.0
        immediately (no cache write, no RNG draw) when shadowing_sigma_db
        <= 0, so disabling shadowing is exactly equivalent to the old
        deterministic-only path loss.
        """
        if self.shadowing_sigma_db <= 0.0:
            return 0.0
        key = (tx_id, rx_pos)
        if key not in self.shadow_cache:
            self.shadow_cache[key] = sample_shadow_db(self.shadowing_sigma_db)
        return self.shadow_cache[key]
    # Rashed-Step 5.B-02-06-2026-end

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
             # Rashed-Step 5.B-02-06-2026-start
             shadow = self.shadow_db(tx.tx_id, sense_pos)
             pr = rx_power_dbm(tx.tx_power_dbm, d, tx.f_hz, n = tx.pl_exp, shadow_db=shadow)
             # Rashed-Step 5.B-02-06-2026-end
             total_mw += dbm_to_mw(pr)

        if total_mw == 0.0:
            return -math.inf
        
        return mw_to_dbm(total_mw)
    

    def is_busy(self, sense_pos: Pos, ed_threshold_dbm: float, exclude_tx_id: Optional[str] = None) -> bool:
        return self.sensed_energy_dbm(sense_pos, exclude_tx_id) >= ed_threshold_dbm
            
        
    # Rashed-Step 3.C-01-12-2026-end



    # Rashed-Step 4.C-01-20-2026-start

    def _rx_pwr_dbm(self, tx:ActiveTx, at_pos: Pos) -> float:
         d = dist(tx.tx_pos, at_pos)
         # Rashed-Step 5.B-02-06-2026-start
         shadow = self.shadow_db(tx.tx_id, at_pos)
         return rx_power_dbm(tx.tx_power_dbm, d, tx.f_hz, n=tx.pl_exp, shadow_db=shadow)
         # Rashed-Step 5.B-02-06-2026-end
    
    # Rashed-Step 5.C-02-06-2026-start
    # BUGFIX/upgrade: noise_dbm used to default to a hardcoded -94.0 dBm
    # constant regardless of bandwidth or receiver noise figure. Now
    # defaults to None, meaning "derive it from target's own
    # bandwidth_mhz/noise_figure_db via thermal_noise_dbm()" - callers can
    # still pass an explicit noise_dbm to override (e.g. for tests that
    # want a fixed noise value).
    def sinr_db(self, target: ActiveTx, noise_dbm: Optional[float] = None) -> float:
        """
        SINR at target.rx_pos considering only transmissions that overlap in time
        with [target.tx_start, target.t_end].
        """
        if noise_dbm is None:
            noise_dbm = thermal_noise_dbm(target.bandwidth_mhz, target.noise_figure_db)
        # Rashed-Step 5.C-02-06-2026-end
        s_dbm = self._rx_pwr_dbm(target, target.rx_pos)
        s_mw = dbm_to_mw(s_dbm)

        i_mw = 0.0

        for other in self.active_txs:
            if other.tx_id == target.tx_id:
                continue
              
            if not (other.tx_start < target.t_end and other.t_end > target.tx_start):
                continue
              
            i_dbm = self._rx_pwr_dbm(other, target.rx_pos)
            i_mw += dbm_to_mw(i_dbm)

        n_mw = dbm_to_mw(noise_dbm)

        # guard against weird numerical issues

        denom = i_mw + n_mw

        if denom == 0.0:
             return float('inf')
        
        sinr_linear = s_mw / denom

        return 10.0 * math.log10(sinr_linear)
    
        

        
         




    # Rashed-Step 4.C-01-20-2026-end
