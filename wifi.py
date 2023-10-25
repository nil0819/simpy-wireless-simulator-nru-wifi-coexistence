from common import *
from Times import *




@dataclass()
class Config:
    data_size: int = 1472  # size od payload in b
    cw_min: int = 15  # min cw window size
    cw_max: int = 63  # max cw window size 1023 def
    r_limit: int = 7
    mcs: int = 7



class WiFi:
    def __init__(
            self,
            env: simpy.Environment,
            name: str,
            channel: dataclass,
            config: Config = Config(),
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

    def start(self):
        while True:
            self.frame_to_send = self.generate_new_frame()
            was_sent = False
            while not was_sent:
                self.process = self.env.process(self.wait_back_off())
                yield self.process
                # self.process = None
                was_sent = yield self.env.process(self.send_frame())
                # self.process = None

    def wait_back_off(self):
        #global start
        self.back_off_time = self.generate_new_back_off_time(
            self.failed_transmissions_in_row)  # generating the new Back Off time

        while self.back_off_time > -1:
            try:
                with self.channel.tx_lock.request() as req:  # waiting  for idle channel -- empty channel
                    yield req
                self.back_off_time += Times.t_difs  # add DIFS time
                log(self, f"Starting to wait backoff (with DIFS): ({self.back_off_time})u...")
                self.first_interrupt = True
                self.start = self.env.now  # store the current simulation time
                self.channel.back_off_list.append(self)  # join the list off stations which are waiting Back Offs

                yield self.env.timeout(self.back_off_time)  # join the environment action queue

                log(self, f"Backoff waited, sending frame...")
                self.back_off_time = -1  # leave the loop

                self.channel.back_off_list.remove(self)  # leave the waiting list as Backoff was waited successfully

            except simpy.Interrupt:  # handle the interruptions from transmitting stations
                if self.first_interrupt and self.start is not None:
                    #tak jest po mojemu:
                    log(self, "Waiting was interrupted, waiting to resume backoff...")
                    all_waited = self.env.now - self.start
                    if all_waited <= Times.t_difs:
                        self.back_off_time -= Times.t_difs
                        log(self, f"Interupted in DIFS ({Times.t_difs}), backoff {self.back_off_time}, already waited: {all_waited}")
                    else:
                        back_waited = all_waited - Times.t_difs
                        slot_waited = int(back_waited / Times.t_slot)
                        self.back_off_time -= ((slot_waited * Times.t_slot) + Times.t_difs)
                        log(self,
                            f"Completed slots(9us) {slot_waited} = {(slot_waited * Times.t_slot)}  plus DIFS time {Times.t_difs}")
                        log(self,
                            f"Backoff decresed by {((slot_waited * Times.t_slot) + Times.t_difs)} new Backoff {self.back_off_time}")
                    self.first_interrupt = False

    def send_frame(self):
        self.channel.tx_list.append(self)  # add station to currently transmitting list
        res = self.channel.tx_queue.request(
            priority=(big_num - self.frame_to_send.frame_time))  # create request basing on this station frame length

        try:
            result = yield res | self.env.timeout(
                0)  # try to hold transmitting lock(station with the longest frame will get this)
            if res not in result:  # check if this station got lock, if not just wait you frame time
                raise simpy.Interrupt("There is a longer frame...")


            with self.channel.tx_lock.request() as lock:  # this station has the longest frame so hold the lock
                yield lock


                for station in self.channel.back_off_list:  # stop all station which are waiting backoff as channel is not idle
                    if station.process.is_alive:
                        station.process.interrupt()
                for gnb in self.channel.back_off_list_NR:  # stop all station which are waiting backoff as channel is not idle
                    if gnb.process.is_alive:
                        gnb.process.interrupt()

                log(self, f'Starting sending frame: {self.frame_to_send.frame_time}')

                yield self.env.timeout(self.frame_to_send.frame_time)  # wait this station frame time
                self.channel.back_off_list.clear()  # channel idle, clear backoff waiting list
                was_sent = self.check_collision()  # check if collision occurred

                if was_sent:  # transmission successful
                    self.channel.airtime_control[self.name] += self.times.get_ack_frame_time()
                    yield self.env.timeout(self.times.get_ack_frame_time())  # wait ack
                    self.channel.tx_list.clear()  # clear transmitting list
                    self.channel.tx_list_NR.clear()
                    self.channel.tx_queue.release(res)  # leave the transmitting queue
                    return True

                # there was collision
                self.channel.tx_list.clear()  # clear transmitting list
                self.channel.tx_list_NR.clear()
                self.channel.tx_queue.release(res)  # leave the transmitting queue
                self.channel.tx_queue = simpy.PreemptiveResource(self.env,
                                                                 capacity=1)  # create new empty transmitting queue
                yield self.env.timeout(self.times.ack_timeout)  # simulate ack timeout after failed transmission
                return False

        except simpy.Interrupt:  # this station does not have the longest frame, waiting frame time
            yield self.env.timeout(self.frame_to_send.frame_time)

        was_sent = self.check_collision()

        if was_sent:  # check if collision occurred
            log(self, f'Waiting for ACK time: {self.times.get_ack_frame_time()}')
            yield self.env.timeout(self.times.get_ack_frame_time())  # wait ack
        else:
            log(self, "waiting ack timeout slave")
            yield self.env.timeout(Times.ack_timeout)  # simulate ack timeout after failed transmission
        return was_sent

    def check_collision(self):  # check if the collision occurred

        if (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) > 1 or (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) == 0:
            self.sent_failed()
            return False
        else:
            self.sent_completed()
            return True

    def generate_new_back_off_time(self, failed_transmissions_in_row):
        upper_limit = (pow(2, failed_transmissions_in_row) * (
                self.cw_min + 1) - 1)  # define the upper limit basing on  unsuccessful transmissions in the row
        upper_limit = (
            upper_limit if upper_limit <= self.cw_max else self.cw_max)  # set upper limit to CW Max if is bigger then this parameter
        back_off = random.randint(0, upper_limit)  # draw the back off value
        self.channel.backoffs[back_off][self.channel.n_of_stations] += 1  # store drawn value for future analyzes
        return back_off * self.times.t_slot

    def generate_new_frame(self):
        # frame_length = self.times.get_ppdu_frame_time()
        frame_length = 5400
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