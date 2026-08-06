
from common.common import *
from Times import *
from common.common import Pos
# Rashed-Step 2.D_1-01-08-2026-start
from common.common_phy import dist, rx_power_dbm

# Rashed-Step 2.D_1-01-08-2026-end


# Rashed-Step 3.D-01-12-2026-start
from channel.channel import ActiveTx
# Rashed-Step 3.D-01-12-2026-end

# Rashed-Step 5.D-02-06-2026-start
from common.common_phy import mcs_sinr_threshold_db
from Times import WIFI_MCS_SINR_THRESHOLDS_DB
from typing import Optional
# Rashed-Step 5.D-02-06-2026-end
# Rashed-Step 5.G-02-06-2026-start
from typing import Any
# Rashed-Step 5.G-02-06-2026-end
# Rashed-Step 8.B-08-06-2026-start
from common.packet import Packet, TrafficConfig
# Rashed-Step 8.B-08-06-2026-end





@dataclass()
class Config:
    data_size: int = 1472  # size od payload in b
    cw_min: int = 15  # min cw window size
    cw_max: int = 63  # max cw window size 1023 def
    r_limit: int = 7
    mcs: int = 7

    # Rashed-Step 2.C_1-01-12-2026-start
    tx_power_dbm: float = 20.0 
    f_ghz: float = 5.18e9
    pl_exp : float = 3.0        #indoor-ish
    # Rashed-Step 2.C_1-12-26-2025-end

    # Rashed-Step 3.A-01-12-2026-start
    ed_threshold_dbm: float = -62.0   # energy detect threshold 
    # Rashed-Step 3.A-01-12-2026-end

    # Rashed-Step 4.D_1-01-28-2026-start
    # Rashed-Step 5.D-02-06-2026-start
    # BUGFIX+UPGRADE: the old `wifi_sinr_thr_db = 10.0` had no type
    # annotation, so it was NOT actually a dataclass field - Config(...)
    # could never set it, every instance silently used the class-level
    # 10.0 no matter what. Given a real annotation now and repurposed as
    # an explicit override: None (default) means "look up the required
    # SINR for `mcs` in WIFI_MCS_SINR_THRESHOLDS_DB"; set it to force a
    # flat threshold instead.
    wifi_sinr_thr_db_override: Optional[float] = None
    # Rashed-Step 5.D-02-06-2026-end
    # Rashed-Step 4.D_1-01-28-2026-end

    # Rashed-Step 5.C-02-06-2026-start
    # Receiver-side noise params, used to derive the SINR noise floor
    # (see common_phy.thermal_noise_dbm) instead of the old hardcoded
    # -94.0 dBm constant. 20 MHz matches the legacy-OFDM rate table in
    # Times.py; 7 dB NF is a typical Wi-Fi NIC value. Together they land
    # right back at ~-94 dBm by default.
    bandwidth_mhz: float = 20.0
    noise_figure_db: float = 7.0
    # Rashed-Step 5.C-02-06-2026-end



