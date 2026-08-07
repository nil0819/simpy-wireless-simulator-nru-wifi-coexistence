# Rashed-Step 7.A-08-05-2026-start
"""
Step 7.A unit tests for generic.generic_device.GenericWirelessDevice.

Same style/harness as test/test_phy_unit.py and test/test_nr_licensed.py:
plain assert-based, no pytest dependency required.

Runnable two ways:
  - Directly:  python test/test_generic_device.py
  - Via pytest, if installed: pytest test/test_generic_device.py
"""

import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import simpy

from channel.channel import Channel, ActiveTx
from generic.generic_device import Config_Generic, GenericWirelessDevice
# Rashed-Step 9.B-08-07-2026-start
from common.packet import Packet
# Rashed-Step 9.B-08-07-2026-end


def make_channel(env, shadowing_sigma_db: float = 0.0):
    return Channel(
        tx_queue=simpy.PriorityResource(env, capacity=1),
        tx_lock=simpy.Resource(env, capacity=1),
        n_of_stations=1,
        n_of_gNB=0,
        backoffs={},
        airtime_data={},
        airtime_control={},
        airtime_data_NR={},
        airtime_control_NR={},
        shadowing_sigma_db=shadowing_sigma_db,
    )


# =======================================================================
# transmit(): registers immediately (unrestricted), other nodes can
# sense it as busy while it's active, gone once it ends
# =======================================================================

def test_transmit_registers_immediately_and_is_sensed_busy_by_others():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_Generic(tx_power_dbm=20.0, f_hz=5.18e9, bandwidth_mhz=20.0)
    dev = GenericWirelessDevice(env, "GEN1", ch, cfg, pos=(0.0, 0.0))

    sensor_pos = (5.0, 0.0)  # close enough to be well above -62 dBm CCA
    observed_busy_during = []
    observed_busy_after = []

    def sensor():
        # No exclude_tx_id here - the sensor is a separate observation
        # point, not GEN1 itself, so it should be able to sense GEN1's
        # transmission just like any other node on the channel would.
        yield env.timeout(10)  # let transmit() register first
        observed_busy_during.append(ch.is_busy(sensor_pos, -62.0))
        yield env.timeout(20000)  # past the 5000us transmission
        observed_busy_after.append(ch.is_busy(sensor_pos, -62.0))

    env.process(dev.transmit(duration_us=5000))
    env.process(sensor())
    env.run(until=30000)

    assert observed_busy_during == [True], (
        f"expected channel to be sensed busy while GenericWirelessDevice.transmit() "
        f"is in flight, got {observed_busy_during}"
    )
    assert observed_busy_after == [False], (
        f"expected channel to be idle after the transmission ended, got {observed_busy_after}"
    )
    assert dev.active_tx is None, "active_tx should be cleared once transmit() finishes"


def test_transmit_is_unrestricted_even_when_channel_already_busy():
    # "Unrestricted transmit" per Rashed's Step 7 confirmation - no
    # sense-before-transmit wait, so a second device's transmit() call
    # should register immediately regardless of existing channel activity.
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_Generic()

    other = ActiveTx(
        tx_id="OTHER", tx_pos=(0.0, 0.0), rx_pos=(1.0, 0.0), tx_start=0,
        tx_power_dbm=20.0, f_hz=5.18e9, pl_exp=3.0, t_end=100000, tech="WiFi",
    )
    ch.register_tx(other)

    dev = GenericWirelessDevice(env, "GEN1", ch, cfg, pos=(0.0, 0.0))
    registered_at = []

    def probe():
        env.process(dev.transmit(duration_us=1000))
        yield env.timeout(0)
        registered_at.append(env.now)
        assert dev.active_tx is not None, "transmit() should have registered synchronously at t=0, no waiting"

    env.process(probe())
    env.run(until=5000)

    assert registered_at == [0]


# =======================================================================
# sniff(): wideband vs in-band filtering, visible_txs breakdown
# =======================================================================

