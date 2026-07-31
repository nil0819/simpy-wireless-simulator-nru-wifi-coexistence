# Rashed-Step 5.H-02-06-2026-start
"""
Step 5.H (H_2) unit tests for the PHY primitives added across Step 5.

Unlike the existing test/test_*.py files in this folder (test_ed_curve.py,
test_backoff_freeze.py, test_hidden_terminal.py), which are print-and-
eyeball diagnostic scripts with no pass/fail assertions, these are real
regression tests: every function here asserts a specific, checkable
condition and raises AssertionError with a useful message if it's wrong.

Runnable two ways:
  - Directly:  python test/test_phy_unit.py   (no pytest dependency -
    the __main__ block below runs every test_* function itself and
    prints a PASS/FAIL summary)
  - Via pytest, if installed: pytest test/test_phy_unit.py
    (function names all start with test_ so pytest will discover them
    with zero extra configuration)

Covers, per the Step 5.txt H_2 plan:
  1. Shadowing distribution sanity (Step 5.B)
  2. Near/far power ordering still holds with shadowing on (Step 5.B)
  3. Capture-effect threshold behavior (Step 3/4's SINR-based decision,
     exercised through Step 5.C/5.E's real noise floor + spectral
     overlap)
  4. SINR->MCS table boundaries (Step 5.D)
Plus regression coverage for pure functions added later in Step 5 that
never got a permanent automated test of their own (5.C's thermal noise
formula, 5.E's spectral overlap fraction, 5.F's U-NII band lookup,
5.G's waypoint mobility interpolation) - these were all verified
ad-hoc via one-off CLI runs/python -c snippets during development but
never persisted as something that can catch a future regression.

Explicitly NOT here (out of scope per current project instructions -
see Step 5.txt's SCOPE NOTE and Project details/STATUS - resume
context.txt): H_1, re-running the CAD paper's DTMC-vs-simulation
comparison. Nothing attack-related is touched or imported by this file.
"""

import sys
import os
import math
import random

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import simpy

from common.common_phy import (
    sample_shadow_db,
    rx_power_dbm,
    dist,
    thermal_noise_dbm,
    mcs_sinr_threshold_db,
    spectral_overlap_fraction,
    get_unii_band,
    UNII_BANDS,
    WaypointMobility,
)
from channel.channel import Channel, ActiveTx
from Times import WIFI_MCS_SINR_THRESHOLDS_DB
from nru.nru import NRU_MCS_SINR_THRESHOLDS_DB


# ---------------------------------------------------------------------
# Shared helper - same pattern as the existing test/*.py files in this
# folder (minimal Channel construction, no simulation.py involved).
# ---------------------------------------------------------------------
def make_channel(env, shadowing_sigma_db: float = 0.0):
    return Channel(
        tx_queue=simpy.PriorityResource(env, capacity=1),
        tx_lock=simpy.Resource(env, capacity=1),
        n_of_stations=1,
        n_of_gNB=0,
        backoffs={},
        airtime_data={},
        airtime_control={},
        airtime_data_NR={},
        airtime_control_NR={},
        shadowing_sigma_db=shadowing_sigma_db,
    )


# =======================================================================
# H_2 item 1: shadowing distribution sanity
# =======================================================================

def test_shadow_disabled_returns_exact_zero():
    random.seed(1)
    for sigma in (0.0, -1.0, -100.0):
        for _ in range(50):
            v = sample_shadow_db(sigma)
            assert v == 0.0, f"sigma={sigma} should always give exactly 0.0, got {v}"


def test_shadow_distribution_matches_configured_sigma():
    random.seed(1)
    sigma = 6.0
    n = 20000
    draws = [sample_shadow_db(sigma) for _ in range(n)]
    mean = sum(draws) / n
    variance = sum((x - mean) ** 2 for x in draws) / n
    std = math.sqrt(variance)
    assert abs(mean) < 0.15, f"sample mean {mean:.4f} should be ~0 (zero-mean Gaussian)"
    assert abs(std - sigma) < 0.15, f"sample std {std:.4f} should be ~{sigma} (configured sigma)"


# =======================================================================
# H_2 item 2: near/far power ordering still holds with shadowing on
# =======================================================================

