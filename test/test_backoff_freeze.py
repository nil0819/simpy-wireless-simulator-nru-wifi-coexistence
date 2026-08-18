# Rashed-Step 3.G_1-01-20-2026-start

import sys
import os
# Rashed-Step 4.C_2-01-21-2026-start
import random
# Rashed-Step 4.C_2-01-21-2026-end
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
            rx_pos=(pos[0] + 1.0, pos[1]), 
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


# Rashed-Step pre_11.E-08-18-2026-start
# Cleaned up this file (real content dated back to Step 4.C_2,
# 2026-01-21, left uncommitted/unfinished ever since - found and
# resolved as part of Step pre_11.E's repo-hygiene pass). Two real
# things were fixed here, not just formatting:
#   1. This script was actually BROKEN as last committed: ActiveTx
#      later gained a required rx_pos field (see periodic_tx() below)
#      that this Jan-2026 script predates, so running the committed
#      version crashed with "ActiveTx.__init__() missing 1 required
#      positional argument: 'rx_pos'". Confirmed by running git show
#      HEAD's copy directly. Not caught by `pytest test/` because this
#      is a standalone __main__ script (no test_*() functions), not an
#      actual pytest test, despite the test_ filename.
#   2. countdown_with_freeze()'s freeze branch used to `yield
#      ch.state_changed` while the channel was busy - i.e. block until
#      the NEXT busy/idle transition instead of counting a fixed slot,
#      so "froze" wasn't counting frozen backoff slots the way the
#      rest of this function counts idle slots. Replaced with the same
#      yield env.timeout(slot_us)/remaining -= 1 pattern used in the
#      idle branch, so freeze ratio is now slot-for-slot comparable.
# Rashed-Step pre_11.E-08-18-2026-end
def countdown_with_freeze(env, ch, sense_pos: Pos, thr_dbm: float, slots=2000, slot_us=9): # type: ignore
    # Rashed-Step 4.C_2-01-21-2026-start
    yield env.timeout(random.randint(0, 5000))
    # Rashed-Step 4.C_2-01-21-2026-end
    remaining = slots
    froze = 0

    while remaining > 0:
        if ch.is_busy(sense_pos, thr_dbm, exclude_tx_id="SENSOR"):
            froze += 1
            # Rashed-Step 4.C_2-01-21-2026-start
            yield env.timeout(slot_us)
            remaining -= 1
            # Rashed-Step 4.C_2-01-21-2026-end
            continue
        yield env.timeout(slot_us)
        remaining -= 1

    return froze, slots


def run(distance_m, thr_dbm=-62.0):
    env = simpy.Environment()
    ch = make_channel(env)

    env.process(periodic_tx(env, ch, pos=(0.0, 0.0)))
    sensor_pos = (distance_m, 0.0)

    proc = env.process(countdown_with_freeze(env, ch, sensor_pos, thr_dbm))

    env.run(until=300000)  # 300 ms

    froze = proc.value if proc.processed else None
    return froze

# Rashed-Step 4.C_2-01-21-2026-start
def run_avg(distance_m, thr_dbm, trials=30):
    ratios = []
    for _ in range(trials):
        froze, slots = run(distance_m, thr_dbm)
        ratios.append(froze / slots)
    return sum(ratios) / len(ratios)
# Rashed-Step 4.C_2-01-21-2026-end


if __name__ == "__main__":
    for thr in [-42.0, -52.0, -62.0, -72.0, -82.0, -92.0]:
        print(f"ED threshold: {thr} dBm")
        for d in [2, 10, 30, 60, 100, 150, 200]:
            r = run_avg(d, thr, trials=30)
            print(f"  distance={d}m -> avg_freeze_ratio={r:.3f}")
# Rashed-Step 3.G_1-01-20-2026-end