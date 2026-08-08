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
import random

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import simpy

from common.packet import (
    Packet, TrafficConfig, compute_packet_stats, compute_packet_stats_by_node,
    packet_to_csv_row, export_packets_csv, PACKET_CSV_HEADER,
    QOS_TRAFFIC_CLASSES, traffic_class_priority_rank, pick_traffic_class,
    # Rashed-Step 10.B-08-07-2026-start
    EdcaAcParams, DEFAULT_EDCA_PARAMS,
    # Rashed-Step 10.B-08-07-2026-end
)
from common.common import Frame
from channel.channel import ActiveTx, Channel
from nru.nru import Transmission_NR, Gnb, Config_NR
from wifi.wifi import WiFi, Config
# Rashed-Step 10.B-08-07-2026-start
from Times import Times
# Rashed-Step 10.B-08-07-2026-end


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


# Rashed-Step 10.A-08-07-2026-start
"""
Step 10.A unit tests: Packet.traffic_class / TrafficConfig.
traffic_class_mix defaults, QOS_TRAFFIC_CLASSES/traffic_class_priority_
rank()/pick_traffic_class() pure functions, and wifi.WiFi/nru.Gnb
_make_packet() wiring (including the zero-RNG-footprint guarantee when
traffic_class_mix is left at its None default).
"""


def test_packet_traffic_class_defaults_to_best_effort():
    p = Packet(packet_id="x", source="a", destination="b", payload_bytes=100, header_bytes=40)
    assert p.traffic_class == "best_effort"


def test_traffic_config_traffic_class_mix_defaults_to_none():
    tc = TrafficConfig()
    assert tc.traffic_class_mix is None


def test_qos_traffic_classes_order_and_membership():
    assert QOS_TRAFFIC_CLASSES == ("voice", "video", "best_effort", "background")
    assert "best_effort" in QOS_TRAFFIC_CLASSES


def test_traffic_class_priority_rank_known_labels_in_order():
    assert traffic_class_priority_rank("voice") == 0
    assert traffic_class_priority_rank("video") == 1
    assert traffic_class_priority_rank("best_effort") == 2
    assert traffic_class_priority_rank("background") == 3
    assert traffic_class_priority_rank("voice") < traffic_class_priority_rank("video") < traffic_class_priority_rank("background")


def test_traffic_class_priority_rank_unknown_label_ranks_lowest():
    rank = traffic_class_priority_rank("totally_made_up_label")
    assert rank == len(QOS_TRAFFIC_CLASSES)
    assert rank > traffic_class_priority_rank("background"), "an unrecognized label must rank BELOW every recognized one"


def test_pick_traffic_class_only_returns_given_keys():
    mix = {"voice": 0.1, "video": 0.2, "best_effort": 0.5, "background": 0.2}
    random.seed(42)
    seen = {pick_traffic_class(mix) for _ in range(200)}
    assert seen <= set(mix.keys())
    # With 200 draws across 4 non-negligible weights, every class should
    # have come up at least once - catches a broken weights= wiring
    # (e.g. always returning the first key) that a single-draw test
    # wouldn't reliably catch.
    assert seen == set(mix.keys())


def test_pick_traffic_class_respects_weights_statistically():
    # A very lopsided mix - "voice" should dominate the draws.
    mix = {"voice": 0.97, "background": 0.03}
    random.seed(1)
    counts = {"voice": 0, "background": 0}
    for _ in range(500):
        counts[pick_traffic_class(mix)] += 1
    assert counts["voice"] > counts["background"] * 5, f"expected voice to dominate a 97/3 mix, got {counts}"


def test_wifi_make_packet_defaults_to_best_effort_with_zero_rng_footprint():
    ap = _make_test_wifi()
    assert ap.traffic_config.traffic_class_mix is None  # default TrafficConfig(mode="saturated")
    state_before = random.getstate()
    p = ap._make_packet()
    state_after = random.getstate()
    assert p.traffic_class == "best_effort"
    assert state_before == state_after, (
        "traffic_class_mix=None must not consume any random draw at all - "
        "see TrafficConfig.traffic_class_mix's docstring on why an unconsumed-"
        "but-still-called random draw would be a regression risk in this codebase"
    )