def test_near_far_ordering_deterministic_no_shadowing():
    p_near = rx_power_dbm(20.0, 5.0, 5.18e9, n=3.0, shadow_db=0.0)
    p_far = rx_power_dbm(20.0, 50.0, 5.18e9, n=3.0, shadow_db=0.0)
    assert p_near > p_far, f"near ({p_near:.2f} dBm) should exceed far ({p_far:.2f} dBm) with no shadowing"


def test_near_far_ordering_holds_on_average_with_shadowing():
    # A single shadow draw can flip near/far (that's the whole point of
    # shadowing), but averaged over enough independent trials the
    # zero-mean shadow term washes out and the deterministic path-loss
    # gap (huge here: 5m vs 50m) must dominate.
    random.seed(2)
    sigma = 8.0
    trials = 3000
    near_sum = 0.0
    far_sum = 0.0
    for _ in range(trials):
        near_sum += rx_power_dbm(20.0, 5.0, 5.18e9, n=3.0, shadow_db=sample_shadow_db(sigma))
        far_sum += rx_power_dbm(20.0, 50.0, 5.18e9, n=3.0, shadow_db=sample_shadow_db(sigma))
    avg_near = near_sum / trials
    avg_far = far_sum / trials
    gap = avg_near - avg_far
    assert gap > 15.0, (
        f"avg near ({avg_near:.2f} dBm) should still clearly exceed avg far "
        f"({avg_far:.2f} dBm) once shadowing averages out - gap was only {gap:.2f} dB"
    )


def test_shadow_db_cache_is_stable_per_link():
    env = simpy.Environment()
    ch = make_channel(env, shadowing_sigma_db=6.0)
    rx_pos = (10.0, 0.0)
    v1 = ch.shadow_db("TX1", rx_pos)
    v2 = ch.shadow_db("TX1", rx_pos)
    v3 = ch.shadow_db("TX1", rx_pos)
    assert v1 == v2 == v3, "repeated shadow_db() calls for the same (tx_id, rx_pos) must return the same cached value"


def test_shadow_db_disabled_never_touches_cache():
    env = simpy.Environment()
    ch = make_channel(env, shadowing_sigma_db=0.0)
    v = ch.shadow_db("TX1", (10.0, 0.0))
    assert v == 0.0
    assert len(ch.shadow_cache) == 0, "sigma<=0 must not write to the cache (regression check for the sigma=0 fast path)"


# =======================================================================
# H_2 item 3: capture-effect threshold behavior
# =======================================================================
# "Capture effect": a receiver can still decode the stronger of two
# simultaneous transmissions, rather than any temporal overlap being an
# automatic failure (the OLD naive collision-counting model this project
# replaced in Step 3/4). These tests exercise Channel.sinr_db() directly
# to confirm that behavior, and that it degrades/improves in the right
# direction and crosses realistic MCS thresholds where physics says it
# should.

def _make_active_tx(tx_id, tx_pos, rx_pos, tx_start, t_end, tech="WiFi",
                     tx_power_dbm=20.0, f_hz=5.18e9, pl_exp=3.0,
                     bandwidth_mhz=20.0, noise_figure_db=7.0):
    return ActiveTx(
        tx_id=tx_id, tx_pos=tx_pos, rx_pos=rx_pos, tx_start=tx_start,
        tx_power_dbm=tx_power_dbm, f_hz=f_hz, pl_exp=pl_exp, t_end=t_end,
        tech=tech, bandwidth_mhz=bandwidth_mhz, noise_figure_db=noise_figure_db,
    )


def test_sinr_matches_hand_computed_value_no_interference():
    env = simpy.Environment()
    ch = make_channel(env)
    target = _make_active_tx("AP", (0.0, 0.0), (10.0, 0.0), tx_start=0, t_end=1000)
    ch.register_tx(target)

    sinr = ch.sinr_db(target)

    expected_signal_dbm = rx_power_dbm(20.0, 10.0, 5.18e9, n=3.0)
    expected_noise_dbm = thermal_noise_dbm(20.0, 7.0)
    expected_sinr = expected_signal_dbm - expected_noise_dbm  # no interferer -> pure SNR
    assert abs(sinr - expected_sinr) < 1e-6, f"sinr={sinr} expected={expected_sinr}"
    ch.unregister_tx(target, success=True)


