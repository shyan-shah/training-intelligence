import pytest

from ti.verdict import weekly_verdict


CLEAN = dict(hrv_position="inside", hrv_days_below=0, tsb=-5.0,
             acwr=1.0, sleep_7d=80.0, rhr_flag_days=0)


def test_push_when_every_condition_holds():
    v = weekly_verdict(**CLEAN)
    assert v.verdict == "push"
    assert all(c.passed for c in v.push_checks)


@pytest.mark.parametrize("override,expected_check", [
    ({"hrv_days_below": 3}, "hrv_days_below"),
    ({"acwr": 1.6}, "acwr_high"),
    ({"tsb": -31.0}, "tsb_low"),
    ({"rhr_flag_days": 3}, "rhr_flags"),
])
def test_any_single_hard_signal_forces_back_off(override, expected_check):
    v = weekly_verdict(**(CLEAN | override))
    assert v.verdict == "back_off"
    assert expected_check in [c.name for c in v.reasons]


def test_back_off_outranks_a_clean_push_sweep():
    """One hard signal must beat four satisfied push conditions."""
    v = weekly_verdict(**(CLEAN | {"acwr": 2.0}))
    assert v.verdict == "back_off"


@pytest.mark.parametrize("override", [
    {"hrv_position": "below"},
    {"tsb": -20.0},
    {"acwr": 1.3},
    {"sleep_7d": 70.0},
])
def test_hold_when_a_push_condition_fails_without_a_hard_signal(override):
    v = weekly_verdict(**(CLEAN | override))
    assert v.verdict == "hold"
    assert v.reasons and not all(c.passed for c in v.reasons)


def test_acwr_boundary_is_inclusive_at_push_ceiling():
    assert weekly_verdict(**(CLEAN | {"acwr": 1.2})).verdict == "push"
    assert weekly_verdict(**(CLEAN | {"acwr": 1.21})).verdict == "hold"


def test_tsb_boundary_is_exclusive_at_push_floor():
    assert weekly_verdict(**(CLEAN | {"tsb": -10.0})).verdict == "hold"
    assert weekly_verdict(**(CLEAN | {"tsb": -9.9})).verdict == "push"


def test_verdict_always_carries_the_numbers_that_triggered_it():
    """Acceptance check: the weekly verdict shows the numbers behind it."""
    v = weekly_verdict(**(CLEAN | {"acwr": 1.7}))
    assert v.reasons
    for c in v.reasons:
        assert c.value is not None
        assert c.threshold
        assert c.detail
    assert "1.7" in v.narrative()


def test_narrative_is_a_template_not_a_bare_label():
    v = weekly_verdict(**CLEAN)
    text = v.narrative()
    assert text.startswith("Push.")
    assert len(text) > len("Push.")


def test_missing_inputs_are_reported_as_unassessed():
    v = weekly_verdict(hrv_position="unknown", hrv_days_below=0, tsb=None,
                       acwr=None, sleep_7d=None, rhr_flag_days=0)
    assert v.verdict == "hold"
    assert len(v.unavailable) == 4
    assert "Not assessed" in v.narrative()


def test_missing_acwr_cannot_trigger_back_off():
    """A None ACWR means not enough history, not a dangerous one."""
    v = weekly_verdict(**(CLEAN | {"acwr": None}))
    assert v.verdict == "hold"


def test_watch_flags_surface_sub_threshold_signals():
    """Signals below the back-off threshold do not change the verdict, by
    design: they ride along as watch flags. A week can legitimately read
    "push" while carrying two of them, which is why the page shows both."""
    v = weekly_verdict(**(CLEAN | {"hrv_days_below": 2, "rhr_flag_days": 1}))
    assert v.verdict == "push"
    assert any("2 of the last 7 nights" in f for f in v.watch_flags)
    assert any("Resting HR flagged on 1" in f for f in v.watch_flags)


def test_hrv_saturation_becomes_a_watch_flag():
    v = weekly_verdict(**(CLEAN | {"hrv_position": "above"}))
    assert any("saturation" in f for f in v.watch_flags)


def test_thresholds_are_overridable_from_settings():
    tuned = {"acwr_backoff": 1.1}
    v = weekly_verdict(**(CLEAN | {"acwr": 1.15}), thresholds=tuned)
    assert v.verdict == "back_off"
