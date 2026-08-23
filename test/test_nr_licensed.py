# Rashed-Step 6.B-07-31-2026-start
"""
Regression tests for the licensed 5G NR module (nr/nr.py, nr/ue.py),
added in Step 6.B. Same style/runner as test/test_phy_unit.py (Step
5.H) - assert-based, no pytest dependency required.

Runnable two ways:
  - Directly:  python test/test_nr_licensed.py
  - Via pytest, if installed: pytest test/test_nr_licensed.py

Covers:
  1. Numerology -> slot duration (3GPP formula: 1ms / 2^mu)
  2. Resource-block count matches the real 3GPP TS 38.101-1 table for
     common bandwidth/SCS combinations, and the formula-based fallback
     is sane for values not in the table
  3. select_mcs_for_sinr() link-adaptation boundaries
  4. Round-robin RB allocation: splits evenly, rotates the remainder
  5. Proportional-fair RB allocation: whole slot to the single best-
     priority UE; over repeated slots with equal channel quality, PF
     converges to giving everyone a turn (its whole point)
"""

import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import simpy

from nr.nr import (
    NUMEROLOGY_SCS_KHZ,
    slot_duration_us,
    resource_block_count,
    select_mcs_for_sinr,
    NR_MCS_TABLE,
    Config_NRL,
    GnbLicensedNR,
)
from nr.ue import NrUeLicensed
from channel.channel import Channel


def make_channel(env):
    return Channel(
        tx_queue=simpy.PriorityResource(env, capacity=1),
        tx_lock=simpy.Resource(env, capacity=1),
        n_of_stations=0,
        n_of_gNB=0,
        backoffs={},
        airtime_data={},
        airtime_control={},
        airtime_data_NR={},
        airtime_control_NR={},
    )


# =======================================================================
# 1. Numerology -> slot duration
# =======================================================================

def test_slot_duration_matches_3gpp_formula():
    # 3GPP TS 38.211: slot duration = 1 ms / 2^mu
    assert slot_duration_us(0) == 1000.0
    assert slot_duration_us(1) == 500.0
    assert slot_duration_us(2) == 250.0
    assert slot_duration_us(3) == 125.0


def test_numerology_scs_table_values():
    assert NUMEROLOGY_SCS_KHZ[0] == 15
    assert NUMEROLOGY_SCS_KHZ[1] == 30
    assert NUMEROLOGY_SCS_KHZ[2] == 60


# =======================================================================
# 2. Resource-block count
# =======================================================================

def test_resource_block_count_matches_3gpp_table():
    # Spot-check a handful of real 3GPP TS 38.101-1 Table 5.3.2-1 values.
    assert resource_block_count(100, 30) == 273
    assert resource_block_count(20, 15) == 106
    assert resource_block_count(50, 30) == 133
    assert resource_block_count(10, 60) == 11


def test_resource_block_count_fallback_is_sane_for_unlisted_bandwidth():
    # 73 MHz @ 30 kHz SCS isn't a real 3GPP bandwidth, but the formula
    # fallback should still return something positive and roughly in
    # between the RB counts for 60 MHz and 80 MHz at the same SCS.
    rb_60 = resource_block_count(60, 30)
    rb_73 = resource_block_count(73, 30)
    rb_80 = resource_block_count(80, 30)
    assert rb_60 < rb_73 < rb_80, f"expected {rb_60} < {rb_73} < {rb_80}"


def test_resource_block_count_never_zero():
    assert resource_block_count(1, 30) >= 1


# =======================================================================
# 3. Link adaptation (select_mcs_for_sinr)
# =======================================================================

def test_select_mcs_picks_highest_qualifying_index():
    # MCS 10 requires 14.0 dB, MCS 11 requires 16.0 dB - 15.0 dB should
    # land exactly on MCS 10, not 11.
    assert select_mcs_for_sinr(15.0) == 10


def test_select_mcs_returns_none_below_lowest_threshold():
    # MCS 0 requires -6.0 dB - anything below that must fail outright.
    assert select_mcs_for_sinr(-10.0) is None


def test_select_mcs_returns_top_index_for_very_high_sinr():
    assert select_mcs_for_sinr(100.0) == max(NR_MCS_TABLE.keys())


def test_select_mcs_boundary_is_inclusive():
    # Exactly at a threshold should qualify for that MCS (>=, not >).
    req_db, _eff = NR_MCS_TABLE[5]
    assert select_mcs_for_sinr(req_db) == 5