def test_sinr_degrades_as_interferer_moves_closer_to_target_rx():
    env = simpy.Environment()
    ch = make_channel(env)
    target = _make_active_tx("AP", (0.0, 0.0), (10.0, 0.0), tx_start=0, t_end=1000)
    ch.register_tx(target)

    sinrs = []
    for interferer_x in (200.0, 100.0, 50.0, 20.0, 12.0):
        interferer = _make_active_tx("GNB", (interferer_x, 0.0), (999.0, 999.0),
                                      tx_start=0, t_end=1000, tech="NRU")
        ch.register_tx(interferer)
        sinrs.append(ch.sinr_db(target))
        ch.unregister_tx(interferer, success=True)

    for i in range(1, len(sinrs)):
        assert sinrs[i] < sinrs[i - 1], (
            f"SINR should strictly decrease as the interferer gets closer to the "
            f"target's receiver: {sinrs}"
        )


def test_capture_effect_near_signal_survives_far_interferer():
    # Near AP (5m from its STA) transmits at the same time as a distant
    # gNB (200m from that STA). Old naive model: 2 simultaneous
    # transmitters = automatic collision/failure for both. New SINR
    # model: the near AP should comfortably "capture" the channel -
    # its SINR should clear even the strictest WiFi MCS7 threshold
    # (25 dB, see Times.WIFI_MCS_SINR_THRESHOLDS_DB).
    env = simpy.Environment()
    ch = make_channel(env)
    sta_pos = (0.0, 0.0)
    near_ap = _make_active_tx("AP", (5.0, 0.0), sta_pos, tx_start=0, t_end=1000)
    far_gnb = _make_active_tx("GNB", (205.0, 0.0), (999.0, 999.0), tx_start=0, t_end=1000, tech="NRU")
    ch.register_tx(near_ap)
    ch.register_tx(far_gnb)

    sinr = ch.sinr_db(near_ap)
    strictest_wifi_threshold = max(WIFI_MCS_SINR_THRESHOLDS_DB.values())
    assert sinr >= strictest_wifi_threshold, (
        f"near AP's SINR ({sinr:.2f} dB) should clear even the strictest WiFi "
        f"MCS threshold ({strictest_wifi_threshold} dB) despite a simultaneous "
        f"far interferer - this is the capture effect the SINR model exists for"
    )


def test_capture_effect_fails_when_interferer_is_close_instead():
    # Mirror of the above: same STA, but now the INTERFERER is close and
    # the desired AP is far - the STA should NOT be able to decode the
    # far AP even against the most lenient WiFi MCS0 threshold (5 dB).
    env = simpy.Environment()
    ch = make_channel(env)
    sta_pos = (0.0, 0.0)
    far_ap = _make_active_tx("AP", (205.0, 0.0), sta_pos, tx_start=0, t_end=1000)
    near_gnb = _make_active_tx("GNB", (5.0, 0.0), (999.0, 999.0), tx_start=0, t_end=1000, tech="NRU")
    ch.register_tx(far_ap)
    ch.register_tx(near_gnb)

    sinr = ch.sinr_db(far_ap)
    most_lenient_wifi_threshold = min(WIFI_MCS_SINR_THRESHOLDS_DB.values())
    assert sinr < most_lenient_wifi_threshold, (
        f"far AP's SINR ({sinr:.2f} dB) should fail even the most lenient WiFi "
        f"MCS threshold ({most_lenient_wifi_threshold} dB) with a close interferer"
    )


def test_spectral_separation_removes_interference_from_capture_decision():
    # Same close-interferer geometry as the failing case above, but put
    # the interferer on a totally separate frequency (Step 5.E). The far
    # AP's SINR should jump back up to the pure-SNR (no-interference)
    # value, since a non-overlapping-channel interferer must not count.
    env = simpy.Environment()
    ch = make_channel(env)
    sta_pos = (0.0, 0.0)
    far_ap = _make_active_tx("AP", (205.0, 0.0), sta_pos, tx_start=0, t_end=1000, f_hz=5.18e9)
    near_gnb_far_freq = _make_active_tx("GNB", (5.0, 0.0), (999.0, 999.0), tx_start=0, t_end=1000,
                                         tech="NRU", f_hz=5.90e9)
    ch.register_tx(far_ap)
    ch.register_tx(near_gnb_far_freq)

    sinr_separated = ch.sinr_db(far_ap)

    expected_signal_dbm = rx_power_dbm(20.0, 205.0, 5.18e9, n=3.0)
    expected_noise_dbm = thermal_noise_dbm(20.0, 7.0)
    expected_sinr_no_interference = expected_signal_dbm - expected_noise_dbm

    assert abs(sinr_separated - expected_sinr_no_interference) < 1e-6, (
        f"a non-overlapping-channel interferer must contribute exactly zero "
        f"interference: sinr={sinr_separated:.4f} expected={expected_sinr_no_interference:.4f}"
    )


