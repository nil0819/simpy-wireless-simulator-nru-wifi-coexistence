from common.common import *
from Times import *
from common.common import Pos
# Rashed-Step 2.D_2-01-08-2026-start
from common.common_phy import rx_power_dbm, dist
# Rashed-Step 2.D_2-01-08-2026-end

# Rashed-Step 3.E_3-01-12-2026-start
from channel.channel import ActiveTx
# Rashed-Step 3.E_3-01-12-2026-end

# Rashed-Step 5.D-02-06-2026-start
from common.common_phy import mcs_sinr_threshold_db
from typing import Optional
# Rashed-Step 5.D-02-06-2026-end
# Rashed-Step 5.G-02-06-2026-start
from typing import Any
# Rashed-Step 5.G-02-06-2026-end


# Rashed-Step 5.D-02-06-2026-start
# NR-U never had an MCS/rate table before (unlike WiFi's Times.py MCS
# dict) - transmission duration here is still purely mcot-based, not
# MCS-dependent (a real per-MCS resource-block/throughput model is out of
# scope for this pass). This table only feeds the success/failure SINR
# gate, giving NR-U a similarly-shaped MCS index -> required-SINR curve to
# WiFi's for a fair side-by-side coexistence comparison. Same caveat as
# Times.WIFI_MCS_SINR_THRESHOLDS_DB: representative/typical values, not
# vendor- or 3GPP-conformance-tested figures.
NRU_MCS_SINR_THRESHOLDS_DB = {
    0: 5.0,
    1: 7.0,
    2: 9.0,
    3: 12.0,
    4: 15.0,
    5: 18.0,
    6: 21.0,
    7: 24.0,
}
# Rashed-Step 5.D-02-06-2026-end


@dataclass()
class Config_NR:
    deter_period: int = 16  # time used for waiting in prioritization period, microsec
    observation_slot_duration: int = 9  # observation slot in mikros
    # synchronization slot lenght in mikros
    synchronization_slot_duration: int = 1000
    max_sync_slot_desync: int = 1000
    min_sync_slot_desync: int = 0
    # channel access class related:
    M: int = 3  # amount of observation slots to wait after deter perion in prioritization period
    cw_min: int = 15
    cw_max: int = 63
    mcot: int = 6  # max ocupancy time

    # Rashed-Step 2.C_2-12-26-2025-start
    tx_power_dbm: float = 23.0 
    f_ghz: float = 5.18e9
    pl_exp : float = 3.0        #indoor-ish
    # Rashed-Step 2.C_2-12-26-2025-end

    # Rashed-Step 3.A-12-26-2025-start
    ed_threshold_dbm: float = -72.0   # example; tune later
    # Rashed-Step 3.A-12-26-2025-end

    # Rashed-Step 4.D_1-01-28-2026-start
    # Rashed-Step 5.D-02-06-2026-start
    # UPGRADE: this used to be a single flat threshold applied regardless
    # of mcs. Renamed to an explicit override: None (default) means "look
    # up the required SINR for `mcs` in NRU_MCS_SINR_THRESHOLDS_DB"; set it
    # to force a flat threshold instead (e.g. for comparison against the
    # old behavior).
    nru_sinr_thr_db_override: Optional[float] = None
    # mcs is new - NR-U had no MCS concept before Step 5.D. Only feeds the
    # SINR threshold lookup above; transmission duration stays mcot-based
    # regardless of mcs (see NRU_MCS_SINR_THRESHOLDS_DB note above).
    mcs: int = 4
    # Rashed-Step 5.D-02-06-2026-end
    # Rashed-Step 4.D_1-01-28-2026-end

    # Rashed-Step 5.C-02-06-2026-start
    # See wifi.Config's matching fields - same idea, drives the SINR noise
    # floor via common_phy.thermal_noise_dbm() instead of a hardcoded
    # -94.0 dBm constant. Defaults land back at ~-94 dBm.
    bandwidth_mhz: float = 20.0
    noise_figure_db: float = 7.0
    # Rashed-Step 5.C-02-06-2026-end



