# Rashed-Step 2.A-12-30-2025-start
import math
import random
from typing import Tuple, Dict
from common.common import *

Pos = Tuple[float, float]

def dist(a: Pos, b: Pos) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def mw_to_dbm(mw: float) -> float:
    return 10.0 * math.log10(mw)

def dbm_to_mw(dbm: float) -> float:
    return 10.0 ** (dbm / 10.0)

def fspl_db(d_m: float, f_hz: float) -> float:
    """Free-space path loss in dB. d_m in meters, f_hz in Hz."""
    d_m = max(d_m, 1e-3)
    c = 3e8
    return 20.0 * math.log10(4.0 * math.pi * d_m * f_hz / c)


def log_distance_pl_db(d_m: float, f_hz: float, n: float = 3.0) -> float:
    """
    Log-distance path loss model:
      PL(d) = PL(d0) + 10*n*log10(d/d0)
    We use d0 = 1m and PL(d0)=FSPL(1m).
    """
    d0 = 1.0
    d_m = max(d_m, 1e-3)
    pl_d0 = fspl_db(d0, f_hz)
    return pl_d0 + 10.0 * n * math.log10(d_m / d0)

def rx_power_dbm(tx_power_dbm: float, d_m: float, f_hz: float, n: float = 3.0, shadow_db: float = 0.0) -> float:
    """
    shadow_db is an additive extra-loss term on top of the deterministic
    log-distance path loss (log-normal shadow fading, expressed directly
    in dB since a Gaussian in dB *is* log-normal in linear space). Positive
    shadow_db = extra attenuation, negative = a temporary "fade up". Callers
    normally get this from Channel.shadow_db(tx_id, rx_pos) rather than
    sampling it here, so the same tx-rx pair keeps a stable shadow value
    for the whole run instead of re-rolling every call.
    """
    pl = log_distance_pl_db(d_m, f_hz, n=n)
    return tx_power_dbm - pl - shadow_db

# Rashed-Step 2.A-12-30-2025-end

# Rashed-Step 5.B-02-06-2026-start
def sample_shadow_db(sigma_db: float) -> float:
    """
    Single log-normal shadow-fading draw, in dB (zero-mean Gaussian with
    std dev sigma_db). sigma_db <= 0 means shadowing is disabled -> 0.0,
    no RNG draw consumed (keeps runs with shadowing off bit-for-bit
    identical to before this feature existed).
    """
    if sigma_db <= 0.0:
        return 0.0
    return random.gauss(0.0, sigma_db)
# Rashed-Step 5.B-02-06-2026-end

# Rashed-Step 5.C-02-06-2026-start
def thermal_noise_dbm(bandwidth_mhz: float, noise_figure_db: float) -> float:
    """
    Receiver thermal noise floor:
      N(dBm) = -174 dBm/Hz (thermal noise density at ~290K) + 10*log10(BW_Hz) + NF(dB)
    Replaces the old hardcoded -94.0 dBm constant in channel.sinr_db().
    At the new defaults (20 MHz, 7 dB NF) this comes out to ~-94.0 dBm too,
    so nothing changes for anyone who doesn't touch bandwidth/NF - it's now
    just derived instead of a magic number, and moves with bandwidth/NF if
    you configure them differently.
    """
    bandwidth_hz = max(bandwidth_mhz, 1e-6) * 1e6
    return -174.0 + 10.0 * math.log10(bandwidth_hz) + noise_figure_db
# Rashed-Step 5.C-02-06-2026-end

# Rashed-Step 5.D-02-06-2026-start
def mcs_sinr_threshold_db(table: Dict[int, float], mcs: int) -> float:
    """
    Look up the minimum SINR (dB) required for a given MCS index in a
    {mcs_index: min_sinr_db} table (e.g. Times.WIFI_MCS_SINR_THRESHOLDS_DB
    or nru.NRU_MCS_SINR_THRESHOLDS_DB). Clamps to the nearest defined index
    instead of raising if mcs falls outside the table's range, so an
    out-of-range config value degrades gracefully rather than crashing a
    run.
    """
    if mcs in table:
        return table[mcs]
    keys = sorted(table.keys())
    if not keys:
        raise ValueError("mcs_sinr_threshold_db: table is empty")
    if mcs < keys[0]:
        return table[keys[0]]
    return table[keys[-1]]