# =======================================================================
# H_2 item 4: SINR->MCS table boundaries
# =======================================================================

def _assert_table_exact_and_clamped(table, label):
    for mcs, expected_thr in table.items():
        got = mcs_sinr_threshold_db(table, mcs)
        assert got == expected_thr, f"{label} mcs={mcs}: got {got}, expected exact {expected_thr}"

    lo_idx = min(table.keys())
    hi_idx = max(table.keys())
    assert mcs_sinr_threshold_db(table, lo_idx - 1) == table[lo_idx], (
        f"{label}: below-range mcs should clamp to the lowest table entry"
    )
    assert mcs_sinr_threshold_db(table, lo_idx - 100) == table[lo_idx], (
        f"{label}: far below-range mcs should still clamp to the lowest table entry"
    )
    assert mcs_sinr_threshold_db(table, hi_idx + 1) == table[hi_idx], (
        f"{label}: above-range mcs should clamp to the highest table entry"
    )
    assert mcs_sinr_threshold_db(table, hi_idx + 100) == table[hi_idx], (
        f"{label}: far above-range mcs should still clamp to the highest table entry"
    )
    # thresholds should be monotonically non-decreasing with mcs index -
    # higher-rate MCS must never require a *lower* SINR than a lower one.
    ordered = [table[k] for k in sorted(table.keys())]
    for i in range(1, len(ordered)):
        assert ordered[i] >= ordered[i - 1], f"{label}: threshold table is not monotonically non-decreasing: {ordered}"


def test_wifi_mcs_table_boundaries():
    _assert_table_exact_and_clamped(WIFI_MCS_SINR_THRESHOLDS_DB, "WIFI_MCS_SINR_THRESHOLDS_DB")


def test_nru_mcs_table_boundaries():
    _assert_table_exact_and_clamped(NRU_MCS_SINR_THRESHOLDS_DB, "NRU_MCS_SINR_THRESHOLDS_DB")


def test_mcs_threshold_empty_table_raises():
    try:
        mcs_sinr_threshold_db({}, 3)
        assert False, "an empty table should raise ValueError, not silently return something"
    except ValueError:
        pass


# =======================================================================
# Bonus regression coverage: pure functions added in 5.C/5.E/5.F/5.G that
# were verified ad-hoc during development but never got a permanent test
# =======================================================================

def test_thermal_noise_formula_exact():
    n = thermal_noise_dbm(20.0, 7.0)
    expected = -174.0 + 10.0 * math.log10(20.0e6) + 7.0
    assert abs(n - expected) < 1e-9, f"n={n} expected={expected}"

    # doubling bandwidth should raise the noise floor by exactly 10*log10(2)
    n2 = thermal_noise_dbm(40.0, 7.0)
    assert abs((n2 - n) - 10.0 * math.log10(2.0)) < 1e-9

    # +8 dB noise figure should raise the noise floor by exactly 8 dB
    n3 = thermal_noise_dbm(20.0, 15.0)
    assert abs((n3 - n) - 8.0) < 1e-9


def test_spectral_overlap_fraction_edge_cases():
    f0 = 5.18e9
    assert spectral_overlap_fraction(f0, 20.0, f0, 20.0) == 1.0, "identical co-channel must be full overlap"
    assert spectral_overlap_fraction(f0, 20.0, f0 + 20e6, 20.0) == 0.0, "touching band edges must be zero overlap"
    half = spectral_overlap_fraction(f0, 20.0, f0 + 10e6, 20.0)
    assert abs(half - 0.5) < 1e-9, f"10 MHz offset with 20 MHz bandwidths should be exactly half overlap, got {half}"
    assert spectral_overlap_fraction(f0, 20.0, 5.90e9, 20.0) == 0.0, "far-apart bands must be zero overlap"
    assert spectral_overlap_fraction(f0, 0.0, f0, 20.0) == 0.0, "zero own-bandwidth must be treated as zero overlap"


