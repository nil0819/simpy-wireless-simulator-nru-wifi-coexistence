# Rashed-Step pre_11.C-08-13-2026-start
"""
Unit tests for model/dtmc.py - pure math, no simulator invocation (fast).

Reference values below are this implementation's own converged output,
cross-checked during this module's development (Project details/Step
pre_11.txt) against: (a) an independent from-scratch reconstruction of
the same equations from the paper's PDF, and (b) real singleRun.py runs
(see test_model_compare.py for the simulator-comparison tests) - not
copied from the paper itself (which doesn't publish per-scenario tau/Cn
numbers at this level of precision).
"""
import pytest

from model.dtmc import channel_occupancy, nru_tau, predict, solve_fixed_point, wifi_tau


def test_wifi_tau_zero_busy_probability():
    # pb=0 -> tau_w = 2*1 / [2*1 + 0 + 1+Wo-0] = 2/(Wo+3)
    assert wifi_tau(0.0, Wo=32) == pytest.approx(2.0 / 35.0, rel=1e-9)


def test_nru_tau_decreases_as_busy_probability_rises():
    # More contention (higher pb/pg) should suppress NR-U's own steady-
    # state transmission probability tau_n=bo.
    low = nru_tau(pb=0.01, pg=0.01, pa=0.0, ng=55, Wo=32)
    high = nru_tau(pb=0.3, pg=0.3, pa=0.0, ng=55, Wo=32)
    assert 0.0 < high < low < 1.0


def test_solve_fixed_point_matches_known_converged_values():
    # w=1, Wo=32, ng=55 - this session's reference scenario (Project
    # details/Step pre_11.txt).
    tau_w, tau_n = solve_fixed_point(w=1, Wo=32, ng=55)
    assert tau_w == pytest.approx(0.055443, abs=1e-5)
    assert tau_n == pytest.approx(0.017280, abs=1e-5)


def test_solve_fixed_point_more_wifi_aps_raises_wifi_tau_lowers_nru_tau():
    # More Wi-Fi APs contending should push tau_n down (NR-U senses a
    # busier channel more often) - a monotonic sanity check, not a
    # precise reference value (Step 6.D covered w=1..4 with default
    # non-fixed CW; this checks the general trend with THIS module's own
    # fixed-Wo assumption instead).
    _, tau_n_w1 = solve_fixed_point(w=1, Wo=32, ng=55)
    _, tau_n_w4 = solve_fixed_point(w=4, Wo=32, ng=55)
    assert tau_n_w4 < tau_n_w1


def test_channel_occupancy_sums_to_total_utilization():
    tau_w, tau_n = solve_fixed_point(w=1, Wo=32, ng=55)
    result = channel_occupancy(
        tau_w, tau_n, w=1, Twp_us=5400.0, Tmcot_us=6000.0, Td_us=34.0,
        sigma_us=9.0, Tsifs_us=16.0, Tack_us=44.0, Tdifs_us=34.0,
    )
    # eq (9)+(11)+(13)+(15)+(17) = 1 by construction (5 mutually exclusive
    # events partition the mean interval).
    total_p = result["Pidle"] + result["Pws"] + result["Pns"] + result["Pwc"] + result["Pnwc"]
    assert total_p == pytest.approx(1.0, abs=1e-9)


def test_channel_occupancy_large_wifi_txop_matches_reference():
    # This session's pre_11.C headline number: Twp=5400us (vs the
    # default 242us) at w=1/Wo=32/ng=55/Tmcot=6ms -> Cn~=0.253 (confirmed
    # against a real singleRun.py run within ~3% - see
    # test_model_compare.py and Project details/Step pre_11.txt).
    result = predict(w=1, Wo=32, ng=55, Twp_us=5400.0, Tmcot_us=6000.0)
    assert result["Cn"] == pytest.approx(0.2530, abs=0.001)
    assert result["Cw"] == pytest.approx(0.7267, abs=0.001)


def test_channel_occupancy_small_wifi_frame_favors_nru():
    # Default 242us Wi-Fi frame vs 6ms NR-U MCOT: NR-U should dominate
    # occupancy (this is the "why is gNB out-occupying my AP" behavior
    # this whole model module exists to explain - see this session's
    # earlier discussion, before Step pre_11 started).
    result = predict(w=1, Wo=32, ng=55, Twp_us=242.0, Tmcot_us=6000.0)
    assert result["Cn"] > result["Cw"]


def test_predict_matches_manual_composition():
    tau_w, tau_n = solve_fixed_point(w=1, Wo=32, ng=55)
    manual = channel_occupancy(tau_w, tau_n, w=1, Twp_us=5400.0, Tmcot_us=6000.0,
                                Td_us=34.0, sigma_us=9.0, Tsifs_us=16.0, Tack_us=44.0,
                                Tdifs_us=34.0)
    convenience = predict(w=1, Wo=32, ng=55, Twp_us=5400.0, Tmcot_us=6000.0)
    assert convenience["Cn"] == pytest.approx(manual["Cn"], rel=1e-12)
    assert convenience["Cw"] == pytest.approx(manual["Cw"], rel=1e-12)
# Rashed-Step pre_11.C-08-13-2026-end
