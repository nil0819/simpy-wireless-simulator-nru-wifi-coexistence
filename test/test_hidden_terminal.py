# Rashed-Step 4.C_2-01-21-2026-start

import sys, os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


import simpy
from channel.channel import Channel, ActiveTx
from common.common_phy import Pos


def make_channel(env):
    return Channel(
        tx_queue=simpy.PriorityResource(env, capacity=10),
        tx_lock=simpy.Resource(env, capacity=999999),
        n_of_stations=1,
        n_of_gNB=0,
        backoffs={},
        airtime_data={},
        airtime_control={},
        airtime_data_NR={},
        airtime_control_NR={}
    )


def tx_burst(env, ch, tx_id, tx_pos: Pos, rx_pos: Pos, start_us: int, dur_us: int, # type: ignore
             p_dbm=20.0, f_hz=5.18e9, pl_exp=2.0, tech="WiFi"):
    yield env.timeout(start_us)
    t0 = env.now

    tx = ActiveTx(
        tx_id=tx_id,
        tx_pos=tx_pos,
        rx_pos=rx_pos,
        tx_start=env.now,
        tx_power_dbm=p_dbm,
        f_hz=f_hz,
        pl_exp=pl_exp,
        t_end=env.now + dur_us,
        tech=tech
    )

    ch.register_tx(tx)
    yield env.timeout(dur_us)

    sinr = ch.sinr_db(tx)
    yield env.timeout(0) 
    ch.unregister_tx(tx)
    return sinr


def run_case(name, AP, STA, GNB, UE, p_dbm=20.0, dur_us=2000):
    env = simpy.Environment()
    ch = make_channel(env)

    # force overlap by same start time
    p1 = env.process(tx_burst(env, ch, "AP",  AP,  STA, start_us=1000, dur_us=dur_us,
                              p_dbm=p_dbm, tech="WiFi"))
    p2 = env.process(tx_burst(env, ch, "GNB", GNB, UE,  start_us=1000, dur_us=dur_us,
                              p_dbm=p_dbm, tech="NRU"))

    env.run()

    print("\n==", name, "==")
    print("AP->STA SINR(dB):", p1.value)
    print("GNB->UE SINR(dB):", p2.value)

if __name__ == "__main__":
    # Hidden-terminal geometry:
    AP  = (0.0, 0.0)
    GNB = (120.0, 0.0)
    STA = (60.0, 0.0)
    UE  = (60.0, 0.0)

    run_case("Hidden-terminal", AP, STA, GNB, UE, p_dbm=30.0)

    # Control: reduce interference at UE by moving UE farther from AP
    STA_c = (20.0, 0.0)
    UE_c  = (140.0, 0.0)
    run_case("Control (less interference)", AP, STA_c, GNB, UE_c, p_dbm=30.0)


# Rashed-Step 4.C_2-01-21-2026-end