def test_unii_band_lookup_edges():
    # Every boundary verified ad-hoc during Step 5.F, now permanent.
    assert get_unii_band(5.15e9)[0] == "U-NII-1"
    assert get_unii_band(5.2499e9)[0] == "U-NII-1"
    assert get_unii_band(5.25e9)[0] == "U-NII-2A"
    assert get_unii_band(5.34999e9)[0] == "U-NII-2A"
    assert get_unii_band(5.35e9) is None, "5.35-5.47 GHz is a real gap, not covered by any U-NII band"
    assert get_unii_band(5.469e9) is None
    assert get_unii_band(5.47e9)[0] == "U-NII-2C"
    assert get_unii_band(5.7249e9)[0] == "U-NII-2C"
    assert get_unii_band(5.725e9)[0] == "U-NII-3"
    assert get_unii_band(5.8499e9)[0] == "U-NII-3"
    assert get_unii_band(5.85e9)[0] == "U-NII-4"
    assert get_unii_band(5.8949e9)[0] == "U-NII-4"
    assert get_unii_band(5.895e9) is None, "5.895 GHz and above is outside every modeled band"
    assert get_unii_band(5.9e9) is None, "the far-frequency value used in Step 5.E/5.E.1 tests must be unmodeled"

    # Every band's cap must come from UNII_BANDS itself (no drift between
    # the table and get_unii_band's traversal logic).
    for name, lo, hi, max_eirp, _citation in UNII_BANDS:
        mid = (lo + hi) / 2.0
        found = get_unii_band(mid)
        assert found is not None and found[0] == name and found[1] == max_eirp


def test_waypoint_mobility_interpolation_and_rollover():
    random.seed(42)
    env = simpy.Environment()
    mob = WaypointMobility(env, area_w=100.0, area_h=100.0, speed_mps=2.0, pause_s=1.0, start_pos=(0.0, 0.0))
    target1 = mob._target
    travel_us = dist((0.0, 0.0), target1) / 2.0 * 1e6

    env._now = travel_us / 2.0
    halfway = mob.pos_now()
    expected_halfway = (target1[0] / 2.0, target1[1] / 2.0)
    assert abs(halfway[0] - expected_halfway[0]) < 1e-6
    assert abs(halfway[1] - expected_halfway[1]) < 1e-6

    env._now = travel_us + 500_000.0
    during_pause = mob.pos_now()
    assert abs(during_pause[0] - target1[0]) < 1e-6
    assert abs(during_pause[1] - target1[1]) < 1e-6

    env._now = travel_us + 1_000_000.0 + 5_000_000.0
    after_rollover = mob.pos_now()
    new_target = mob._target
    assert new_target != target1, "should have picked a new random waypoint after the pause elapsed"
    travelled = dist(target1, after_rollover)
    assert abs(travelled - 10.0) < 1e-6, f"5s @ 2 m/s into the new leg should be exactly 10.0m, got {travelled}"


def test_waypoint_mobility_static_when_speed_zero_never_touched():
    # Defensive: simulation.py never constructs a WaypointMobility at all
    # when speed<=0 (checked before construction), but confirm the class
    # itself degrades sanely if it ever were constructed with speed=0.
    env = simpy.Environment()
    mob = WaypointMobility(env, area_w=100.0, area_h=100.0, speed_mps=0.0, pause_s=0.0, start_pos=(5.0, 5.0))
    p = mob.pos_now()
    assert isinstance(p, tuple) and len(p) == 2, "pos_now() must still return a valid (x, y) tuple, not crash"


# =======================================================================
# Runner (no pytest dependency required)
# =======================================================================

def _all_test_functions():
    g = globals()
    return [g[name] for name in sorted(g) if name.startswith("test_") and callable(g[name])]


if __name__ == "__main__":
    tests = _all_test_functions()
    passed = 0
    failed = []
    for fn in tests:
        try:
            fn()
            passed += 1
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed.append(fn.__name__)
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:
            failed.append(fn.__name__)
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")

    print()
    print(f"{passed}/{len(tests)} passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
        sys.exit(0)

# Rashed-Step 5.H-02-06-2026-end
