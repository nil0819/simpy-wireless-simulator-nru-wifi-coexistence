# Rashed-Step 9.C-08-07-2026-start
"""
Step 9.C unit tests for attacker.packet_attacker.PacketAttacker.

Same style/harness as test/test_generic_device.py: plain assert-based,
no pytest dependency required.

Runnable two ways:
  - Directly:  python test/test_packet_attacker.py
  - Via pytest, if installed: pytest test/test_packet_attacker.py
"""

import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import simpy

from channel.channel import Channel, ActiveTx
from common.packet import Packet
from attacker.packet_attacker import Config_PacketAttacker, PacketAttacker


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
# capture() / capture_loop(): passive sniffing builds up captured_packets
# =======================================================================

def test_capture_records_a_visible_packet_by_id():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_PacketAttacker(f_hz=5.18e9, bandwidth_mhz=20.0)

    pkt = Packet(packet_id="victim-1", source="AP 1", destination="STA 1-1",
                 payload_bytes=1000, header_bytes=40, created_at=0.0)
    victim_tx = ActiveTx(
        tx_id="AP 1", tx_pos=(1.0, 0.0), rx_pos=(2.0, 0.0), tx_start=0,
        tx_power_dbm=20.0, f_hz=5.18e9, pl_exp=3.0, t_end=100000, tech="WiFi",
        bandwidth_mhz=20.0, packet=pkt,
    )
    ch.register_tx(victim_tx)

    attacker = PacketAttacker(env, "ATTACKER1", ch, cfg, pos=(0.0, 0.0))
    newly = attacker.capture()

    assert len(newly) == 1 and newly[0] is pkt
    assert attacker.captured_packets == {"victim-1": pkt}


def test_capture_does_not_re_add_already_known_packet_id():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_PacketAttacker(f_hz=5.18e9, bandwidth_mhz=20.0)

    pkt = Packet(packet_id="victim-1", source="AP 1", destination="STA 1-1",
                 payload_bytes=1000, header_bytes=40, created_at=0.0)
    victim_tx = ActiveTx(
        tx_id="AP 1", tx_pos=(1.0, 0.0), rx_pos=(2.0, 0.0), tx_start=0,
        tx_power_dbm=20.0, f_hz=5.18e9, pl_exp=3.0, t_end=100000, tech="WiFi",
        bandwidth_mhz=20.0, packet=pkt,
    )
    ch.register_tx(victim_tx)

    attacker = PacketAttacker(env, "ATTACKER1", ch, cfg, pos=(0.0, 0.0))
    first = attacker.capture()
    second = attacker.capture()

    assert len(first) == 1
    assert second == [], "a packet_id already in captured_packets should not be reported as newly captured again"
    assert len(attacker.captured_packets) == 1


def test_capture_loop_collects_over_time():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_PacketAttacker(f_hz=5.18e9, bandwidth_mhz=20.0)

    pkt = Packet(packet_id="victim-1", source="AP 1", destination="STA 1-1",
                 payload_bytes=1000, header_bytes=40, created_at=0.0)
    victim_tx = ActiveTx(
        tx_id="AP 1", tx_pos=(1.0, 0.0), rx_pos=(2.0, 0.0), tx_start=0,
        tx_power_dbm=20.0, f_hz=5.18e9, pl_exp=3.0, t_end=100000, tech="WiFi",
        bandwidth_mhz=20.0, packet=pkt,
    )
    ch.register_tx(victim_tx)

    attacker = PacketAttacker(env, "ATTACKER1", ch, cfg, pos=(0.0, 0.0))
    env.process(attacker.capture_loop(duration_us=1000, interval_us=100))
    env.run(until=2000)

    assert "victim-1" in attacker.captured_packets