class WiFi:
    def __init__(
            self,
            env: simpy.Environment,
            name: str,
            channel: dataclass,
            # Rashed-Step 1.C_1-01-12-2026-start
            pos: Pos,
            sta_list: list,
            # Rashed-Step 1.C_1-01-12-2026-start
            config: Config,
            # Rashed-Step 5.G-02-06-2026-start
            mobility: Optional[Any] = None,
            # Rashed-Step 5.G-02-06-2026-end
            # Rashed-Step 8.B-08-06-2026-start
            # None (default) is normalized to TrafficConfig(mode=
            # "saturated") below - every existing caller that doesn't
            # know about this yet (simulation.py, every standalone
            # test/*.py file) gets exactly today's always-has-a-frame-
            # ready behavior, unchanged.
            traffic_config: Optional[TrafficConfig] = None
            # Rashed-Step 8.B-08-06-2026-end
    ):
        self.config = config
        self.times = Times(config.data_size, config.mcs)  # using Times script to get time calculations
        self.name = name  # name of the station
        self.env = env  # simpy environment
        self.col = random.choice(colors)  # color of output -- for future station distinction
        self.frame_to_send = None  # the frame object which is next to send
        self.succeeded_transmissions = 0  # all succeeded transmissions for station
        self.failed_transmissions = 0  # all failed transmissions for station
        self.failed_transmissions_in_row = 0  # all failed transmissions for station in a row
        self.cw_min = config.cw_min  # cw min parameter value
        self.cw_max = config.cw_max  # cw max parameter value
        self.channel = channel  # channel obj

        # Rashed-Step 8.B-08-06-2026-start
        # Queue + arrival-process state. self.packet_queue is
        # constructed unconditionally (cheap - an unused simpy.Store
        # costs nothing) but is only ever actually touched when
        # traffic_config.mode != "saturated" - see _next_packet()/
        # _traffic_generator() below. In saturated mode (the default),
        # packets are synthesized on demand instead, so this AP never
        # contends for the channel any differently than it did before
        # Step 8.B.
        self.traffic_config = traffic_config if traffic_config is not None else TrafficConfig(mode="saturated")
        self.packet_queue = simpy.Store(env)
        self._packet_seq = 0
        if self.traffic_config.mode != "saturated":
            env.process(self._traffic_generator())
        # Rashed-Step 8.B-08-06-2026-end

        # Rashed-Step 8.F-08-06-2026-start
        # Separate counter from _packet_seq so ACK packet_ids never
        # collide with (or get confused for) data packet_ids.
        self._ack_seq = 0
        # Rashed-Step 8.F-08-06-2026-end

        # Rashed-Step 8.E-08-06-2026-start
        # Set by sent_failed() when the retry limit is exceeded; consumed
        # by start()'s inner retry loop, which then blocks on
        # _next_packet() for a real replacement before contending for
        # the channel again. See sent_failed()'s comment for why this is
        # a flag instead of sent_failed() blocking directly.
        self._need_new_packet = False
        # Rashed-Step 8.E-08-06-2026-end

        env.process(self.start())  # starting simulation process
        self.process = None  # waiting back off process
        self.channel.airtime_data.update({name: 0})
        self.channel.airtime_control.update({name: 0})
        self.first_interrupt = False
        self.back_off_time = 0
        self.start = 0

        # Rashed-Step 1.C_1-01-12-2026-start
        self.pos = pos
        self.sta_list = sta_list
        # Rashed-Step 1.C_1-01-12-2026-end
        # Rashed-Step 5.G-02-06-2026-start
        self.mobility = mobility
        # Rashed-Step 5.G-02-06-2026-end


        # Rashed-Step 4.C_2-01-21-2026-start
        self.sinr_print_ctr = 0
        # Rashed-Step 4.C_2-01-21-2026-end

    # Rashed-Step 5.G-02-06-2026-start
    def current_pos(self) -> Pos:
        """
        Current interpolated position if mobility is enabled (see
        common_phy.WaypointMobility), else the static self.pos - byte-
        identical to every pre-5.G run when mobility is None (the
        default). All position reads that matter for CCA/collision
        physics (is_busy() sensing, tx_pos/rx_pos at actual transmission
        time) should go through this, not self.pos directly, so a moving
        AP's sensed/transmitted position is always "now", not "at
        construction time".
        """
        return self.mobility.pos_now() if self.mobility is not None else self.pos
    # Rashed-Step 5.G-02-06-2026-end

    # Rashed-Step 8.B-08-06-2026-start
    def _make_packet(self) -> Packet:
        """
        Synthesize a fresh Packet - used directly in saturated mode
        (bypasses the queue entirely, see _next_packet()) and by the
        traffic generator (poisson/cbr) to fill the queue. Payload size
        defaults to self.config.data_size (matching every pre-Step-8
        run exactly) unless traffic_config.packet_size_bytes overrides
        it. header_bytes uses Times.mac_overhead (the same 40-byte MAC
        header size the PHY duration formula already assumes), so
        total_bytes() is meaningful immediately rather than a
        placeholder - real per-technology header modeling is still a
        later sub-step, this just reuses the constant that already
        exists.
        """
        self._packet_seq += 1
        payload = self.traffic_config.packet_size_bytes if self.traffic_config.packet_size_bytes is not None else self.config.data_size
        destination = self.sta_list[0].name if self.sta_list else self.name
        return Packet(
            packet_id=f"{self.name}-{self._packet_seq:06d}",
            source=self.name,
            destination=destination,
            payload_bytes=payload,
            header_bytes=Times.mac_overhead // 8,
            created_at=self.env.now,
        )

    # Rashed-Step 8.F-08-06-2026-start
    def _make_ack_packet(self, data_packet: Optional[Packet]) -> Packet:
        """
        Construct the ACK Packet sent back in response to a successfully
        delivered data_packet. Direction is reversed from the data
        packet: source is the receiving STA, destination is this AP.
        payload_bytes=0 (an ACK carries no payload); header_bytes uses
        Times.ack_size (14 bytes) - the same constant
        Times.get_ack_frame_time() already uses to compute the ACK's
        on-air duration, so total_bytes() is consistent with the timing
        model rather than an unrelated placeholder. Called only from
        sent_completed() (i.e. only when the data frame actually
        succeeded) - there is no ACK object for a failed transmission,
        matching real 802.11 semantics (the sender just times out
        waiting for one that was never sent).
        """
        self._ack_seq += 1
        rx_name = self.sta_list[0].name if self.sta_list else self.name
        return Packet(
            packet_id=f"{self.name}-ACK-{self._ack_seq:06d}",
            source=rx_name,
            destination=self.name,
            payload_bytes=0,
            header_bytes=Times.ack_size // 8,
            packet_type="ACK",
            created_at=self.env.now,
        )
    # Rashed-Step 8.F-08-06-2026-end

    def _next_packet(self):
        """
        Generator (SimPy-safe to `yield from` even though the saturated
        branch never actually yields - see module note in Step 8.txt).
        Saturated mode: returns a fresh Packet immediately, no queue
        involved - operationally identical to every pre-Step-8.B run,
        this AP is never idle waiting for "something to send".
        Poisson/cbr mode: blocks on self.packet_queue.get() until the
        traffic generator has produced one - this AP genuinely does not
        contend for the channel while its queue is empty.
        """
        if self.traffic_config.mode == "saturated":
            return self._make_packet()
        pkt = yield self.packet_queue.get()
        return pkt

    def _traffic_generator(self):
        """
        Only started (in __init__) when traffic_config.mode !=
        "saturated". Produces Packets per a Poisson process
        (exponential inter-arrival, mean = 1/arrival_rate_pps seconds)
        or CBR (fixed inter-arrival = 1/arrival_rate_pps seconds) and
        pushes them into self.packet_queue.
        """
        while True:
            if self.traffic_config.mode == "poisson":
                interval_us = random.expovariate(self.traffic_config.arrival_rate_pps / 1e6)
            else:  # "cbr"
                interval_us = 1e6 / self.traffic_config.arrival_rate_pps
            yield self.env.timeout(interval_us)
            yield self.packet_queue.put(self._make_packet())
    # Rashed-Step 8.B-08-06-2026-end

    def start(self):
        # Rashed-Step 3.F-12-26-2025-start
        #print(self.env.now, self.name, "START LOOP")
        # Rashed-Step 3.F-12-26-2025-end
        while True:
            # Rashed-Step 8.B-08-06-2026-start
            # UPGRADE: used to unconditionally call generate_new_frame()
            # here, i.e. this AP always had a frame ready the instant it
            # got channel access ("saturated" traffic, implicit and
            # unconditional). Now goes through _next_packet() first -
            # in saturated mode (the default) that's still a same-tick,
            # non-blocking call (see _next_packet()'s docstring), so
            # this loop's timing is unchanged; in poisson/cbr mode this
            # AP now genuinely waits here, not contending for the
            # channel at all, until it actually has something to send.
            packet = yield from self._next_packet()
            # Rashed-Step 8.C-08-06-2026: pass packet through so frame
            # duration reflects its actual payload_bytes (see
            # generate_new_frame()'s docstring/comment).
            self.frame_to_send = self.generate_new_frame(packet)
            self.frame_to_send.packet = packet
            # Rashed-Step 8.B-08-06-2026-end
            was_sent = False
            while not was_sent:
                # Rashed-Step 8.E-08-06-2026-start
                # UPGRADE: sent_failed() (called inside the send_frame()
                # attempt below) sets this flag instead of directly
                # synthesizing a replacement packet when the retry limit
                # is exceeded. Checked at the top of every retry attempt
                # (not just once per episode) - this is exactly the
                # point, analogous to _next_packet() at the top of the
                # outer loop, where it's safe to block: send_frame() has
                # already fully finished the PREVIOUS attempt's own
                # bookkeeping (unregister_tx, ACK-timeout wait) before
                # returning was_sent=False, so waiting here for a new
                # packet doesn't delay that unrelated teardown. Saturated
                # mode: still a same-tick, non-blocking call. Poisson/
                # cbr mode: this AP now genuinely sits idle here, not
                # contending for the channel, until its queue actually
                # produces a replacement - closing the simplification
                # documented in Step 8.B/8.C where the replacement was
                # always synthesized immediately regardless of traffic
                # mode.
                if self._need_new_packet:
                    new_packet = yield from self._next_packet()
                    self.frame_to_send = self.generate_new_frame(new_packet)
                    self.frame_to_send.packet = new_packet
                    self._need_new_packet = False
                # Rashed-Step 8.E-08-06-2026-end
                self.process = self.env.process(self.wait_back_off())
                yield self.process
                # self.process = None
                was_sent = yield self.env.process(self.send_frame())
                # self.process = None

    
    # Rashed-Step 3.D-12-26-2025-start
    # def wait_back_off(self):
    #     #global start
    #     self.back_off_time = self.generate_new_back_off_time(
    #         self.failed_transmissions_in_row)  # generating the new Back Off time

    #     while self.back_off_time > -1:
    #         try:
    #             with self.channel.tx_lock.request() as req:  # waiting  for idle channel -- empty channel
    #                 yield req
    #             self.back_off_time += Times.t_difs  # add DIFS time
    #             log(self, f"Starting to wait backoff (with DIFS): ({self.back_off_time})u...")
    #             self.first_interrupt = True
    #             self.start = self.env.now  # store the current simulation time
    #             self.channel.back_off_list.append(self)  # join the list off stations which are waiting Back Offs

    #             yield self.env.timeout(self.back_off_time)  # join the environment action queue

    #             log(self, f"Backoff waited, sending frame...")
    #             self.back_off_time = -1  # leave the loop

    #             self.channel.back_off_list.remove(self)  # leave the waiting list as Backoff was waited successfully

    #         except simpy.Interrupt:  # handle the interruptions from transmitting stations
    #             if self.first_interrupt and self.start is not None:
    #                 #tak jest po mojemu:
    #                 log(self, "Waiting was interrupted, waiting to resume backoff...")
    #                 all_waited = self.env.now - self.start
    #                 if all_waited <= Times.t_difs:
    #                     self.back_off_time -= Times.t_difs
    #                     log(self, f"Interupted in DIFS ({Times.t_difs}), backoff {self.back_off_time}, already waited: {all_waited}")
    #                 else:
    #                     back_waited = all_waited - Times.t_difs
    #                     slot_waited = int(back_waited / Times.t_slot)
    #                     self.back_off_time -= ((slot_waited * Times.t_slot) + Times.t_difs)
    #                     log(self,
    #                         f"Completed slots(9us) {slot_waited} = {(slot_waited * Times.t_slot)}  plus DIFS time {Times.t_difs}")
    #                     log(self,
    #                         f"Backoff decresed by {((slot_waited * Times.t_slot) + Times.t_difs)} new Backoff {self.back_off_time}")
    #                 self.first_interrupt = False

        
    def wait_back_off(self):
        backoff_slots = self.generate_new_back_off_slots(self.failed_transmissions_in_row)

        dif_remaining = Times.t_difs

        while dif_remaining > 0:
            # Rashed-Step 5.E-02-06-2026-start
            # Sensing is now channel-aware: pass this AP's own f_ghz/
            # bandwidth_mhz so energy on a non-overlapping channel doesn't
            # falsely mark the channel busy.
            if self.channel.is_busy(self.current_pos(), self.config.ed_threshold_dbm, exclude_tx_id=self.name,
                                     sense_f_hz=self.config.f_ghz, sense_bw_mhz=self.config.bandwidth_mhz):
            # Rashed-Step 5.E-02-06-2026-end
                log(self, "Channel busy during DIFS, waiting...")
                yield self.channel.state_changed
                continue
            step = min(1, dif_remaining)
            yield self.env.timeout(step)
            dif_remaining -= step

        while backoff_slots > 0:
            # Rashed-Step 5.E-02-06-2026-start
            if self.channel.is_busy(self.current_pos(), self.config.ed_threshold_dbm, exclude_tx_id=self.name,
                                     sense_f_hz=self.config.f_ghz, sense_bw_mhz=self.config.bandwidth_mhz):
            # Rashed-Step 5.E-02-06-2026-end
                log(self, "Channel busy during backoff, waiting...")
                yield self.channel.state_changed
                continue
            yield self.env.timeout(Times.t_slot)
            backoff_slots -= 1
            
        log(self, f"Backoff waited, sending frame...")

        return


    # Rashed-Step 3.D-01-12-2026-end
    # Rashed-Step 3.F-01-13-2026-start
    # def send_frame(self):
    #     self.channel.tx_list.append(self)  # add station to currently transmitting list
    #     res = self.channel.tx_queue.request(
    #         priority=(big_num - self.frame_to_send.frame_time))  # create request basing on this station frame length

    #     try:
    #         result = yield res | self.env.timeout(
    #             0)  # try to hold transmitting lock(station with the longest frame will get this)
    #         if res not in result:  # check if this station got lock, if not just wait you frame time
    #             raise simpy.Interrupt("There is a longer frame...")


    #         with self.channel.tx_lock.request() as lock:  # this station has the longest frame so hold the lock
    #             yield lock

    #             # Rashed-Step 3.D-01-12-2026-start
    #             # for station in self.channel.back_off_list:  # stop all station which are waiting backoff as channel is not idle
    #             #     if station.process.is_alive:
    #             #         station.process.interrupt()
    #             # for gnb in self.channel.back_off_list_NR:  # stop all station which are waiting backoff as channel is not idle
    #             #     if gnb.process.is_alive:
    #             #         gnb.process.interrupt()
    #             # Rashed-Step 3.D-01-12-2026-end

    #             log(self, f'Starting sending frame: {self.frame_to_send.frame_time}')

    #             # Rashed-Step 2.E-01-08-2026-start
    #             if self.frame_to_send.pr_dbm is not None:
    #                 log(self, f"Frame TX pos: {self.frame_to_send.tx_pos}, RX pos: {self.frame_to_send.rx_pos}, Distance: {self.frame_to_send.distance_m} m, Pr: {self.frame_to_send.pr_dbm} dBm")
    #             # Rashed-Step 2.E-01-08-2026-end

    #             # Rashed-Step 3.D-12-26-2025-start
    #             tx_start = self.env.now
    #             tx_dur = self.frame_to_send.frame_time + self.times.get_ack_frame_time()

    #             tx_start = self.env.now
    #             tx = ActiveTx(
    #                 tx_id=self.name,
    #                 tx_pos=self.pos,
    #                 tx_start=tx_start,
    #                 tx_power_dbm=self.config.tx_power_dbm,
    #                 f_hz=self.config.f_ghz,
    #                 pl_exp=self.config.pl_exp,
    #                 t_end=tx_start + self.frame_to_send.frame_time,
    #                 tech="WiFi"
    #             )
    #             self.channel.register_tx(tx)
    #             # Rashed-Step 3.F-01-13-2026-start
    #             # yield self.env.timeout(self.frame_to_send.frame_time)  # wait this station frame time
    #             # self.channel.unregister_tx(tx)
    #             try:
    #                 yield self.env.timeout(self.frame_to_send.frame_time)
    #                 was_sent = self.check_collision()
    #             finally:
    #                 self.channel.unregister_tx(tx)


    #             # Rashed-Step 3.F-01-13-2026-end

    #             # Rashed-Step 3.D-12-26-2025-end
    #             #self.channel.back_off_list.clear()  # channel idle, clear backoff waiting list
    #             was_sent = self.check_collision()  # check if collision occurred

    #             if was_sent:  # transmission successful
    #                 self.channel.airtime_control[self.name] += self.times.get_ack_frame_time()
    #                 yield self.env.timeout(self.times.get_ack_frame_time())  # wait ack
    #                 # Rashed-Step 3.F-01-13-2026-start
    #                 #self.channel.tx_list.clear()  # clear transmitting list
    #                 #self.channel.tx_list_NR.clear()
    #                 # Rashed-Step 3.F-01-13-2026-end
                    
    #                 self.channel.tx_queue.release(res)  # leave the transmitting queue
    #                 return True
    #             # Rashed-Step 3.D-12-26-2025-start
    #             self.channel.unregister_tx(tx)
    #             # Rashed-Step 3.D-12-26-2025-end

    #             # there was collision
    #             self.channel.tx_list.clear()  # clear transmitting list
    #             self.channel.tx_list_NR.clear()
    #             self.channel.tx_queue.release(res)  # leave the transmitting queue
    #             self.channel.tx_queue = simpy.PreemptiveResource(self.env,
    #                                                              capacity=1)  # create new empty transmitting queue
    #             yield self.env.timeout(self.times.ack_timeout)  # simulate ack timeout after failed transmission
    #             return False

    #     except simpy.Interrupt:  # this station does not have the longest frame, waiting frame time
    #         yield self.env.timeout(self.frame_to_send.frame_time)

    #     was_sent = self.check_collision()

    #     if was_sent:  # check if collision occurred
    #         log(self, f'Waiting for ACK time: {self.times.get_ack_frame_time()}')
    #         yield self.env.timeout(self.times.get_ack_frame_time())  # wait ack
    #     else:
    #         log(self, "waiting ack timeout slave")
    #         yield self.env.timeout(Times.ack_timeout)  # simulate ack timeout after failed transmission
    #     return was_sent


    def send_frame(self):
        # Rashed-Step 6.A-07-31-2026-start
        # UPGRADE: this used to acquire self.channel.tx_queue (one
        # capacity-1 resource shared by every WiFi AP) before transmitting,
        # so no two WiFi APs could ever be "in flight" on the channel at
        # the same simulated instant - real 802.11 collisions (two
        # independent backoff counters hitting zero in the same slot) were
        # structurally impossible. This is the gap the realism validation
        # report (2026-07-31) flagged against Bianchi's DCF model: measured
        # PCOLL stayed at 0.0000 for N=1/5/20 stations while Bianchi
        # predicts 0%/22.7%/76.0%. wait_back_off() already does correct
        # per-station, per-slot channel sensing (freeze on busy, resume on
        # idle) independently for every AP, so removing the queue and
        # registering the transmission immediately lets two APs whose
        # backoff both hit zero in the same tick genuinely overlap on the
        # channel - the existing SINR/capture-effect logic below
        # (unchanged) then decides who, if anyone, survives, exactly like
        # it already does for cross-technology WiFi/NR-U interference.
        # Rashed-Step 6.A-07-31-2026-end
        log(self, f'Starting sending frame: {self.frame_to_send.frame_time}')
        # Rashed-Step 4.D_2-01-28-2026-end
        # Rashed-Step 5.G-02-06-2026-start
        # BUGFIX/UPGRADE (Step 5.G, G_2): rx_pos is computed here (right
        # before actual transmission start), not back when send_frame()
        # was first called, so a moving STA's position is always "now".
        tx_start = self.env.now
        tx_pos = self.current_pos()
        rx_pos = self.sta_list[0].current_pos() if self.sta_list else tx_pos
        # Rashed-Step 5.G-02-06-2026-end
        tx = ActiveTx(
            tx_id=self.name,
            tx_pos=tx_pos,
            rx_pos=rx_pos,
            tx_start=tx_start,
            tx_power_dbm=self.config.tx_power_dbm,
            f_hz=self.config.f_ghz,
            pl_exp=self.config.pl_exp,
            t_end=tx_start + self.frame_to_send.frame_time,
            tech="WiFi",
            # Rashed-Step 5.C-02-06-2026-start
            bandwidth_mhz=self.config.bandwidth_mhz,
            noise_figure_db=self.config.noise_figure_db
            # Rashed-Step 5.C-02-06-2026-end
        )
        # Rashed-Step 4.B_4-01-20-2026-start
        #print(self.env.now, self.name, "TX->RX d=", dist(self.pos, rx_pos))
        # Rashed-Step 4.B_4-01-20-2026-end
        self.channel.register_tx(tx)

        # Rashed-Step 5.1-02-06-2026-start
        was_sent = False
        # Rashed-Step 5.1-02-06-2026-end
        try:
            yield self.env.timeout(self.frame_to_send.frame_time)
            # Rashed-Step 4.C_2-01-21-2026-start
            #self.sinr_print_ctr += 1
            # if self.sinr_print_ctr % 50 == 0:
            #     print(self.env.now, self.name, "WiFi SINR(dB) =", self.channel.sinr_db(tx))
            # Rashed-Step 4.C_2-01-21-2026-end
            # Rashed-Step 4.D_2-01-28-2026-start
            sinr = self.channel.sinr_db(tx)
            # Rashed-Step 5.D-02-06-2026-start
            # UPGRADE: required SINR now depends on the configured MCS
            # (per-MCS table) instead of one flat threshold for every
            # rate. wifi_sinr_thr_db_override, if set, forces a flat
            # value instead (e.g. to compare against pre-5.D behavior).
            required_sinr = self.required_sinr_db()
            log(self, f"TX->RX SINR(dB) = {sinr:.2f} dB, required (MCS {self.config.mcs}) = {required_sinr:.2f} dB")
            # Rashed-Step 5.D-02-06-2026-end
            #was_sent = self.check_collision()
            was_sent = (sinr >= required_sinr)

            if was_sent:
                self.sent_completed()
            else:
                self.sent_failed()
            # Rashed-Step 4.D_2-01-28-2026-end
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
            # BUGFIX: pass success so airtime isn't recorded twice -
            # sent_completed() below no longer touches airtime_data,
            # unregister_tx() is now the only place that does.
            self.channel.unregister_tx(tx, success=was_sent)
            # Rashed-Step 5.1-02-06-2026-end
        except BaseException:
            # Rashed-Step 5.I-02-06-2026-start
            # BUGFIX: this used to be `finally: yield ...; unregister_tx
            # (...)`, which ran on EVERY exit path including the
            # generator being closed via GeneratorExit at simulation
            # shutdown (env.run(until=...) returning while this AP was
            # still mid-transmission - a near-certain occurrence at the
            # end of any run). Yielding again while a generator is being
            # closed is invalid and raised "RuntimeError: generator
            # ignored GeneratorExit" (printed by the interpreter as
            # "Exception ignored in: ..." since it happens during
            # garbage collection with no caller to propagate to -
            # harmless to already-computed results, but noisy on every
            # single run). Fixed by moving the yield+unregister above
            # into the normal (non-exception) tail of the try block, and
            # handling GeneratorExit (or any other exception) here with
            # a purely SYNCHRONOUS cleanup instead - was_sent is still
            # False here unless the try body got far enough to decide
            # otherwise, matching the original finally's intent of
            # "always unregister on the way out", just without the
            # illegal re-yield.
            self.channel.unregister_tx(tx, success=was_sent)
            raise
            # Rashed-Step 5.I-02-06-2026-end

        if was_sent:
            self.channel.airtime_control[self.name] += self.times.get_ack_frame_time()
            yield self.env.timeout(self.times.get_ack_frame_time())
            # Rashed-Step 8.F-08-06-2026-start
            # The ACK's own "airtime" has now genuinely elapsed (the
            # yield above) - mark it DELIVERED here, not when it was
            # constructed in sent_completed() (that was still mid-flight
            # at env.now - get_ack_frame_time()).
            if self.frame_to_send.ack_packet is not None:
                self.frame_to_send.ack_packet.status = "DELIVERED"
                self.frame_to_send.ack_packet.delivered_at = self.env.now
            # Rashed-Step 8.F-08-06-2026-end
            return True
        else:
            yield self.env.timeout(self.times.ack_timeout)
            return False
    # Rashed-Step 3.F-01-13-2026-end

    def check_collision(self):  # check if the collision occurred

        # if (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) > 1 or (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) == 0:
        #     self.sent_failed()
        #     return False
        # else:
        #     self.sent_completed()
        #     return True
        # Rashed-Step 3.F-12-26-2025-start
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
        # Rashed-Step 3.F-12-26-2025-end

    # Rashed-Step 3.D-12-26-2025-start
    #def generate_new_back_off_time(self, failed_transmissions_in_row):

        
        # upper_limit = (pow(2, failed_transmissions_in_row) * (
        #         self.cw_min + 1) - 1)  # define the upper limit basing on  unsuccessful transmissions in the row
        # upper_limit = (
        #     upper_limit if upper_limit <= self.cw_max else self.cw_max)  # set upper limit to CW Max if is bigger then this parameter
        # back_off = random.randint(0, upper_limit)  # draw the back off value
        # self.channel.backoffs[back_off][self.channel.n_of_stations] += 1  # store drawn value for future analyzes
        # return back_off * self.times.t_slot


    def generate_new_back_off_slots(self, failed_transmissions_in_row)-> int:
        upper_limit = (pow(2, failed_transmissions_in_row) * (self.cw_min + 1) - 1)# define the upper limit basing on  unsuccessful transmissions in the row
        upper_limit = upper_limit if upper_limit <= self.cw_max else self.cw_max
        back_off = random.randint(0, upper_limit)  # draw the back off value
        self.channel.backoffs[back_off][self.channel.n_of_stations] += 1  # store drawn value for future analyzes
        return back_off

    


    # Rashed-Step 3.D-12-26-2025-end

    def generate_new_frame(self, packet: Optional[Packet] = None):
        # Rashed-Step pre_5.C-02-06-2026-start
        # BUGFIX: frame duration was hardcoded to 5400us, so config.mcs had
        # zero effect on airtime or on the SINR window used for capture.
        # Times.get_ppdu_frame_time() already derives duration from
        # payload size + MCS - re-enabled it.
        # Rashed-Step 8.C-08-06-2026-start
        # UPGRADE: duration (and the reported data_size) now come from
        # the actual dequeued Packet's payload_bytes when one is passed
        # in, instead of always assuming self.config.data_size. packet
        # is None only for legacy/defensive call sites (there are none
        # left in wifi.py itself as of this change, but keeping the
        # default keeps this method safely callable standalone, e.g.
        # from a test) - falls back to config.data_size, which is
        # exactly the old behavior. Note: pass packet.payload_bytes, NOT
        # packet.total_bytes() - Times.get_ppdu_frame_time() already
        # adds the MAC header (Times.mac_overhead) internally, so
        # total_bytes() would double-count the header that
        # _make_packet() derived from that same constant.
        payload_bytes = packet.payload_bytes if packet is not None else self.config.data_size
        frame_length = self.times.get_ppdu_frame_time(payload_bytes)
        # Rashed-Step 8.C-08-06-2026-end
        # Rashed-Step pre_5.C-02-06-2026-end

        # Rashed-Step 2.D_1-01-08-2026-start

        rx_sta = random.choice(self.sta_list) if self.sta_list else None

        fr = Frame (frame_length, self.name, self.col, payload_bytes, self.env.now)

        # Rashed-Step 5.G-02-06-2026-start
        # current_pos() instead of self.pos/rx_sta.pos - this is a
        # diagnostic snapshot only (not used for the actual send_frame()
        # success decision, which recomputes its own tx_pos/rx_pos fresh
        # right at transmission time - see send_frame()), but should
        # still reflect where things actually are *now* if mobility is
        # enabled, not stale construction-time positions.
        my_pos = self.current_pos()
        fr.tx_pos = my_pos
        if rx_sta is not None:
            rx_pos = rx_sta.current_pos()
            fr.rx_name = rx_sta.name
            fr.rx_pos = rx_pos
            fr.distance_m = dist(my_pos, rx_pos)
            # Rashed-Step 5.G-02-06-2026-end
            # Rashed-Step 5.B-02-06-2026-start
            # Route through channel.shadow_db() so this diagnostic pr_dbm
            # (logged on the Frame, not used for the actual success
            # decision) reflects the same per-link shadow value sinr_db()
            # will use at transmission time.
            fr.pr_dbm = rx_power_dbm(
                tx_power_dbm=self.config.tx_power_dbm,
                d_m=fr.distance_m,
                f_hz=self.config.f_ghz,
                n=self.config.pl_exp,
                shadow_db=self.channel.shadow_db(self.name, fr.rx_pos)
            )
            # Rashed-Step 5.B-02-06-2026-end

        return fr

        #return Frame(frame_length, self.name, self.col, self.config.data_size, self.env.now)

        # Rashed-Step 2.D_1-01-08-2026-end

    # Rashed-Step 5.D-02-06-2026-start
    def required_sinr_db(self) -> float:
        """
        Required SINR for this AP's configured MCS, or the flat override
        if config.wifi_sinr_thr_db_override is set.
        """
        if self.config.wifi_sinr_thr_db_override is not None:
            return self.config.wifi_sinr_thr_db_override
        return mcs_sinr_threshold_db(WIFI_MCS_SINR_THRESHOLDS_DB, self.config.mcs)
    # Rashed-Step 5.D-02-06-2026-end

    def sent_failed(self):
        log(self, "There was a collision")
        self.frame_to_send.number_of_retransmissions += 1
        self.channel.failed_transmissions += 1
        self.failed_transmissions += 1
        self.failed_transmissions_in_row += 1
        log(self, self.channel.failed_transmissions)
        # Rashed-Step 8.B-08-06-2026-start
        if self.frame_to_send.packet is not None:
            self.frame_to_send.packet.retry_count = self.frame_to_send.number_of_retransmissions
        # Rashed-Step 8.B-08-06-2026-end
        if self.frame_to_send.number_of_retransmissions > self.config.r_limit:
            # Rashed-Step 8.B-08-06-2026-start
            # UPGRADE: the old packet gave up on/exceeded its retry
            # limit here and used to just vanish with no record beyond
            # the aggregate failed_transmissions counter. Now marked
            # DROPPED before being replaced.
            # Rashed-Step 8.B-08-06-2026-end
            if self.frame_to_send.packet is not None:
                self.frame_to_send.packet.status = "DROPPED"
            # Rashed-Step 8.E-08-06-2026-start
            # UPGRADE: saturated mode (the default) keeps the EXACT old
            # inline behavior - build the replacement frame/packet right
            # here, synchronously, byte-identical to every pre-8.E run.
            # This matters beyond just "no blocking": generate_new_frame()
            # calls random.choice(self.sta_list), and moving that call to
            # a different point in this generator's yield sequence (even
            # one that doesn't itself consume simulated time) shifts its
            # position relative to OTHER processes' events at the same
            # simulated instant, which cascades into a different random-
            # draw ordering downstream - confirmed empirically: an
            # earlier version of this fix that unconditionally deferred
            # to start()'s inner loop reproduced the mixed WiFi+NR-U and
            # NR-U-only baselines exactly, but shifted the WiFi-only N=5
            # collision baseline (PCOLL 0.6438->0.6462, a different but
            # equally valid run, not a bug - same class of divergence
            # documented in Step 8.D) even with r_limit at its DEFAULT
            # value and no new CLI flags set at all. That violated this
            # project's "no new flags -> byte-identical" convention, so
            # only poisson/cbr mode (a genuinely new code path with no
            # pre-8.E baseline to preserve) defers to the queue; saturated
            # mode is untouched.
            if self.traffic_config.mode == "saturated":
                new_packet = self._make_packet()
                self.frame_to_send = self.generate_new_frame(new_packet)
                self.frame_to_send.packet = new_packet
            else:
                # This method stays SYNCHRONOUS (not a generator) even
                # for this branch - it's called from deep inside
                # send_frame()'s try block, BEFORE that transmission's
                # own housekeeping (unregister_tx, the ACK-timeout wait)
                # has run. Blocking here to wait on the queue would delay
                # that unrelated bookkeeping. Instead, just flag that a
                # fresh packet is needed and let start()'s inner retry
                # loop pick it up via _next_packet() - genuinely blocking,
                # but only AFTER send_frame() has fully finished this
                # attempt and returned. See start() for where the flag is
                # consumed.
                self._need_new_packet = True
            # Rashed-Step 8.E-08-06-2026-end
            self.failed_transmissions_in_row = 0

    def sent_completed(self):
        log(self, f"Successfully sent frame, waiting ack: {self.times.get_ack_frame_time()}")
        self.frame_to_send.t_end = self.env.now
        self.frame_to_send.t_to_send = (self.frame_to_send.t_end - self.frame_to_send.t_start)
        self.channel.succeeded_transmissions += 1
        self.succeeded_transmissions += 1
        self.failed_transmissions_in_row = 0
        self.channel.bytes_sent += self.frame_to_send.data_size
        # Rashed-Step 8.B-08-06-2026-start
        if self.frame_to_send.packet is not None:
            self.frame_to_send.packet.status = "DELIVERED"
            self.frame_to_send.packet.delivered_at = self.env.now
        # Rashed-Step 8.B-08-06-2026-end
        # Rashed-Step 8.F-08-06-2026-start
        # Construct the ACK packet now (data delivery just confirmed) -
        # status stays PENDING (Packet's own default) until send_frame()
        # finishes waiting out the ACK's on-air time and marks it
        # DELIVERED (see send_frame(), right after the
        # get_ack_frame_time() timeout). No ack_packet is ever created
        # on the failure path (sent_failed()) - matches real 802.11
        # semantics: a failed frame gets no ACK at all, the sender just
        # times out.
        self.frame_to_send.ack_packet = self._make_ack_packet(self.frame_to_send.packet)
        # Rashed-Step 8.F-08-06-2026-end
        # Rashed-Step 5.1-02-06-2026-start
        # BUGFIX: this used to also do
        # self.channel.airtime_data[self.name] += self.frame_to_send.frame_time
        # here, double-counting against channel.unregister_tx(tx,
        # success=...) in send_frame()'s finally block, which now records
        # airtime_data on success. Removed - unregister_tx is the single
        # source of truth.
        # Rashed-Step 5.1-02-06-2026-end
        return True
    
