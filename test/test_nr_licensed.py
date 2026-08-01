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
