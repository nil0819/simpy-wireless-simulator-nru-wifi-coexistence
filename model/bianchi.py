# Rashed-Step pre_11.C-08-13-2026-start
"""
Bianchi's 802.11 DCF saturation-throughput model (simplified closed form).

G. Bianchi, "Performance Analysis of the IEEE 802.11 Distributed
Coordination Function," IEEE Journal on Selected Areas in Communications,
18(3), 2000.

Models n saturated (always-backlogged) Wi-Fi stations sharing one channel
under the DCF (CSMA/CA + binary exponential backoff) access rule, purely
combinatorially - no path loss/SINR/capture-effect concept at all (every
attempt is either a clean success or a collision, decided only by whether
more than one station's backoff timer hit zero in the same slot).

Two coupled unknowns, solved here via bisection (not naive fixed-point
iteration - see KNOWN LIMITATION below for why that matters):
  tau = P(a given station transmits in a randomly chosen slot)
  p   = P(a transmitted frame collides | it was transmitted)
      = 1 - (1-tau)^(n-1)   (someone else also transmitted in that slot)

  tau(p) = 2*(1-2p) / [(1-2p)*(W+1) + p*W*(1-(2p)^m)]

where W = cw_min+1 (minimum contention window, i.e. backoff drawn
uniformly from [0, cw_min]) and m is the number of backoff STAGES before
the window stops growing (cw_max+1 = W * 2^m). m=0 (cw_min == cw_max,
fixed window) collapses this to the well-known tau = 2/(W+1), independent
of p - freezing on a busy channel doesn't change which backoff VALUE gets
drawn, only when it's consumed.

p, as defined above, is exactly this simulator's own printed PCOLL metric
(failed_transmissions / (failed+succeeded), i.e. collision probability
GIVEN a transmission attempt) - directly comparable, no unit conversion
needed.

KNOWN LIMITATION (confirmed with Rashed, 2026-08-13 - see Project
details/Step pre_11.txt): the (1-2p) terms in tau(p) above are only
mathematically well-posed for p < 0.5. At high enough contention for a
given window (e.g. N=20 saturated stations at this simulator's default
cw_min=15/cw_max=63, W=16, m=2), the fixed-point equation p =
1-(1-tau(p))^(n-1) has NO crossing in the valid p<0.5 range at all - the
simplified closed-form breaks down, not just gets less accurate. solve_p()
detects this (no sign change across the whole valid bisection interval)
and raises BianchiNotValidError instead of silently returning a number
from outside the formula's valid domain (naive fixed-point iteration can
converge to such an out-of-domain "solution" without any warning - this
is exactly what happened during this module's own development, which is
why bisection is used here instead). The fix for that regime would be
Bianchi's full bi-dimensional Markov chain (not this simplified closed
form) - out of scope for now, deliberately not implemented (see Step
pre_11.txt for the scope discussion). Practically: this module is
validated against the simulator at contention levels where it IS valid
(N=1, N=5 - see test/test_model_bianchi.py), not at N=20.
"""
from typing import Dict


class BianchiNotValidError(Exception):
    """Raised when solve_p() cannot find a solution with p < 0.5 for the
    given (n, cw_min, cw_max) - see this module's KNOWN LIMITATION note."""
    pass


def backoff_stages(cw_min: int, cw_max: int) -> int:
    """
    m = number of doubling steps from (cw_min+1) to reach (cw_max+1).
    m=0 if cw_max <= cw_min (fixed window, matches this simulator's
    --wifi_cw_min == --wifi_cw_max convention for "no exponential
    backoff" runs - see Project details/Step 6.D).
    """
    w_min = cw_min + 1
    w_max = cw_max + 1
    if w_max <= w_min:
        return 0
    m = 0
    w = w_min
    while w < w_max:
        w *= 2
        m += 1
    return m


def _tau_of_p(p: float, W: int, m: int) -> float:
    two_p = 2.0 * p
    if m == 0:
        return 2.0 / (W + 1)
    denom = (1.0 - two_p) * (W + 1) + p * W * (1.0 - two_p ** m)
    return (2.0 * (1.0 - two_p)) / denom


def _residual(p: float, n: int, W: int, m: int) -> float:
    tau = _tau_of_p(p, W, m)
    rhs = 1.0 - (1.0 - tau) ** (n - 1) if n > 1 else 0.0
    return rhs - p


