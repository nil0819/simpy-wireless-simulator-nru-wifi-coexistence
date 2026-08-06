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
from typing import Optional


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
    """
    delivered = [p for p in packets if p.status == "DELIVERED"]
    dropped = [p for p in packets if p.status == "DROPPED"]
    total = len(delivered) + len(dropped)

    latencies = [p.delivered_at - p.created_at for p in delivered if p.delivered_at is not None]

    return {
        "total": total,
        "delivered": len(delivered),
        "dropped": len(dropped),
        "loss_rate": (len(dropped) / total) if total > 0 else 0.0,
        "avg_latency_us": (sum(latencies) / len(latencies)) if latencies else None,
        "min_latency_us": min(latencies) if latencies else None,
        "max_latency_us": max(latencies) if latencies else None,
    }
# Rashed-Step 8.G-08-06-2026-end
