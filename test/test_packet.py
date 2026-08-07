# Rashed-Step 8.A-08-06-2026-start
"""
Step 8.A unit tests for common.packet.Packet/TrafficConfig, plus
backward-compatibility checks that Frame/ActiveTx/Transmission_NR's new
optional `packet` field defaults to None and doesn't disturb existing
construction call sites.

Same style/harness as test_phy_unit.py/test_nr_licensed.py/
test_generic_device.py: plain assert-based, no pytest dependency.
"""

import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import simpy

from common.packet import Packet, TrafficConfig, compute_packet_stats, compute_packet_stats_by_node
from common.common import Frame
from channel.channel import ActiveTx, Channel
from nru.nru import Transmission_NR
from wifi.wifi import WiFi, Config


def test_packet_defaults():
    p = Packet(
        packet_id="AP 1-000001", source="AP 1", destination="STA 1-1",
        payload_bytes=1472, header_bytes=40,
    )
    assert p.packet_type == "DATA"
    assert p.created_at == 0.0
    assert p.retry_count == 0
    assert p.status == "PENDING"
    assert p.delivered_at is None


def test_packet_total_bytes():
    p = Packet(
        packet_id="x", source="a", destination="b",
        payload_bytes=1472, header_bytes=40,
    )
    assert p.total_bytes() == 1512


def test_packet_status_transitions_are_plain_mutation():
    # Packet is a plain mutable dataclass - status/retry_count/
    # delivered_at are meant to be updated in place by the owning
    # node's sent_completed()/sent_failed() (Step 8.B), not replaced
    # wholesale. Just confirms that works as expected.
    p = Packet(packet_id="x", source="a", destination="b", payload_bytes=100, header_bytes=40)
    p.retry_count += 1
    p.status = "DELIVERED"
    p.delivered_at = 12345.0
    assert p.retry_count == 1
    assert p.status == "DELIVERED"
    assert p.delivered_at == 12345.0


def test_traffic_config_defaults_to_saturated():
    tc = TrafficConfig()
    assert tc.mode == "saturated"
    assert tc.packet_size_bytes is None


def test_traffic_config_poisson_cbr_construction():
    tc_p = TrafficConfig(mode="poisson", arrival_rate_pps=50.0)
    assert tc_p.mode == "poisson"
    assert tc_p.arrival_rate_pps == 50.0

    tc_c = TrafficConfig(mode="cbr", arrival_rate_pps=200.0, packet_size_bytes=512)
    assert tc_c.mode == "cbr"
    assert tc_c.packet_size_bytes == 512


# =======================================================================
# Backward compatibility: packet field defaults to None everywhere,
# every pre-Step-8.A construction call site is unaffected.
# =======================================================================

def test_frame_packet_field_defaults_to_none():
    fr = Frame(frame_time=242, station_name="AP 1", col="", data_size=1472, t_start=0)
    assert fr.packet is None


def test_activetx_packet_field_defaults_to_none():
    tx = ActiveTx(
        tx_id="AP 1", tx_pos=(0.0, 0.0), tx_start=0, rx_pos=(1.0, 0.0),
        tx_power_dbm=20.0, f_hz=5.18e9, pl_exp=3.0, t_end=100, tech="WiFi",
    )
    assert tx.packet is None


def test_transmission_nr_packet_field_defaults_to_none():
    tx = Transmission_NR(
        transmission_time=6000, gnb_name="Gnb 1", col="", t_start=0,
        airtime=6000, rs_time=0,
    )
    assert tx.packet is None


def test_frame_and_activetx_and_transmission_nr_accept_explicit_packet():
    p = Packet(packet_id="x", source="a", destination="b", payload_bytes=100, header_bytes=40)

    fr = Frame(frame_time=242, station_name="AP 1", col="", data_size=1472, t_start=0, packet=p)
    assert fr.packet is p

    tx = ActiveTx(
        tx_id="AP 1", tx_pos=(0.0, 0.0), tx_start=0, rx_pos=(1.0, 0.0),
        tx_power_dbm=20.0, f_hz=5.18e9, pl_exp=3.0, t_end=100, tech="WiFi", packet=p,
    )
    assert tx.packet is p

    trn = Transmission_NR(
        transmission_time=6000, gnb_name="Gnb 1", col="", t_start=0,
        airtime=6000, rs_time=0, packet=p,
    )
    assert trn.packet is p


# Rashed-Step 8.A-08-06-2026-end


# Rashed-Step 8.F-08-06-2026-start
"""
Step 8.F unit tests: Frame.ack_packet defaults/explicit-set, and
WiFi._make_ack_packet()'s field correctness (direction reversed from
the data packet, packet_type="ACK", payload_bytes=0, header_bytes
matches Times.ack_size).
"""