# =======================================================================
# 4. Round-robin RB allocation
# =======================================================================

def _make_gnb(env, channel, n_ues=3, scheduler="round_robin", total_rbs_override=None):
    config = Config_NRL(scheduler=scheduler, bandwidth_mhz=20.0, numerology=0)  # 106 RBs @ 15kHz
    ues = [NrUeLicensed(name=f"UE{i}", pos=(10.0 * i, 0.0), gnb_name="G1") for i in range(n_ues)]
    gnb = GnbLicensedNR(env, "G1", channel, (0.0, 0.0), ues, config)
    if total_rbs_override is not None:
        gnb.total_rbs = total_rbs_override
    return gnb, ues


def test_round_robin_splits_evenly_when_divisible():
    env = simpy.Environment()
    channel = make_channel(env)
    gnb, ues = _make_gnb(env, channel, n_ues=3)
    gnb.total_rbs = 30  # divisible by 3 stations -> exactly 10 each, no remainder
    alloc = gnb._round_robin_allocation()
    assert set(alloc.keys()) == {ue.name for ue in ues}
    assert all(v == 10 for v in alloc.values()), f"expected 10 RBs each, got {alloc}"
    assert sum(alloc.values()) == 30


def test_round_robin_rotates_the_remainder_across_slots():
    env = simpy.Environment()
    channel = make_channel(env)
    gnb, ues = _make_gnb(env, channel, n_ues=3)
    gnb.total_rbs = 10  # 3 each + 1 remainder RB, which should rotate who gets it
    winners = []
    for _ in range(3):
        alloc = gnb._round_robin_allocation()
        assert sum(alloc.values()) == 10, "every RB must be allocated somewhere"
        winner = max(alloc, key=alloc.get)
        winners.append(winner)
    # Over 3 rotations of 3 UEs, the +1 "remainder" RB should not land on
    # the exact same UE every single time.
    assert len(set(winners)) > 1, f"remainder RB never rotated: {winners}"


def test_round_robin_empty_ue_list_returns_empty_allocation():
    env = simpy.Environment()
    channel = make_channel(env)
    gnb, _ues = _make_gnb(env, channel, n_ues=0)
    assert gnb._round_robin_allocation() == {}


# =======================================================================
# 5. Proportional-fair RB allocation
# =======================================================================

def test_proportional_fair_gives_whole_slot_to_one_winner():
    env = simpy.Environment()
    channel = make_channel(env)
    gnb, ues = _make_gnb(env, channel, n_ues=3, scheduler="proportional_fair")
    alloc = gnb._proportional_fair_allocation()
    assert len(alloc) == 1, f"PF should pick exactly one winner per slot, got {alloc}"
    winner_rbs = list(alloc.values())[0]
    assert winner_rbs == gnb.total_rbs


def test_proportional_fair_takes_turns_over_time_for_equal_channel_ues():
    # All 3 UEs are placed at the identical position (identical SINR /
    # instantaneous rate every slot), so PF's fairness mechanism (not
    # channel differences) must be what spreads allocation across them.
    env = simpy.Environment()
    channel = make_channel(env)
    config = Config_NRL(scheduler="proportional_fair", bandwidth_mhz=20.0, numerology=0)
    ues = [NrUeLicensed(name=f"UE{i}", pos=(20.0, 0.0), gnb_name="G1") for i in range(3)]
    gnb = GnbLicensedNR(env, "G1", channel, (0.0, 0.0), ues, config)

    winners = []
    for _ in range(9):
        alloc = gnb._proportional_fair_allocation()
        winners.append(next(iter(alloc)))

    # With identical channel quality, PF's R_inst/R_avg metric must
    # rotate the winner - it should not fixate on a single UE forever.
    assert len(set(winners)) == 3, f"expected all 3 UEs to win at least once, got winners={winners}"


# =======================================================================
# 6. Step 13.E.3: Packet/measured_sinr_db wiring + ahead-of-time rate
# adaptation (opt-in via Config_NRL.rate_adapt_enabled) + predictor hook
# =======================================================================
"""
Default (rate_adapt_enabled=False, the pre-13.E.3 behavior) must stay
byte-identical: MCS is chosen AFTER the slot's real SINR is known
(select_mcs_for_sinr(sinr), a "genie-aided"/oracle pick), which can
only fail below MCS0's threshold. rate_adapt_enabled=True switches to
an AHEAD-OF-TIME pick (from a UE's last-measured or model-predicted
SINR, decided BEFORE this slot's real SINR is known) - a genuinely
fallible scheme, unlike the oracle, since a wrong ahead-of-time guess
now causes a real failure (DROPPED) even if a lower MCS would have
worked. See nr/nr.py's Config_NRL.rate_adapt_enabled docstring for the
full design rationale (this was a real design fork found while
building this sub-step).
"""