def test_capture_ignores_packet_less_active_tx():
    # An ActiveTx with no packet= (e.g. a legacy/no-packet transmit())
    # should not crash capture() and should not add anything.
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_PacketAttacker(f_hz=5.18e9, bandwidth_mhz=20.0)

    victim_tx = ActiveTx(
        tx_id="AP 1", tx_pos=(1.0, 0.0), rx_pos=(2.0, 0.0), tx_start=0,
        tx_power_dbm=20.0, f_hz=5.18e9, pl_exp=3.0, t_end=100000, tech="WiFi",
        bandwidth_mhz=20.0,
    )
    ch.register_tx(victim_tx)

    attacker = PacketAttacker(env, "ATTACKER1", ch, cfg, pos=(0.0, 0.0))
    newly = attacker.capture()

    assert newly == []
    assert attacker.captured_packets == {}


# =======================================================================
# spoof(): forged source, real physical origin
# =======================================================================

def test_spoof_transmits_packet_with_forged_source_from_attacker_position():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_PacketAttacker(f_hz=5.18e9, bandwidth_mhz=20.0)
    attacker = PacketAttacker(env, "ATTACKER1", ch, cfg, pos=(7.0, 3.0))

    captured = []

    def run():
        proc = env.process(attacker.spoof(duration_us=1000, forged_source="AP 1",
                                           destination="STA 1-1", payload_bytes=500))
        yield env.timeout(10)
        active = attacker.active_tx
        captured.append((active.tx_id, active.tx_pos, active.packet.source, active.packet.destination))
        yield proc

    env.process(run())
    env.run(until=5000)

    tx_id, tx_pos, pkt_source, pkt_dest = captured[0]
    assert tx_id == "ATTACKER1", "the physical ActiveTx.tx_id must be the attacker's own name, not the forged source"
    assert tx_pos == (7.0, 3.0), "the physical transmission must originate from the attacker's own real position"
    assert pkt_source == "AP 1", "the Packet.source field should carry the forged identity"
    assert pkt_dest == "STA 1-1"


def test_spoof_logs_packet_on_completion_only():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_PacketAttacker(f_hz=5.18e9, bandwidth_mhz=20.0)
    attacker = PacketAttacker(env, "ATTACKER1", ch, cfg, pos=(0.0, 0.0))

    env.process(attacker.spoof(duration_us=1000, forged_source="AP 1"))
    env.run(until=5000)

    assert len(attacker.spoofed_log) == 1
    assert attacker.spoofed_log[0].source == "AP 1"
    assert attacker.spoofed_log[0] in attacker.packet_log, (
        "a completed spoof() should also land in the inherited packet_log, same as any other transmit() call"
    )


def test_spoof_interrupted_does_not_log():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_PacketAttacker(f_hz=5.18e9, bandwidth_mhz=20.0)
    attacker = PacketAttacker(env, "ATTACKER1", ch, cfg, pos=(0.0, 0.0))

    gen = attacker.spoof(duration_us=10000, forged_source="AP 1")
    env.process(gen)
    env.run(until=4000)
    gen.close()

    assert attacker.spoofed_log == []
    assert attacker.packet_log == []


def test_spoof_default_packet_ids_are_unique_across_calls():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_PacketAttacker(f_hz=5.18e9, bandwidth_mhz=20.0)
    attacker = PacketAttacker(env, "ATTACKER1", ch, cfg, pos=(0.0, 0.0))

    def run():
        yield env.process(attacker.spoof(duration_us=100, forged_source="AP 1"))
        yield env.process(attacker.spoof(duration_us=100, forged_source="AP 1"))

    env.process(run())
    env.run(until=5000)

    assert len(attacker.spoofed_log) == 2
    ids = {p.packet_id for p in attacker.spoofed_log}
    assert len(ids) == 2, f"expected two distinct default packet_ids, got {ids}"


# =======================================================================
# replay(): exact content copy, fresh delivery-status fields
# =======================================================================

