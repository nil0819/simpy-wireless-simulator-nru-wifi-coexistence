# Rashed-Step 11.A-08-12-2026-start
"""
Step 11.A unit tests for generic.generic_transmitter.GenericTransmitter.

Same style/harness as test/test_generic_device.py: plain assert-based,
no pytest dependency required.

Runnable two ways:
  - Directly:  python test/test_generic_transmitter.py
  - Via pytest, if installed: pytest test/test_generic_transmitter.py
"""

import sys
import os
import random

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import simpy

from channel.channel import Channel
from generic.generic_device import Config_Generic
from generic.generic_transmitter import GenericTransmitter


def make_channel(env, shadowing_sigma_db: float = 0.0):
    return Channel(
        tx_queue=simpy.PriorityResource(env, capacity=1),
        tx_lock=simpy.Resource(env, capacity=1),
        n_of_stations=0,
        n_of_gNB=0,
        backoffs={},
        airtime_data={},
        airtime_control={},
        airtime_data_NR={},
        airtime_control_NR={},
        shadowing_sigma_db=shadowing_sigma_db,
    )


def test_single_device_saturates_the_channel_when_alone():
    # With nothing else on the channel, a lone GenericTransmitter should
    # be busy roughly tx_duration/(tx_duration+avg_backoff) of the time -
    # not exactly 100% (it still waits out its own backoff before every
    # attempt) but should complete many attempts and hold a substantial
    # occupancy share over a reasonably long run.
    random.seed(1)
    env = simpy.Environment()
    ch = make_channel(env)
    dev = GenericTransmitter(
        env, "GEN1", ch, Config_Generic(), pos=(0.0, 0.0),
        tx_duration_us=500.0, backoff_min_us=0.0, backoff_max_us=200.0,
    )
    sim_us = 200_000
    env.run(until=sim_us)

    assert dev.transmissions_attempted > 0
    assert dev.transmissions_completed > 0
    # completed can lag attempted by at most 1 (the one still in flight
    # when the sim ended).
    assert dev.transmissions_attempted - dev.transmissions_completed <= 1
    occ = dev.channel_occupancy(sim_us)
    assert 0.3 < occ < 1.0  # holds a real, substantial (but not literally 100%) share
    assert len(dev.packet_log) == dev.transmissions_completed


def test_two_devices_share_the_channel_and_both_make_progress():
    random.seed(2)
    env = simpy.Environment()
    ch = make_channel(env)
    dev1 = GenericTransmitter(env, "GEN1", ch, Config_Generic(), pos=(0.0, 0.0),
                               tx_duration_us=300.0, backoff_min_us=0.0, backoff_max_us=300.0)
    dev2 = GenericTransmitter(env, "GEN2", ch, Config_Generic(), pos=(5.0, 0.0),
                               tx_duration_us=300.0, backoff_min_us=0.0, backoff_max_us=300.0)
    sim_us = 200_000
    env.run(until=sim_us)

    assert dev1.transmissions_completed > 0
    assert dev2.transmissions_completed > 0
    # Neither device should be able to claim the whole channel to itself
    # once a second one is contending too.
    assert dev1.channel_occupancy(sim_us) < 1.0
    assert dev2.channel_occupancy(sim_us) < 1.0


def test_backoff_freezes_while_channel_busy_and_resumes_not_restarts():
    # A device must never START a new transmission while another
    # transmitter's busy window is open - confirms the freeze-and-
    # resume convention (same as wifi.WiFi.wait_back_off()) rather than
    # an "ignore busy" bug. Checked via dev.tx_log's own (t_start, ...)
    # records (populated by the inherited transmit()), not by sampling
    # ch.active_txs from outside - a transmission that was ALREADY in
    # flight when the jammer keys up is legitimate (GEN1 doesn't abort
    # a commitment already made) and must not be confused with one that
    # started too late.
    random.seed(3)
    env = simpy.Environment()
    ch = make_channel(env)

    from generic.generic_device import GenericWirelessDevice
    jammer = GenericWirelessDevice(env, "JAMMER", ch, Config_Generic(), pos=(0.0, 0.0))

    def jam():
        yield env.timeout(1000)  # let GEN1 finish several short attempts first
        yield from jammer.transmit(duration_us=2000.0)  # busy window [1000, 3000)
    env.process(jam())

    dev = GenericTransmitter(env, "GEN1", ch, Config_Generic(), pos=(1.0, 0.0),
                              tx_duration_us=50.0, backoff_min_us=0.0, backoff_max_us=50.0)

    env.run(until=3100)

    starts_during_jam = [t_start for (t_start, _t_end, _tech, _success) in dev.tx_log if 1000 < t_start < 3000]
    assert starts_during_jam == []
    # And it resumes once the jammer's window ends.
    assert any(t_start >= 3000 for (t_start, _t_end, _tech, _success) in dev.tx_log)


def test_generic_transmitter_inherits_mobility():
    random.seed(4)
    env = simpy.Environment()
    ch = make_channel(env)
    dev = GenericTransmitter(
        env, "GEN1", ch, Config_Generic(), pos=(0.0, 0.0),
        tx_duration_us=200.0, backoff_min_us=0.0, backoff_max_us=200.0,
        mobility_speed_mps=5.0, area_w=50.0, area_h=50.0,
    )
    start_pos = dev.current_pos()
    env.run(until=100_000)
    assert dev.current_pos() != start_pos  # actually moved


def test_static_generic_transmitter_never_moves():
    random.seed(5)
    env = simpy.Environment()
    ch = make_channel(env)
    dev = GenericTransmitter(
        env, "GEN1", ch, Config_Generic(), pos=(3.0, 4.0),
        tx_duration_us=200.0, backoff_min_us=0.0, backoff_max_us=200.0,
        mobility_speed_mps=0.0,
    )
    env.run(until=50_000)
    assert dev.current_pos() == (3.0, 4.0)


def test_packets_carry_generic_devices_own_identity():
    random.seed(6)
    env = simpy.Environment()
    ch = make_channel(env)
    dev = GenericTransmitter(env, "GEN1", ch, Config_Generic(), pos=(0.0, 0.0),
                              tx_duration_us=200.0, backoff_min_us=0.0, backoff_max_us=100.0,
                              payload_bytes=777)
    env.run(until=50_000)
    assert len(dev.packet_log) > 0
    for pkt in dev.packet_log:
        assert pkt.source == "GEN1"
        assert pkt.destination == "GEN1"
        assert pkt.payload_bytes == 777


if __name__ == "__main__":
    tests = [
        test_single_device_saturates_the_channel_when_alone,
        test_two_devices_share_the_channel_and_both_make_progress,
        test_backoff_freezes_while_channel_busy_and_resumes_not_restarts,
        test_generic_transmitter_inherits_mobility,
        test_static_generic_transmitter_never_moves,
        test_packets_carry_generic_devices_own_identity,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        sys.exit(1)
    print("ALL TESTS PASSED")
# Rashed-Step 11.A-08-12-2026-end
