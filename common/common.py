import logging
import csv
import os
import random
import time
import pandas as pd
import simpy


# Rashed-Step 1.A-12-26-2025-start
from typing import Tuple
import math
# Rashed-Step 1.A-12-26-2025-end


from dataclasses import dataclass, field
from typing import Dict, List, Optional

# from .Times import *
from datetime import datetime

# Rashed-Step 8.A-08-06-2026-start
from common.packet import Packet
# Rashed-Step 8.A-08-06-2026-end


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


# Rashed-Step 1.A-12-26-2025-start
Pos = Tuple[float, float]

def dist(a: Pos, b: Pos) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])

def rand_pos(area_w: float, area_h: float) -> Pos:
    return (random.uniform(0, area_w), random.uniform(0, area_h))

# Rashed-Step 1.A-12-26-2025-end



# Rashed-Step 2.B-12-30-2025-start
# @dataclass()
# class Frame:
#     frame_time: int  # time of the frame
#     station_name: str  # name of the owning it station
#     col: str  # output color
#     data_size: int  # payload size
#     t_start: int  # generation time
#     number_of_retransmissions: int = 0  # retransmissions count
#     t_end: int = None  # sent time
#     t_to_send: int = None  # how much time it took to sent successfully

#     def __repr__(self):
#         return (self.col + "Frame: start=%d, end=%d, frame_time=%d, retransmissions=%d"
#                 % (self.t_start, self.t_end, self.t_to_send, self.number_of_retransmissions)
#                 )
 # Rashed-Step 2.B-12-30-2025-end   

# Rashed-Step 2.B_1-12-30-2025-start
@dataclass()
class Frame:
    frame_time: int
    station_name: str
    col: str
    data_size: int
    t_start: int
    number_of_retransmissions: int = 0
    t_end: int = None
    t_to_send: int = None

    # NEW: topology + link info
    tx_pos: Pos = None
    rx_name: str = None
    rx_pos: Pos = None
    distance_m: float = None
    pr_dbm: float = None

    # Rashed-Step 8.A-08-06-2026-start
    # Optional reference to the Packet this Frame is carrying - None by
    # default so every existing caller that constructs a Frame directly
    # (there are none outside wifi.py/attacker/*.py, but this keeps the
    # default fully backward compatible either way) is unaffected. Step
    # 8.B is what actually populates this field.
    packet: Optional[Packet] = None
    # Rashed-Step 8.A-08-06-2026-end
# Rashed-Step 2.B_1-12-30-2025-end