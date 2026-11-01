"""Body composition tests.

The real baseline scan (13 Sep 2026) is used as a fixture: 66.7kg, 14.1% body
fat, 32.0kg skeletal muscle, 57.3kg lean mass.
"""
from datetime import date, timedelta

import pytest

from ti.body import (
    Scan, Weigh, conditions_mismatch, gain_quality, project_target_date,
    rolling_scan_average, smoothed_weight, validate_scan, weekly_rate,
)

BASELINE = Scan(date(2026, 9, 13), weight_kg=66.7, body_fat_pct=14.1,
                skeletal_muscle_kg=32.0, lean_mass_kg=57.3)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_the_real_baseline_scan_validates():
    ok, reason = validate_scan({"weight_kg": 66.7, "body_fat_pct": 14.1,
                                "skeletal_muscle_kg": 32.0, "lean_mass_kg": 57.3})
    assert ok is True
    assert reason is None


@pytest.mark.parametrize("field,value", [
    ("weight_kg", 45.0), ("weight_kg", 105.0),
    ("body_fat_pct", 2.0), ("body_fat_pct", 45.0),
])
def test_out_of_range_values_are_rejected_for_review(field, value):
    ok, reason = validate_scan({field: value})
    assert ok is False
    assert field in reason


def test_internally_inconsistent_scan_is_rejected():
    """Lean mass that does not follow from weight and body fat means a parse
    error, so it goes to review rather than into the trend."""
    ok, reason = validate_scan({"weight_kg": 66.7, "body_fat_pct": 14.1,
                                "lean_mass_kg": 40.0})
    assert ok is False
    assert "inconsistent" in reason


def test_partial_scan_with_only_valid_fields_passes():
    ok, _ = validate_scan({"weight_kg": 66.7})
    assert ok is True


# ---------------------------------------------------------------------------
# Gain quality
# ---------------------------------------------------------------------------
def test_gain_quality_needs_two_scans_and_says_so():
    """Only one scan exists today, so this must explain itself rather than
    return a number."""
    gq = gain_quality([BASELINE])
    assert gq.value is None
    assert gq.n_scans == 1
    assert "needs 2 scans" in gq.reason


def test_gain_quality_with_no_scans():
    gq = gain_quality([])
    assert gq.value is None
    assert gq.n_scans == 0


def test_gain_quality_computes_the_lean_fraction():
    """+0.9kg of which 0.63kg is muscle reads as 70% lean."""
    later = Scan(BASELINE.scanned_at + timedelta(weeks=4), weight_kg=67.6,
                 skeletal_muscle_kg=32.63)
    gq = gain_quality([BASELINE, later], weeks=4)
    assert gq.value == pytest.approx(0.7, abs=0.01)
    assert gq.delta_weight_kg == pytest.approx(0.9)
    assert gq.delta_muscle_kg == pytest.approx(0.63)
    assert gq.weeks == pytest.approx(4.0)


def test_gain_quality_guards_a_near_zero_weight_change():
    """Dividing by a weight change inside scan noise produces a meaningless
    ratio, so it must refuse instead."""
    later = Scan(BASELINE.scanned_at + timedelta(weeks=4), weight_kg=66.8,
                 skeletal_muscle_kg=32.5)
    gq = gain_quality([BASELINE, later], weeks=4)
    assert gq.value is None
    assert "scan noise" in gq.reason


def test_gain_quality_handles_weight_loss():
    later = Scan(BASELINE.scanned_at + timedelta(weeks=4), weight_kg=65.7,
                 skeletal_muscle_kg=31.5)
    gq = gain_quality([BASELINE, later], weeks=4)
    assert gq.delta_weight_kg < 0
    assert gq.value == pytest.approx(0.5, abs=0.01)


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------
def test_rolling_scan_average_uses_a_trailing_window():
    scans = [
        Scan(date(2026, 9, 13), weight_kg=66.0),
        Scan(date(2026, 9, 20), weight_kg=67.0),
        Scan(date(2026, 9, 27), weight_kg=68.0),
        Scan(date(2026, 10, 4), weight_kg=69.0),
    ]
    out = rolling_scan_average(scans, window=3)
    assert out[0][1]["weight_kg"] == pytest.approx(66.0)
    assert out[0][1]["n"] == 1
    assert out[2][1]["weight_kg"] == pytest.approx(67.0)
    assert out[3][1]["weight_kg"] == pytest.approx(68.0)
    assert out[3][1]["n"] == 3