def solve_tau_p(n: int, cw_min: int, cw_max: int, lo: float = 1e-12, hi: float = 0.499999999,
                 iters: int = 200) -> Dict[str, float]:
    """
    Bisection solve for (tau, p) given n contending stations and a
    cw_min/cw_max window. Returns {"tau": ..., "p": ..., "m": ..., "W": ...}.

    Raises BianchiNotValidError if no root exists in the valid p<0.5
    range for these parameters (see module KNOWN LIMITATION).

    n=1 is a degenerate but valid case: p=1-(1-tau)^0=0 always (a lone
    station can never collide with itself), so this correctly reduces to
    tau=2/(W+1) regardless of m, with no bisection needed.
    """
    W = cw_min + 1
    m = backoff_stages(cw_min, cw_max)

    if n <= 1:
        tau = _tau_of_p(0.0, W, m)
        return {"tau": tau, "p": 0.0, "m": float(m), "W": float(W)}

    if m == 0:
        # Fixed window: tau = 2/(W+1) is a CONSTANT, independent of p (no
        # (1-2p) term exists in this branch at all - see _tau_of_p). p is
        # then directly determined, not found via a fixed point, and has
        # no reason to be capped at 0.5 (that cap is a real domain limit
        # of the m>0 closed-form's (1-2p) terms, which simply don't
        # appear here). Computing it via the same bisection path as m>0
        # would wrongly raise BianchiNotValidError whenever the direct
        # answer happens to exceed 0.5 (found while writing this
        # module's own tests - see Project details/Step pre_11.txt).
        tau = _tau_of_p(0.0, W, m)
        p = 1.0 - (1.0 - tau) ** (n - 1)
        return {"tau": tau, "p": p, "m": float(m), "W": float(W)}

    g_lo = _residual(lo, n, W, m)
    g_hi = _residual(hi, n, W, m)
    if g_lo * g_hi > 0:
        raise BianchiNotValidError(
            f"No p<0.5 solution for n={n}, cw_min={cw_min}, cw_max={cw_max} "
            f"(W={W}, m={m}) - the simplified Bianchi closed-form is not "
            f"valid at this contention level/window. See this module's "
            f"docstring KNOWN LIMITATION section."
        )
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        g_mid = _residual(mid, n, W, m)
        if g_mid == 0.0:
            lo = hi = mid
            break
        if g_lo * g_mid < 0:
            hi = mid
        else:
            lo, g_lo = mid, g_mid
    p = (lo + hi) / 2.0
    tau = _tau_of_p(p, W, m)
    return {"tau": tau, "p": p, "m": float(m), "W": float(W)}


def collision_probability(n: int, cw_min: int, cw_max: int) -> float:
    """
    P(a Wi-Fi transmission attempt collides), a.k.a. PCOLL in this
    simulator's own printed output.
    """
    return solve_tau_p(n, cw_min, cw_max)["p"]


def saturation_throughput(
    n: int,
    cw_min: int,
    cw_max: int,
    payload_bits: float,
    t_success_us: float,
    t_collision_us: float,
    sigma_us: float,
) -> float:
    """
    Bianchi's normalized saturation throughput S (bits/us == Mbps), eq.
    (9)/(11)-(13) of the original paper:

      S = P_s * P_tr * E[payload] / [(1-P_tr)*sigma + P_tr*P_s*T_s
                                      + P_tr*(1-P_s)*T_c]

    where P_tr = 1-(1-tau)^n (someone transmits this slot), P_s =
    n*tau*(1-tau)^(n-1) / P_tr (that transmission is successful, i.e.
    exactly one station transmitted). t_success_us/t_collision_us are the
    slot-equivalent durations of a successful transmission and of a
    collision respectively (caller supplies these - they depend on this
    simulator's own frame/ACK/DIFS timing via Times.py, not on Bianchi's
    model, which treats them as external constants).
    """
    tau = solve_tau_p(n, cw_min, cw_max)["tau"]
    p_tr = 1.0 - (1.0 - tau) ** n
    if p_tr <= 0.0:
        return 0.0
    p_s = (n * tau * (1.0 - tau) ** (n - 1)) / p_tr
    numerator = p_s * p_tr * payload_bits
    denominator = (
        (1.0 - p_tr) * sigma_us
        + p_tr * p_s * t_success_us
        + p_tr * (1.0 - p_s) * t_collision_us
    )
    if denominator <= 0.0:
        return 0.0
    return numerator / denominator


if __name__ == "__main__":
    # Default Wi-Fi CW_MIN=15/CW_MAX=63 (W=16, m=2). N=20 is expected to
    # raise BianchiNotValidError - see module KNOWN LIMITATION.
    for n in (1, 5, 20):
        try:
            result = solve_tau_p(n, cw_min=15, cw_max=63)
            print(f"N={n:>2}  tau={result['tau']:.6f}  PCOLL(model)={result['p']*100:.1f}%")
        except BianchiNotValidError as e:
            print(f"N={n:>2}  {e}")
# Rashed-Step pre_11.C-08-13-2026-end