def _make_test_wifi():
    """Minimal WiFi construction, same pattern as test_phy_unit.py's
    make_channel() helper - no simulation.py involved, no env.run()."""
    env = simpy.Environment()
    channel = Channel(
        tx_queue=simpy.PriorityResource(env, capacity=1),
        tx_lock=simpy.Resource(env, capacity=1),
        n_of_stations=1,
        n_of_gNB=0,
        backoffs={},
        airtime_data={},
        airtime_control={},
        airtime_data_NR={},
        airtime_control_NR={},
    )
    channel.airtime_data["AP 1"] = 0
    channel.airtime_control["AP 1"] = 0

    class _FakeSta:
        name = "STA 1-1"
        def current_pos(self):
            return (1.0, 0.0)

    ap = WiFi(env, "AP 1", channel, (0.0, 0.0), [_FakeSta()], Config())
    return ap


def test_frame_ack_packet_field_defaults_to_none():
    fr = Frame(frame_time=242, station_name="AP 1", col="", data_size=1472, t_start=0)
    assert fr.ack_packet is None


def test_frame_ack_packet_field_accepts_explicit_packet():
    ack = Packet(packet_id="AP 1-ACK-000001", source="STA 1-1", destination="AP 1",
                 payload_bytes=0, header_bytes=14, packet_type="ACK")
    fr = Frame(frame_time=242, station_name="AP 1", col="", data_size=1472, t_start=0, ack_packet=ack)
    assert fr.ack_packet is ack


def test_wifi_make_ack_packet_fields():
    ap = _make_test_wifi()
    data_pkt = ap._make_packet()
    ack = ap._make_ack_packet(data_pkt)

    assert ack.packet_type == "ACK"
    assert ack.payload_bytes == 0
    assert ack.header_bytes == 14  # Times.ack_size // 8
    assert ack.total_bytes() == 14
    # Direction reversed vs the data packet: STA -> AP, not AP -> STA.
    assert ack.source == "STA 1-1"
    assert ack.destination == "AP 1"
    assert data_pkt.source == "AP 1"
    assert data_pkt.destination == "STA 1-1"
    assert ack.status == "PENDING"
    assert ack.delivered_at is None


def test_wifi_make_ack_packet_ids_dont_collide_with_data_packet_ids():
    ap = _make_test_wifi()
    data_pkt = ap._make_packet()
    ack_pkt = ap._make_ack_packet(data_pkt)
    assert ack_pkt.packet_id != data_pkt.packet_id
    assert "ACK" in ack_pkt.packet_id
# Rashed-Step 8.F-08-06-2026-end


# Rashed-Step 9.A-08-07-2026-start
"""
Step 9.A unit tests: compute_packet_stats()'s jitter/stddev/percentile
math, hand-verified against a fixed synthetic dataset, plus
compute_packet_stats_by_node().
"""


def _make_delivered(packet_id, created_at, latency):
    return Packet(
        packet_id=packet_id, source="a", destination="b",
        payload_bytes=100, header_bytes=40,
        created_at=created_at, status="DELIVERED",
        delivered_at=created_at + latency,
    )


def _make_dropped(packet_id, created_at):
    return Packet(
        packet_id=packet_id, source="a", destination="b",
        payload_bytes=100, header_bytes=40,
        created_at=created_at, status="DROPPED",
    )


def test_compute_packet_stats_hand_verified_dataset():
    # created_at = 0,100,200,300,400 ; latency = 100,200,150,300,250
    # (delivered_at = created_at + latency, so this list is already in
    # creation order - jitter's internal re-sort should be a no-op here)
    packets = [
        _make_delivered("p1", 0, 100),
        _make_delivered("p2", 100, 200),
        _make_delivered("p3", 200, 150),
        _make_delivered("p4", 300, 300),
        _make_delivered("p5", 400, 250),
    ]
    stats = compute_packet_stats(packets)

    assert stats["total"] == 5
    assert stats["delivered"] == 5
    assert stats["dropped"] == 0
    assert stats["loss_rate"] == 0.0
    assert stats["avg_latency_us"] == 200.0  # (100+200+150+300+250)/5
    assert stats["min_latency_us"] == 100
    assert stats["max_latency_us"] == 300

    # population stddev of [100,200,150,300,250], mean=200:
    # variance = (10000+0+2500+10000+2500)/5 = 5000 -> stddev = sqrt(5000)
    assert abs(stats["latency_stddev_us"] - 5000 ** 0.5) < 1e-9

    # mean abs successive diff, creation order [100,200,150,300,250]:
    # |200-100|=100, |150-200|=50, |300-150|=150, |250-300|=50
    # mean = (100+50+150+50)/4 = 87.5
    assert stats["jitter_us"] == 87.5

    # sorted latencies [100,150,200,250,300], linear interpolation:
    # p50: rank=(5-1)*0.5=2.0 -> index 2 -> 200
    # p95: rank=4*0.95=3.8 -> 250 + 0.8*(300-250) = 290
    # p99: rank=4*0.99=3.96 -> 250 + 0.96*(300-250) = 298
    assert stats["p50_latency_us"] == 200.0
    assert abs(stats["p95_latency_us"] - 290.0) < 1e-9
    assert abs(stats["p99_latency_us"] - 298.0) < 1e-9