def test_sniff_wideband_sees_out_of_band_energy_inband_does_not():
    env = simpy.Environment()
    ch = make_channel(env)

    # A far-away-frequency transmitter (fully non-overlapping channel)
    tx = ActiveTx(
        tx_id="FARFREQ", tx_pos=(1.0, 0.0), rx_pos=(2.0, 0.0), tx_start=0,
        tx_power_dbm=30.0, f_hz=6.0e9, pl_exp=3.0, t_end=100000, tech="WiFi",
        bandwidth_mhz=20.0,
    )
    ch.register_tx(tx)

    cfg = Config_Generic(f_hz=5.18e9, bandwidth_mhz=20.0)  # 5.18 GHz vs the tx's 6.0 GHz - no overlap
    dev = GenericWirelessDevice(env, "SNIFF1", ch, cfg, pos=(0.0, 0.0))

    snap = dev.sniff()

    assert snap.wideband_energy_dbm > -200.0, "wideband sensing should pick up the far-frequency transmitter's energy"
    assert snap.inband_energy_dbm == float("-inf"), (
        f"in-band sensing (device's own 5.18 GHz/20 MHz channel) should NOT see a fully "
        f"non-overlapping 6.0 GHz transmitter, got {snap.inband_energy_dbm}"
    )
    assert len(snap.visible_txs) == 1
    assert snap.visible_txs[0].tx_id == "FARFREQ"
    assert snap.visible_txs[0].tech == "WiFi"


def test_sniff_excludes_own_transmission_from_visible_txs():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_Generic()
    dev = GenericWirelessDevice(env, "GEN1", ch, cfg, pos=(0.0, 0.0))

    def run():
        env.process(dev.transmit(duration_us=5000))
        yield env.timeout(10)
        snap = dev.sniff()
        assert all(v.tx_id != "GEN1" for v in snap.visible_txs), (
            "sniff() should never list this device's own in-flight transmission as a 'visible' external tx"
        )
        # sense_energy_dbm()/sniff() default to exclude_self=True (a
        # transmitting radio doesn't do CCA sensing against its own
        # signal - same half-duplex assumption as a real device), so a
        # lone device sniffing while only ITS OWN transmission is active
        # should read the channel as idle, not busy.
        assert not snap.is_busy_inband, (
            "sniff() excludes this device's own transmission by default, so with no other "
            "activity on the channel it should read idle, not busy"
        )

    env.process(run())
    env.run(until=10000)


# =======================================================================
# Local airtime bookkeeping (tx_log / total_airtime_us / channel_occupancy)
# =======================================================================

def test_airtime_bookkeeping_tracks_successful_transmissions():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_Generic()
    dev = GenericWirelessDevice(env, "GEN1", ch, cfg, pos=(0.0, 0.0))

    def run():
        yield env.process(dev.transmit(duration_us=3000))
        yield env.timeout(2000)  # idle gap
        yield env.process(dev.transmit(duration_us=4000))

    env.process(run())
    env.run(until=20000)

    assert dev.total_airtime_us() == 7000.0, f"expected 3000+4000=7000us total airtime, got {dev.total_airtime_us()}"
    assert len(dev.tx_log) == 2
    assert all(success for (_s, _e, _t, success) in dev.tx_log)

    occ = dev.channel_occupancy(sim_duration_us=env.now)
    expected_occ = 7000.0 / env.now
    assert abs(occ - expected_occ) < 1e-9


def test_airtime_bookkeeping_records_interrupted_transmission_as_failed():
    # A transmission cut short mid-flight (the generator being closed,
    # throwing GeneratorExit in at its current yield point - exactly what
    # happens for real when env.run(until=...) returns while a process is
    # still in flight and Python later garbage-collects it) should still
    # land in tx_log, marked success=False, via the GeneratorExit-safe
    # except/finally path in transmit() - not silently dropped. env.run()
    # itself doesn't force this synchronously (the suspended generator
    # frame just sits there until GC'd), so close() it explicitly here
    # for a deterministic test instead of relying on GC timing.
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_Generic()
    dev = GenericWirelessDevice(env, "GEN1", ch, cfg, pos=(0.0, 0.0))

    gen = dev.transmit(duration_us=10000)
    env.process(gen)
    env.run(until=4000)  # ends well before the 10000us transmission finishes
    assert dev.tx_log == [], "transmission should still be in flight, not yet logged, before the generator is closed"

    gen.close()

    assert len(dev.tx_log) == 1, f"expected the interrupted transmission to be logged after close(), got {dev.tx_log}"
    t_start, t_end, tech, success = dev.tx_log[0]
    assert success is False
    assert t_end == 4000.0
    assert dev.active_tx is None