def test_wifi_make_packet_draws_from_configured_mix():
    ap = _make_test_wifi()
    ap.traffic_config = TrafficConfig(mode="saturated", traffic_class_mix={"voice": 0.5, "video": 0.5})
    random.seed(7)
    classes_seen = {ap._make_packet().traffic_class for _ in range(100)}
    assert classes_seen <= {"voice", "video"}
    assert classes_seen == {"voice", "video"}, "expected both configured classes to appear across 100 draws"


def test_wifi_make_ack_packet_inherits_data_packet_traffic_class():
    ap = _make_test_wifi()
    ap.traffic_config = TrafficConfig(mode="saturated", traffic_class_mix={"voice": 1.0})
    data_pkt = ap._make_packet()
    assert data_pkt.traffic_class == "voice"
    ack = ap._make_ack_packet(data_pkt)
    assert ack.traffic_class == "voice"


def test_wifi_make_ack_packet_falls_back_to_best_effort_when_data_packet_none():
    ap = _make_test_wifi()
    ack = ap._make_ack_packet(None)
    assert ack.traffic_class == "best_effort"


def _make_test_gnb():
    """Minimal Gnb construction, same pattern as _make_test_wifi()."""
    env = simpy.Environment()
    channel = Channel(
        tx_queue=simpy.PriorityResource(env, capacity=1),
        tx_lock=simpy.Resource(env, capacity=1),
        n_of_stations=0,
        n_of_gNB=1,
        backoffs={},
        airtime_data={},
        airtime_control={},
        airtime_data_NR={},
        airtime_control_NR={},
    )
    channel.airtime_data_NR["Gnb 1"] = 0
    channel.airtime_control_NR["Gnb 1"] = 0

    class _FakeUe:
        name = "UE 1-1"
        def current_pos(self):
            return (1.0, 0.0)

    g = Gnb(env, "Gnb 1", channel, (0.0, 0.0), [_FakeUe()], Config_NR())
    return g


def test_nru_make_packet_defaults_to_best_effort_with_zero_rng_footprint():
    g = _make_test_gnb()
    assert g.traffic_config.traffic_class_mix is None
    state_before = random.getstate()
    p = g._make_packet()
    state_after = random.getstate()
    assert p.traffic_class == "best_effort"
    assert state_before == state_after


def test_nru_make_packet_draws_from_configured_mix():
    g = _make_test_gnb()
    g.traffic_config = TrafficConfig(mode="saturated", traffic_class_mix={"video": 0.5, "background": 0.5})
    random.seed(3)
    classes_seen = {g._make_packet().traffic_class for _ in range(100)}
    assert classes_seen <= {"video", "background"}
    assert classes_seen == {"video", "background"}
# Rashed-Step 10.A-08-07-2026-end


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


# Rashed-Step 9.D-08-07-2026-start
def test_packet_to_csv_row_delivered_has_numeric_latency():
    p = _make_delivered("p1", created_at=100.0, latency=250.0)
    row = packet_to_csv_row(p, seed=7, technology="WiFi", node="AP 1")
    assert row == [
        7, "WiFi", "AP 1", "p1", "a", "b",
        100, 40, 140, "DATA",
        100.0, 0, "DELIVERED", 350.0, 250.0,
    ]


def test_packet_to_csv_row_dropped_has_blank_latency_and_delivered_at():
    p = _make_dropped("p2", created_at=50.0)
    row = packet_to_csv_row(p, seed=1, technology="NRU", node="Gnb 1")
    # index 13 = delivered_at_us, index 14 = latency_us
    assert row[13] == ""
    assert row[14] == ""
    assert row[12] == "DROPPED"


