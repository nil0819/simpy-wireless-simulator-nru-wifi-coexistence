import logging
import csv
import os
import random
import time
import pandas as pd
import simpy

from dataclasses import dataclass, field
from typing import Dict, List

# from .Times import *
from datetime import datetime


output_csv = "lool.csv"
file_log_name = f"{'log/'+datetime.today().strftime('%Y-%m-%d-%H-%M-%S')}.log"




colors = [
    "\033[30m",
    "\033[32m",
    "\033[31m",
    "\033[33m",
    "\033[34m",
    "\033[35m",
    "\033[36m",
    "\033[37m",
]  # colors to distinguish stations in output

typ_filename = "RS_coex_1sta_1wifi2.log"

logging.basicConfig(filename=file_log_name,
                    format='%(asctime)s %(message)s',
                    filemode='w')
logger = logging.getLogger()
logger.setLevel(logging.INFO)  # chose DEBUG to display stats in debug mode :)


def log(gnb, mes: str) -> None:
    logger.info(
        f"{gnb.col}Time: {gnb.env.now} Station: {gnb.name} Message: {mes}"
    )


gap = True

big_num = 100000  # some big number for quesing in peeemtive resources - big starting point



@dataclass()
class Frame:
    frame_time: int  # time of the frame
    station_name: str  # name of the owning it station
    col: str  # output color
    data_size: int  # payload size
    t_start: int  # generation time
    number_of_retransmissions: int = 0  # retransmissions count
    t_end: int = None  # sent time
    t_to_send: int = None  # how much time it took to sent successfully

    def __repr__(self):
        return (self.col + "Frame: start=%d, end=%d, frame_time=%d, retransmissions=%d"
                % (self.t_start, self.t_end, self.t_to_send, self.number_of_retransmissions)
                )