def test_smoothed_weight_damps_a_single_spike():
    """One salty day must not move the trend line much."""
    days = [Weigh(date(2026, 10, 1) + timedelta(days=i), 66.0) for i in range(10)]
    days.append(Weigh(date(2026, 10, 11), 69.0))
    sm = smoothed_weight(days)
    assert sm[-1][1] < 66.4
    assert sm[-1][1] > 66.0


def test_weekly_rate_against_the_target_band():
    """+0.2kg a week on 67kg is 0.3% of bodyweight, inside the 0.25-0.5% band."""
    days = [Weigh(date(2026, 9, 1) + timedelta(days=i), 66.0 + i * (0.2 / 7)) for i in range(60)]
    rate = weekly_rate(days)
    assert rate.weekly_kg == pytest.approx(0.2, abs=0.03)
    assert rate.in_band is True


def test_weekly_rate_flags_gaining_too_fast():
    days = [Weigh(date(2026, 9, 1) + timedelta(days=i), 66.0 + i * (0.8 / 7)) for i in range(60)]
    rate = weekly_rate(days)
    assert rate.in_band is False
    assert rate.weekly_pct_bw > 0.005


def test_weekly_rate_needs_a_week_of_span():
    days = [Weigh(date(2026, 10, 1) + timedelta(days=i), 66.0) for i in range(3)]
    rate = weekly_rate(days)
    assert rate.weekly_kg is None
    assert "days of span" in rate.reason


def test_weekly_rate_with_one_weigh_in():
    rate = weekly_rate([Weigh(date(2026, 10, 1), 66.0)])
    assert rate.weekly_kg is None
    assert "at least 2" in rate.reason


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------
def test_projection_reaches_the_target_band():
    days = [Weigh(date(2026, 9, 1) + timedelta(days=i), 66.0 + i * (0.2 / 7)) for i in range(60)]
    got = project_target_date(days, 68.0)
    assert got is not None
    target_day, weeks = got
    assert weeks > 0
    assert target_day > days[-1].day


def test_projection_returns_none_when_moving_away_from_target():
    """A projection that silently says 2041 is worse than no projection."""
    days = [Weigh(date(2026, 9, 1) + timedelta(days=i), 66.0 - i * (0.2 / 7)) for i in range(60)]
    assert project_target_date(days, 68.0) is None


def test_projection_returns_none_on_a_flat_trend():
    days = [Weigh(date(2026, 9, 1) + timedelta(days=i), 66.0) for i in range(60)]
    assert project_target_date(days, 68.0) is None


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------
def test_scan_taken_under_different_conditions_is_flagged():
    usual = {"time": "morning", "fasted": True}
    odd = {"time": "evening", "fasted": False}
    scans = [
        Scan(date(2026, 9, 13), weight_kg=66.7, conditions=usual),
        Scan(date(2026, 9, 20), weight_kg=67.0, conditions=usual),
        Scan(date(2026, 9, 27), weight_kg=68.4, conditions=odd),
    ]
    assert conditions_mismatch(scans) == [date(2026, 9, 27)]


def test_no_mismatch_when_conditions_are_consistent():
    usual = {"time": "morning", "fasted": True}
    scans = [Scan(date(2026, 9, 13) + timedelta(weeks=i), weight_kg=66.0, conditions=usual)
             for i in range(3)]
    assert conditions_mismatch(scans) == []
