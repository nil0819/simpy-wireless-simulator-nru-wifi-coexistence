# Rashed-Step 8.A-08-06-2026-start
"""
Step 8.A: Packet - the shared, technology-agnostic unit of data this
simulator moves around, plus TrafficConfig - the knob that decides how
packets get created (saturated / poisson / cbr). See "Project details/
Step 8.txt" for the full rationale.

WHY THIS EXISTS
Until now, every technology's "thing being transmitted" (wifi.Frame,
nru.Transmission_NR, channel.ActiveTx) has been a technology-specific,
duration-and-diagnostics-only object - real enough to drive airtime/
SINR math, but with no persistent identity, no notion of a generic
"packet" a queue or a sniffer could reason about independent of which
technology sent it, and (for WiFi at least) already a fixed payload
size assumed to always be ready to send (the "saturated" traffic
model baked into Steps 5/6's validation work). Packet is the new,
shared layer underneath all of that: every technology's own
Frame/Transmission_NR/ActiveTx gets an optional `packet` field
pointing at one of these, so a Packet's identity/size/retry history/
delivery status is visible regardless of which technology carried it.

WHAT THIS FILE DELIBERATELY DOES NOT DO YET
  - Packet.header_bytes is a plain int set by whoever constructs the
    Packet (wifi.py currently uses Times.mac_overhead//8, i.e. the
    same 40-byte MAC header size the PHY duration formula already
    assumes) - there's no per-technology header-size table here yet.
  - Nothing in this file computes on-air duration from a Packet's
    size - that wiring (Times.py taking a Packet's real size instead
    of a fixed config.data_size scalar) is explicitly deferred to a
    later Step 8 sub-step (8.C in the roadmap), to keep this one
    additive/non-behavior-changing.
  - No fragmentation/aggregation, no real payload bytes (content) -
    payload_bytes is a size only, matching this simulator's existing
    MAC/PHY-layer scope (not an application-layer simulator).
"""

from dataclasses import dataclass
from typing import Dict, Optional
import random
import statistics


# Rashed-Step 10.A-08-07-2026-start
# Canonical traffic-class labels this simulator recognizes, in PRIORITY
# ORDER (index 0 = highest priority) - deliberately named after Wi-Fi
# WMM's real Access Categories (AC_VO/AC_VI/AC_BE/AC_BK, 802.11e) rather
# than something simulator-specific, since that's the real standard
# Step 10.B (differentiated EDCA-style channel access, not built yet)
# will map these onto. "best_effort" is the class every Packet has
# always implicitly been before this step - see Packet.traffic_class's
# own default and TrafficConfig.traffic_class_mix's docstring for why
# that keeps every pre-Step-10.A run byte-identical.
QOS_TRAFFIC_CLASSES = ("voice", "video", "best_effort", "background")


def traffic_class_priority_rank(traffic_class: str) -> int:
    """
    Lower return value = higher priority (0 = "voice", the highest).
    An unrecognized label (any string not in QOS_TRAFFIC_CLASSES) ranks
    LOWEST rather than raising - deliberately lenient, matching this
    project's existing "don't validate caller-supplied labels" policy
    (e.g. attacker.packet_attacker.spoof()'s forged_source isn't
    checked against the real topology either). Not used by anything
    yet in Step 10.A itself - defined here as the shared ordering a
    later differentiated-channel-access phase (Step 10.B) will consume,
    so that phase doesn't need to invent its own ranking scheme.
    """
    try:
        return QOS_TRAFFIC_CLASSES.index(traffic_class)
    except ValueError:
        return len(QOS_TRAFFIC_CLASSES)


