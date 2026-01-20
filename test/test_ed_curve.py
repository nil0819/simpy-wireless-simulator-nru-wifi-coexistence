# Rashed-Step 3.G_1-01-19-2026-start
import os
import sys
import simpy
import math

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

#from typing import Tuple, TypeAlias
from channel.channel import Channel, ActiveTx
from common.common_phy import dist
from common.common_phy import Pos





def make_channel(env):
    # minimal Channel init; adjust dicts if your Channel constructor requires keys
    return Channel(
        tx_queue=simpy.PriorityResource(env, capacity=1),
        tx_lock=simpy.Resource(env, capacity=1),
        n_of_stations=1,
        n_of_gNB=0,
        backoffs={},
        airtime_data={},
        airtime_control={},
        airtime_data_NR={},
        airtime_control_NR={}
    )

def run_once(distance_m, thr_dbm=-62.0):
    env = simpy.Environment()
    ch = make_channel(env)

    tx_pos = (0.0, 0.0)
    rx_pos = (distance_m, 0.0)

    tx = ActiveTx(
        tx_id="TX",
        tx_pos=tx_pos,
        tx_start=0,
        tx_power_dbm=20.0,     # adjust to your WiFi/NR config power
        f_hz=5.18e9,           # adjust to your band
        pl_exp=2.0,            # free-space-ish; adjust
        t_end=1000,
        tech="WiFi"
    )
    ch.register_tx(tx)

    # sensed energy should be well-defined now
    e = ch.sensed_energy_dbm(rx_pos, exclude_tx_id=None)
    busy = ch.is_busy(rx_pos, thr_dbm)

    # cleanup
    ch.unregister_tx(tx)
    return e, busy

if __name__ == "__main__":
    thr = -62.0
    print("Distance(m), SensedEnergy(dBm), Busy(>=thr?) thr=", thr)

    for d in [1, 2, 5, 10, 20, 30, 40, 60, 80, 100]:
        e, busy = run_once(d, thr_dbm=thr)
        print(f"{d:>4}, {e:>8.2f}, {busy}")

# Rashed-Step 3.G_1-01-19-2026-end