from common.packet import Packet


class _FakePredictor:
    """Same pattern as test_packet.py's Step 13.D/13.E.1 fake predictor -
    records every call, always returns a fixed prediction."""
    def __init__(self, lag_k=3, fixed_prediction=100.0):
        self.lag_k = lag_k
        self.fixed_prediction = fixed_prediction
        self.calls = []

    def predict_next(self, history, technology_is_wifi=0):
        self.calls.append((list(history), technology_is_wifi))
        return self.fixed_prediction


def _make_rate_adapt_gnb(n_ues=1, rate_adapt_enabled=False, sinr_predictor=None, pos=(0.0, 0.0), ue_pos=(50.0, 0.0)):
    env = simpy.Environment()
    channel = make_channel(env)
    config = Config_NRL(
        scheduler="round_robin", bandwidth_mhz=20.0, numerology=0,
        rate_adapt_enabled=rate_adapt_enabled, sinr_predictor=sinr_predictor,
    )
    ues = [NrUeLicensed(name=f"UE{i}", pos=ue_pos, gnb_name="G1") for i in range(n_ues)]
    gnb = GnbLicensedNR(env, "G1", channel, pos, ues, config)
    return env, gnb, ues


def test_run_one_slot_populates_packet_log_and_measured_sinr_db():
    # NOTE: GnbLicensedNR.__init__ already auto-starts an infinite
    # start()->run_one_slot() loop (env.process(self.start())) - do NOT
    # also manually env.process(gnb.run_one_slot()) here, or two slots'
    # worth of packets get created in the same window. Just advance
    # time far enough for exactly one auto-started slot to complete.
    env, gnb, ues = _make_rate_adapt_gnb(n_ues=2)
    env.run(until=gnb.slot_us + 10)

    assert len(gnb.packet_log) == 2
    for pkt in gnb.packet_log:
        assert isinstance(pkt, Packet)
        assert pkt.measured_sinr_db is not None
        assert pkt.status in ("DELIVERED", "DROPPED")
        assert pkt.source == "G1"
        assert pkt.destination in {ue.name for ue in ues}


def test_run_one_slot_default_oracle_mode_matches_select_mcs_for_sinr():
    # Regression guard: rate_adapt_enabled=False (default) must produce
    # EXACTLY the pre-13.E.3 oracle outcome - status/bits driven by
    # select_mcs_for_sinr(measured_sinr_db) directly, nothing ahead-of-
    # time involved.
    env, gnb, ues = _make_rate_adapt_gnb(n_ues=1, rate_adapt_enabled=False)
    env.run(until=gnb.slot_us + 10)

    pkt = gnb.packet_log[0]
    expected_mcs = select_mcs_for_sinr(pkt.measured_sinr_db)
    if expected_mcs is not None:
        assert pkt.status == "DELIVERED"
        assert gnb.succeeded_transmissions == 1
    else:
        assert pkt.status == "DROPPED"
        assert gnb.failed_transmissions == 1
    assert gnb.link_state == {}, "rate_adapt_enabled=False must never populate link_state"


def test_current_mcs_for_ue_returns_none_when_disabled():
    _env, gnb, _ues = _make_rate_adapt_gnb(rate_adapt_enabled=False)
    gnb.record_link_result("UE0", 20.0)  # no-op when disabled
    assert gnb.current_mcs_for_ue("UE0") is None
    assert gnb.link_state == {}


def test_current_mcs_for_ue_returns_none_before_first_measurement():
    # Bootstrap: rate_adapt_enabled=True but no prior measurement yet
    # for this UE - must signal "use oracle" (None), not crash.
    _env, gnb, _ues = _make_rate_adapt_gnb(rate_adapt_enabled=True)
    assert gnb.current_mcs_for_ue("UE0") is None


def test_current_mcs_for_ue_uses_last_measured_sinr():
    _env, gnb, _ues = _make_rate_adapt_gnb(rate_adapt_enabled=True)
    gnb.record_link_result("UE0", 15.0)
    assert gnb.current_mcs_for_ue("UE0") == select_mcs_for_sinr(15.0)


