# Rashed-Step 9.C-08-07-2026-start
"""
Step 9.C: PacketAttacker - packet-level attack capabilities (spoofing +
replay), built on Step 7.A's generic.generic_device.GenericWirelessDevice
and Step 9.B's real Packet visibility (ActiveTx.packet / VisibleTx.packet).

WHY THIS IS A SEPARATE FILE
The existing attacker/roguewificad.py, attacker/roguewifijammer.py, and
attacker/roguewifiselfbackoff.py have been explicitly out of scope since
Step 5 ("For now do not focus on the CAD attack or any other attack...
We will focus on the attack later" - see "Project details/STATUS -
resume context.txt"'s scope constraint section). Rashed confirmed via
AskUserQuestion for 9.C: this new capability should live in its own new
file, NOT be bolted onto any of those three - so this file touches
NONE of them, and none of them import from or depend on this file
either. They remain exactly as untouched as before.

WHAT "SPOOFING" AND "REPLAY" MEAN HERE
Both are built the same way a real MAC-spoofing/replay attack works:
the attacker's PHYSICAL transmission (position, tx power, timing - all
via the inherited transmit()) is completely real and its own, but the
Packet's CLAIMED identity/content is forged or reused.
  - spoof(): constructs a brand-new Packet whose `source` field claims
    to be some other real node's name (e.g. "AP 1", a real WiFi.name),
    while it is physically transmitted from THIS attacker's own
    position/power. Nothing about the physical channel model is
    touched - this is exactly the same "claimed identity != physical
    origin" split real 802.11 address spoofing has, modeled at the
    Packet.source field.
  - replay(): re-transmits an EXACT content copy (same packet_id,
    source, destination, payload_bytes, header_bytes) of a Packet this
    attacker previously captured via sniff()/capture(), after resetting
    its delivery-status fields (status/retry_count/delivered_at) back
    to a fresh PENDING/0/None - this is a NEW transmission of OLD
    content, not a resume of whatever happened to the original.

WHAT THIS DELIBERATELY DOES NOT DO
  - No decode/receive modeling of the attack's effect on a real
    WiFi STA / NR-U UE - GenericWirelessDevice (Step 7.A) has no MAC/
    receive/ACK logic at all, by design (see its own module
    docstring), and this class doesn't add any. What's actually
    modeled: the forged/replayed Packet gets a completely real
    ActiveTx on the shared channel (real tx power, real position, real
    duration), so any REAL node's own SINR-based decode/collision
    logic (wifi.py/nru.py's existing, already-verified success math)
    sees it exactly like any other interfering transmission - the
    attack's channel-level impact (occupying airtime, causing SINR
    degradation / collisions for legitimate traffic) is real and
    already fully modeled by the existing PHY layer. What's NOT
    modeled is a legitimate receiver being fooled into acting on the
    forged/replayed packet's contents (accepting a forged source as
    authentic, replaying a stale command) - there's no receiver-side
    application logic anywhere in this simulator to fool.
  - No MAC-layer channel-access discipline (no CSMA/LBT) - same as the
    base class, transmit() is unrestricted. A subclass or caller that
    wants a more polite/stealthy attacker can call is_channel_busy()
    itself first, same pattern as any other GenericWirelessDevice use.
  - No on-air duration model as detailed as Times.py's real 802.11/
    NR-U PPDU formulas (preamble, SIFS, PHY headers, etc.) - this is a
    generic, protocol-unlabeled attacker, not literally an 802.11 or
    NR-U radio, so duration is estimated from a simple configurable
    link-rate (Config_PacketAttacker.bitrate_mbps) when not given
    explicitly. Callers that want exact WiFi/NR-U-realistic timing can
    still pass duration_us explicitly (e.g. computed the same way
    wifi.py/nru.py do, via Times.py, if a scenario wants that level of
    realism for a specific packet).
"""

import dataclasses
from typing import Dict, List, Optional

from common.common_phy import Pos
from channel.channel import Channel
from common.packet import Packet
from generic.generic_device import Config_Generic, GenericWirelessDevice


