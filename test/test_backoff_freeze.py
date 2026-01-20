# Rashed-Step 3.G_1-01-20-2026-start

import sys
import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import simpy
from channel.channel import Channel, ActiveTx
from common.common_phy import Pos
import math


def make_channel(env):
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


def periodic_tx(env, ch, pos=(0.0, 0.0), period = 5000, on_time= 2000):
    while True:
        start = env.now
        tx = ActiveTx(
            tx_id="TX",
            tx_pos=pos,
            tx_start=env.now,
            tx_power_dbm=20.0,
            f_hz=5.18e9,
            pl_exp=2.0,
            t_end=env.now + on_time,
            tech="WiFi"
        )
        ch.register_tx(tx)
        yield env.timeout(on_time)
        ch.unregister_tx(tx)
        yield env.timeout(period - on_time)


def countdown_with_freeze(env, ch, sense_pos: Pos, thr_dbm: float, slots=50, slot_us=9): # type: ignore
    remaining = slots
    froze = 0

    while remaining > 0:
        if ch.is_busy(sense_pos, thr_dbm, exclude_tx_id="SENSOR"):
            froze += 1
            yield ch.state_changed
            continue
        yield env.timeout(slot_us)
        remaining -= 1

    return froze


def run(distance_m, thr_dbm=-62.0):
    env = simpy.Environment()
    ch = make_channel(env)

    env.process(periodic_tx(env, ch, pos=(0.0, 0.0)))
    sensor_pos = (distance_m, 0.0)

    proc = env.process(countdown_with_freeze(env, ch, sensor_pos, thr_dbm))

    env.run(until=300000)  # 300 ms

    froze = proc.value if proc.processed else None
    return froze


if __name__ == "__main__":

    for thr in [-42.0, -52.0, -62.0, -72.0, -82.0, -92.0]:
        print(f"ED threshold: {thr} dBm")
        for d in [2, 10, 30, 60, 100, 150, 200]:
            froze = run(d, thr_dbm=thr)
            print(f"  distance={d}m -> freeze_events={froze}")
    # thr = -52.0
    # for d in [2,10, 30, 60, 100]:
    #     froze = run(d, thr_dbm=thr)
    #     print(f"distance={d}m -> freeze_events={froze}")

# Rashed-Step 3.G_1-01-20-2026-end