def test_export_packets_csv_writes_header_once_and_all_rows():
    import csv
    import tempfile
    import os as _os

    fd, path = tempfile.mkstemp(suffix=".csv")
    _os.close(fd)
    _os.remove(path)  # export_packets_csv should create it fresh
    try:
        wifi_logs = {"AP 1": [_make_delivered("p1", 0, 100)]}
        nru_logs = {"Gnb 1": [_make_dropped("p2", 0)]}

        n1 = export_packets_csv(path, seed=1, node_packet_logs_by_tech={"WiFi": wifi_logs, "NRU": nru_logs})
        assert n1 == 2

        # Second call (e.g. -r runs > 1 with a different seed) should
        # APPEND, not overwrite, and must NOT write the header again.
        n2 = export_packets_csv(path, seed=2, node_packet_logs_by_tech={"WiFi": wifi_logs, "NRU": {}})
        assert n2 == 1

        with open(path, newline="") as f:
            rows = list(csv.reader(f))

        assert rows[0] == PACKET_CSV_HEADER
        # 1 header + 2 rows (seed=1) + 1 row (seed=2) = 4 total lines
        assert len(rows) == 4
        seeds_seen = [r[0] for r in rows[1:]]
        assert seeds_seen == ["1", "1", "2"]
    finally:
        if _os.path.exists(path):
            _os.remove(path)


def test_export_packets_csv_empty_logs_writes_only_header_no_rows():
    import csv
    import tempfile
    import os as _os

    fd, path = tempfile.mkstemp(suffix=".csv")
    _os.close(fd)
    _os.remove(path)
    try:
        n = export_packets_csv(path, seed=1, node_packet_logs_by_tech={"WiFi": {}, "NRU": {}})
        assert n == 0
        with open(path, newline="") as f:
            rows = list(csv.reader(f))
        assert rows == [PACKET_CSV_HEADER]
    finally:
        if _os.path.exists(path):
            _os.remove(path)
# Rashed-Step 9.D-08-07-2026-end


# Rashed-Step 10.B-08-07-2026-start
"""
Step 10.B unit tests: real 802.11e EDCA differentiated channel access
for Wi-Fi (Config.qos_enabled=True). Covers: DEFAULT_EDCA_PARAMS/
Times.get_aifs_us() correctness against the 802.11e/WMM spec table;
the qos_enabled=True + non-saturated-mode fail-fast guard;
generate_new_back_off_slots_edca()'s CW bounds; wait_back_off_edca()'s
virtual-collision tie resolution (winner picked by priority, losers'
CW grown WITHOUT touching their packet's retry_count); sent_failed_
edca()/sent_completed_edca()'s per-AC bookkeeping parity with the
legacy sent_failed()/sent_completed(); and an end-to-end saturated
smoke run confirming voice's much shorter AIFS/CW lets it dominate
channel access over background under real contention, exactly the
qualitative behavior real EDCA is supposed to produce.
"""


class _NoAutoStartWiFi(WiFi):
    """
    Same WiFi class, but with BOTH background driving loops (start()/
    start_edca()) replaced by immediately-finishing no-op generators.
    Used so a test can construct a real WiFi instance (real __init__,
    real state, real config.qos_enabled fail-fast guard) without an
    uncontrolled background contention process also running and
    interleaving with whatever the test drives directly via
    env.process(...)/env.run(until=...).
    """
    def start(self):
        return
        yield  # pragma: no cover - never reached, makes this a generator

    def start_edca(self):
        return
        yield  # pragma: no cover - never reached, makes this a generator


def _make_test_edca_wifi(qos_enabled=True, traffic_config=None):
    """Same construction pattern as _make_test_wifi() above, but using
    _NoAutoStartWiFi and defaulting qos_enabled=True (this module's
    whole point), so tests can drive wait_back_off_edca()/
    send_frame_edca()/sent_completed_edca()/sent_failed_edca()
    directly and deterministically."""
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

    cfg = Config(qos_enabled=qos_enabled)
    ap = _NoAutoStartWiFi(
        env, "AP 1", channel, (0.0, 0.0), [_FakeSta()], cfg,
        traffic_config=traffic_config if traffic_config is not None else TrafficConfig(mode="saturated"),
    )
    return env, ap


def test_default_edca_params_match_80211e_wmm_spec_table():
    # 802.11-2020 Table 9-155 default EDCA parameters (AC_VO/AC_VI/AC_BE/
    # AC_BK) - see common/packet.py's DEFAULT_EDCA_PARAMS docstring.
    assert DEFAULT_EDCA_PARAMS["voice"] == EdcaAcParams(cw_min=3, cw_max=7, aifsn=2)
    assert DEFAULT_EDCA_PARAMS["video"] == EdcaAcParams(cw_min=7, cw_max=15, aifsn=2)
    assert DEFAULT_EDCA_PARAMS["best_effort"] == EdcaAcParams(cw_min=15, cw_max=1023, aifsn=3)
    assert DEFAULT_EDCA_PARAMS["background"] == EdcaAcParams(cw_min=15, cw_max=1023, aifsn=7)
    assert set(DEFAULT_EDCA_PARAMS.keys()) == set(QOS_TRAFFIC_CLASSES)


