# Rashed-Step 2.A-12-30-2025-start
import math
import random
from typing import Tuple
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
