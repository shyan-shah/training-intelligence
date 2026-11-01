"""Load engine tests, including the hand calculation the acceptance checks ask
for: 'CTL, ATL and TSB match a hand calculation on 3 sample days'.
"""
from datetime import date, timedelta
from fractions import Fraction

import pytest

from ti.load import (
    CTL_TAU, ATL_TAU, STRENGTH_TSS, IF_CAP,
    Session, Settings, session_tss, daily_tss, load_series,
)

CFG = Settings(ftp_w=213, threshold_pace=240.0, css_swim=120.0, lthr=170)
D = date(2026, 11, 1)


# ---------------------------------------------------------------------------
# Hand calculation. Acceptance check: "CTL, ATL and TSB match a hand
# calculation on 3 sample days."
#
# Rather than paste float literals, the expected values are re-derived here in
# exact rational arithmetic straight from the recurrences in the brief:
#
#   CTL_t = CTL_{t-1} + (TSS_t - CTL_{t-1}) / 42
#   ATL_t = ATL_{t-1} + (TSS_t - ATL_{t-1}) / 7
#   TSB_t = CTL_{t-1} - ATL_{t-1}
#
# That makes this an independent check of the engine's float path rather than a
# copy of its output. From zero seeds with TSS 100, 0, 50 the exact values are:
#
#   Day 1:  CTL = 50/21     ATL = 100/7     TSB = 0
#   Day 2:  CTL = 1025/441  ATL = 600/49    TSB = -250/21
#   Day 3:  CTL = 64075/18522  ATL = 6050/343  TSB = -625/63
# ---------------------------------------------------------------------------
SAMPLE_TSS = [100.0, 0.0, 50.0]

# The exact rationals above, as a regression guard on the derivation itself.
EXPECTED_EXACT = [
    (Fraction(50, 21), Fraction(100, 7), Fraction(0)),
    (Fraction(1025, 441), Fraction(600, 49), Fraction(-250, 21)),
    (Fraction(64075, 18522), Fraction(6050, 343), Fraction(-625, 63)),
]


def _derive_by_hand(tss_values):
    """Walk the recurrences in exact arithmetic. No engine code involved."""
    ctl = atl = Fraction(0)
    out = []
    for t in (Fraction(v).limit_denominator() for v in tss_values):
        tsb = ctl - atl                      # previous day's values, per the brief
        ctl = ctl + (t - ctl) / 42
        atl = atl + (t - atl) / 7
        out.append((ctl, atl, tsb))
    return out


def test_hand_derivation_matches_the_stated_rationals():
    """Guard the guard: the by-hand walk must reproduce the exact fractions
    written in the comment above."""
    assert _derive_by_hand(SAMPLE_TSS) == EXPECTED_EXACT


def test_ctl_atl_tsb_match_hand_calculation():
    tss_by_day = {D + timedelta(days=i): v for i, v in enumerate(SAMPLE_TSS)}
    series = load_series(tss_by_day, D, D + timedelta(days=2))
    expected = _derive_by_hand(SAMPLE_TSS)

    assert len(series) == 3
    for i, (point, (ctl, atl, tsb)) in enumerate(zip(series, expected), start=1):
        assert point.day == D + timedelta(days=i - 1)
        assert point.tss == pytest.approx(SAMPLE_TSS[i - 1])
        assert point.ctl == pytest.approx(float(ctl), abs=1e-12), f"CTL day {i}"
        assert point.atl == pytest.approx(float(atl), abs=1e-12), f"ATL day {i}"
        assert point.tsb == pytest.approx(float(tsb), abs=1e-12), f"TSB day {i}"


def test_time_constants_are_42_and_7():
    assert (CTL_TAU, ATL_TAU) == (42, 7)


def test_rest_days_decay_fitness():
    """A gap in the activity feed must still decay CTL and ATL. If rest days
    were skipped rather than zero-filled, fitness would never come down."""
    tss_by_day = {D: 100.0}
    series = load_series(tss_by_day, D, D + timedelta(days=10))
    assert len(series) == 11
    ctls = [p.ctl for p in series]
    assert ctls[0] > ctls[-1]
    assert all(b <= a for a, b in zip(ctls, ctls[1:]))
    assert series[-1].atl < series[0].atl


def test_tsb_uses_previous_day_values():
    """TSB on a hard day must not already reflect that day's session."""
    series = load_series({D: 200.0}, D, D)
    assert series[0].tsb == 0.0
    assert series[0].atl > 0


# ---------------------------------------------------------------------------
# Session TSS
# ---------------------------------------------------------------------------
def test_power_tss_matches_the_briefs_closed_form():
    """TSS = (t_s * NP * IF) / (FTP * 3600) * 100 is the same as
    hours * IF**2 * 100. Both forms must agree."""
    t_s, np_w = 3600, 213          # exactly one hour at FTP
    s = Session(D, "bike", duration_s=t_s, np=np_w)
    got = session_tss(s, CFG)

    if_val = np_w / CFG.ftp_w
    brief_form = (t_s * np_w * if_val) / (CFG.ftp_w * 3600) * 100

    assert got.method == "power"
    assert got.tss == pytest.approx(brief_form)
    assert got.tss == pytest.approx(100.0)       # one hour at FTP is 100 TSS