def test_get_aifs_us_matches_legacy_difs_for_aifsn_2():
    # AIFSN=2 is exactly DCF's fixed DIFS - see Times.get_aifs_us()'s
    # docstring. This is the anchor point tying EDCA's generalized
    # formula back to the already-Bianchi-validated legacy constant.
    assert Times.get_aifs_us(2) == Times.t_difs == 34


def test_get_aifs_us_matches_spec_formula_for_other_aifsn():
    # AIFS = AIFSN * aSlotTime(9) + aSIFSTime(16).
    assert Times.get_aifs_us(3) == 3 * 9 + 16 == 43   # best_effort
    assert Times.get_aifs_us(7) == 7 * 9 + 16 == 79   # background


def test_wifi_config_qos_disabled_by_default():
    assert Config().qos_enabled is False
    assert Config().edca_params is None


def test_wifi_qos_enabled_requires_saturated_traffic_mode():
    try:
        _make_test_edca_wifi(qos_enabled=True, traffic_config=TrafficConfig(mode="poisson", arrival_rate_pps=10.0))
        assert False, "expected ValueError for qos_enabled=True + non-saturated mode"
    except ValueError as e:
        assert "saturated" in str(e)


def test_wifi_qos_enabled_true_uses_default_edca_params_when_unset():
    _, ap = _make_test_edca_wifi(qos_enabled=True)
    assert ap.edca_params is DEFAULT_EDCA_PARAMS
    assert set(ap.ac_frame_to_send.keys()) == set(QOS_TRAFFIC_CLASSES)
    assert all(v is None for v in ap.ac_frame_to_send.values())
    assert all(v == 0 for v in ap.ac_failed_in_row.values())


def test_generate_new_back_off_slots_edca_respects_cw_bounds_no_failures():
    _, ap = _make_test_edca_wifi()
    # background: cw_min=15, 0 prior failures -> upper_limit = cw_min = 15.
    for _ in range(200):
        v = ap.generate_new_back_off_slots_edca("background")
        assert 0 <= v <= 15


def test_generate_new_back_off_slots_edca_grows_with_failures_and_caps_at_cw_max():
    _, ap = _make_test_edca_wifi()
    # voice: cw_min=3, cw_max=7. After enough failures, 2^k*(cw_min+1)-1
    # exceeds cw_max=7, so the draw must be capped there.
    ap.ac_failed_in_row["voice"] = 10
    for _ in range(200):
        v = ap.generate_new_back_off_slots_edca("voice")
        assert 0 <= v <= 7


def test_make_packet_for_ac_forces_traffic_class_with_zero_rng_footprint():
    _, ap = _make_test_edca_wifi()
    state_before = random.getstate()
    p = ap._make_packet_for_ac("voice")
    assert random.getstate() == state_before  # no traffic_class_mix draw involved
    assert p.traffic_class == "voice"


def test_refresh_ac_frame_builds_frame_with_packet_attached():
    _, ap = _make_test_edca_wifi()
    ap._refresh_ac_frame("video")
    frame = ap.ac_frame_to_send["video"]
    assert frame is not None
    assert frame.packet is not None
    assert frame.packet.traffic_class == "video"


