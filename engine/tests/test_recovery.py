from datetime import date

import pytest

from ti.recovery import (
    DEFAULT_WEIGHTS, MIN_DAYS_FOR_TSB,
    baseline, bedtime_regularity, hrv_days_below_band, hrv_state,
    readiness, rhr_flag_days, rhr_flagged, rolling_mean,
)


def _steady(value, n):
    return [float(value)] * n


# ---------------------------------------------------------------------------
# HRV
# ---------------------------------------------------------------------------
def test_hrv_inside_band_for_steady_values():
    # 60 nights around 60ms with small jitter.
    nightly = [60.0 + (1 if i % 2 else -1) for i in range(60)]
    st = hrv_state(nightly)
    assert st.position == "inside"
    assert st.flag is None
    assert st.band is not None


def test_hrv_below_band_flags_strain():
    nightly = [60.0 + (1 if i % 2 else -1) for i in range(53)] + _steady(45, 7)
    st = hrv_state(nightly)
    assert st.position == "below"
    assert st.flag == "strain"


def test_hrv_above_band_flags_saturation_not_praise():
    """A sharp rise can be parasympathetic saturation, so it must be flagged
    rather than silently read as good news."""
    nightly = [60.0 + (1 if i % 2 else -1) for i in range(53)] + _steady(85, 7)
    st = hrv_state(nightly)
    assert st.position == "above"
    assert st.flag == "saturation"


def test_hrv_unknown_without_enough_baseline():
    st = hrv_state(_steady(60, 5))
    assert st.position == "unknown"
    assert st.band is None


def test_baseline_needs_fourteen_points_to_be_usable():
    assert baseline([float(i) for i in range(13)], 60).usable is False
    assert baseline([float(i) for i in range(14)], 60).usable is True


def test_rolling_mean_ignores_missing_nights():
    assert rolling_mean([50.0, None, 70.0], 7) == pytest.approx(60.0)
    assert rolling_mean([None, None], 7) is None


def test_days_below_band_counts_single_nights():
    band = (55.0, 65.0)
    nightly = [60.0, 50.0, 60.0, 48.0, 60.0, 52.0, 60.0]
    assert hrv_days_below_band(nightly, band) == 3
    assert hrv_days_below_band(nightly, None) == 0


# ---------------------------------------------------------------------------
# Resting HR
# ---------------------------------------------------------------------------
def test_rhr_flag_fires_at_five_bpm_above_baseline():
    assert rhr_flagged([50] * 30 + [55]) is True
    assert rhr_flagged([50] * 30 + [54]) is False


def test_rhr_flag_needs_a_baseline():
    assert rhr_flagged([]) is False
    assert rhr_flagged([None]) is False


def test_rhr_flag_days_counts_a_window():
    series = [50] * 30 + [57, 57, 57, 50, 50, 50, 50]
    assert rhr_flag_days(series) == 3


# ---------------------------------------------------------------------------
# Sleep
# ---------------------------------------------------------------------------
def test_bedtime_regularity_is_sd_in_minutes():
    assert bedtime_regularity([1380.0, 1380.0, 1380.0]) == 0.0
    assert bedtime_regularity([1320.0, 1380.0, 1440.0]) == pytest.approx(60.0)
    assert bedtime_regularity([1380.0]) is None


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------
def _full_inputs():
    return dict(
        hrv_nightly=[60.0 + (1 if i % 2 else -1) for i in range(60)],
        sleep_scores=_steady(80, 10),
        rhr=[50] * 31,
        tsb=0.0,
        checkin=(2, 4, 4),
        load_history_days=90,
    )


def test_readiness_returns_score_band_and_drivers():
    r = readiness(**_full_inputs())
    assert r.score is not None
    assert 0 <= r.score <= 100
    assert r.band in {"green", "amber", "red"}
    assert len(r.drivers) == 3
    assert r.cold_start is False


def test_weights_sum_to_one():
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)


def test_weights_applied_sum_to_one_when_all_inputs_present():
    r = readiness(**_full_inputs())
    applied = sum(c["weight"] for c in r.components.values() if c["weight"])
    assert applied == pytest.approx(1.0)


def test_cold_start_drops_tsb_and_renormalises():
    """Before 42 days of load history, a seeded CTL of zero would read as
    'well rested'. TSB must be excluded and the row marked."""
    args = _full_inputs() | {"load_history_days": 10, "tsb": 0.0}
    r = readiness(**args)
    assert r.cold_start is True
    assert r.components["tsb"]["weight"] == 0.0
    assert r.components["tsb"]["subscore"] is None
    applied = sum(c["weight"] for c in r.components.values() if c["weight"])
    assert applied == pytest.approx(1.0)
    assert "TSB excluded" in (r.note or "")


def test_cold_start_boundary_is_42_days():
    assert readiness(**(_full_inputs() | {"load_history_days": MIN_DAYS_FOR_TSB - 1})).cold_start
    assert not readiness(**(_full_inputs() | {"load_history_days": MIN_DAYS_FOR_TSB})).cold_start


def test_missing_input_is_dropped_not_scored_zero():
    """A night with no HRV must not cost 35% of the score and render red."""
    with_hrv = readiness(**_full_inputs())
    without = readiness(**(_full_inputs() | {"hrv_nightly": []}))
    assert without.components["hrv"]["weight"] == 0.0
    assert without.score is not None
    # Dropping a mid-range input should not crater the score.
    assert abs(without.score - with_hrv.score) < 25


def test_no_inputs_at_all_returns_unknown_not_zero():
    r = readiness([], [], [], None, (None, None, None), load_history_days=0)
    assert r.score is None
    assert r.band == "unknown"


def test_soreness_is_inverted():
    """Soreness 5 means very sore, so it must lower the score."""
    sore = readiness(**(_full_inputs() | {"checkin": (5, 3, 3)}))
    fresh = readiness(**(_full_inputs() | {"checkin": (1, 3, 3)}))
    assert fresh.score > sore.score


def test_low_hrv_lowers_the_score_and_shows_as_a_driver():
    poor = _full_inputs() | {
        "hrv_nightly": [60.0 + (1 if i % 2 else -1) for i in range(53)] + _steady(40, 7)
    }
    r = readiness(**poor)
    good = readiness(**_full_inputs())
    assert r.score < good.score
    top = r.drivers[0]
    assert top["component"] == "hrv"
    assert top["contribution"] < 0