def test_run_tss_if_is_above_one_when_faster_than_threshold():
    """Pace is in seconds per km, so faster means a smaller number. IF must
    still come out above 1."""
    s = Session(D, "run", duration_s=3600, avg_pace=220.0)
    got = session_tss(s, CFG)
    assert got.method == "pace"
    assert got.intensity_factor == pytest.approx(240.0 / 220.0)
    assert got.intensity_factor > 1.0
    assert got.tss == pytest.approx(3600 / 3600 * (240 / 220) ** 2 * 100)


def test_run_tss_derives_pace_from_distance_when_absent():
    s = Session(D, "run", duration_s=1800, distance_m=7500)   # 240 s/km exactly
    got = session_tss(s, CFG)
    assert got.method == "pace"
    assert got.intensity_factor == pytest.approx(1.0)
    assert got.tss == pytest.approx(50.0)


def test_swim_tss_is_cubed():
    s = Session(D, "swim", duration_s=3600, distance_m=3000)   # 120 s/100m = CSS
    got = session_tss(s, CFG)
    assert got.method == "swim_css"
    assert got.intensity_factor == pytest.approx(1.0)
    assert got.tss == pytest.approx(100.0)

    faster = Session(D, "swim", duration_s=3600, distance_m=3300)
    g2 = session_tss(faster, CFG)
    expected_if = 120.0 / (3600 / 33.0)
    assert g2.tss == pytest.approx(1.0 * expected_if**3 * 100)


def test_hr_fallback_used_only_when_primary_method_unavailable():
    no_power = Settings(lthr=170)
    s = Session(D, "bike", duration_s=3600, avg_hr=170, np=200)
    got = session_tss(s, no_power)
    assert got.method == "hr"
    assert got.tss == pytest.approx(100.0)


def test_hr_fallback_disabled_without_lthr():
    """LTHR has no source in the audited data, so HR TSS must return nothing
    rather than invent a denominator."""
    no_lthr = Settings(ftp_w=None, lthr=None)
    s = Session(D, "run", duration_s=3600, avg_hr=160)
    got = session_tss(s, no_lthr)
    assert got.method == "none"
    assert got.tss == 0.0


def test_strength_gets_a_fixed_estimate_by_label():
    assert session_tss(Session(D, "strength", 3600, label="legs"), CFG).tss == STRENGTH_TSS["legs"]
    assert session_tss(Session(D, "strength", 3600, label=None), CFG).tss == STRENGTH_TSS["DEFAULT"]
    assert session_tss(Session(D, "strength", 3600), CFG).method == "fixed"


def test_intensity_factor_is_capped():
    """A GPS spike or bad FTP must not dominate CTL for six weeks."""
    s = Session(D, "bike", duration_s=3600, np=1000)    # IF would be 4.7
    got = session_tss(s, CFG)
    assert got.capped is True
    assert got.intensity_factor == IF_CAP
    assert got.tss == pytest.approx(IF_CAP**2 * 100)


def test_moving_time_drives_tss_not_elapsed():
    """The audited 2026-09-22 session had 175,726s elapsed against 4,678s
    moving. TSS must be built on the 4,678."""
    s = Session(D, "run", duration_s=4678, avg_pace=240.0)
    got = session_tss(s, CFG)
    assert got.tss == pytest.approx(4678 / 3600 * 100)
    assert got.tss < 140


def test_zero_duration_scores_nothing():
    assert session_tss(Session(D, "run", duration_s=0, avg_pace=240.0), CFG).tss == 0.0


def test_daily_tss_sums_multiple_sessions():
    sessions = [
        Session(D, "bike", 3600, np=213),
        Session(D, "strength", 2400, label="push"),
    ]
    assert daily_tss(sessions, CFG)[D] == pytest.approx(100.0 + STRENGTH_TSS["push"])


# ---------------------------------------------------------------------------
# ACWR
# ---------------------------------------------------------------------------
def test_acwr_is_none_until_28_days_of_history():
    """Before a full chronic window the ratio would read high off a partial
    denominator and fire a spurious back-off."""
    tss = {D + timedelta(days=i): 50.0 for i in range(10)}
    series = load_series(tss, D, D + timedelta(days=9))
    assert all(p.acwr is None for p in series)


def test_acwr_is_one_for_steady_load():
    tss = {D + timedelta(days=i): 50.0 for i in range(40)}
    series = load_series(tss, D, D + timedelta(days=39))
    assert series[-1].acwr == pytest.approx(1.0, abs=0.01)


def test_acwr_rises_on_a_spike():
    tss = {D + timedelta(days=i): 50.0 for i in range(40)}
    for i in range(33, 40):
        tss[D + timedelta(days=i)] = 150.0
    series = load_series(tss, D, D + timedelta(days=39))
    assert series[-1].acwr > 1.5


def test_both_acwr_definitions_are_reported():
    """The brief defined ACWR as ATL/CTL, which is a 7:42 exponential ratio and
    not calibrated to the 0.8-1.3 band. Both are kept so the difference stays
    visible."""
    tss = {D + timedelta(days=i): 50.0 for i in range(40)}
    last = load_series(tss, D, D + timedelta(days=39))[-1]
    assert last.acwr is not None and last.acwr_ewma is not None


def test_ctl_ramp_is_the_seven_day_change():
    tss = {D + timedelta(days=i): 80.0 for i in range(20)}
    series = load_series(tss, D, D + timedelta(days=19))
    by_day = {p.day: p for p in series}
    p = series[-1]
    # ctl_ramp_7d is rounded to 2dp on the way to storage.
    assert p.ctl_ramp_7d == pytest.approx(p.ctl - by_day[p.day - timedelta(days=7)].ctl, abs=0.005)
    assert series[0].ctl_ramp_7d is None
