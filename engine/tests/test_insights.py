"""Insight engine tests. The gates matter more than the maths here: an insight
that is wrong is worse than no insight, because it gets acted on.
"""
import random
from datetime import date, timedelta

import pytest

from ti import stats
from ti.insights import (
    MIN_EFFECT_SD, MIN_N, Insight, cause_hunt, driver_binary, driver_continuous,
    ef_trend, efficiency_factor, publish, trend_break,
)

D0 = date(2026, 8, 1)


def _days(n, start=D0):
    return [start + timedelta(days=i) for i in range(n)]


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------
def test_minimum_sample_size_is_fourteen():
    assert MIN_N == 14


def test_insight_below_minimum_n_is_suppressed():
    i = Insight("personal_driver", "h", "d", effect_size=10.0, effect_unit="ms", n=13)
    assert publish([i], outcome_sd=5.0) == []


def test_insight_at_minimum_n_is_published():
    i = Insight("personal_driver", "h", "d", effect_size=10.0, effect_unit="ms", n=14)
    assert len(publish([i], outcome_sd=5.0)) == 1


def test_effect_inside_day_to_day_noise_is_suppressed():
    """An effect smaller than a quarter of the outcome's own SD is noise."""
    sd = 8.0
    small = Insight("personal_driver", "h", "d",
                    effect_size=MIN_EFFECT_SD * sd * 0.9, effect_unit="ms", n=30)
    big = Insight("personal_driver", "h", "d",
                  effect_size=MIN_EFFECT_SD * sd * 1.1, effect_unit="ms", n=30)
    assert publish([small], outcome_sd=sd) == []
    assert len(publish([big], outcome_sd=sd)) == 1


def test_published_insights_are_ranked_by_effect_size():
    a = Insight("k", "small", "d", effect_size=2.0, effect_unit="ms", n=20)
    b = Insight("k", "big", "d", effect_size=-9.0, effect_unit="ms", n=20)
    out = publish([a, b], outcome_sd=1.0)
    assert [i.headline for i in out] == ["big", "small"]


def test_nothing_is_ever_marked_causal():
    """This engine only ever observes, so no insight may claim causation."""
    rng = random.Random(3)
    late = {d for i, d in enumerate(_days(40)) if i % 2 == 0}
    outcome = {
        d: (54.0 if (d - timedelta(days=1)) in late else 60.0) + rng.gauss(0, 1.5)
        for d in _days(40, D0 + timedelta(days=1))
    }
    i = driver_binary("Late session", late, outcome, "HRV", "ms")
    assert i is not None
    assert i.is_causal is False
    assert "not proven cause" in i.detail


def test_sample_size_travels_with_the_claim():
    i = Insight("k", "h", "d", effect_size=5.0, effect_unit="ms", n=22)
    row = i.to_row("user-1")
    assert row["n"] == 22
    assert row["is_causal"] is False
    assert row["expires_at"] is not None


# ---------------------------------------------------------------------------
# Binary driver
# ---------------------------------------------------------------------------
def test_binary_driver_detects_a_real_effect_and_states_the_direction():
    """Late sessions on even days, next-day HRV 6ms lower after them."""
    late = {d for i, d in enumerate(_days(40)) if i % 2 == 0}
    outcome = {}
    for i, d in enumerate(_days(40, D0 + timedelta(days=1))):
        outcome[d] = 54.0 if (d - timedelta(days=1)) in late else 60.0

    i = driver_binary("Sessions ending after 19:00", late, outcome, "HRV", "ms")
    assert i is not None
    assert i.effect_size == pytest.approx(-6.0, abs=0.5)
    assert "cuts" in i.headline
    assert "n=" in i.headline


def test_binary_driver_direction_flips_for_a_positive_effect():
    good = {d for i, d in enumerate(_days(40)) if i % 2 == 0}
    outcome = {d: (66.0 if (d - timedelta(days=1)) in good else 60.0)
               for d in _days(40, D0 + timedelta(days=1))}
    i = driver_binary("Sleep before 23:00", good, outcome, "HRV", "ms")
    assert i is not None and "raises" in i.headline


def test_binary_driver_needs_both_groups():
    all_days = set(_days(20))
    outcome = {d: 60.0 for d in _days(20, D0 + timedelta(days=1))}
    assert driver_binary("x", all_days, outcome, "HRV", "ms") is None