# =======================================================================
# estimate_sinr_db(): convenience wrapper around channel.sinr_db()
# =======================================================================

def test_estimate_sinr_db_matches_channel_sinr_db_directly():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_Generic(tx_power_dbm=20.0, f_hz=5.18e9, bandwidth_mhz=20.0)
    dev = GenericWirelessDevice(env, "GEN1", ch, cfg, pos=(0.0, 0.0))

    captured = []

    def run():
        proc = dev.transmit(duration_us=5000, rx_pos=(10.0, 0.0))
        gen_proc = env.process(proc)
        yield env.timeout(10)
        captured.append(dev.estimate_sinr_db())
        captured.append(ch.sinr_db(dev.active_tx))
        yield gen_proc

    env.process(run())
    env.run(until=10000)

    assert len(captured) == 2
    assert captured[0] == captured[1], "estimate_sinr_db() should match calling channel.sinr_db() directly on the same ActiveTx"


def test_estimate_sinr_db_raises_when_nothing_in_flight():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_Generic()
    dev = GenericWirelessDevice(env, "GEN1", ch, cfg, pos=(0.0, 0.0))

    raised = []
    try:
        dev.estimate_sinr_db()
    except ValueError:
        raised.append(True)
    assert raised == [True], "estimate_sinr_db() should raise ValueError when no transmission is in flight and none is given"


# =======================================================================
# Mobility passthrough (reuses common_phy.WaypointMobility, Step 5.G)
# =======================================================================

def test_static_device_never_moves():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_Generic()
    dev = GenericWirelessDevice(env, "GEN1", ch, cfg, pos=(3.0, 4.0))  # mobility_speed_mps=0.0 default

    assert dev.current_pos() == (3.0, 4.0)
    env.run(until=50000)
    assert dev.current_pos() == (3.0, 4.0), "a device constructed with mobility_speed_mps=0.0 (default) must never move"
    assert dev.mobility is None


# Rashed-Step 9.B-08-07-2026-start
# =======================================================================
# Packet visibility: transmit(packet=...) stamps ActiveTx.packet,
# sniff() surfaces it via VisibleTx.packet, packet_log records it
# =======================================================================

def test_transmit_with_no_packet_behaves_exactly_as_before():
    # Default (no packet= arg) must be indistinguishable from every
    # pre-9.B call site - same as wifi.py/nru.py's ActiveTx.packet
    # defaulting to None before their own 9.B fix.
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_Generic()
    dev = GenericWirelessDevice(env, "GEN1", ch, cfg, pos=(0.0, 0.0))

    captured = []

    def run():
        proc = env.process(dev.transmit(duration_us=1000))
        yield env.timeout(10)
        captured.append(dev.active_tx.packet)
        yield proc

    env.process(run())
    env.run(until=5000)

    assert captured == [None]
    assert dev.packet_log == [], "packet_log must stay empty when no packet was ever passed to transmit()"


def test_transmit_with_packet_stamps_active_tx_and_logs_on_completion():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_Generic()
    dev = GenericWirelessDevice(env, "GEN1", ch, cfg, pos=(0.0, 0.0))

    pkt = Packet(packet_id="p1", source="GEN1", destination="GEN2",
                 payload_bytes=100, header_bytes=20, created_at=0.0)
    captured = []

    def run():
        proc = env.process(dev.transmit(duration_us=1000, packet=pkt))
        yield env.timeout(10)
        captured.append(dev.active_tx.packet)
        yield proc

    env.process(run())
    env.run(until=5000)

    assert captured == [pkt], "ActiveTx.packet should carry the exact Packet instance passed to transmit()"
    assert dev.packet_log == [pkt], "packet_log should record the packet once transmit() completes uninterrupted"