# Rashed-Step 5.D-02-06-2026-end

# Rashed-Step 5.F-02-06-2026-start
# Simplified FCC 47 CFR 15.407 U-NII band EIRP caps (5 GHz only - this
# project's stated scope). The regulation itself specifies *conducted*
# power + antenna-gain limits and per-MHz power spectral density (PSD),
# both of which depend on channel bandwidth and antenna gain - neither of
# which this simulator tracks separately (tx_power_dbm is treated as EIRP
# directly, i.e. an implicit 0 dBi antenna / conducted-power-equals-EIRP
# simplification). Each entry below collapses the real rule to a single
# EIRP number for a representative 20 MHz channel and a <=6 dBi antenna
# (the common case for indoor Wi-Fi/NR-U APs), same "typical/
# representative, not vendor-certified" caveat as the Step 5.D MCS->SINR
# tables. Applies to both WiFi and NR-U configs - Part 15.407 caps are
# per-spectrum, not per-technology, and NR-U operating in U-NII bands is
# subject to the same unlicensed rules as Wi-Fi.
#   - U-NII-1 (5.15-5.25 GHz): 15.407(a)(1) caps PSD at 17 dBm/MHz for an
#     AP -> 17 + 10*log10(20) = 30.0 dBm EIRP over a 20 MHz channel.
#   - U-NII-2A (5.25-5.35 GHz) / U-NII-2C (5.47-5.725 GHz):
#     15.407(a)(2)+(h)(1) - conducted power is bandwidth-dependent (lesser
#     of 250 mW or 11 dBm+10log(B)), but 15.407(h)(1)'s TPC requirement
#     explicitly names 30 dBm as "the mean EIRP value" for these bands, so
#     that's used directly rather than re-deriving it.
#   - U-NII-3 (5.725-5.850 GHz): 15.407(a)(3)(i) - conducted power capped
#     at 1 W (30 dBm) regardless of bandwidth (PSD limit of 30 dBm/500kHz
#     is looser and not binding for typical channel widths) -> +6 dBi
#     antenna = 36.0 dBm EIRP.
#   - U-NII-4 / 5 GHz extension band (5.850-5.895 GHz): 15.407(a)(3)(ii)
#     states an explicit 36 dBm EIRP cap for an indoor AP directly - no
#     antenna-gain math needed for this one.
# Frequencies at or above 5.895 GHz (e.g. the far-separated 5.90 GHz used
# in the Step 5.E verification runs) fall outside every band modeled here
# and are intentionally left unchecked - get_unii_band() returns None.
UNII_BANDS = [
    # (name, f_lo_hz, f_hi_hz, max_eirp_dbm, citation)
    ("U-NII-1", 5.150e9, 5.250e9, 30.0,
     "47 CFR 15.407(a)(1): PSD <=17 dBm/MHz -> 30 dBm EIRP @ 20 MHz"),
    ("U-NII-2A", 5.250e9, 5.350e9, 30.0,
     "47 CFR 15.407(h)(1): TPC requirement anchors mean EIRP at 30 dBm"),
    ("U-NII-2C", 5.470e9, 5.725e9, 30.0,
     "47 CFR 15.407(h)(1): TPC requirement anchors mean EIRP at 30 dBm"),
    ("U-NII-3", 5.725e9, 5.850e9, 36.0,
     "47 CFR 15.407(a)(3)(i): 1 W conducted + <=6 dBi antenna -> 36 dBm EIRP"),
    ("U-NII-4", 5.850e9, 5.895e9, 36.0,
     "47 CFR 15.407(a)(3)(ii): explicit 36 dBm EIRP cap, indoor AP"),
]