def pick_traffic_class(traffic_class_mix: "dict[str, float]") -> str:
    """
    Weighted random draw of one traffic-class label from
    traffic_class_mix (e.g. {"voice": 0.1, "video": 0.2,
    "best_effort": 0.5, "background": 0.2} - weights don't need to sum
    to 1, random.choices() normalizes them itself). Split out as its
    own function (rather than inlined in wifi.py/nru.py) so the actual
    draw logic has one implementation both technologies share and so
    it's independently unit-testable without constructing a full WiFi/
    Gnb object. Uses the global `random` module directly (not a
    per-object Random instance) - matches every other random draw in
    this simulator (wifi.py/nru.py's own traffic generators, backoff
    slot selection, etc.), all of which go through the single
    `random.seed(seed)` call at the top of run_simulation() for
    reproducibility. Callers are responsible for only calling this when
    traffic_class_mix is not None (see TrafficConfig.traffic_class_mix's
    docstring on why the None case must skip this entirely, not just
    skip via a trivial single-key dict) - keeps this function simple
    and its one random.choices() call an honest, minimal footprint.
    """
    classes = list(traffic_class_mix.keys())
    weights = list(traffic_class_mix.values())
    return random.choices(classes, weights=weights)[0]
# Rashed-Step 10.A-08-07-2026-end


# Rashed-Step 10.B-08-07-2026-start
@dataclass
class EdcaAcParams:
    """
    Per-Access-Category EDCA channel-access parameters (802.11e). cw_min/
    cw_max are contention-window bounds in SLOTS (same units as
    wifi.Config.cw_min/cw_max already use for the non-EDCA path); aifsn
    is the Arbitration Inter-Frame Space Number - the AIFS itself
    (analogous to DCF's fixed DIFS) is aifsn * Times.t_slot + Times.
    t_sifs, computed by Times.get_aifs_us(). TXOP bursting (multiple
    frames per won contention) is NOT modeled - see wifi.WiFi's EDCA
    docstring for the full scope note.
    """
    cw_min: int
    cw_max: int
    aifsn: int


# Standard default EDCA parameter set (802.11-2020 Table 9-155 / the
# same values widely published as the Wi-Fi Alliance WMM default set),
# for the legacy-OFDM/non-HT PHY this simulator's Times.py already
# models (aCWmin=15, aCWmax=1023, aSlotTime=9us, aSIFSTime=16us - see
# Times.py). AC_VO/AC_VI's aifsn=2 giving AIFS=34us is a deliberate,
# checkable consistency point: that's EXACTLY Times.t_difs (fixed at
# 34us since Step 6.A's DIFS bugfix) - i.e. non-EDCA DCF's single DIFS
# IS, by construction, what AC_VO/AC_VI's AIFS already equals. Keyed by
# the same QOS_TRAFFIC_CLASSES labels (voice=AC_VO, video=AC_VI,
# best_effort=AC_BE, background=AC_BK) rather than raw "AC_VO"-style
# strings, so this table plugs directly into Packet.traffic_class /
# TrafficConfig.traffic_class_mix without a separate label mapping.
DEFAULT_EDCA_PARAMS: Dict[str, EdcaAcParams] = {
    "voice": EdcaAcParams(cw_min=3, cw_max=7, aifsn=2),
    "video": EdcaAcParams(cw_min=7, cw_max=15, aifsn=2),
    "best_effort": EdcaAcParams(cw_min=15, cw_max=1023, aifsn=3),
    "background": EdcaAcParams(cw_min=15, cw_max=1023, aifsn=7),
}
# Rashed-Step 10.B-08-07-2026-end


@dataclass
class Packet:
    packet_id: str
    source: str
    destination: str
    payload_bytes: int
    header_bytes: int
    # "DATA" (the only kind actually produced as of Step 8.A/8.B - ACK
    # stays the existing fixed-duration constant in Times.py for now),
    # "ACK"/"CONTROL"/"MGMT" reserved for a later sub-step.
    packet_type: str = "DATA"
    created_at: float = 0.0
    retry_count: int = 0
    # "PENDING" (in flight / still queued or being retried), "DELIVERED"
    # (successfully sent, see delivered_at), or "DROPPED" (gave up after
    # exceeding the technology's retry limit).
    status: str = "PENDING"
    delivered_at: Optional[float] = None
    # Rashed-Step 10.A-08-07-2026-start
    # QoS traffic class - see QOS_TRAFFIC_CLASSES for the recognized
    # labels (not enforced/validated here, same leniency policy as
    # traffic_class_priority_rank()). Default "best_effort" matches
    # every Packet's implicit class before this field existed, so any
    # code that doesn't know about traffic classes yet (every call site
    # before Step 10.A, and every technology/scenario that never opts
    # into TrafficConfig.traffic_class_mix) is completely unaffected -
    # this field is added at the END of the dataclass specifically so
    # it cannot shift any existing POSITIONAL Packet(...) construction
    # call's argument indices (every real call site in this codebase
    # already uses keyword arguments, but appending at the end is the
    # zero-risk choice regardless).
    traffic_class: str = "best_effort"
    # Rashed-Step 10.A-08-07-2026-end

    def total_bytes(self) -> int:
        return self.payload_bytes + self.header_bytes


