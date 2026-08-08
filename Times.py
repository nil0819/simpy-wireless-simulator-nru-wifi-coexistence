import math
from typing import Optional

MCS = {
    0: [6, 6],
    1: [9, 6],
    2: [12, 12],
    3: [18, 12],
    4: [24, 24],
    5: [36, 24],
    6: [48, 24],
    7: [54, 24],
}

# Rashed-Step 5.D-02-06-2026-start
# Approximate/typical minimum-SINR-for-reliable-decode thresholds per
# legacy 802.11a/g OFDM MCS index, in dB. These are representative values
# commonly used in DCF/coexistence simulation literature (rising with
# modulation order and coding rate: BPSK 1/2 at the low end, 64-QAM 3/4 at
# the top) - not vendor-certified figures for any specific chipset. Swap
# these out for your own measured/published numbers if you need exact
# reproduction of a particular paper's PHY abstraction.
WIFI_MCS_SINR_THRESHOLDS_DB = {
    0: 5.0,   # BPSK 1/2,   6 Mbps
    1: 6.0,   # BPSK 3/4,   9 Mbps
    2: 8.0,   # QPSK 1/2,  12 Mbps
    3: 11.0,  # QPSK 3/4,  18 Mbps
    4: 15.0,  # 16-QAM 1/2, 24 Mbps
    5: 19.0,  # 16-QAM 3/4, 36 Mbps
    6: 23.0,  # 64-QAM 2/3, 48 Mbps
    7: 25.0,  # 64-QAM 3/4, 54 Mbps
}
# Rashed-Step 5.D-02-06-2026-end


class Times:

    t_slot = 9  # [us]
    t_sifs = 16  # [us]
    # Rashed-Step 6.A-07-31-2026-start
    # BUGFIX: was 3*t_slot+t_sifs = 43us. The 802.11 standard defines
    # DIFS = SIFS + 2*aSlotTime = 34us (flagged by the realism validation
    # report, 2026-07-31 - confirmed against 802.11a/2020 spec values).
    t_difs = 2 * t_slot + t_sifs  # [us]
    # Rashed-Step 6.A-07-31-2026-end
    ack_timeout = 45  # [us]

    # Rashed-Step 10.B-08-07-2026-start
    @staticmethod
    def get_aifs_us(aifsn: int) -> float:
        """
        AIFS (Arbitration Inter-Frame Space) for a given AIFSN, per
        802.11e: AIFS = AIFSN * aSlotTime + aSIFSTime. Generalizes
        t_difs (DCF's single fixed DIFS = 2*t_slot+t_sifs) to EDCA's
        per-Access-Category value - get_aifs_us(2) == t_difs exactly,
        by construction (AC_VO/AC_VI's real-spec AIFSN is 2 - see
        common.packet.DEFAULT_EDCA_PARAMS).
        """
        return aifsn * Times.t_slot + Times.t_sifs
    # Rashed-Step 10.B-08-07-2026-end

    # Mac overhead
    mac_overhead = 40 * 8  # [b]

    # ACK size
    ack_size = 14 * 8  # [b]

    # overhead
    _overhead = 22  # [b]

    def __init__(self, payload: int = 1472, mcs: int = 7):
        self.payload = payload
        self.mcs = mcs
        # OFDM parameters
        self.phy_data_rate = MCS[mcs][0] * pow(
            10, -6
        )  # [Mb/us] Possible values 6, 9, 12, 18, 24, 36, 48, 54
        self.phy_ctr_rate = MCS[mcs][1] * pow(10, -6)  # [Mb/u]
        self.n_data = 4 * self.phy_data_rate  # [b/symbol]
        self.n_ctr = 4 * self.phy_ctr_rate  # [b/symbol]
        self.data_rate = MCS[mcs][0]  # [b/us]
        self.ctr_rate = MCS[mcs][1]  # [b/us]

        self.ofdm_preamble = 16  # [us]
        self.ofdm_signal = 24 / self.ctr_rate  # [us]

    # Data frame time
    # Rashed-Step 8.C-08-06-2026-start
    # UPGRADE: added an optional payload_bytes override so a caller can
    # get the PPDU duration for a SPECIFIC packet's payload size without
    # constructing a whole new Times object (mcs stays fixed per-node;
    # only the payload varies per-packet). Defaults to self.payload (the
    # value Times() was constructed with) when omitted, so every
    # pre-existing no-arg call site (rogue AP/jammer/selfbackoff files,
    # any test) is byte-identical to before this change.
    def get_ppdu_frame_time(self, payload_bytes: Optional[int] = None):
        payload = payload_bytes if payload_bytes is not None else self.payload
        msdu = payload * 8  # [b]
    # Rashed-Step 8.C-08-06-2026-end
        # MacFrame
        mac_frame = Times.mac_overhead + msdu  # [b]
        # PPDU Padding
        ppdu_padding = math.ceil(
            (Times._overhead + mac_frame) / self.n_data
        ) * self.n_data - (Times._overhead + mac_frame)
        # CPSDU Frame
        cpsdu = Times._overhead + mac_frame + ppdu_padding  # [b]
        # PPDU Frame
        ppdu = self.ofdm_preamble + self.ofdm_signal + cpsdu / self.data_rate  # [us]
        ppdu_tx_time = math.ceil(ppdu)
        return ppdu_tx_time  # [us]

    # ACK frame time with SIFS
    def get_ack_frame_time(self):
        ack = Times._overhead + Times.ack_size  # [b]
        ack = self.ofdm_preamble + self.ofdm_signal + ack / self.ctr_rate  # [us]
        ack_tx_time = Times.t_sifs + ack
        # return math.ceil(ack_tx_time)  # [us]
        return 44

    # # ACK Timeout
    # def get_ack_timeout():
    #     return ack_timeout

    def get_thr(self):
        return (self.payload * 8) / (
            self.get_ppdu_frame_time() + self.get_ack_frame_time() + Times.t_difs
        )