def test_wait_back_off_edca_virtual_collision_winner_is_higher_priority():
    """
    Force a genuine tie between voice (AIFSN=2, aifs=34us) and
    background (AIFSN=7, aifs=79us): with voice backoff=5 slots
    (34+5*9=79us) and background backoff=0 slots (79us), both windows
    expire at exactly the same simulated instant. voice must win
    (traffic_class_priority_rank favors it) and background's
    ac_failed_in_row must grow by 1 as a virtual-collision loser -
    while voice's own packet is untouched (no real transmission
    attempt happened yet, this method only resolves who WINS the
    right to transmit next).
    """
    env, ap = _make_test_edca_wifi()
    ap._refresh_ac_frame("voice")
    ap._refresh_ac_frame("background")
    # video/best_effort intentionally left with no pending frame (None)
    # so they don't participate in this contention episode at all -
    # confirms wait_back_off_edca() only considers ACs with something
    # to send.
    assert ap.ac_frame_to_send["video"] is None
    assert ap.ac_frame_to_send["best_effort"] is None

    def fixed_backoff(ac):
        return {"voice": 5, "background": 0}[ac]
    ap.generate_new_back_off_slots_edca = fixed_backoff

    proc = env.process(ap.wait_back_off_edca())
    env.run(until=proc)
    winner = proc.value

    assert winner == "voice"
    assert ap.ac_failed_in_row["background"] == 1
    assert ap.ac_failed_in_row["voice"] == 0
    # Virtual collision does not touch the packet itself.
    assert ap.ac_frame_to_send["background"].packet.retry_count == 0
    assert ap.ac_frame_to_send["background"].packet.status == "PENDING"


def test_sent_failed_edca_increments_retry_count_and_grows_cw_without_drop():
    _, ap = _make_test_edca_wifi()
    ap._refresh_ac_frame("voice")
    original_packet = ap.ac_frame_to_send["voice"].packet
    ap.sent_failed_edca("voice")
    assert ap.ac_frame_to_send["voice"].packet is original_packet  # same packet, retried
    assert ap.ac_frame_to_send["voice"].packet.retry_count == 1
    assert ap.ac_frame_to_send["voice"].number_of_retransmissions == 1
    assert ap.ac_failed_in_row["voice"] == 1
    assert ap.failed_transmissions == 1


def test_sent_failed_edca_drops_and_refreshes_after_r_limit_exceeded():
    _, ap = _make_test_edca_wifi()
    ap._refresh_ac_frame("background")
    original_packet = ap.ac_frame_to_send["background"].packet
    for _ in range(ap.config.r_limit + 1):
        ap.sent_failed_edca("background")
    assert original_packet.status == "DROPPED"
    assert original_packet in ap.packet_log
    # A fresh packet/frame replaced the dropped one, and the failure
    # streak reset for this AC.
    assert ap.ac_frame_to_send["background"].packet is not original_packet
    assert ap.ac_frame_to_send["background"].packet.traffic_class == "background"
    assert ap.ac_failed_in_row["background"] == 0


def test_sent_completed_edca_marks_delivered_and_builds_matching_ack():
    _, ap = _make_test_edca_wifi()
    ap._refresh_ac_frame("voice")
    packet = ap.ac_frame_to_send["voice"].packet
    ap.sent_completed_edca("voice")
    assert packet.status == "DELIVERED"
    assert packet in ap.packet_log
    assert ap.ac_failed_in_row["voice"] == 0
    ack = ap.ac_frame_to_send["voice"].ack_packet
    assert ack is not None
    assert ack.packet_type == "ACK"
    assert ack.traffic_class == "voice"  # inherits the data packet's class
    assert ap.succeeded_transmissions == 1


