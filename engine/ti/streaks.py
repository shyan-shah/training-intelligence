"""Habit streaks and the daily scorecard.

Three states per habit per day, never two: hit, missed, or no data. A day with
no data is grey and breaks nothing, because treating a missing weigh-in as a
missed target would manufacture a red column out of a flat battery.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

HIT, MISS, NODATA = "hit", "missed", "no_data"


@dataclass(frozen=True)
class Habit:
    key: str
    label: str
    # Returns True (hit), False (missed) or None (no data) for one day.
    evaluate: Callable[[dict], bool | None]
    weekly_target: int | None = None     # e.g. gym 4 per week


@dataclass
class HabitResult:
    key: str
    label: str
    days: dict[date, str] = field(default_factory=dict)
    current_streak: int = 0
    best_streak: int = 0
    week_hits: int = 0
    week_possible: int = 0
    weekly_target: int | None = None

    @property
    def week_completion(self) -> float | None:
        if self.weekly_target:
            return round(min(self.week_hits / self.weekly_target, 1.0), 3)
        if self.week_possible == 0:
            return None
        return round(self.week_hits / self.week_possible, 3)


def default_habits(targets: dict) -> list[Habit]:
    """The habit set from the brief, bound to targets from athlete_settings."""
    protein_target = targets.get("protein_g", 216)
    kcal_target = targets.get("kcal", 2874)
    sleep_hours = targets.get("sleep_hours", 7.5)
    sleep_score = targets.get("sleep_score", 75)
    gym_per_week = targets.get("gym_per_week", 4)

    def _protein(d: dict) -> bool | None:
        v = d.get("protein_g")
        return None if v is None else v >= protein_target

    def _kcal(d: dict) -> bool | None:
        v = d.get("kcal")
        return None if v is None else v >= kcal_target

    def _gym(d: dict) -> bool | None:
        # Absence of a logged session is a real miss, not missing data: the
        # activity feed is always present even on a rest day.
        return bool(d.get("strength_sessions", 0) >= 1)

    def _sleep_dur(d: dict) -> bool | None:
        v = d.get("sleep_total_min")
        return None if v is None else v >= sleep_hours * 60

    def _sleep_score(d: dict) -> bool | None:
        v = d.get("sleep_score")
        return None if v is None else v >= sleep_score

    def _checkin(d: dict) -> bool | None:
        return bool(d.get("has_checkin"))

    def _scan(d: dict) -> bool | None:
        return bool(d.get("scan_this_week"))

    return [
        Habit("protein", f"Protein >= {protein_target}g", _protein),
        Habit("kcal", f"Calories >= {kcal_target}", _kcal),
        Habit("gym", f"Gym session ({gym_per_week}/week)", _gym, weekly_target=gym_per_week),
        Habit("sleep_duration", f"Sleep >= {sleep_hours}h", _sleep_dur),
        Habit("sleep_quality", f"Sleep score >= {sleep_score}", _sleep_score),
        Habit("checkin", "Daily check-in", _checkin),
        Habit("evolt", "Weekly Evolt scan", _scan, weekly_target=1),
    ]


def evaluate(habits: list[Habit], day_rows: dict[date, dict],
             start: date, end: date, week_start: date | None = None) -> list[HabitResult]:
    """Build per-habit calendars, streaks and this week's completion."""
    results: list[HabitResult] = []
    week_start = week_start or (end - timedelta(days=end.weekday()))

    for h in habits:
        res = HabitResult(h.key, h.label, weekly_target=h.weekly_target)
        day = start
        while day <= end:
            row = day_rows.get(day, {})
            verdict = h.evaluate(row)
            res.days[day] = HIT if verdict is True else MISS if verdict is False else NODATA
            if week_start <= day <= end:
                if verdict is True:
                    res.week_hits += 1
                if verdict is not None:
                    res.week_possible += 1
            day += timedelta(days=1)

        res.current_streak, res.best_streak = _streaks(res.days, start, end)
        results.append(res)
    return results


def _streaks(days: dict[date, str], start: date, end: date) -> tuple[int, int]:
    """Current and best run of hits. A no-data day pauses the streak without
    breaking it; a missed day breaks it."""
    best = run = 0
    day = start
    while day <= end:
        state = days.get(day, NODATA)
        if state == HIT:
            run += 1
            best = max(best, run)
        elif state == MISS:
            run = 0
        day += timedelta(days=1)

    current = 0
    day = end
    while day >= start:
        state = days.get(day, NODATA)
        if state == HIT:
            current += 1
        elif state == MISS:
            break
        day -= timedelta(days=1)
    return current, best