@dataclass
class TrafficConfig:
    """
    Controls how a node's packets get created. Passed as an optional
    constructor arg to WiFi/Gnb (None, the default, is normalized to
    TrafficConfig(mode="saturated") internally - i.e. every existing
    caller that doesn't know about this yet gets EXACTLY today's
    always-has-something-to-send behavior, byte-identical to before
    Step 8.B).

    mode:
      "saturated" - the node always has a packet ready the instant it
        gets channel access (today's implicit behavior, made explicit).
        No queue/arrival process is actually used in this mode - see
        wifi.WiFi._next_packet()/nru.Gnb's equivalent.
      "poisson" - packets arrive per a Poisson process at
        arrival_rate_pps (packets/sec); the node's queue can genuinely
        sit empty, and the node does not contend for the channel while
        it has nothing queued.
      "cbr" - constant bit/packet rate: packets arrive at a fixed
        interval of 1/arrival_rate_pps seconds. Same "can sit idle"
        behavior as poisson, just deterministic inter-arrival times.
    """
    mode: str = "saturated"
    arrival_rate_pps: float = 100.0
    # None (default) = use the node's own config.data_size for payload
    # size, matching today's fixed-size behavior exactly. Set this to
    # override with a different fixed size without touching the
    # node's main Config/Config_NR object.
    packet_size_bytes: Optional[int] = None
    # Rashed-Step 10.A-08-07-2026-start
    # None (default) = every packet this node creates gets
    # traffic_class="best_effort" (Packet's own default) via a plain
    # hardcoded assignment - NO random draw happens at all, so a run
    # with this unset is not just behaviorally but RNG-footprint
    # identical to every pre-Step-10.A run (an important distinction in
    # this codebase - see Step 8.E's writeup on how even an
    # unconsumed-but-still-called random draw can shift unrelated
    # downstream random sequences and break regression baselines).
    # Set to a dict of {traffic_class_label: weight, ...} (labels
    # should normally be from QOS_TRAFFIC_CLASSES, though this isn't
    # enforced - see traffic_class_priority_rank()'s docstring) to have
    # each new packet draw its class via pick_traffic_class() instead -
    # e.g. {"voice": 0.1, "video": 0.2, "best_effort": 0.5,
    # "background": 0.2} models one node generating a realistic mixed
    # traffic load, rather than every packet being the same class.
    traffic_class_mix: "Optional[dict[str, float]]" = None
    # Rashed-Step 10.A-08-07-2026-end
# Rashed-Step 8.A-08-06-2026-end


