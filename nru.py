from common import *
from Times import *


@dataclass()
class Config_NR:
    deter_period: int = 16  # time used for waiting in prioritization period, microsec
    observation_slot_duration: int = 9  # observation slot in mikros
    # synchronization slot lenght in mikros
    synchronization_slot_duration: int = 500
    max_sync_slot_desync: int = 500
    min_sync_slot_desync: int = 0
    # channel access class related:
    M: int = 3  # amount of observation slots to wait after deter perion in prioritization period
    cw_min: int = 32
    cw_max: int = 32
    mcot: int = 6  # max ocupancy time


@dataclass()
class Transmission_NR:
    transmission_time: int
    enb_name: str  # name of the owning it station
    col: str
    t_start: int  # generation time / transmision start (including RS)
    airtime: int  # time spent on sending data
    rs_time: int  # time spent on sending reservation signal before data
    number_of_retransmissions: int = 0
    t_end: int = None  # sent time / transsmision end = start + rs_time + airtime
    t_to_send: int = None
    collided: bool = False  # true if transmission colided with another one


class Gnb:
    def __init__(
            self,
            env: simpy.Environment,
            name: str,
            channel: dataclass,
            config_nr: Config_NR = Config_NR(),
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
        #channel access delay calculation
        self.channel_access_delay = 0
        self.channel_access_attempt_start = 0

        

        #NR-U minislot specific busy count log
        #self.minislot_log_start_time = 0
        

    def start(self):

        #yield self.env.timeout(self.desync)
        while True:
            # self.transmission_to_send = self.gen_new_transmission()
            was_sent = False
            while not was_sent:
                if gap:
                    #print("Backoff Starts ", self.env.now)
                    transmission_prob = random.randint(0, 100)
                    #print(self.channel.nru_transmission_probability)

                    if transmission_prob <= self.channel.nru_transmission_probability:
                        # print("now ",self.env.now)
                        # print("transmission prob value ",transmission_prob, " and transmitting")
                        self.process = self.env.process(self.wait_back_off_gap())
                        yield self.process
                        was_sent = yield self.env.process(self.send_transmission())
                    else:
                        #print("now ",self.env.now)
                        # print("transmission prob value ",transmission_prob, " and not transmitting")
                        #attack model 1
                        #attacker_start_time = 495
                        #attack model 2
                        attacker_start_time = random.randint(0,495)
                        #attack model 3
                        #attacker_start_time = random.randint(55,495)
                        self.log_nru_minislot_busy_count(attacker_start_time)
                        self.process = self.env.process(self.wait_back_off_gap())
                        yield self.process
                        was_sent = yield self.env.process(self.do_not_transmit())
                    #print("Current time: ",self.env.now," Next slot boundary: ", self.next_sync_slot_boundry)
                    # transmission_prob = random.randint(0, 100)
                    # attacker_start_time = random.randint(0,500)
                    # self.attacker_trigger_time = self.env.now+attacker_start_time
                    # self.process = self.env.process(self.wait_back_off_gap())
                    # yield self.process

                    # if transmission_prob <= self.channel.nru_transmission_probability:
                    #     was_sent = yield self.env.process(self.send_transmission())
                    # else:
                    #     was_sent = yield self.env.process(self.do_not_transmit())
                    
                    # self.process = self.env.process(self.wait_back_off_gap())
                    # yield self.process

                    # if transmission_prob <= self.channel.nru_transmission_probability:
                    #     was_sent = yield self.env.process(self.send_transmission())
                    # else:
                        
                else:
                    self.process = self.env.process(self.wait_back_off())
                    yield self.process
                    was_sent = yield self.env.process(self.send_transmission())

    def do_not_transmit(self):
        
        time_remaining = self.next_sync_slot_boundry-self.env.now
        #print("Time remaining ", time_remaining)
        yield self.env.timeout(time_remaining)
        #print("Now ", self.env.now)
        return False

    def wait_back_off_gap(self):
        self.channel_access_attempt_start = self.env.now
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

                # log(self,
                #     f'Backoff = {self.back_off_time} , and time to next slot: {self.time_to_next_sync_slot}')
                while self.back_off_time >= self.time_to_next_sync_slot:
                    self.time_to_next_sync_slot += self.config_nr.synchronization_slot_duration
                    # log(self,
                    #     f'Backoff > time to sync slot: new time to next possible sync +1000 = {self.time_to_next_sync_slot}')

                gap_time = self.time_to_next_sync_slot - self.back_off_time
                # log(self, f"Waiting gap period of : {gap_time} us")
                assert gap_time >= 0, "Gap period is < 0!!!"

                yield self.env.timeout(gap_time)
                # log(self, f"Finished gap period")

                self.first_interrupt = True

                self.start_nr = self.env.now  # store the current simulation time

                # log(self,
                #     f'Channels in use by {self.channel.tx_lock.count} stations')

                # checking if channel if idle
                if (len(self.channel.tx_list_NR) + len(self.channel.tx_list)) > 0:
                    # log(self, 'Channel busy -- waiting to be free')
                    with self.channel.tx_lock.request() as req:
                        yield req
                    # log(self, 'Finished waiting for free channel - restarting backoff procedure')

                else:
                    # log(self, 'Channel free')
                    # log(self,
                    #     f"Starting to wait backoff: ({self.back_off_time}) us...")
                    # join the list off stations which are waiting Back Offs
                    self.channel.back_off_list_NR.append(self)
                    self.waiting_backoff = True

                    # join the environment action queue
                    yield self.env.timeout(self.back_off_time)

                    # log(self, f"Backoff waited, sending frame...")
                    self.back_off_time = -1  # leave the loop
                    self.waiting_backoff = False

                    self.channel.back_off_list_NR.remove(
                        self)  # leave the waiting list as Backoff was waited successfully

            except simpy.Interrupt:  # handle the interruptions from transmitting stations
                # log(self, "Waiting was interrupted")
                if self.first_interrupt and self.start is not None and self.waiting_backoff is True:
                    # log(self, "Backoff was interrupted, waiting to resume backoff...")
                    already_waited = self.env.now - self.start_nr

                    if already_waited <= prioritization_period_time:
                        self.back_off_time -= prioritization_period_time
                        # log(self,
                        #     f"Interrupted in PP time {prioritization_period_time}, backoff {self.back_off_time}")
                    else:
                        slots_waited = int(
                            (already_waited - prioritization_period_time) / self.config_nr.observation_slot_duration)
                        # self.back_off_time -= already_waited  # set the Back Off to the remaining one
                        self.back_off_time -= (
                            (slots_waited * self.config_nr.observation_slot_duration) + prioritization_period_time)
                        # log(self,
                        #     f"Completed slots(9us) {slots_waited} = {(slots_waited * self.config_nr.observation_slot_duration)}  plus PP time {prioritization_period_time}")
                        # log(self, f"Backoff decresed by {(slots_waited * self.config_nr.observation_slot_duration) + prioritization_period_time} new Backoff {self.back_off_time}")

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
                # log(self,
                #     f"Starting to wait backoff (with PP): ({self.back_off_time}) us...")
                start = self.env.now  # store the current simulation time
                # join the list off stations which are waiting Back Offs
                self.channel.back_off_list_NR.append(self)

                # join the environment action queue
                yield self.env.timeout(self.back_off_time)

                # log(self, f"Backoff waited, sending frame...")
                self.back_off_time = -1  # leave the loop

                # leave the waiting list as Backoff was waited successfully
                self.channel.back_off_list_NR.remove(self)

            except simpy.Interrupt:  # handle the interruptions from transmitting stations
                # log(self, "Backoff was interrupted, waiting to resume backoff...")
                if self.first_interrupt and start is not None:
                    already_waited = self.env.now - start

                    if already_waited <= prioritization_period_time:
                        self.back_off_time -= prioritization_period_time
                        # log(self,
                        #     f"Interrupted in PP time {prioritization_period_time}, backoff {self.back_off_time}")
                    else:
                        slots_waited = int(
                            (already_waited - prioritization_period_time) / self.config_nr.observation_slot_duration)
                        # self.back_off_time -= already_waited  # set the Back Off to the remaining one
                        self.back_off_time -= (
                            (slots_waited * self.config_nr.observation_slot_duration) + prioritization_period_time)
                        # log(self,
                        #     f"Completed slots(9us) {slots_waited} = {(slots_waited * self.config_nr.observation_slot_duration)}  plus PP time {prioritization_period_time}")
                        # log(self, f"Backoff decresed by {(slots_waited * self.config_nr.observation_slot_duration) + prioritization_period_time} new Backoff {self.back_off_time}")

                    self.first_interrupt = False
                    self.waiting_backoff = False

    def sync_slot_counter(self):
        # Process responsible for keeping the next sync slot boundry timestamp
        self.desync = random.randint(
            self.config_nr.min_sync_slot_desync, self.config_nr.max_sync_slot_desync)
        self.next_sync_slot_boundry = self.desync
        # log(self, f"Selected random desync to {self.desync} us")
        # waiting randomly chosen desync time
        yield self.env.timeout(self.desync)
        #print("Sync slot counter ending at ",self.env.now)
        self.channel.minislot_log_start_time = self.env.now
        while True:
            self.next_sync_slot_boundry += self.config_nr.synchronization_slot_duration
            # log(self,
            #     f"Next synch slot boundry is: {self.next_sync_slot_boundry}")
            #print(f"Next synch slot boundry is: ",self.next_sync_slot_boundry)
            yield self.env.timeout(self.config_nr.synchronization_slot_duration)

    def send_transmission(self):
        # add station to currently transmitting list
        self.channel.tx_list_NR.append(self)
        self.transmission_to_send = self.gen_new_transmission()
        res = self.channel.tx_queue.request(priority=(
            big_num - self.transmission_to_send.transmission_time))  # create request basing on this station frame length

        try:
            result = yield res | self.env.timeout(
                0)  # try to hold transmitting lock(station with the longest frame will get this)

            if res not in result:  # check if this station got lock, if not just wait you frame time
                raise simpy.Interrupt("There is a longer frame...")
            
            self.log_channel_access_delay()

            with self.channel.tx_lock.request() as lock:  # this station has the longest frame so hold the lock
                yield lock

                # stop all station which are waiting backoff as channel is not idle
                for station in self.channel.back_off_list:
                    if station.process.is_alive:
                        station.process.interrupt()
                for gnb in self.channel.back_off_list_NR:  # stop all station which are waiting backoff as channel is not idle
                    if gnb.process.is_alive:
                        gnb.process.interrupt()

                # log(self,
                #     f'Transmission will be for: {self.transmission_to_send.transmission_time} time')
                #print('GNB is transmitting now at ', self.env.now)

                yield self.env.timeout(self.transmission_to_send.transmission_time)

                # channel idle, clear backoff waiting list
                self.channel.back_off_list_NR.clear()
                was_sent = self.check_collision()  # check if collision occurred

                if was_sent:  # transmission successful
                    self.channel.airtime_control_NR[self.name] += self.transmission_to_send.rs_time
                    # log(self,
                    #     f"adding rs time to control data: {self.transmission_to_send.rs_time}")
                    self.channel.airtime_data_NR[self.name] += self.transmission_to_send.airtime
                    # log(self,
                    #     f"adding data airtime to data: {self.transmission_to_send.airtime}")
                    self.channel.tx_list_NR.clear()  # clear transmitting list
                    self.channel.tx_list.clear()
                    # leave the transmitting queue
                    self.channel.tx_queue.release(res)
                    return True

            # there was collision
            self.channel.tx_list_NR.clear()  # clear transmitting list
            self.channel.tx_list.clear()
            self.channel.tx_queue.release(res)  # leave the transmitting queue
            self.channel.tx_queue = simpy.PreemptiveResource(self.env,
                                                             capacity=1)  # create new empty transmitting queue
            # yield self.env.timeout(self.times.ack_timeout)
            return False

        except simpy.Interrupt:  # this station does not have the longest frame, waiting frame time
            yield self.env.timeout(self.transmission_to_send.transmission_time)

        was_sent = self.check_collision()
        return was_sent

    def check_collision(self):  # check if the collision occurred

        if gap:
            # if (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) > 1 and self.waiting_backoff is True:
            if (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) > 1 or (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) == 0:
                self.sent_failed()
                return False
            else:
                self.sent_completed()
                return True
        else:
            if (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) > 1 or (len(self.channel.tx_list) + len(self.channel.tx_list_NR)) == 0:
                self.sent_failed()
                return False
            else:
                self.sent_completed()
                return True

    def gen_new_transmission(self):
        transmission_time = self.config_nr.mcot * 1000  # transforming to usec
        if gap:
            rs_time = 0
        else:
            rs_time = self.next_sync_slot_boundry - self.env.now
        airtime = transmission_time - rs_time
        return Transmission_NR(transmission_time, self.name, self.col, self.env.now, airtime, rs_time)

    def generate_new_back_off_time(self, failed_transmissions_in_row):
        # BACKOFF TIME GENERATION
        upper_limit = (pow(2, failed_transmissions_in_row) * (
            self.cw_min + 1) - 1)  # define the upper limit basing on  unsuccessful transmissions in the row
        upper_limit = (
            upper_limit if upper_limit <= self.cw_max else self.cw_max)  # set upper limit to CW Max if is bigger then this parameter
        back_off = random.randint(0, upper_limit)  # draw the back off value
        # store drawn value for future analyzes
        self.channel.backoffs[back_off][self.channel.n_of_stations] += 1
        return back_off * self.config_nr.observation_slot_duration

    def sent_failed(self):
        # log(self, "There was a collision")
        self.transmission_to_send.number_of_retransmissions += 1
        self.channel.failed_transmissions_NR += 1
        self.failed_transmissions += 1
        self.failed_transmissions_in_row += 1
        # log(self, self.channel.failed_transmissions_NR)
        if self.transmission_to_send.number_of_retransmissions > 7:
            self.failed_transmissions_in_row = 0

    def sent_completed(self):
        # log(self, f"Successfully sent transmission")
        self.transmission_to_send.t_end = self.env.now
        self.transmission_to_send.t_to_send = (
            self.transmission_to_send.t_end - self.transmission_to_send.t_start)
        self.channel.succeeded_transmissions_NR += 1
        self.succeeded_transmissions += 1
        self.failed_transmissions_in_row = 0
        return True
    
    def log_channel_access_delay(self):

        self.channel_access_delay = self.env.now - self.channel_access_attempt_start
        self.channel.nru_channel_access_delays_log[self.env.now] = self.channel_access_delay

    
    def log_nru_minislot_busy_count(self,attacker_start_time):
        #print("Attack model 1 at ",self.env.now)
        busy_slot_time = (self.env.now-self.channel.minislot_log_start_time+attacker_start_time) % 500

        if busy_slot_time <= 495:
            busy_slot = (busy_slot_time//9)
        else:
            busy_slot = ((busy_slot_time-1)//9)-5
        
        self.channel.nru_minislot_busy_log[busy_slot] = self.channel.nru_minislot_busy_log[busy_slot]+1
