from common import *
from Times import *



#Calculating channel Occupancy differently

class SimCalculation():
    def __init__(self, channel: dataclass):
        #New calculation of Channel Occupancy
        self.channel = channel
        self.new_channel_occupancy_wifi: Dict[int, int] = field(default_factory=dict)
        self.new_channel_occupancy_nru: Dict[int, int] = field(default_factory=dict)

        

    
    @staticmethod
    def insert_channel_occupancy_nru(self, time, channel_occupancy):

        if time in SimCalculation.new_channel_occupancy_nru and (time in SimCalculation.new_channel_occupancy_wifi and SimCalculation.new_channel_occupancy_wifi[time]>channel_occupancy):

            self.new_channel_occupancy_nru[time] = self.new_channel_occupancy_wifi[time]

        else:
            self.new_channel_occupancy_nru[time] = channel_occupancy 

    @staticmethod


    @staticmethod
    def get_normalized_occupancy(self, simulation_time):

        total_channel_occupancy_nru=0
        total_channel_occupancy_wifi=0

        for key,value in self.new_channel_occupancy_nru.items():
            total_channel_occupancy_nru += value
        
        for key_value in self.new_channel_occupancy_wifi.items():
            total_channel_occupancy_wifi+= value
        

        self.channel.normalized_channel_occupancy_nru = total_channel_occupancy_nru/simulation_time
        self.channel.normalized_channel_occupancy_wifi = total_channel_occupancy_wifi/simulation_time