def test_compute_packet_stats_jitter_uses_creation_order_not_list_order():
    # Same 5 packets as above, but shuffled in the input list - jitter
    # must still be 87.5 (it re-sorts by created_at internally), while
    # avg/min/max/stddev/percentiles (order-independent) are unaffected.
    packets = [
        _make_delivered("p4", 300, 300),
        _make_delivered("p1", 0, 100),
        _make_delivered("p5", 400, 250),
        _make_delivered("p2", 100, 200),
        _make_delivered("p3", 200, 150),
    ]
    stats = compute_packet_stats(packets)
    assert stats["jitter_us"] == 87.5
    assert stats["avg_latency_us"] == 200.0


def test_compute_packet_stats_dropped_packets_excluded_from_latency_math():
    packets = [
        _make_delivered("p1", 0, 100),
        _make_delivered("p2", 100, 200),
        _make_dropped("p3", 200),
        _make_dropped("p4", 300),
    ]
    stats = compute_packet_stats(packets)
    assert stats["total"] == 4
    assert stats["delivered"] == 2
    assert stats["dropped"] == 2
    assert stats["loss_rate"] == 0.5
    assert stats["avg_latency_us"] == 150.0  # (100+200)/2, dropped excluded
    assert stats["jitter_us"] == 100.0  # only one successive pair: |200-100|


def test_compute_packet_stats_empty_list():
    stats = compute_packet_stats([])
    assert stats["total"] == 0
    assert stats["delivered"] == 0
    assert stats["dropped"] == 0
    assert stats["loss_rate"] == 0.0
    assert stats["avg_latency_us"] is None
    assert stats["min_latency_us"] is None
    assert stats["max_latency_us"] is None
    assert stats["latency_stddev_us"] is None
    assert stats["jitter_us"] is None
    assert stats["p50_latency_us"] is None
    assert stats["p95_latency_us"] is None
    assert stats["p99_latency_us"] is None


def test_compute_packet_stats_single_delivered_packet():
    stats = compute_packet_stats([_make_delivered("p1", 0, 500)])
    assert stats["delivered"] == 1
    assert stats["avg_latency_us"] == 500
    assert stats["latency_stddev_us"] == 0.0  # no variation to observe, not unknown
    assert stats["jitter_us"] is None  # no successive pair possible
    assert stats["p50_latency_us"] == 500
    assert stats["p95_latency_us"] == 500
    assert stats["p99_latency_us"] == 500


def test_compute_packet_stats_by_node():
    node_logs = {
        "AP 1": [_make_delivered("p1", 0, 100), _make_delivered("p2", 100, 300)],
        "AP 2": [_make_dropped("p3", 0)],
    }
    by_node = compute_packet_stats_by_node(node_logs)
    assert set(by_node.keys()) == {"AP 1", "AP 2"}
    assert by_node["AP 1"]["delivered"] == 2
    assert by_node["AP 1"]["avg_latency_us"] == 200.0
    assert by_node["AP 2"]["dropped"] == 1
    assert by_node["AP 2"]["loss_rate"] == 1.0
# Rashed-Step 9.A-08-07-2026-end


# Rashed-Step 8.A-08-06-2026-start
if __name__ == "__main__":
    tests = [
        test_packet_defaults,
        test_packet_total_bytes,
        test_packet_status_transitions_are_plain_mutation,
        test_traffic_config_defaults_to_saturated,
        test_traffic_config_poisson_cbr_construction,
        test_frame_packet_field_defaults_to_none,
        test_activetx_packet_field_defaults_to_none,
        test_transmission_nr_packet_field_defaults_to_none,
        test_frame_and_activetx_and_transmission_nr_accept_explicit_packet,
        test_frame_ack_packet_field_defaults_to_none,
        test_frame_ack_packet_field_accepts_explicit_packet,
        test_wifi_make_ack_packet_fields,
        test_wifi_make_ack_packet_ids_dont_collide_with_data_packet_ids,
        test_compute_packet_stats_hand_verified_dataset,
        test_compute_packet_stats_jitter_uses_creation_order_not_list_order,
        test_compute_packet_stats_dropped_packets_excluded_from_latency_math,
        test_compute_packet_stats_empty_list,
        test_compute_packet_stats_single_delivered_packet,
        test_compute_packet_stats_by_node,
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
# Rashed-Step 8.A-08-06-2026-end
