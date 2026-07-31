


from common.common import *
from Times import *
from common.common import Pos

# Rashed-Step pre_5.D-02-06-2026-start
# BUGFIX: this class was never actually wired into simulation.py's topology
# builder (--rogue True printed "Rogue WiFi" and built an unused Config
# object, but no RogueWiFiCAD was ever instantiated), and it predates
# Step 1-4: no self.pos, no PHY fields (tx_power_dbm/f_ghz/pl_exp), and its
# channel sensing + collision logic still used the retired
# channel.tx_lock / channel.tx_list model instead of the ED-sensing
# (channel.is_busy) + SINR-gated (channel.register_tx/sinr_db) pipeline
# WiFi/NR-U now use. This pass: (1) gives it position + PHY config so it can
# register a real ActiveTx and be sensed/interfered with like everyone else,
# (2) reconnects it in simulation.py so --rogue True actually spawns it,
# (3) ports its channel-busy check and success/failure decision onto the
# same primitives wifi.py uses. The attack TIMING model itself (observe,
# then fire near a slot boundary at attack_slot_us cadence, matching the
# CAD-attack paper's mini-slot targeting) is preserved, not redesigned -
# that is research-sensitive and deserves its own pass with your input.
from common.common_phy import dist, rx_power_dbm
from channel.channel import ActiveTx
# Rashed-Step pre_5.D-02-06-2026-end




@dataclass()
class ConfigRoguesWiFi:
    data_size: int = 20  # size od payload in b
    cw_min: int = 15  # min cw window size
    cw_max: int = 63  # max cw window size 1023 def
    r_limit: int = 7
    mcs: int = 7

    # Rashed-Step pre_5.D-02-06-2026-start
    # PHY params mirroring wifi.Config - previously missing entirely.
    tx_power_dbm: float = 20.0
    f_ghz: float = 5.18e9
    pl_exp: float = 3.0        # indoor-ish
    ed_threshold_dbm: float = -62.0
    attacker_sinr_thr_db: float = 10.0
    attack_slot_us: int = 500  # attack cadence (~AIFS-scale, CAD paper Fig.1)
    # Rashed-Step pre_5.D-02-06-2026-end