def test_edca_saturated_run_favors_voice_over_background_under_contention():
    """
    End-to-end smoke run (real start_edca() this time, not the no-op
    double): voice's much shorter AIFS(34us)/CW(3-7) vs background's
    AIFS(79us)/CW(15-1023) should make voice complete dramatically more
    deliveries in the same wall-clock window - the qualitative
    behavior EDCA exists to produce. Uses the REAL WiFi class (not
    _NoAutoStartWiFi) since this test wants the actual driving loop.
    """
    random.seed(7)
    env = simpy.Environment()
    channel = Channel(
        tx_queue=simpy.PriorityResource(env, capacity=1),
        tx_lock=simpy.Resource(env, capacity=1),
        n_of_stations=1,
        n_of_gNB=0,
        # generate_new_back_off_slots() (legacy path) writes into this
        # diagnostic histogram - EDCA's own generate_new_back_off_slots_
        # edca() deliberately does NOT (see its docstring), but this test
        # constructs a real WiFi via the normal constructor, so match
        # singleRun.py's real initialization shape ({backoff_value:
        # {n_of_stations: 0}}) instead of an empty dict, defensively.
        backoffs={key: {1: 0} for key in range(Config().cw_max + 1)},
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

    ap = WiFi(env, "AP 1", channel, (0.0, 0.0), [_FakeSta()], Config(qos_enabled=True),
              traffic_config=TrafficConfig(mode="saturated"))
    env.run(until=200000)

    from collections import Counter
    counts = Counter(p.traffic_class for p in ap.packet_log)
    assert counts["voice"] > counts.get("background", 0)
    assert counts["voice"] > counts.get("best_effort", 0)
    assert len(ap.packet_log) > 0


def test_legacy_wifi_untouched_when_qos_disabled():
    """
    Regression guard: with qos_enabled left at its default (False), a
    WiFi instance must still spawn the legacy start() process, not
    start_edca() - confirmed indirectly here by checking the per-AC
    EDCA state is initialized but never advanced (still all zeros/None)
    after running the simulation for a while, since only the legacy
    frame_to_send path should be active.
    """
    random.seed(3)
    env = simpy.Environment()
    channel = Channel(
        tx_queue=simpy.PriorityResource(env, capacity=1),
        tx_lock=simpy.Resource(env, capacity=1),
        n_of_stations=1,
        n_of_gNB=0,
        backoffs={key: {1: 0} for key in range(Config().cw_max + 1)},
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

    ap = WiFi(env, "AP 1", channel, (0.0, 0.0), [_FakeSta()], Config(),
              traffic_config=TrafficConfig(mode="saturated"))
    env.run(until=50000)

    assert ap.succeeded_transmissions > 0  # legacy path is doing real work
    assert all(v is None for v in ap.ac_frame_to_send.values())  # EDCA path untouched
    assert all(v == 0 for v in ap.ac_failed_in_row.values())
# Rashed-Step 10.B-08-07-2026-end


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
        test_packet_to_csv_row_delivered_has_numeric_latency,
        test_packet_to_csv_row_dropped_has_blank_latency_and_delivered_at,
        test_export_packets_csv_writes_header_once_and_all_rows,
        test_export_packets_csv_empty_logs_writes_only_header_no_rows,
        test_packet_traffic_class_defaults_to_best_effort,
        test_traffic_config_traffic_class_mix_defaults_to_none,
        test_qos_traffic_classes_order_and_membership,
        test_traffic_class_priority_rank_known_labels_in_order,
        test_traffic_class_priority_rank_unknown_label_ranks_lowest,
        test_pick_traffic_class_only_returns_given_keys,
        test_pick_traffic_class_respects_weights_statistically,
        test_wifi_make_packet_defaults_to_best_effort_with_zero_rng_footprint,
        test_wifi_make_packet_draws_from_configured_mix,
        test_wifi_make_ack_packet_inherits_data_packet_traffic_class,
        test_wifi_make_ack_packet_falls_back_to_best_effort_when_data_packet_none,
        test_nru_make_packet_defaults_to_best_effort_with_zero_rng_footprint,
        test_nru_make_packet_draws_from_configured_mix,
        # Rashed-Step 10.B-08-07-2026-start
        test_default_edca_params_match_80211e_wmm_spec_table,
        test_get_aifs_us_matches_legacy_difs_for_aifsn_2,
        test_get_aifs_us_matches_spec_formula_for_other_aifsn,
        test_wifi_config_qos_disabled_by_default,
        test_wifi_qos_enabled_requires_saturated_traffic_mode,
        test_wifi_qos_enabled_true_uses_default_edca_params_when_unset,
        test_generate_new_back_off_slots_edca_respects_cw_bounds_no_failures,
        test_generate_new_back_off_slots_edca_grows_with_failures_and_caps_at_cw_max,
        test_make_packet_for_ac_forces_traffic_class_with_zero_rng_footprint,
        test_refresh_ac_frame_builds_frame_with_packet_attached,
        test_wait_back_off_edca_virtual_collision_winner_is_higher_priority,
        test_sent_failed_edca_increments_retry_count_and_grows_cw_without_drop,
        test_sent_failed_edca_drops_and_refreshes_after_r_limit_exceeded,
        test_sent_completed_edca_marks_delivered_and_builds_matching_ack,
        test_edca_saturated_run_favors_voice_over_background_under_contention,
        test_legacy_wifi_untouched_when_qos_disabled,
        # Rashed-Step 10.B-08-07-2026-end
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
