# Rashed-Step 11.A-08-12-2026-start
"""
Step 11.A: GenericTransmitter - a THIRD, protocol-agnostic device that
actively transmits and contends for the shared channel, sitting
alongside Wi-Fi (CSMA/CA-ish DCF/EDCA) and NR-U (Cat-4 LBT) as a real
competitor for airtime.

WHY THIS EXISTS
Rashed asked (2026-08-12) for CLI commands to check a scenario with "a
generic wireless which is also in the similar sensing region and
communicating" / "the wireless device can traverse and transmit".
Two existing GenericWirelessDevice (Step 7.A) subclasses/scenarios
already exist, but neither fits "communicates/transmits saturated
traffic and competes for the channel like a normal node":
  - singleRunSpectrum.py's sniffers are PASSIVE ONLY (sniff(), never
    transmit()) - a spectrum analyzer, not a communicating device.
  - attacker/packet_attacker.py's PacketAttacker DOES transmit, but
    only in an event-driven capture->spoof->replay timeline with no
    sense-before-transmit discipline and no notion of "ongoing
    traffic" - it's an attack tool, not a well-behaved third traffic
    source.
Confirmed via AskUserQuestion before building this: the generic device
should actively transmit and contend for the channel (not just sense
it), and this capability didn't exist yet as a ready CLI scenario -
this file is exactly that missing piece.

WHAT "GENERIC" MEANS HERE (READ BEFORE USING)
This is deliberately NOT modeling any specific real standard's MAC.
Unlike Wi-Fi's DCF (Step 6.A, Bianchi-validated) or EDCA (Step 10.B,
real 802.11e CW/AIFSN per class) or NR-U's Cat-4 LBT (real 3GPP
exponential backoff + mcot), GenericTransmitter uses ONE FLAT UNIFORM
RANDOM BACKOFF RANGE (backoff_min_us..backoff_max_us, no CW growth, no
retry-limit-driven widening) before each transmission attempt, and a
FIXED transmission duration (tx_duration_us) - not derived from a
Packet's payload_bytes the way Wi-Fi's PPDU duration is (Step 8.C).
This is intentional: it represents "some other, unspecified/unknown
wireless technology sharing the band", not a re-implementation of any
particular real protocol. If you need standards-accurate behavior for
a THIRD real technology, that's new, separate scope - this is a
generic stand-in.

WHAT IS AND ISN'T MODELED
  - Sense-before-transmit (in-band CCA via the inherited
    is_channel_busy(), same energy-detect primitive every other node
    type in this simulator uses) WITH freeze-and-resume backoff (same
    convention as wifi.py's wait_back_off()/EDCA's wait_back_off_edca()
    - if the channel goes busy mid-backoff, the countdown pauses and
    resumes from wherever it was, it does not restart from scratch).
  - Saturated traffic only: this device ALWAYS has something to send
    (immediately starts a new backoff+transmit cycle after each
    attempt finishes) - matching this simulator's existing meaning of
    "saturated" for Wi-Fi/NR-U (Step 8.B).
  - Real ActiveTx registration on the shared Channel (via the
    inherited transmit()) - a GenericTransmitter's signal is exactly
    as real to every other node's SINR/collision math as a Wi-Fi or
    NR-U transmission is. It genuinely can cause (and suffer) real
    interference.
  - Mobility (inherited from GenericWirelessDevice/Step 7.A's
    WaypointMobility) - a GenericTransmitter can move between
    positions/zones while continuing to contend for the channel from
    wherever it currently is.
  - NOT modeled: any receive/decode/ACK logic, any notion of "this
    transmission was successfully received by someone" beyond "this
    device's own transmit() call completed its airtime uninterrupted"
    - same limitation the base GenericWirelessDevice already has (see
    its own module docstring). transmissions_completed counts
    completed AIRTIME, not confirmed delivery. A caller wanting a
    delivery/SINR judgment can call estimate_sinr_db() (inherited)
    against a specific attempt if needed - not done automatically here.
"""

import random
from typing import Optional

import simpy

from common.common_phy import Pos
from common.packet import Packet
from generic.generic_device import Config_Generic, GenericWirelessDevice


class GenericTransmitter(GenericWirelessDevice):
    """
    See module docstring. Adds a saturated sense-then-transmit driving
    loop on top of GenericWirelessDevice's raw sniff()/transmit()
    primitives.
    """

    def __init__(
        self,
        env: simpy.Environment,
        name: str,
        channel,
        config: Config_Generic,
        pos: Pos,
        tx_duration_us: float = 500.0,
        backoff_min_us: float = 0.0,
        backoff_max_us: float = 500.0,
        sense_step_us: float = 1.0,
        payload_bytes: int = 500,
        mobility_speed_mps: float = 0.0,
        area_w: float = 50.0,
        area_h: float = 50.0,
        mobility_pause_s: float = 0.0,
    ):
        super().__init__(
            env, name, channel, config, pos,
            mobility_speed_mps=mobility_speed_mps, area_w=area_w, area_h=area_h,
            mobility_pause_s=mobility_pause_s,
        )
        self.tx_duration_us = tx_duration_us
        self.backoff_min_us = backoff_min_us
        self.backoff_max_us = backoff_max_us
        self.sense_step_us = sense_step_us
        self.payload_bytes = payload_bytes

        # Attempt-level counters (distinct from the inherited tx_log/
        # packet_log, which only ever record COMPLETED attempts - these
        # also count one still in-flight when the simulation ends).
        self.transmissions_attempted = 0
        self.transmissions_completed = 0
        self._packet_seq = 0

        self.process = env.process(self.start())

    def _make_packet(self) -> Packet:
        self._packet_seq += 1
        return Packet(
            packet_id=f"{self.name}-{self._packet_seq:06d}",
            source=self.name,
            destination=self.name,
            payload_bytes=self.payload_bytes,
            header_bytes=0,
            created_at=self.env.now,
        )

    def wait_backoff(self):
        """
        Flat uniform random backoff (see module docstring for why this
        is NOT CW-based like Wi-Fi/NR-U) with freeze-and-resume on
        channel-busy, same convention as wifi.WiFi.wait_back_off()/
        wait_back_off_edca(). Senses in-band (is_channel_busy()'s
        default wideband=False), matching every other node type's own
        CCA behavior.
        """
        remaining_us = random.uniform(self.backoff_min_us, self.backoff_max_us)
        while remaining_us > 0:
            if self.is_channel_busy():
                yield self.channel.state_changed
                continue
            step = min(self.sense_step_us, remaining_us)
            yield self.env.timeout(step)
            remaining_us -= step

    def start(self):
        """
        Top-level driving loop: backoff -> transmit -> repeat, forever
        (saturated). GeneratorExit-safe by construction - wait_backoff()
        only yields env.timeout()/channel.state_changed (nothing to
        clean up there), and transmit() already handles its own
        GeneratorExit-safe cleanup (Step 5.I convention, inherited
        unchanged from GenericWirelessDevice) - yield from propagates
        GeneratorExit into it correctly, same pattern already used by
        attacker/packet_attacker.py's spoof()/replay().
        """
        while True:
            yield from self.wait_backoff()
            packet = self._make_packet()
            self.transmissions_attempted += 1
            yield from self.transmit(self.tx_duration_us, packet=packet)
            self.transmissions_completed += 1
# Rashed-Step 11.A-08-12-2026-end