def test_replay_transmits_exact_content_copy():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_PacketAttacker(f_hz=5.18e9, bandwidth_mhz=20.0)
    attacker = PacketAttacker(env, "ATTACKER1", ch, cfg, pos=(9.0, 1.0))

    original = Packet(packet_id="victim-1", source="AP 1", destination="STA 1-1",
                       payload_bytes=1000, header_bytes=40, packet_type="DATA",
                       created_at=0.0, retry_count=2, status="DELIVERED", delivered_at=500.0)

    captured = []

    def run():
        proc = env.process(attacker.replay(original, duration_us=2000))
        yield env.timeout(10)
        active = attacker.active_tx
        captured.append(active)
        yield proc

    env.process(run())
    env.run(until=5000)

    active = captured[0]
    assert active.tx_id == "ATTACKER1", "physically transmitted from the attacker's own identity"
    assert active.tx_pos == (9.0, 1.0)
    replayed_pkt = active.packet
    assert replayed_pkt.packet_id == "victim-1"
    assert replayed_pkt.source == "AP 1"
    assert replayed_pkt.destination == "STA 1-1"
    assert replayed_pkt.payload_bytes == 1000
    assert replayed_pkt.header_bytes == 40
    assert replayed_pkt is not original, "replay() must transmit a COPY, not mutate the original captured Packet"


def test_replay_resets_delivery_status_fields():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_PacketAttacker(f_hz=5.18e9, bandwidth_mhz=20.0)
    attacker = PacketAttacker(env, "ATTACKER1", ch, cfg, pos=(0.0, 0.0))

    original = Packet(packet_id="victim-1", source="AP 1", destination="STA 1-1",
                       payload_bytes=1000, header_bytes=40, packet_type="DATA",
                       created_at=0.0, retry_count=3, status="DROPPED", delivered_at=None)

    env.process(attacker.replay(original, duration_us=1000))
    env.run(until=5000)

    assert len(attacker.replayed_log) == 1
    replayed = attacker.replayed_log[0]
    assert replayed.status == "PENDING"
    assert replayed.retry_count == 0
    assert replayed.delivered_at is None
    # the original, untouched, should still show its own terminal state
    assert original.status == "DROPPED"
    assert original.retry_count == 3


def test_replay_default_duration_derived_from_bitrate():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_PacketAttacker(f_hz=5.18e9, bandwidth_mhz=20.0, bitrate_mbps=8.0)
    attacker = PacketAttacker(env, "ATTACKER1", ch, cfg, pos=(0.0, 0.0))

    # total_bytes = 1000 + 40 = 1040; total_bits = 8320; 8320 / 8.0 = 1040us
    original = Packet(packet_id="victim-1", source="AP 1", destination="STA 1-1",
                       payload_bytes=1000, header_bytes=40, created_at=0.0)

    finished_at = []

    def run():
        yield env.process(attacker.replay(original))
        finished_at.append(env.now)

    env.process(run())
    env.run(until=10000)

    assert finished_at == [1040.0], f"expected duration derived as 1040us from bitrate_mbps=8.0, got {finished_at}"


def test_replay_logs_only_on_uninterrupted_completion():
    env = simpy.Environment()
    ch = make_channel(env)
    cfg = Config_PacketAttacker(f_hz=5.18e9, bandwidth_mhz=20.0)
    attacker = PacketAttacker(env, "ATTACKER1", ch, cfg, pos=(0.0, 0.0))

    original = Packet(packet_id="victim-1", source="AP 1", destination="STA 1-1",
                       payload_bytes=1000, header_bytes=40, created_at=0.0)

    gen = attacker.replay(original, duration_us=10000)
    env.process(gen)
    env.run(until=4000)
    gen.close()

    assert attacker.replayed_log == []
    assert attacker.packet_log == []


if __name__ == "__main__":
    tests = [
        test_capture_records_a_visible_packet_by_id,
        test_capture_does_not_re_add_already_known_packet_id,
        test_capture_loop_collects_over_time,
        test_capture_ignores_packet_less_active_tx,
        test_spoof_transmits_packet_with_forged_source_from_attacker_position,
        test_spoof_logs_packet_on_completion_only,
        test_spoof_interrupted_does_not_log,
        test_spoof_default_packet_ids_are_unique_across_calls,
        test_replay_transmits_exact_content_copy,
        test_replay_resets_delivery_status_fields,
        test_replay_default_duration_derived_from_bitrate,
        test_replay_logs_only_on_uninterrupted_completion,
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
# Rashed-Step 9.C-08-07-2026-end