def get_unii_band(f_hz: float):
    """
    Return (name, max_eirp_dbm, citation) for the U-NII sub-band
    containing f_hz, or None if f_hz doesn't fall within any band modeled
    in UNII_BANDS (e.g. it's above 5.895 GHz, or in a gap/guard region).
    Band edges are [lo, hi) - a frequency exactly on a shared edge (e.g.
    5.25 GHz) belongs to the higher band, matching how the CFR itself
    describes these as contiguous, non-overlapping ranges.
    """
    for name, lo, hi, max_eirp, citation in UNII_BANDS:
        if lo <= f_hz < hi:
            return name, max_eirp, citation
    return None


def check_eirp_compliance(tech_label: str, tx_power_dbm: float, f_hz: float) -> None:
    """
    Startup-time (not per-transmission) informational check: does this
    tech's configured tx_power_dbm (treated as EIRP - see UNII_BANDS
    comment above) exceed the modeled U-NII cap for its configured
    frequency? Prints a warning if so, but does NOT clamp or raise -
    per-project decision to keep out-of-compliance configs runnable
    (useful for deliberately exploring "what if a rogue/misconfigured
    device exceeds the legal limit" scenarios later) while still making
    the violation visible instead of silent.
    """
    band = get_unii_band(f_hz)
    if band is None:
        print(f"[EIRP CHECK] {tech_label}: f={f_hz / 1e9:.3f} GHz is outside "
              f"all modeled U-NII sub-bands (5.15-5.895 GHz) - no regulatory "
              f"cap checked.")
        return
    name, max_eirp_dbm, citation = band
    if tx_power_dbm > max_eirp_dbm:
        print(f"[EIRP CHECK] WARNING: {tech_label} tx_power_dbm="
              f"{tx_power_dbm:.1f} dBm EXCEEDS the {name} EIRP cap of "
              f"{max_eirp_dbm:.1f} dBm by {tx_power_dbm - max_eirp_dbm:.1f} dB "
              f"({citation}). Not clamped - flagged only.")
    else:
        print(f"[EIRP CHECK] {tech_label} tx_power_dbm={tx_power_dbm:.1f} dBm "
              f"is within the {name} EIRP cap of {max_eirp_dbm:.1f} dBm "
              f"(headroom {max_eirp_dbm - tx_power_dbm:.1f} dB).")
# Rashed-Step 5.F-02-06-2026-end

# Rashed-Step 5.E-02-06-2026-start
def spectral_overlap_fraction(f1_hz: float, bw1_mhz: float, f2_hz: float, bw2_mhz: float) -> float:
    """
    What fraction of channel 1's bandwidth does channel 2 overlap, given
    each channel's center frequency and bandwidth. Meant to be called as
    spectral_overlap_fraction(receiver's own f_hz/bandwidth_mhz,
    interferer's f_hz/bandwidth_mhz) - i.e. "how much of the spectrum the
    receiver is tuned to is this other signal actually stepping on".

    Returns 1.0 for identical co-channel signals (same f_hz, same
    bandwidth - the default before Step 5.E, when everyone was hardcoded
    to 5.18 GHz), 0.0 for channels that don't overlap in frequency at all,
    and a value in between for partial/adjacent-channel overlap. This is a
    simplified flat-PSD approximation (real adjacent-channel rejection
    curves aren't flat), good enough to distinguish "same channel" vs
    "adjacent channel" vs "different band entirely" without hand-tuning a
    separate ACR constant.
    """
    bw1_hz = max(bw1_mhz, 0.0) * 1e6
    bw2_hz = max(bw2_mhz, 0.0) * 1e6
    if bw1_hz <= 0.0:
        return 0.0
    lo1, hi1 = f1_hz - bw1_hz / 2.0, f1_hz + bw1_hz / 2.0
    lo2, hi2 = f2_hz - bw2_hz / 2.0, f2_hz + bw2_hz / 2.0
    overlap_hz = max(0.0, min(hi1, hi2) - max(lo1, lo2))
    return min(1.0, overlap_hz / bw1_hz)
# Rashed-Step 5.E-02-06-2026-end
