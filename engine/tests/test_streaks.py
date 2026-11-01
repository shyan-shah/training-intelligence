from datetime import date, timedelta

import pytest

from ti.streaks import HIT, MISS, NODATA, default_habits, evaluate

START = date(2026, 10, 19)      # a Monday
END = date(2026, 11, 1)         # the Sunday two weeks later
TARGETS = {"protein_g": 216, "kcal": 2874, "gym_per_week": 4,
           "sleep_hours": 7.5, "sleep_score": 75}


def _habit(key):
    return [h for h in default_habits(TARGETS) if h.key == key]


def test_default_habit_set_matches_the_brief():
    keys = {h.key for h in default_habits(TARGETS)}
    assert keys == {"protein", "kcal", "gym", "sleep_duration",
                    "sleep_quality", "checkin", "evolt"}


def test_habit_labels_carry_the_actual_target():
    labels = {h.key: h.label for h in default_habits(TARGETS)}
    assert "216" in labels["protein"]
    assert "4/week" in labels["gym"]


def test_missing_data_is_grey_not_red():
    """A flat battery must not render as a missed target."""
    rows = {START: {}}
    res = evaluate(_habit("protein"), rows, START, START)[0]
    assert res.days[START] == NODATA
    assert res.current_streak == 0
    assert res.week_possible == 0


def test_hit_and_miss_are_distinguished():
    rows = {START: {"protein_g": 220.0}, START + timedelta(days=1): {"protein_g": 180.0}}
    res = evaluate(_habit("protein"), rows, START, START + timedelta(days=1))[0]
    assert res.days[START] == HIT
    assert res.days[START + timedelta(days=1)] == MISS


def test_protein_boundary_is_inclusive():
    rows = {START: {"protein_g": 216.0}}
    assert evaluate(_habit("protein"), rows, START, START)[0].days[START] == HIT


def test_gym_absence_is_a_real_miss_not_missing_data():
    """The activity feed is always present, even on a rest day, so no logged
    session means a genuine miss."""
    rows = {START: {}}
    res = evaluate(_habit("gym"), rows, START, START)[0]
    assert res.days[START] == MISS


def test_current_streak_counts_back_from_today():
    rows = {}
    day = START
    while day <= END:
        rows[day] = {"protein_g": 220.0}
        day += timedelta(days=1)
    rows[START + timedelta(days=3)] = {"protein_g": 100.0}      # one miss
    res = evaluate(_habit("protein"), rows, START, END)[0]
    assert res.current_streak == (END - (START + timedelta(days=3))).days


def test_best_streak_survives_a_later_break():
    rows = {}
    day = START
    while day <= END:
        rows[day] = {"protein_g": 220.0}
        day += timedelta(days=1)
    rows[END] = {"protein_g": 100.0}
    res = evaluate(_habit("protein"), rows, START, END)[0]
    assert res.current_streak == 0
    assert res.best_streak == (END - START).days


def test_no_data_day_pauses_a_streak_without_breaking_it():
    rows = {
        START: {"protein_g": 220.0},
        START + timedelta(days=1): {},                   # no data
        START + timedelta(days=2): {"protein_g": 220.0},
    }
    res = evaluate(_habit("protein"), rows, START, START + timedelta(days=2))[0]
    assert res.days[START + timedelta(days=1)] == NODATA
    assert res.current_streak == 2


def test_weekly_target_habit_reports_completion_against_the_target():
    """Gym is counted against 4 per week, not against 7 days."""
    rows = {}
    week_start = date(2026, 10, 26)
    for i in range(7):
        rows[week_start + timedelta(days=i)] = {"strength_sessions": 1 if i < 2 else 0}
    res = evaluate(_habit("gym"), rows, week_start, week_start + timedelta(days=6),
                   week_start=week_start)[0]
    assert res.week_hits == 2
    assert res.weekly_target == 4
    assert res.week_completion == pytest.approx(0.5)


def test_weekly_completion_caps_at_one():
    rows = {}
    week_start = date(2026, 10, 26)
    for i in range(7):
        rows[week_start + timedelta(days=i)] = {"strength_sessions": 1}
    res = evaluate(_habit("gym"), rows, week_start, week_start + timedelta(days=6),
                   week_start=week_start)[0]
    assert res.week_completion == pytest.approx(1.0)


def test_daily_habit_completion_is_hits_over_days_with_data():
    rows = {}
    week_start = date(2026, 10, 26)
    for i in range(7):
        rows[week_start + timedelta(days=i)] = (
            {"protein_g": 220.0} if i < 3 else {} if i < 5 else {"protein_g": 100.0}
        )
    res = evaluate(_habit("protein"), rows, week_start, week_start + timedelta(days=6),
                   week_start=week_start)[0]
    assert res.week_hits == 3
    assert res.week_possible == 5
    assert res.week_completion == pytest.approx(0.6)


def test_every_day_in_range_gets_a_state():
    rows = {}
    res = evaluate(default_habits(TARGETS), rows, START, END)
    for h in res:
        assert len(h.days) == (END - START).days + 1
        assert set(h.days.values()) <= {HIT, MISS, NODATA}