@dataclass()
class Transmission_NR:
    transmission_time: int
    gnb_name: str  # name of the owning it station
    col: str
    t_start: int  # generation time / transmision start (including RS)
    airtime: int  # time spent on sending data
    rs_time: int  # time spent on sending reservation signal before data
    number_of_retransmissions: int = 0
    t_end: int = None  # sent time / transsmision end = start + rs_time + airtime
    t_to_send: int = None
    collided: bool = False  # true if transmission colided with another one

    # Rashed-Step 2.B_2-12-30-2025-start
    tx_pos: Pos = None
    rx_name: str = None
    rx_pos: Pos = None
    distance_m: float = None
    pr_dbm: float = None
    # Rashed-Step 2.B_2-12-30-2025-end
    # Rashed-Step 5.G-02-06-2026-start
    # Reference to the actual chosen NrUE object (not just a position
    # snapshot) - gen_new_transmission() does random.choice(self.ue_list)
    # to pick which UE this transmission targets; send_transmission()
    # needs to re-read *that same UE's* current_pos() after potentially
    # waiting on tx_queue_nru, not fall back to an arbitrary/first UE.
    rx_ue: Optional[Any] = None
    # Rashed-Step 5.G-02-06-2026-end

    

    



class Gnb:
    def __init__(
            self,
            env: simpy.Environment,
            name: str,
            channel: dataclass,
            # Rashed-Step 1.C_2-12-26-2025-start
            pos: Pos,
            ue_list: list,
            # Rashed-Step 1.C_2-12-26-2025-end
            config_nr: Config_NR,
            # Rashed-Step 5.G-02-06-2026-start
            mobility: Optional[Any] = None
            # Rashed-Step 5.G-02-06-2026-end
    ):
        self.config_nr = config_nr
        # self.times = Times(config.data_size, config.mcs)  # using Times script to get time calculations
        self.name = name  # name of the station
        self.env = env  # simpy environment
        # color of output -- for future station distinction
        self.col = random.choice(colors)
        self.transmission_to_send = None  # the transmision object which is next to send
        self.succeeded_transmissions = 0  # all succeeded transmissions for station
        self.failed_transmissions = 0  # all failed transmissions for station
        # all failed transmissions for station in a row
        self.failed_transmissions_in_row = 0
        self.cw_min = config_nr.cw_min  # cw min parameter value
        self.N = None  # backoff counter
        self.desync = 0
        self.next_sync_slot_boundry = 0
        self.cw_max = config_nr.cw_max  # cw max parameter value
        self.channel = channel  # channel objfirst_transmission
        env.process(self.start())  # starting simulation process
        env.process(self.sync_slot_counter())
        self.process = None  # waiting back off process
        self.channel.airtime_data_NR.update({name: 0})
        self.channel.airtime_control_NR.update({name: 0})
        self.desync_done = False
        self.first_interrupt = False
        self.back_off_time = 0
        self.time_to_next_sync_slot = 0
        self.waiting_backoff = False
        self.start_nr = 0
        


        # Rashed-Step 1.C_2-12-26-2025-start
        self.pos = pos
        self.ue_list = ue_list
        # Rashed-Step 1.C_2-12-26-2025-end
        # Rashed-Step 5.G-02-06-2026-start
        self.mobility = mobility
        # Rashed-Step 5.G-02-06-2026-end
        # Rashed-Step 4.C_2-01-21-2026-start
        self.sinr_print_ctr = 0
        # Rashed-Step 4.C_2-01-21-2026-end

    # Rashed-Step 5.G-02-06-2026-start
    def current_pos(self) -> Pos:
        """See wifi.WiFi.current_pos() - same idea for gNBs."""
        return self.mobility.pos_now() if self.mobility is not None else self.pos
    # Rashed-Step 5.G-02-06-2026-end

    def start(self):
        # Rashed-Step 3.F-12-26-2025-start
        #print(self.env.now, self.name, "START LOOP")
        # Rashed-Step 3.F-12-26-2025-end

        # yield self.env.timeout(self.desync)
        while True:
            # self.transmission_to_send = self.gen_new_transmission()
            was_sent = False
            while not was_sent:
                if gap:
                    # Rashed-Step 3.E_2-01-12-2026-start
                    #self.process = self.env.process(self.wait_back_off_gap())
                    self.process = self.env.process(self.wait_back_off_gap_after())
                    # Rashed-Step 3.E_2-01-12-2026-end
                    yield self.process
                    was_sent = yield self.env.process(self.send_transmission())
                else:
                    self.process = self.env.process(self.wait_back_off())
                    yield self.process
                    was_sent = yield self.env.process(self.send_transmission())

    # Rashed-Step 3.E_2-01-12-2026-start

    def wait_back_off_gap_after(self):

        pp = self.config_nr.deter_period + self.config_nr.M * self.config_nr.observation_slot_duration
        backoff_slots = self.generate_backoff_slots(self.failed_transmissions_in_row)
        backoff_time = pp + backoff_slots * self.config_nr.observation_slot_duration

        remaining = backoff_time

        while remaining > 0:
            # Rashed-Step 5.E-02-06-2026-start
            if self.channel.is_busy(self.current_pos(), self.config_nr.ed_threshold_dbm, exclude_tx_id=self.name,
                                     sense_f_hz=self.config_nr.f_ghz, sense_bw_mhz=self.config_nr.bandwidth_mhz):
            # Rashed-Step 5.E-02-06-2026-end
                log(self, f"Channel busy during backoff, pausing backoff with {remaining} us remaining")
                yield self.channel.state_changed
                continue

            step = min(self.config_nr.observation_slot_duration, remaining)
            yield self.env.timeout(step)
            remaining -= step

        
        time_to_next_sync_slot = self.next_sync_slot_boundry - self.env.now
        while time_to_next_sync_slot <= 0:
            time_to_next_sync_slot += self.config_nr.synchronization_slot_duration
            log(self,
                f'Backoff finished but next sync slot was in the past, new time to next possible sync = {time_to_next_sync_slot}')
            
        # gap_time = time_to_next_sync_slot
        # log(self, f"Waiting gap period of : {gap_time} us")
        # yield self.env.timeout(gap_time)

        gap_remaining = time_to_next_sync_slot

        log(self, f"Starting gap period of : {gap_remaining} us")

        while gap_remaining > 0:
            # Rashed-Step 5.E-02-06-2026-start
            if self.channel.is_busy(self.current_pos(), self.config_nr.ed_threshold_dbm, exclude_tx_id=self.name,
                                     sense_f_hz=self.config_nr.f_ghz, sense_bw_mhz=self.config_nr.bandwidth_mhz):
            # Rashed-Step 5.E-02-06-2026-end
                log(self, f"Channel busy during gap, pausing gap with {gap_remaining} us remaining")
                yield self.channel.state_changed
                continue

            step = min (self.config_nr.observation_slot_duration, gap_remaining)
            yield self.env.timeout(step)
            gap_remaining -= step
        
        log(self, "Finished GAP-after-backoff (reached sync boundary)")

        return


    # Rashed-Step 3.E_2-01-12-2026-end

    def wait_back_off_gap(self):
        self.back_off_time = self.generate_new_back_off_time(
            self.failed_transmissions_in_row)
        # adding pp to the backoff timer
        m = self.config_nr.M
        prioritization_period_time = self.config_nr.deter_period + \
            m * self.config_nr.observation_slot_duration
        # add Priritization Period time to bacoff procedure
        self.back_off_time += prioritization_period_time

        while self.back_off_time > -1:
            try:
                with self.channel.tx_lock.request() as req:  # waiting  for idle channel -- empty channel
                    yield req

                self.time_to_next_sync_slot = self.next_sync_slot_boundry - self.env.now


                log(self,
                    f'Backoff = {self.back_off_time} , and time to next slot: {self.time_to_next_sync_slot}')
                while self.back_off_time >= self.time_to_next_sync_slot:
                    self.time_to_next_sync_slot += self.config_nr.synchronization_slot_duration
                    log(self,
                        f'Backoff > time to sync slot: new time to next possible sync +1000 = {self.time_to_next_sync_slot}')

                gap_time = self.time_to_next_sync_slot - self.back_off_time
                log(self, f"Waiting gap period of : {gap_time} us")
                assert gap_time >= 0, "Gap period is < 0!!!"

                yield self.env.timeout(gap_time)
                log(self, f"Finished gap period")

                self.first_interrupt = True

                self.start_nr = self.env.now  # store the current simulation time

                log(self,
                    f'Channels in use by {self.channel.tx_lock.count} stations')

                # checking if channel if idle
                if (len(self.channel.tx_list_NR) + len(self.channel.tx_list)) > 0:
                    log(self, 'Channel busy -- waiting to be free')
                    with self.channel.tx_lock.request() as req:
                        yield req
                    log(self, 'Finished waiting for free channel - restarting backoff procedure')

                else:
                    log(self, 'Channel free')
                    log(self,
                        f"Starting to wait backoff: ({self.back_off_time}) us...")
                    # join the list off stations which are waiting Back Offs
                    self.channel.back_off_list_NR.append(self)
                    self.waiting_backoff = True

                    # join the environment action queue
                    yield self.env.timeout(self.back_off_time)

                    log(self, f"Backoff waited, sending frame...")
                    self.back_off_time = -1  # leave the loop
                    self.waiting_backoff = False

                    self.channel.back_off_list_NR.remove(
                        self)  # leave the waiting list as Backoff was waited successfully

            except simpy.Interrupt:  # handle the interruptions from transmitting stations
                log(self, "Waiting was interrupted")
                if self.first_interrupt and self.start is not None and self.waiting_backoff is True:
                    log(self, "Backoff was interrupted, waiting to resume backoff...")
                    already_waited = self.env.now - self.start_nr

                    if already_waited <= prioritization_period_time:
                        self.back_off_time -= prioritization_period_time
                        log(self,
                            f"Interrupted in PP time {prioritization_period_time}, backoff {self.back_off_time}")
                    else:
                        slots_waited = int(
                            (already_waited - prioritization_period_time) / self.config_nr.observation_slot_duration)
                        # self.back_off_time -= already_waited  # set the Back Off to the remaining one
                        self.back_off_time -= (
                            (slots_waited * self.config_nr.observation_slot_duration) + prioritization_period_time)
                        log(self,
                            f"Completed slots(9us) {slots_waited} = {(slots_waited * self.config_nr.observation_slot_duration)}  plus PP time {prioritization_period_time}")
                        log(self, f"Backoff decresed by {(slots_waited * self.config_nr.observation_slot_duration) + prioritization_period_time} new Backoff {self.back_off_time}")

                    #log(self, f"already waited {already_waited} Backoff us, new Backoff {self.back_off_time}")
                    # addnin new PP before next weiting
                    self.back_off_time += prioritization_period_time
                    self.first_interrupt = False
                    self.waiting_backoff = False

    def wait_back_off(self):
        # Wait random number of slots N x OBSERVATION_SLOT_DURATION us
        global start
        self.back_off_time = self.generate_new_back_off_time(
            self.failed_transmissions_in_row)
        m = self.config_nr.M
        prioritization_period_time = self.config_nr.deter_period + \
            m * self.config_nr.observation_slot_duration

        while self.back_off_time > -1:

            try:
                with self.channel.tx_lock.request() as req:  # waiting  for idle channel -- empty channel
                    yield req

                self.first_interrupt = True
                # add Priritization Period time to bacoff procedure
                self.back_off_time += prioritization_period_time
                log(self,
                    f"Starting to wait backoff (with PP): ({self.back_off_time}) us...")
                start = self.env.now  # store the current simulation time
                # join the list off stations which are waiting Back Offs
                self.channel.back_off_list_NR.append(self)

                # join the environment action queue
                yield self.env.timeout(self.back_off_time)

                log(self, f"Backoff waited, sending frame...")
                self.back_off_time = -1  # leave the loop

                # leave the waiting list as Backoff was waited successfully
                self.channel.back_off_list_NR.remove(self)

            except simpy.Interrupt:  # handle the interruptions from transmitting stations
                log(self, "Backoff was interrupted, waiting to resume backoff...")
                if self.first_interrupt and start is not None:
                    already_waited = self.env.now - start

                    if already_waited <= prioritization_period_time:
                        self.back_off_time -= prioritization_period_time
                        log(self,
                            f"Interrupted in PP time {prioritization_period_time}, backoff {self.back_off_time}")
                    else:
                        slots_waited = int(
                            (already_waited - prioritization_period_time) / self.config_nr.observation_slot_duration)
                        # self.back_off_time -= already_waited  # set the Back Off to the remaining one
                        self.back_off_time -= (
                            (slots_waited * self.config_nr.observation_slot_duration) + prioritization_period_time)
                        log(self,
                            f"Completed slots(9us) {slots_waited} = {(slots_waited * self.config_nr.observation_slot_duration)}  plus PP time {prioritization_period_time}")
                        log(self, f"Backoff decresed by {(slots_waited * self.config_nr.observation_slot_duration) + prioritization_period_time} new Backoff {self.back_off_time}")

                    self.first_interrupt = False
                    self.waiting_backoff = False

    def sync_slot_counter(self):
        # Process responsible for keeping the next sync slot boundry timestamp
        self.desync = random.randint(
            self.config_nr.min_sync_slot_desync, self.config_nr.max_sync_slot_desync)
        self.next_sync_slot_boundry = self.desync
        log(self, f"Selected random desync to {self.desync} us")
        # waiting randomly chosen desync time
        yield self.env.timeout(self.desync)
        while True:
            self.next_sync_slot_boundry += self.config_nr.synchronization_slot_duration
            log(self,
                f"Next synch slot boundry is: {self.next_sync_slot_boundry}")
            #print(f"Next synch slot boundry is: ",self.next_sync_slot_boundry)
            yield self.env.timeout(self.config_nr.synchronization_slot_duration)

    def send_transmission(self):
        self.transmission_to_send = self.gen_new_transmission()

        # Rashed-Step 5.E.1-02-06-2026-start
        # BUGFIX: was self.channel.tx_queue (WiFi's queue - shared with
        # every WiFi AP AND the rogue AP), so NR-U transmissions competed
        # for the same MAC-layer resource as WiFi even on a totally
        # separate, non-overlapping frequency. Now uses its own queue.
        with self.channel.tx_queue_nru.request(priority=(big_num - self.transmission_to_send.transmission_time)) as req:
        # Rashed-Step 5.E.1-02-06-2026-end
            yield req
            # Rashed-Step 4.A-01-20-2026-start
            # with self.channel.tx_lock.request() as lock:
            #     yield lock
            # Rashed-Step 4.A-01-20-2026-end

            log(self, f'Starting transmission: {self.transmission_to_send.transmission_time}')

            # Rashed-Step 5.G-02-06-2026-start
            # BUGFIX/UPGRADE (Step 5.G, G_2): rx_pos used to be read from
            # self.transmission_to_send.rx_pos, a snapshot taken back in
            # gen_new_transmission() - BEFORE the tx_queue_nru wait above -
            # so a moving UE could have already moved on by actual
            # transmission start if this gNB had to wait for the queue.
            # Now re-read fresh from the SAME UE object gen_new_transmission()
            # randomly chose (transmission_to_send.rx_ue), via current_pos(),
            # right here after the wait. Falls back to self.pos when there's
            # no UE at all, same as the old rx_pos=...else self.pos branch.
            tx_start = self.env.now
            tx_pos = self.current_pos()
            rx_ue = self.transmission_to_send.rx_ue
            rx_pos = rx_ue.current_pos() if rx_ue is not None else tx_pos
            tx_dur = self.transmission_to_send.transmission_time
            # Rashed-Step 5.G-02-06-2026-end

            active = ActiveTx(
                tx_id=self.name,
                tx_pos=tx_pos,
                rx_pos=rx_pos,
                tx_start=tx_start,
                tx_power_dbm=self.config_nr.tx_power_dbm,
                f_hz=self.config_nr.f_ghz,
                pl_exp=self.config_nr.pl_exp,
                t_end=tx_start + tx_dur,
                tech="NRU",
                # Rashed-Step 5.C-02-06-2026-start
                bandwidth_mhz=self.config_nr.bandwidth_mhz,
                noise_figure_db=self.config_nr.noise_figure_db
                # Rashed-Step 5.C-02-06-2026-end
            )
            # Rashed-Step 4.B_4-01-20-2026-start
            #print(self.env.now, self.name, "TX->RX d=", dist(self.pos, rx_pos))
            # Rashed-Step 4.B_4-01-20-2026-end
            self.channel.register_tx(active)

            # Rashed-Step 5.1-02-06-2026-start
            was_sent = False
            # Rashed-Step 5.1-02-06-2026-end
            try:
                yield self.env.timeout(tx_dur)
                # Rashed-Step 4.C_2-01-21-2026-start
                self.sinr_print_ctr += 1
                if self.sinr_print_ctr % 50 == 0:
                    print(self.env.now, self.name, "NRU SINR(dB) =", self.channel.sinr_db(active))
                # Rashed-Step 4.C_2-01-21-2026-end
                # Rashed-Step 4.D_3-01-29-2026-start
                #was_sent = self.check_collision()
                sinr = self.channel.sinr_db(active)
                # Rashed-Step 5.D-02-06-2026-start
                required_sinr = self.required_sinr_db()
                log(self, f"TX->RX SINR(dB) = {sinr:.2f} dB, required (MCS {self.config_nr.mcs}) = {required_sinr:.2f} dB")
                was_sent = (sinr >= required_sinr)
                # Rashed-Step 5.D-02-06-2026-end
                if was_sent:
                    self.sent_completed()
                else:
                    self.sent_failed()
                # Rashed-Step 4.D_3-01-29-2026-start
                # Rashed-Step 4.C_2-01-21-2026-start
                # Yield one extra zero-duration tick before unregistering,
                # so another transmission ending at this exact same env.now
                # still sees this one in channel.active_txs while computing
                # its own SINR (avoids an artificial tie-break bias from
                # unregistering "too early" relative to a same-tick peer -
                # see channel.sinr_db()/sensed_energy_dbm(), both of which
                # only count what's currently in active_txs).
                yield self.env.timeout(0)
                # Rashed-Step 4.C_2-01-21-2026-end
                # Rashed-Step 5.1-02-06-2026-start
                # BUGFIX: pass success so airtime isn't recorded twice - see
                # matching note below where the old manual
                # airtime_data_NR += line was removed.
                self.channel.unregister_tx(active, success=was_sent)
                # Rashed-Step 5.1-02-06-2026-end
            except BaseException:
                # Rashed-Step 5.I-02-06-2026-start
                # BUGFIX: this used to be `finally: yield ...; unregister_tx
                # (...)`, which ran on EVERY exit path including the
                # generator being closed via GeneratorExit at simulation
                # shutdown (env.run(until=...) returning while this gNB was
                # still mid-transmission - a near-certain occurrence at the
                # end of any run). Yielding again while a generator is being
                # closed is invalid and raised "RuntimeError: generator
                # ignored GeneratorExit" (printed by the interpreter as
                # "Exception ignored in: ..." since it happens during
                # garbage collection with no caller to propagate to -
                # harmless to already-computed results, but noisy on every
                # single run). Fixed the same way as wifi.WiFi.send_frame():
                # move the yield+unregister into the normal (non-exception)
                # tail of the try, and handle GeneratorExit (or any other
                # exception) here with purely SYNCHRONOUS cleanup instead.
                self.channel.unregister_tx(active, success=was_sent)
                raise
                # Rashed-Step 5.I-02-06-2026-end

        # after leaving the 'with', resource is released automatically

        if was_sent:
            self.channel.airtime_control_NR[self.name] += self.transmission_to_send.rs_time
            # Rashed-Step 5.1-02-06-2026-start
            # BUGFIX: this used to also do
            # self.channel.airtime_data_NR[self.name] += self.transmission_to_send.airtime
            # here, double-counting against channel.unregister_tx(active,
            # success=...) above, which now records airtime_data_NR on
            # success. Removed - unregister_tx is the single source of
            # truth. airtime_control_NR (RS time) is untouched since it
            # was never duplicated.
            # Rashed-Step 5.1-02-06-2026-end
            return True
        else:
            return False

    def check_collision(self):  # check if the collision occurred

        # if gap:
        #     # if (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) > 1 and self.waiting_backoff is True:
        #     if (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) > 1 or (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) == 0:
        #         self.sent_failed()
        #         return False
        #     else:
        #         self.sent_completed()
        #         return True
        # else:
        #     if (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) > 1 or (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) == 0:
        #         self.sent_failed()
        #         return False
        #     else:
        #         self.sent_completed()
        #         return True
        # Rashed-Step 3.F-01-13-2026-start
        # ok = all(t.tx_id == self.name for t in self.channel.active_txs)
        # (self.sent_completed() if ok else self.sent_failed())
        # return ok
        mine = any(t.tx_id == self.name for t in self.channel.active_txs)

        if not mine:
            self.sent_failed()
            return False
        
        others = [t for t in self.channel.active_txs if t.tx_id != self.name]
        
        if others:
            self.sent_failed()
            return False
        
        self.sent_completed()
        return True
        # Rashed-Step 3.F-01-13-2026-end

    def gen_new_transmission(self):
        # Rashed-Step 2.D_2-01-08-2026-start
        
        # transmission_time = self.config_nr.mcot * 1000  # transforming to usec
        # if gap:
        #     rs_time = 0
        # else:
        #     rs_time = self.next_sync_slot_boundry - self.env.now
        # airtime = transmission_time - rs_time
        # return Transmission_NR(transmission_time, self.name, self.col, self.env.now, airtime, rs_time)
        
        transmission_time = self.config_nr.mcot * 1000
        rs_time = 0 if gap else (self.next_sync_slot_boundry - self.env.now)
        airtime = transmission_time - rs_time

        rx_ue = random.choice(self.ue_list) if self.ue_list else None

        tx = Transmission_NR(
            transmission_time, self.name, self.col, self.env.now, airtime, rs_time)

        # Rashed-Step 5.G-02-06-2026-start
        # current_pos() instead of self.pos/rx_ue.pos for this diagnostic
        # snapshot (distance_m/pr_dbm are logged, not used for the actual
        # send_transmission() success decision, which recomputes its own
        # tx_pos/rx_pos fresh right at transmission time). tx.rx_ue stores
        # the actual chosen UE object (not just its position) so
        # send_transmission() can re-read *its* current_pos() later, after
        # potentially waiting on tx_queue_nru - see send_transmission().
        my_pos = self.current_pos()
        tx.tx_pos = my_pos
        tx.rx_ue = rx_ue
        if rx_ue is not None:
            rx_pos = rx_ue.current_pos()
            tx.rx_name = rx_ue.name
            tx.rx_pos = rx_pos
            tx.distance_m = dist(my_pos, rx_pos)
            # Rashed-Step 5.G-02-06-2026-end

            # Rashed-Step 5.B-02-06-2026-start
            tx.pr_dbm = rx_power_dbm(
                tx_power_dbm=self.config_nr.tx_power_dbm,
                d_m= tx.distance_m,
                f_hz=self.config_nr.f_ghz,
                n = self.config_nr.pl_exp,
                shadow_db=self.channel.shadow_db(self.name, tx.rx_pos)
            )
            # Rashed-Step 5.B-02-06-2026-end

        return tx
        
        # Rashed-Step 2.D_2-01-08-2026-end


    # Rashed-Step 3.E_1-12-26-2025-start
    # def generate_new_back_off_time(self, failed_transmissions_in_row):
    #     # BACKOFF TIME GENERATION
    #     upper_limit = (pow(2, failed_transmissions_in_row) * (
    #         self.cw_min + 1) - 1)  # define the upper limit basing on  unsuccessful transmissions in the row
    #     upper_limit = (
    #         upper_limit if upper_limit <= self.cw_max else self.cw_max)  # set upper limit to CW Max if is bigger then this parameter
    #     back_off = random.randint(0, upper_limit)  # draw the back off value
    #     # store drawn value for future analyzes
    #     self.channel.backoffs[back_off][self.channel.n_of_stations] += 1
    #     return back_off * self.config_nr.observation_slot_duration

    def generate_backoff_slots(self, failed_transmissions_in_row: int)-> int:
        # BACKOFF SLOTS GENERATION
        upper_limit = (pow(2, failed_transmissions_in_row) * (self.cw_min + 1) - 1)  # define the upper limit basing on  unsuccessful transmissions in the row
        upper_limit = upper_limit if upper_limit <= self.cw_max else self.cw_max  # set upper limit to CW Max if is bigger then this parameter
    
        return random.randint(0, upper_limit)
    
    # Rashed-Step 3.E_1-12-26-2025-end

    # Rashed-Step 5.D-02-06-2026-start
    def required_sinr_db(self) -> float:
        """
        Required SINR for this gNB's configured MCS, or the flat override
        if config_nr.nru_sinr_thr_db_override is set. Shared by the
        send_transmission() success decision and the sent_failed() log
        line so they can't drift apart.
        """
        if self.config_nr.nru_sinr_thr_db_override is not None:
            return self.config_nr.nru_sinr_thr_db_override
        return mcs_sinr_threshold_db(NRU_MCS_SINR_THRESHOLDS_DB, self.config_nr.mcs)
    # Rashed-Step 5.D-02-06-2026-end

    def sent_failed(self):
        # Rashed-Step 2.D_4-02-03-2026-start
        #log(self, "There was a collision")
        # Rashed-Step 5.D-02-06-2026-start
        log(self, f"TX failed (SINR < {self.required_sinr_db():.2f} dB)")
        # Rashed-Step 5.D-02-06-2026-end
        # Rashed-Step 2.D_4-02-03-2026-end
        self.transmission_to_send.number_of_retransmissions += 1
        self.channel.failed_transmissions_NR += 1
        self.failed_transmissions += 1
        self.failed_transmissions_in_row += 1
        log(self, self.channel.failed_transmissions_NR)
        if self.transmission_to_send.number_of_retransmissions > 7:
            self.failed_transmissions_in_row = 0

    def sent_completed(self):
        log(self, f"Successfully sent transmission")
        self.transmission_to_send.t_end = self.env.now
        self.transmission_to_send.t_to_send = (
            self.transmission_to_send.t_end - self.transmission_to_send.t_start)
        self.channel.succeeded_transmissions_NR += 1
        self.succeeded_transmissions += 1
        self.failed_transmissions_in_row = 0
        return True

    