class RogueWiFiCAD:
    def __init__(
            self,
            env: simpy.Environment,
            name: str,
            channel: dataclass,
            # Rashed-Step pre_5.D-02-06-2026-start
            pos: Pos,
            # Rashed-Step pre_5.D-02-06-2026-end
            config: ConfigRoguesWiFi = ConfigRoguesWiFi(),
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
        env.process(self.start())  # starting simulation process
        self.process = None  # waiting back off process
        self.channel.airtime_data.update({name: 0})
        self.channel.airtime_control.update({name: 0})
        self.first_interrupt = False
        self.back_off_time = 0
        self.start = 0

        # Rashed-Step pre_5.D-02-06-2026-start
        self.pos = pos
        self.next_slot = 0
        # Rashed-Step pre_5.D-02-06-2026-end

    def start(self):
        # Rashed-Step pre_5.D-02-06-2026-start
        while True:
            self.frame_to_send = self.generate_new_frame()
            yield self.env.process(self.wait_for_slot_boundary())
            yield self.env.process(self.send_frame())
        # Rashed-Step pre_5.D-02-06-2026-end

    # Rashed-Step pre_5.D-02-06-2026-start
    def wait_for_slot_boundary(self):
        """
        Replaces the old observe_transmission()/tx_lock warm-up loop.
        Senses energy at the attacker's own position with the same ED
        primitive WiFi/NR-U use (channel.is_busy), waits for it to go idle,
        then aligns to the periodic attack_slot_us cadence used to target
        mini-slot boundaries per the CAD attack model.
        """
        while self.channel.is_busy(self.pos, self.config.ed_threshold_dbm, exclude_tx_id=self.name):
            log(self, "Attacker sensing busy channel, waiting...")
            yield self.channel.state_changed

        if self.next_slot <= self.env.now:
            self.next_slot = self.env.now + self.config.attack_slot_us

        wait_time = max(0, self.next_slot - self.env.now)
        yield self.env.timeout(wait_time)
        self.next_slot += self.config.attack_slot_us

    def send_frame(self):
        """
        Registers a real ActiveTx (so victims sense/interfere with this
        signal via the shared channel model) and decides its own
        success/failure the same way wifi.py does: SINR at rx_pos vs a
        threshold. The attacker has no legitimate receiver, so rx_pos is
        just its own position - this only affects the attacker's own
        succeeded/failed bookkeeping, not the interference it causes to
        others (that's computed from *their* rx_pos in their own sinr_db
        calls, same as any other ActiveTx).
        """
        tx_start = self.env.now
        tx = ActiveTx(
            tx_id=self.name,
            tx_pos=self.pos,
            rx_pos=self.pos,
            tx_start=tx_start,
            tx_power_dbm=self.config.tx_power_dbm,
            f_hz=self.config.f_ghz,
            pl_exp=self.config.pl_exp,
            t_end=tx_start + self.frame_to_send.frame_time,
            tech="WiFi"
        )
        self.channel.register_tx(tx)

        was_sent = False
        try:
            yield self.env.timeout(self.frame_to_send.frame_time)
            sinr = self.channel.sinr_db(tx)
            log(self, f"Attack TX SINR(dB) = {sinr:.2f} dB")
            was_sent = (sinr >= self.config.attacker_sinr_thr_db)
            if was_sent:
                self.sent_completed()
            else:
                self.sent_failed()
        finally:
            yield self.env.timeout(0)
            self.channel.unregister_tx(tx)

        return was_sent
    # Rashed-Step pre_5.D-02-06-2026-end

    # Rashed-Step pre_5.D-02-06-2026-start
    # Retired: old tx_lock / tx_list based wait_back_off, send_frame,
    # observe_transmission, wait_to_transmit, send_dummy_frame and
    # check_collision. These relied on channel.tx_lock and channel.tx_list,
    # which Step 3/4 removed from the WiFi/NR-U CCA and collision decisions
    # (replaced by channel.is_busy / channel.register_tx / channel.sinr_db).
    # Kept here as comments for reference rather than deleted.
    #
    # def wait_to_transmit(self,waiting_time):
    #     yield self.env.timeout(self.waiting_time)
    #
    # def observe_transmission(self):
    #     observer_time=20000
    #     while self.env.now < observer_time+1000:
    #         try:
    #             with self.channel.tx_lock.request() as req:
    #                 yield req
    #             self.first_interrupt = True
    #             self.start = self.env.now
    #             self.channel.back_off_list.append(self)
    #             yield self.env.timeout(observer_time)
    #             self.channel.back_off_list.remove(self)
    #         except simpy.Interrupt:
    #             if self.first_interrupt and self.start is not None:
    #                 current_time = self.env.now
    #                 self.next_slot = current_time+500
    #                 self.waiting_time = self.next_slot-current_time-20
    #
    # def send_dummy_frame(self):
    #     self.channel.tx_list.append(self)
    #     res = self.channel.tx_queue.request(priority=(big_num - self.frame_to_send.frame_time))
    #     if self.channel.n_of_eNB>0:
    #         yield self.env.timeout(10000)
    #         return True
    #     else:
    #         yield self.env.timeout(10000)
    #         return True
    #
    # def wait_back_off(self):
    #     self.back_off_time = self.generate_new_back_off_time(self.failed_transmissions_in_row)
    #     while self.back_off_time > -1:
    #         try:
    #             with self.channel.tx_lock.request() as req:
    #                 yield req
    #             self.back_off_time += Times.t_difs
    #             self.first_interrupt = True
    #             self.start = self.env.now
    #             self.channel.back_off_list.append(self)
    #             yield self.env.timeout(self.back_off_time)
    #             self.back_off_time = -1
    #             self.channel.back_off_list.remove(self)
    #         except simpy.Interrupt:
    #             if self.first_interrupt and self.start is not None:
    #                 all_waited = self.env.now - self.start
    #                 if all_waited <= Times.t_difs:
    #                     self.back_off_time -= Times.t_difs
    #                 else:
    #                     back_waited = all_waited - Times.t_difs
    #                     slot_waited = int(back_waited / Times.t_slot)
    #                     self.back_off_time -= ((slot_waited * Times.t_slot) + Times.t_difs)
    #                 self.first_interrupt = False
    #
    # def check_collision(self):
    #     if (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) > 1 or (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) == 0:
    #         self.sent_failed()
    #         return False
    #     else:
    #         self.sent_completed()
    #         return True
    # Rashed-Step pre_5.D-02-06-2026-end

    def generate_new_back_off_time(self, failed_transmissions_in_row):
        upper_limit = (pow(2, failed_transmissions_in_row) * (
                self.cw_min + 1) - 1)  # define the upper limit basing on  unsuccessful transmissions in the row
        upper_limit = (
            upper_limit if upper_limit <= self.cw_max else self.cw_max)  # set upper limit to CW Max if is bigger then this parameter
        back_off = random.randint(0, upper_limit)  # draw the back off value
        self.channel.backoffs[back_off][self.channel.n_of_stations] += 1  # store drawn value for future analyzes
        return back_off * self.times.t_slot

    def generate_new_frame(self):
        # Rashed-Step pre_5.D-02-06-2026-start
        # frame_length=20 is intentional here (tiny "interference signal"
        # per the CAD attack model, matching config.data_size=20) - unlike
        # WiFi's old hardcoded 5400, this one isn't a bug.
        frame_length = 20
        # Rashed-Step pre_5.D-02-06-2026-end
        return Frame(frame_length, self.name, self.col, self.config.data_size, self.env.now)

    def sent_failed(self):
        log(self, "There was a collision")
        self.frame_to_send.number_of_retransmissions += 1
        self.channel.failed_transmissions += 1
        self.failed_transmissions += 1
        self.failed_transmissions_in_row += 1
        log(self, self.channel.failed_transmissions)
        if self.frame_to_send.number_of_retransmissions > self.config.r_limit:
            self.frame_to_send = self.generate_new_frame()
            self.failed_transmissions_in_row = 0

    def sent_completed(self):
        log(self, f"Successfully sent frame, waiting ack: {self.times.get_ack_frame_time()}")
        self.frame_to_send.t_end = self.env.now
        self.frame_to_send.t_to_send = (self.frame_to_send.t_end - self.frame_to_send.t_start)
        self.channel.succeeded_transmissions += 1
        self.succeeded_transmissions += 1
        self.failed_transmissions_in_row = 0
        self.channel.bytes_sent += self.frame_to_send.data_size
        self.channel.airtime_data[self.name] += self.frame_to_send.frame_time
        return True