# Rashed-Step 8.G-08-06-2026-start
def compute_packet_stats(packets: "list[Packet]") -> dict:
    """
    Aggregate latency/loss stats over a list of Packets that have
    reached a terminal state (DELIVERED or DROPPED) - see wifi.WiFi/
    nru.Gnb's packet_log, populated by sent_completed()/sent_failed().
    A Packet still PENDING at the moment its owning node's log is read
    (e.g. mid-retry when the simulation ends) is deliberately excluded -
    it never reached a terminal state, so it has no delivered_at and no
    resolved fate to count as a loss or a success either way.

    Returns a plain dict (not a dataclass - this is a report snapshot,
    not a live object anything mutates) with:
      total            - len(delivered) + len(dropped) (PENDING excluded)
      delivered        - count of status == "DELIVERED"
      dropped          - count of status == "DROPPED"
      loss_rate         - dropped / total, or 0.0 if total == 0
      avg_latency_us   - mean(delivered_at - created_at) over DELIVERED
                          packets only, or None if there are none
      min_latency_us   - min of the same set, or None if empty
      max_latency_us   - max of the same set, or None if empty
      # Rashed-Step 9.A-08-07-2026-start
      latency_stddev_us - population stddev (statistics.pstdev) of the
                          same latency set. 0.0 for exactly one
                          DELIVERED packet (no variation to observe,
                          not "unknown"), None only when there are zero.
      jitter_us         - mean absolute difference between EACH
                          DELIVERED packet's latency and the PREVIOUS
                          one's, in packet-creation order (sorted by
                          created_at - NOT packet_log append order,
                          which can interleave multiple nodes'
                          packets arbitrarily when this function is
                          called on an aggregated cross-node list).
                          None if fewer than 2 DELIVERED packets (no
                          successive pair to compare). This is the
                          conventional "packet delay variation"
                          definition (same spirit as RFC 3550's jitter,
                          simplified for this simulator's timestamps).
      p50_latency_us,
      p95_latency_us,
      p99_latency_us    - percentiles of the same latency set, linear-
                          interpolation method (same convention as
                          numpy's default 'linear' interpolation) - see
                          _percentile() below. None if empty.
      # Rashed-Step 9.A-08-07-2026-end
    """
    delivered = [p for p in packets if p.status == "DELIVERED"]
    dropped = [p for p in packets if p.status == "DROPPED"]
    total = len(delivered) + len(dropped)

    latencies = [p.delivered_at - p.created_at for p in delivered if p.delivered_at is not None]

    # Rashed-Step 9.A-08-07-2026-start
    # Sorted by created_at (generation order) - the order Packets happen
    # to sit in `packets`/`delivered` is whatever order sent_completed()
    # appended them in, which for a cross-node aggregated list (multiple
    # APs' packet_logs concatenated - see simulation.py) is essentially
    # arbitrary relative to when each packet was actually GENERATED.
    # Jitter is only a meaningful "variation between consecutive
    # packets" measure if "consecutive" means consecutive in time.
    delivered_by_creation = sorted(
        (p for p in delivered if p.delivered_at is not None),
        key=lambda p: p.created_at,
    )
    latencies_in_order = [p.delivered_at - p.created_at for p in delivered_by_creation]

    if len(latencies_in_order) >= 2:
        diffs = [
            abs(latencies_in_order[i] - latencies_in_order[i - 1])
            for i in range(1, len(latencies_in_order))
        ]
        jitter_us = sum(diffs) / len(diffs)
    else:
        jitter_us = None

    latency_stddev_us = statistics.pstdev(latencies) if latencies else None

    sorted_latencies = sorted(latencies)
    p50 = _percentile(sorted_latencies, 50)
    p95 = _percentile(sorted_latencies, 95)
    p99 = _percentile(sorted_latencies, 99)
    # Rashed-Step 9.A-08-07-2026-end

    return {
        "total": total,
        "delivered": len(delivered),
        "dropped": len(dropped),
        "loss_rate": (len(dropped) / total) if total > 0 else 0.0,
        "avg_latency_us": (sum(latencies) / len(latencies)) if latencies else None,
        "min_latency_us": min(latencies) if latencies else None,
        "max_latency_us": max(latencies) if latencies else None,
        # Rashed-Step 9.A-08-07-2026-start
        "latency_stddev_us": latency_stddev_us,
        "jitter_us": jitter_us,
        "p50_latency_us": p50,
        "p95_latency_us": p95,
        "p99_latency_us": p99,
        # Rashed-Step 9.A-08-07-2026-end
    }
# Rashed-Step 8.G-08-06-2026-end


