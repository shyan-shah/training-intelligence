"""Dedupe tests built on real audited Strava records, so the window is sized
against actual data rather than a guess.
"""
from datetime import datetime

from ti.dedupe import Candidate, DEFAULT_WINDOW_S, group


def _c(key, source, sport, iso, dur, dist=None):
    return Candidate(key=key, source=source, sport=sport,
                     start_at=datetime.fromisoformat(iso), duration_s=dur, distance_m=dist)


def test_default_window_is_wider_than_two_minutes():
    """The audited duplicate pair sits 2m36s apart, so a 2-minute window would
    miss it."""
    assert DEFAULT_WINDOW_S >= 156


def test_the_audited_duplicate_tempo_runs_are_grouped():
    """Real records: 2026-08-27 11:21:23 (10.32km / 3982s) and 11:23:59
    (12.52km / 4550s), both from the same training plan export. 2m36s apart,
    similar duration and distance, so they are one session."""
    a = _c("strava:19921236713", "strava", "run", "2026-08-27T11:21:23", 3982, 10322.4)
    b = _c("strava:19921771400", "strava", "run", "2026-08-27T11:23:59", 4550, 12519.7)
    winners = group([a, b])
    assert winners[a.key] == winners[b.key]


def test_the_audited_back_to_back_rides_stay_separate():
    """Real records: 2026-10-28 12:43:02 (1.25km / 245s) and 12:59:19
    (16.13km / 2926s). 16 minutes apart and nothing alike, so two sessions."""
    a = _c("strava:20764558680", "strava", "bike", "2026-10-28T12:43:02", 245, 1252.3)
    b = _c("strava:20766055808", "strava", "bike", "2026-10-28T12:59:19", 2926, 16133.2)
    winners = group([a, b])
    assert winners[a.key] != winners[b.key]


def test_garmin_wins_over_strava():
    g = _c("garmin:1", "garmin", "run", "2026-10-11T11:11:40", 2817, 8486.2)
    s = _c("strava:2", "strava", "run", "2026-10-11T11:11:55", 2817, 8486.2)
    winners = group([g, s])
    assert winners[g.key] == "garmin:1"
    assert winners[s.key] == "garmin:1"


def test_close_start_but_different_sport_is_not_a_duplicate():
    a = _c("garmin:1", "garmin", "run", "2026-10-11T11:00:00", 1800, 5000)
    b = _c("strava:2", "strava", "bike", "2026-10-11T11:01:00", 1800, 5000)
    assert group([a, b])[a.key] != group([a, b])[b.key]


def test_close_start_but_wildly_different_duration_is_not_a_duplicate():
    a = _c("garmin:1", "garmin", "run", "2026-10-11T11:00:00", 600)
    b = _c("strava:2", "strava", "run", "2026-10-11T11:01:00", 3600)
    winners = group([a, b])
    assert winners[a.key] != winners[b.key]


def test_distance_disagreement_splits_the_pair():
    a = _c("garmin:1", "garmin", "run", "2026-10-11T11:00:00", 1800, 5000)
    b = _c("strava:2", "strava", "run", "2026-10-11T11:01:00", 1800, 9000)
    winners = group([a, b])
    assert winners[a.key] != winners[b.key]


def test_missing_distance_falls_back_to_duration_only():
    """Strength sessions have no distance, so duration has to carry it."""
    a = _c("garmin:1", "garmin", "strength", "2026-10-26T09:18:33", 2226)
    b = _c("strava:2", "strava", "strength", "2026-10-26T09:18:40", 2226)
    assert group([a, b])[a.key] == group([a, b])[b.key]


def test_every_candidate_gets_a_winner():
    cands = [
        _c("garmin:1", "garmin", "run", "2026-10-11T11:00:00", 1800, 5000),
        _c("strava:2", "strava", "run", "2026-10-11T11:01:00", 1800, 5000),
        _c("strava:3", "strava", "bike", "2026-10-12T11:00:00", 3600, 20000),
    ]
    winners = group(cands)
    assert set(winners) == {c.key for c in cands}
    assert winners["strava:3"] == "strava:3"


def test_longer_session_wins_a_same_source_tie():
    a = _c("strava:1", "strava", "run", "2026-08-27T11:21:23", 3982, 10322.4)
    b = _c("strava:2", "strava", "run", "2026-08-27T11:23:59", 4550, 12519.7)
    assert group([a, b])[a.key] == "strava:2"
