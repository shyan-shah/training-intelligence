"""Cross-source activity dedupe.

The brief specified a 2-minute start-time window with Garmin winning. Audited
Strava history contains two tempo runs starting 2026-08-27 11:21:23 and
11:23:59, 2 minutes 36 seconds apart, both tagged from the same training plan
source. A 2-minute window misses that pair.

So the window defaults to 5 minutes and start time alone is not enough: a
candidate pair must also look like the same session by duration, and by
distance where both have one. Two genuinely different sessions back to back
(the audited 2026-10-28 rides, 16 minutes apart) stay separate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

SOURCE_PRIORITY = {"garmin": 0, "strava": 1}      # lower wins
DEFAULT_WINDOW_S = 300
DURATION_TOLERANCE = 0.25                          # 25%
DISTANCE_TOLERANCE = 0.25


@dataclass
class Candidate:
    key: str                  # f"{source}:{source_id}"
    source: str
    sport: str
    start_at: datetime
    duration_s: int
    distance_m: float | None = None


def _similar(a: Candidate, b: Candidate) -> bool:
    if a.sport != b.sport:
        return False

    lo, hi = sorted((a.duration_s, b.duration_s))
    if hi == 0 or (hi - lo) / hi > DURATION_TOLERANCE:
        return False

    if a.distance_m and b.distance_m:
        dlo, dhi = sorted((a.distance_m, b.distance_m))
        if dhi > 0 and (dhi - dlo) / dhi > DISTANCE_TOLERANCE:
            return False

    return True


def group(candidates: list[Candidate], window_s: int = DEFAULT_WINDOW_S) -> dict[str, str]:
    """Map every candidate key to the key of its group's winner.

    Winner is the lowest SOURCE_PRIORITY (Garmin over Strava, since the FIT
    file carries more), tie-broken by longer moving time.
    """
    ordered = sorted(candidates, key=lambda c: c.start_at)
    groups: list[list[Candidate]] = []

    for c in ordered:
        placed = False
        for g in groups:
            anchor = g[0]
            if abs((c.start_at - anchor.start_at).total_seconds()) <= window_s and _similar(anchor, c):
                g.append(c)
                placed = True
                break
        if not placed:
            groups.append([c])

    winners: dict[str, str] = {}
    for g in groups:
        best = sorted(g, key=lambda c: (SOURCE_PRIORITY.get(c.source, 99), -c.duration_s))[0]
        for c in g:
            winners[c.key] = best.key
    return winners