# Rashed-Step 9.A-08-07-2026-start
def _percentile(sorted_values: list, p: float):
    """
    Linear-interpolation percentile (same convention as numpy's default
    'linear' method): rank = (n-1) * p/100, interpolate between the
    values at floor(rank) and ceil(rank). sorted_values must already be
    sorted ascending. Returns None for an empty list.

    Example: sorted_values=[100,150,200,250,300], p=95 -> rank=3.8 ->
    interpolate between index 3 (250) and index 4 (300) at 80% ->
    250 + 0.8*(300-250) = 290.
    """
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (p / 100.0)
    lower = int(rank // 1)
    upper = lower + 1
    if upper >= len(sorted_values):
        return sorted_values[-1]
    frac = rank - lower
    return sorted_values[lower] + frac * (sorted_values[upper] - sorted_values[lower])


def compute_packet_stats_by_node(node_packet_logs: "dict[str, list[Packet]]") -> dict:
    """
    Per-node breakdown: {node_name: packet_log, ...} ->
    {node_name: compute_packet_stats(packet_log), ...}. Same underlying
    computation as compute_packet_stats(), just run once per node
    instead of once over an aggregated cross-node list - useful for
    spotting a single AP/gNB behaving differently from its peers (e.g.
    one station stuck near the edge of range with much higher loss)
    that an aggregate-only number would average away.
    """
    return {name: compute_packet_stats(log) for name, log in node_packet_logs.items()}
# Rashed-Step 9.A-08-07-2026-end


# Rashed-Step 9.D-08-07-2026-start
# Packet-level CSV export - optional (opt-in via singleRun.py's
# --export-packets-csv, unset by default), for offline analysis at
# individual-packet granularity rather than the aggregate/per-node
# stats compute_packet_stats()/compute_packet_stats_by_node() already
# print. Deliberately its own proper multi-column CSV, NOT copying
# common/common.py's existing lool.csv pattern's two known bugs (a
# single quoted header field with embedded commas instead of separate
# columns, and a header/data column-count mismatch) - see "Project
# details/Step 9.txt"'s 9.D section for the lool.csv code this was
# checked against before writing this.
PACKET_CSV_HEADER = [
    "seed", "technology", "node", "packet_id", "source", "destination",
    "payload_bytes", "header_bytes", "total_bytes", "packet_type",
    "created_at_us", "retry_count", "status", "delivered_at_us", "latency_us",
]


def packet_to_csv_row(packet: Packet, seed, technology: str, node: str) -> list:
    """
    Pure function (no I/O) - builds one CSV row (list, same column
    order as PACKET_CSV_HEADER) for a single Packet. Split out from
    export_packets_csv() so it's independently unit-testable without
    touching the filesystem. latency_us is delivered_at - created_at
    for a DELIVERED packet with a real delivered_at, "" otherwise
    (PENDING/DROPPED packets, or the theoretical case of a DELIVERED
    packet somehow missing delivered_at) - same "no defined latency"
    treatment compute_packet_stats() already uses for those cases,
    just expressed as an empty CSV cell instead of a Python None.
    """
    if packet.status == "DELIVERED" and packet.delivered_at is not None:
        latency_us = packet.delivered_at - packet.created_at
    else:
        latency_us = ""
    return [
        seed, technology, node, packet.packet_id, packet.source, packet.destination,
        packet.payload_bytes, packet.header_bytes, packet.total_bytes(), packet.packet_type,
        packet.created_at, packet.retry_count, packet.status,
        packet.delivered_at if packet.delivered_at is not None else "",
        latency_us,
    ]


def export_packets_csv(path: str, seed, node_packet_logs_by_tech: "dict[str, dict[str, list[Packet]]]") -> int:
    """
    Append one CSV row per Packet to `path`, across every (technology,
    node) pair in node_packet_logs_by_tech - e.g.
    {"WiFi": {"AP 1": [...], "AP 2": [...]}, "NRU": {"Gnb 1": [...]}}.
    Same "write header once if the file doesn't already exist, then
    append rows" pattern as lool.csv (so running with -r N > 1, or
    running the same --export-packets-csv path across multiple
    separate invocations, accumulates rows rather than overwriting) -
    the `seed` column is what keeps rows from different runs
    distinguishable once appended to the same file.

    Returns the number of rows written (packet count), mainly so a
    caller/scenario can print a confirmation without re-counting.
    """
    import csv
    import os

    write_header = not os.path.isfile(path)
    rows_written = 0
    with open(path, mode="a", newline="") as f:
        writer = csv.writer(f, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
        if write_header:
            writer.writerow(PACKET_CSV_HEADER)
        for technology, node_logs in node_packet_logs_by_tech.items():
            for node, packets in node_logs.items():
                for p in packets:
                    writer.writerow(packet_to_csv_row(p, seed, technology, node))
                    rows_written += 1
    return rows_written
# Rashed-Step 9.D-08-07-2026-end