@dataclasses.dataclass
class Config_PacketAttacker(Config_Generic):
    # Simplified link-rate model used ONLY to estimate on-air duration
    # for spoof()/replay() when the caller doesn't pass duration_us
    # explicitly - see module docstring's "WHAT THIS DELIBERATELY DOES
    # NOT DO" section. 54.0 (802.11a/g's top OFDM rate) is a reasonable
    # generic default, not tied to any specific technology's real PPDU
    # framing overhead.
    bitrate_mbps: float = 54.0
    # Default tech_label override - PacketAttacker's own transmissions
    # are labeled "ATTACKER" by default (distinct from Config_Generic's
    # plain "GENERIC" default) so they're easy to pick out in a
    # sniff()/VisibleTx breakdown or a scenario's diagnostic print,
    # same "just an opaque string channel.py doesn't special-case"
    # caveat Config_Generic.tech_label already documents.
    tech_label: str = "ATTACKER"


class PacketAttacker(GenericWirelessDevice):
    """
    GenericWirelessDevice subclass adding two packet-level attack
    primitives on top of the inherited raw sniff()/transmit(): spoof()
    (forged source identity) and replay() (re-transmit captured
    content). See module docstring for the full design/rationale.
    """

    def __init__(
        self,
        env,
        name: str,
        channel: Channel,
        config: Config_PacketAttacker,
        pos: Pos,
        **kwargs,
    ):
        super().__init__(env, name, channel, config, pos, **kwargs)
        # packet_id -> most-recently-seen copy of that Packet, built up
        # by capture()/capture_loop(). A dict (not a list) so seeing the
        # same in-flight packet across multiple sniff() samples (e.g.
        # capture_loop()'s periodic polling catching the same long
        # NR-U transmission twice) doesn't create duplicate entries.
        self.captured_packets: Dict[str, Packet] = {}
        # Separate from the inherited packet_log (which records EVERY
        # packet this device transmit()'d, spoofed or replayed alike) -
        # these two track which of those completions were specifically
        # spoof() vs replay() calls, for attack-specific reporting.
        self.spoofed_log: List[Packet] = []
        self.replayed_log: List[Packet] = []
        self._spoof_seq = 0

    # ------------------------------------------------------------------
    # Capture (passive - builds up captured_packets from real traffic)
    # ------------------------------------------------------------------
    def capture(self, threshold_dbm: Optional[float] = None) -> List[Packet]:
        """
        One-shot: sniff() the channel right now, record any newly-seen
        Packet (by packet_id) into self.captured_packets. Returns just
        the packets that were NEW this call (already-known packet_ids
        are skipped, not re-added/overwritten) so a caller driving a
        capture_loop() can log capture events without re-processing the
        same packet on every sample.
        """
        snap = self.sniff(threshold_dbm=threshold_dbm)
        newly_captured = []
        for v in snap.visible_txs:
            if v.packet is not None and v.packet.packet_id not in self.captured_packets:
                self.captured_packets[v.packet.packet_id] = v.packet
                newly_captured.append(v.packet)
        return newly_captured

    def capture_loop(self, duration_us: float, interval_us: float = 50.0,
                      threshold_dbm: Optional[float] = None):
        """
        SimPy process - start with env.process(attacker.capture_loop(...)).
        Repeatedly calls capture() every interval_us for duration_us of
        simulated time. Same periodic-sampling pattern as Step 7.B's
        simulation_spectrum.py _sniffer_process - a passive sniffer only
        ever gets point-in-time reads, no push notifications, so a
        transmission shorter than interval_us could in principle be
        missed entirely (same real-world limitation any point-sampling
        analyzer has - smaller interval_us catches more, at the cost of
        more simulated events).
        """
        end_at = self.env.now + duration_us
        while self.env.now < end_at:
            self.capture(threshold_dbm=threshold_dbm)
            yield self.env.timeout(interval_us)

    # ------------------------------------------------------------------
    # Attack primitives
    # ------------------------------------------------------------------
    def _duration_us_for(self, packet: Packet) -> float:
        """
        Simplified on-air duration estimate: total_bytes*8 bits at
        config.bitrate_mbps (Mbit/s == bits/us numerically, so
        total_bits / bitrate_mbps gives microseconds directly). See
        module docstring's caveat re: this NOT being a real 802.11/
        NR-U PPDU duration formula.
        """
        total_bits = packet.total_bytes() * 8
        return total_bits / self.config.bitrate_mbps

    def spoof(self, forged_source: str, duration_us: Optional[float] = None,
              destination: str = "?", payload_bytes: int = 1000,
              header_bytes: int = 40, rx_pos: Optional[Pos] = None,
              tx_power_dbm: Optional[float] = None,
              packet_id: Optional[str] = None):
        """
        SimPy process - start with env.process(attacker.spoof(...)).

        Constructs a fresh Packet with source=forged_source (e.g. a
        real WiFi AP's or NR-U gNB's own .name - nothing stops a caller
        from forging ANY string, this class doesn't validate that
        forged_source corresponds to a real node) and transmits it via
        the inherited transmit(), which registers a completely real
        ActiveTx at THIS attacker's own physical position/tx power -
        see module docstring for why the physical/claimed split is the
        point of this method. On successful (uninterrupted) completion,
        the Packet lands in both the inherited packet_log (every
        transmitted packet) and this class's own spoofed_log
        (spoof() calls specifically).

        duration_us defaults to _duration_us_for() (the simplified
        bitrate-based estimate, same as replay()) when not given
        explicitly - pass one explicitly for a more realistic duration
        if the scenario has a specific target (e.g. reusing a real
        technology's own Times.py-derived duration).
        """
        self._spoof_seq += 1
        pkt = Packet(
            packet_id=packet_id if packet_id is not None else f"SPOOF-{self.name}-{self._spoof_seq}",
            source=forged_source,
            destination=destination,
            payload_bytes=payload_bytes,
            header_bytes=header_bytes,
            packet_type="DATA",
            created_at=self.env.now,
        )
        dur = duration_us if duration_us is not None else self._duration_us_for(pkt)
        # yield from, not a bare call - transmit() is itself a
        # generator (SimPy process); delegating this way is the same
        # pattern used throughout wifi.py/nru.py since Step 5.I for
        # calling one generator from another.
        yield from self.transmit(dur, rx_pos=rx_pos,
                                  tx_power_dbm=tx_power_dbm, packet=pkt)
        # Only reached if transmit() completed without raising (see its
        # own except/finally) - same "only log terminal/completed
        # states" convention as packet_log itself.
        self.spoofed_log.append(pkt)

    def replay(self, packet: Packet, rx_pos: Optional[Pos] = None,
               tx_power_dbm: Optional[float] = None,
               duration_us: Optional[float] = None):
        """
        SimPy process - start with env.process(attacker.replay(...)).

        Re-transmits an exact CONTENT copy of `packet` (same packet_id/
        source/destination/payload_bytes/header_bytes/packet_type) -
        typically one previously captured via capture()/capture_loop(),
        though nothing here requires that; any Packet instance works.
        A copy is made via dataclasses.replace() with status reset to
        "PENDING", retry_count reset to 0, and delivered_at reset to
        None - this is a NEW transmission attempt of OLD content, so it
        should not silently carry over whatever terminal state
        (DELIVERED/DROPPED, a stale delivered_at timestamp) the
        ORIGINAL transmission happened to end up in.

        duration_us defaults to _duration_us_for(packet) (the
        simplified bitrate-based estimate) when not given explicitly -
        pass one explicitly for a more realistic duration if the
        scenario has a specific target (e.g. reusing the real
        technology's own Times.py-derived duration).
        """
        replay_copy = dataclasses.replace(
            packet, status="PENDING", retry_count=0, delivered_at=None,
            created_at=self.env.now,
        )
        dur = duration_us if duration_us is not None else self._duration_us_for(replay_copy)
        yield from self.transmit(dur, rx_pos=rx_pos, tx_power_dbm=tx_power_dbm,
                                  packet=replay_copy)
        self.replayed_log.append(replay_copy)
# Rashed-Step 9.C-08-07-2026-end
