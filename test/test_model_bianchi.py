# Rashed-Step pre_11.C-08-13-2026-start
"""
Unit tests for model/bianchi.py - pure math, no simulator invocation (fast).
"""
import pytest

from model.bianchi import (
    BianchiNotValidError,
    backoff_stages,
    collision_probability,
    saturation_throughput,
    solve_tau_p,
)


def test_backoff_stages_default_wifi_window():
    # cw_min=15, cw_max=63 -> W=16, doubles 16->32->64, m=2
    assert backoff_stages(15, 63) == 2


def test_backoff_stages_fixed_window():
    # cw_min == cw_max (Step 6.D's fixed-Wo convention) -> m=0
    assert backoff_stages(31, 31) == 0
    assert backoff_stages(15, 10) == 0  # cw_max < cw_min also treated as fixed


def test_solve_tau_p_lone_station_never_collides():
    result = solve_tau_p(1, cw_min=15, cw_max=63)
    assert result["p"] == 0.0
    # At p=0, classic Bianchi's tau(p) = 2*(1-2p) / [(1-2p)*(W+1) +
    # p*W*(1-(2p)^m)] collapses to 2/(W+1) regardless of m, since every
    # p-dependent term vanishes. W=16 -> 2/17.
    assert result["tau"] == pytest.approx(2.0 / 17.0, rel=1e-9)


def test_solve_tau_p_fixed_window_independent_of_p():
    # m=0 -> tau = 2/(W+1) regardless of n/p (classic result: freezing on
    # a busy channel doesn't change which backoff VALUE gets drawn).
    # cw_min=cw_max=31 -> W=32 -> tau=2/33.
    for n in (1, 5, 20):
        result = solve_tau_p(n, cw_min=31, cw_max=31)
        assert result["tau"] == pytest.approx(2.0 / 33.0, rel=1e-9)


def test_solve_tau_p_five_stations_default_window():
    # Cross-checked via independent bisection during this module's own
    # development (Project details/Step pre_11.txt) - not a value from
    # the literature, a value THIS implementation converges to and is
    # then locked in as a regression check.
    result = solve_tau_p(5, cw_min=15, cw_max=63)
    assert result["p"] == pytest.approx(0.2903, abs=0.001)
    assert 0.0 < result["tau"] < 1.0


def test_solve_tau_p_raises_when_no_valid_solution():
    # N=20 at the default Wi-Fi window has no p<0.5 solution for this
    # simplified closed-form - see module KNOWN LIMITATION. Must raise,
    # not silently return an out-of-domain number.
    with pytest.raises(BianchiNotValidError):
        solve_tau_p(20, cw_min=15, cw_max=63)


def test_collision_probability_matches_solve_tau_p():
    assert collision_probability(5, 15, 63) == solve_tau_p(5, 15, 63)["p"]


def test_saturation_throughput_positive_and_bounded():
    thr = saturation_throughput(
        n=5, cw_min=15, cw_max=63,
        payload_bits=1472 * 8, t_success_us=286.0, t_collision_us=286.0,
        sigma_us=9.0,
    )
    assert thr > 0.0
    # Sanity upper bound: can't exceed payload_bits/sigma_us (an
    # impossible zero-overhead, always-successful channel).
    assert thr < (1472 * 8) / 9.0


def test_saturation_throughput_zero_stations_is_zero():
    # n=0 -> P_tr=0 -> throughput must be exactly 0, not a division error.
    thr = saturation_throughput(
        n=0, cw_min=15, cw_max=63,
        payload_bits=1472 * 8, t_success_us=286.0, t_collision_us=286.0,
        sigma_us=9.0,
    )
    assert thr == 0.0
# Rashed-Step pre_11.C-08-13-2026-end