# ---------------------------------------------------------------------------
# Continuous driver
# ---------------------------------------------------------------------------
def test_continuous_driver_finds_a_load_to_hrv_slope():
    """HRV falls 0.04ms per TSS, so a 150 TSS day costs about 6ms."""
    rng = random.Random(7)
    tss = {d: float(40 + (i * 7) % 120) for i, d in enumerate(_days(60))}
    hrv = {}
    for i, d in enumerate(_days(60, D0 + timedelta(days=1))):
        prior = tss[d - timedelta(days=1)]
        hrv[d] = 70.0 - 0.04 * prior + rng.gauss(0, 0.6)

    i = driver_continuous("training load", tss, hrv, "HRV", "ms", "TSS", per_unit=150)
    assert i is not None
    assert i.effect_size == pytest.approx(-6.0, abs=1.5)
    assert "costs" in i.headline
    assert i.is_causal is False


def test_continuous_driver_rejects_pure_noise():
    """No relationship must produce no insight, not a weak one."""
    rng = random.Random(11)
    tss = {d: rng.uniform(0, 150) for d in _days(60)}
    hrv = {d: rng.gauss(60, 5) for d in _days(60, D0 + timedelta(days=1))}
    assert driver_continuous("training load", tss, hrv, "HRV", "ms", "TSS") is None


# ---------------------------------------------------------------------------
# Trend break
# ---------------------------------------------------------------------------
def test_trend_break_detects_a_sustained_shift():
    rng = random.Random(5)
    series = [(D0 + timedelta(days=i), 50.0 + rng.gauss(0, 0.8)) for i in range(30)]
    series += [(D0 + timedelta(days=30 + i), 54.0 + rng.gauss(0, 0.8)) for i in range(10)]
    i = trend_break(series, "Resting HR", "bpm")
    assert i is not None
    assert "crept up" in i.headline
    assert i.effect_size == pytest.approx(4.0, abs=1.0)


def test_trend_break_ignores_a_single_bad_day():
    """Change point detection, not single day noise. One 70bpm reading in an
    otherwise flat series must not produce "resting HR has crept up"."""
    rng = random.Random(9)
    series = [(D0 + timedelta(days=i), 50.0 + rng.gauss(0, 1.0)) for i in range(40)]
    series[-1] = (series[-1][0], 70.0)
    assert trend_break(series, "Resting HR", "bpm") is None


def test_trend_break_false_positive_rate_on_pure_noise_is_low():
    """The gates are only worth having if they hold across seeds, so this
    measures the false positive rate rather than trusting one lucky draw: 300
    stationary series, no real shift anywhere."""
    fired = 0
    for seed in range(300):
        rng = random.Random(seed)
        series = [(D0 + timedelta(days=i), 50.0 + rng.gauss(0, 1.0)) for i in range(40)]
        if trend_break(series, "Resting HR", "bpm") is not None:
            fired += 1
    assert fired / 300 <= 0.10, f"fired on {fired}/300 stationary series"


def test_trend_break_detection_rate_on_a_real_shift_is_high():
    """The same gates must still catch a genuine 4bpm shift most of the time."""
    caught = 0
    for seed in range(100):
        rng = random.Random(1000 + seed)
        series = [(D0 + timedelta(days=i), 50.0 + rng.gauss(0, 1.0)) for i in range(30)]
        series += [(D0 + timedelta(days=30 + i), 54.0 + rng.gauss(0, 1.0)) for i in range(10)]
        if trend_break(series, "Resting HR", "bpm") is not None:
            caught += 1
    assert caught / 100 >= 0.90, f"caught only {caught}/100 real shifts"


def test_cause_hunt_false_positive_rate_on_pure_noise_is_low():
    """Same check for the decile comparison, which is the most false-positive
    prone part of the engine because the groups are small."""
    fired = 0
    trials = 200
    for seed in range(trials):
        rng = random.Random(seed)
        days = _days(60)
        hrv = {d: rng.gauss(60, 5) for d in days}
        behaviours = {f"b{j}": {d: rng.gauss(100, 20) for d in days} for j in range(3)}
        if cause_hunt(hrv, behaviours, "HRV"):
            fired += 1
    assert fired / trials <= 0.15, f"fired on {fired}/{trials} noise-only histories"