def test_ahead_of_time_wrong_guess_causes_failure_even_though_lower_mcs_would_work():
    # Seed a stale, over-optimistic last-measured SINR for this UE, then
    # place the UE far enough that the REAL slot SINR is much lower -
    # the ahead-of-time pick (from the stale high SINR) should FAIL
    # even though a lower MCS (or even MCS0) would have succeeded at
    # the real, lower SINR - proves this is genuinely fallible, unlike
    # the oracle default.
    env, gnb, ues = _make_rate_adapt_gnb(n_ues=1, rate_adapt_enabled=True, pos=(0.0, 0.0), ue_pos=(2000.0, 0.0))
    gnb.record_link_result(ues[0].name, 100.0)  # wildly optimistic stale reading -> picks a high mcs
    chosen = gnb.current_mcs_for_ue(ues[0].name)
    assert chosen == max(NR_MCS_TABLE.keys()), "sanity: the stale 100.0 dB reading must pick the top MCS"

    env.run(until=gnb.slot_us + 10)

    pkt = gnb.packet_log[0]
    # At 2000m the real SINR must be far below the top MCS's threshold.
    assert pkt.measured_sinr_db < NR_MCS_TABLE[chosen][0]
    assert pkt.status == "DROPPED", "a wrong ahead-of-time guess must fail even if a lower mcs would have worked"
    assert gnb.failed_transmissions == 1


def test_predictor_unset_falls_back_to_last_measured():
    _env, gnb, _ues = _make_rate_adapt_gnb(rate_adapt_enabled=True, sinr_predictor=None)
    gnb.record_link_result("UE0", 15.0)
    assert gnb.current_mcs_for_ue("UE0") == select_mcs_for_sinr(15.0)


def test_predictor_not_enough_history_falls_back_to_last_measured():
    fake = _FakePredictor(lag_k=3, fixed_prediction=100.0)  # would pick top mcs if used
    _env, gnb, _ues = _make_rate_adapt_gnb(rate_adapt_enabled=True, sinr_predictor=fake)
    gnb.record_link_result("UE0", 15.0)  # only 1 measurement, lag_k=3
    assert gnb.current_mcs_for_ue("UE0") == select_mcs_for_sinr(15.0)
    assert fake.calls == []


def test_predictor_used_once_enough_history():
    fake = _FakePredictor(lag_k=3, fixed_prediction=100.0)  # -> top mcs
    _env, gnb, _ues = _make_rate_adapt_gnb(rate_adapt_enabled=True, sinr_predictor=fake)
    for sinr in (5.0, 6.0, 7.0):  # NOT constant - see the guard test below
        gnb.record_link_result("UE0", sinr)
    assert gnb.current_mcs_for_ue("UE0") == max(NR_MCS_TABLE.keys())
    assert len(fake.calls) == 1
    history_passed, technology_is_wifi = fake.calls[0]
    assert history_passed == [5.0, 6.0, 7.0]
    assert technology_is_wifi == 0, "licensed NR's own use site must always pass technology_is_wifi=0"


def test_predictor_skipped_when_history_is_exactly_constant():
    # Same constant-link safety guard as Config_NR.sinr_predictor
    # (Step 13.D-fix) / wifi.Config.sinr_predictor (Step 13.E.1-fix) -
    # built in from the start here rather than as a follow-up fix.
    fake = _FakePredictor(lag_k=3, fixed_prediction=100.0)
    _env, gnb, _ues = _make_rate_adapt_gnb(rate_adapt_enabled=True, sinr_predictor=fake)
    for _ in range(3):
        gnb.record_link_result("UE0", 15.0)  # exactly constant
    assert gnb.current_mcs_for_ue("UE0") == select_mcs_for_sinr(15.0), "must fall back to last-measured, predictor skipped"
    assert fake.calls == []


def test_record_link_result_history_capped_at_8():
    _env, gnb, _ues = _make_rate_adapt_gnb(rate_adapt_enabled=True)
    for i in range(10):
        gnb.record_link_result("UE0", float(i))
    assert gnb.link_state["UE0"]["sinr_history"] == [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]


if __name__ == "__main__":
    def _all_test_functions():
        g = globals()
        return [g[name] for name in sorted(g) if name.startswith("test_") and callable(g[name])]

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
# Rashed-Step 6.B-07-31-2026-end