def test_transmit_with_packet_interrupted_does_not_log():
    # Mirrors the tx_log success=False path (8.G/9.B convention): a
    # transmission cut short mid-flight must NOT land in packet_log,
    # same as it's excluded from any "delivered" bookkeeping elsewhere.
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_Generic()
    dev = GenericWirelessDevice(env, "GEN1", ch, cfg, pos=(0.0, 0.0))

    pkt = Packet(packet_id="p1", source="GEN1", destination="GEN2",
                 payload_bytes=100, header_bytes=20, created_at=0.0)

    gen = dev.transmit(duration_us=10000, packet=pkt)
    env.process(gen)
    env.run(until=4000)  # well before the 10000us transmission finishes
    gen.close()

    assert dev.packet_log == [], "an interrupted transmission's packet must not be logged"
    assert len(dev.tx_log) == 1 and dev.tx_log[0][3] is False


def test_sniff_surfaces_packet_from_another_nodes_active_tx():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_Generic(f_hz=5.18e9, bandwidth_mhz=20.0)

    pkt = Packet(packet_id="p1", source="OTHER", destination="GEN1",
                 payload_bytes=100, header_bytes=20, created_at=0.0)
    other = ActiveTx(
        tx_id="OTHER", tx_pos=(1.0, 0.0), rx_pos=(2.0, 0.0), tx_start=0,
        tx_power_dbm=20.0, f_hz=5.18e9, pl_exp=3.0, t_end=100000, tech="WiFi",
        bandwidth_mhz=20.0, packet=pkt,
    )
    ch.register_tx(other)

    dev = GenericWirelessDevice(env, "GEN1", ch, cfg, pos=(0.0, 0.0))
    snap = dev.sniff()

    assert len(snap.visible_txs) == 1
    assert snap.visible_txs[0].packet is pkt, "sniff() should surface the other node's real Packet via VisibleTx.packet"


def test_sniff_visible_tx_packet_is_none_when_not_carried():
    # Default/no-packet ActiveTx (every wifi.py/nru.py ACK-less legacy
    # call before 9.B, or any generic transmit() without packet=) must
    # surface as packet=None, not error/omit the field.
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_Generic(f_hz=5.18e9, bandwidth_mhz=20.0)

    other = ActiveTx(
        tx_id="OTHER", tx_pos=(1.0, 0.0), rx_pos=(2.0, 0.0), tx_start=0,
        tx_power_dbm=20.0, f_hz=5.18e9, pl_exp=3.0, t_end=100000, tech="WiFi",
        bandwidth_mhz=20.0,
    )
    ch.register_tx(other)

    dev = GenericWirelessDevice(env, "GEN1", ch, cfg, pos=(0.0, 0.0))
    snap = dev.sniff()

    assert len(snap.visible_txs) == 1
    assert snap.visible_txs[0].packet is None
# Rashed-Step 9.B-08-07-2026-end


def test_mobile_device_position_changes_over_time():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_Generic()
    dev = GenericWirelessDevice(
        env, "GEN1", ch, cfg, pos=(0.0, 0.0),
        mobility_speed_mps=5.0, area_w=50.0, area_h=50.0,
    )
    assert dev.mobility is not None

    p0 = dev.current_pos()
    env.run(until=3_000_000)  # 3 simulated seconds at 5 m/s - plenty of movement
    p1 = dev.current_pos()
    assert p0 != p1, "a mobile device's position should change after simulated time passes"


if __name__ == "__main__":
    tests = [
        test_transmit_registers_immediately_and_is_sensed_busy_by_others,
        test_transmit_is_unrestricted_even_when_channel_already_busy,
        test_sniff_wideband_sees_out_of_band_energy_inband_does_not,
        test_sniff_excludes_own_transmission_from_visible_txs,
        test_airtime_bookkeeping_tracks_successful_transmissions,
        test_airtime_bookkeeping_records_interrupted_transmission_as_failed,
        test_estimate_sinr_db_matches_channel_sinr_db_directly,
        test_estimate_sinr_db_raises_when_nothing_in_flight,
        test_static_device_never_moves,
        test_mobile_device_position_changes_over_time,
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
# Rashed-Step 7.A-08-05-2026-end