def test_trend_break_needs_enough_history():
    series = [(D0 + timedelta(days=i), 50.0) for i in range(8)]
    assert trend_break(series, "Resting HR", "bpm") is None


def test_trend_break_reports_a_fall():
    rng = random.Random(13)
    series = [(D0 + timedelta(days=i), 60.0 + rng.gauss(0, 1.0)) for i in range(30)]
    series += [(D0 + timedelta(days=30 + i), 55.0 + rng.gauss(0, 1.0)) for i in range(10)]
    i = trend_break(series, "HRV", "ms")
    assert i is not None and "fallen" in i.headline


# ---------------------------------------------------------------------------
# Cause hunting
# ---------------------------------------------------------------------------
def test_cause_hunt_ranks_what_was_different_on_the_worst_days():
    rng = random.Random(17)
    days = _days(40)
    hrv = {d: 60.0 - (i % 20) for i, d in enumerate(days)}
    protein = {d: (120.0 if hrv[d] < 48 else 220.0) + rng.gauss(0, 8) for d in days}
    sleep = {d: 7.5 + rng.gauss(0, 0.2) for d in days}

    out = cause_hunt(hrv, {"protein": protein, "sleep hours": sleep}, "HRV")
    assert out
    assert out[0].headline.startswith("On your worst HRV days, protein")
    assert "not proven cause" in out[0].detail
    assert all(i.kind == "cause_hunt" for i in out)


def test_cause_hunt_ignores_behaviours_that_did_not_differ():
    rng = random.Random(19)
    days = _days(40)
    hrv = {d: 60.0 - (i % 20) for i, d in enumerate(days)}
    flat = {d: 7.5 + rng.gauss(0, 0.2) for d in days}
    assert cause_hunt(hrv, {"sleep hours": flat}, "HRV") == []


def test_cause_hunt_needs_minimum_n():
    days = _days(10)
    hrv = {d: float(i) for i, d in enumerate(days)}
    assert cause_hunt(hrv, {"x": {d: float(i) for i, d in enumerate(days)}}, "HRV") == []


# ---------------------------------------------------------------------------
# Efficiency factor
# ---------------------------------------------------------------------------
def test_efficiency_factor_is_metres_per_beat():
    assert efficiency_factor(3.0, 150) == pytest.approx(1.2)
    assert efficiency_factor(None, 150) is None
    assert efficiency_factor(3.0, None) is None
    assert efficiency_factor(3.0, 0) is None


def test_ef_trend_reports_improvement():
    samples = [(D0 + timedelta(days=i * 3), 1.10) for i in range(6)]
    samples += [(D0 + timedelta(days=18 + i * 3), 1.20) for i in range(6)]
    i = ef_trend(samples, "run")
    assert i is not None
    assert "better" in i.headline
    assert i.effect_size == pytest.approx(9.09, abs=0.1)


def test_ef_trend_ignores_a_tiny_change():
    samples = [(D0 + timedelta(days=i * 3), 1.10) for i in range(6)]
    samples += [(D0 + timedelta(days=18 + i * 3), 1.11) for i in range(6)]
    assert ef_trend(samples, "run") is None


def test_ef_trend_needs_twelve_sessions():
    """Audited reality: 9 runs in 90 days, so this will return None for now."""
    samples = [(D0 + timedelta(days=i * 10), 1.10) for i in range(9)]
    assert ef_trend(samples, "run") is None


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------
def test_pearson_on_a_perfect_line():
    assert stats.pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert stats.pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)


def test_pearson_on_constant_series_is_none():
    assert stats.pearson([1, 1, 1], [1, 2, 3]) is None


def test_significance_needs_both_strength_and_n():
    assert stats.r_is_significant(0.2, 10) is False
    assert stats.r_is_significant(0.8, 10) is True


def test_linreg_recovers_a_known_slope():
    xs = [float(i) for i in range(20)]
    ys = [3.0 + 2.5 * x for x in xs]
    slope, intercept = stats.linreg(xs, ys)
    assert slope == pytest.approx(2.5)
    assert intercept == pytest.approx(3.0)


def test_cohens_d_sign_and_magnitude():
    a = [10.0, 11.0, 12.0, 11.0]
    b = [5.0, 6.0, 7.0, 6.0]
    assert stats.cohens_d(a, b) > 2.0
    assert stats.cohens_d(b, a) < -2.0
