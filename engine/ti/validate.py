"""Activity validation.

The brief specified range checks for Evolt scans but not for activities. Real
Strava history makes the case for them. Audited examples:

  * "Night Workout", 2026-10-09: elapsed 4s, zero distance. A junk row.
  * "Night Workout", 2026-09-22: elapsed 175,726s (48.8h), moving 4,678s.
    A timer left running.
  * "Afternoon Walk", 2026-09-26: max_speed 48.9 km/h. GPS spike.
  * "Lunch Ride", 2026-08-15: max_speed 81.0 km/h on a 9.8km ride. GPS spike.

Rows are flagged, not deleted, so a rejected session stays auditable and can
be reinstated by hand.
"""
from __future__ import annotations

from dataclasses import dataclass

MIN_DURATION_S = 60
MAX_ELAPSED_TO_MOVING = 3.0

# A max speed this many times the session average is a spike regardless of
# whether it clears the absolute ceiling. The audited 2026-08-15 ride peaked at
# 81.0 km/h while averaging 11.3, which sits under the 90 km/h bike ceiling but
# is 7.2x the average. Zwift rides (1.8x) and normal road rides (2.5x) stay
# well clear of this.
MAX_SPEED_TO_AVG = 4.0

# Plausible top speeds in km/h, used only to flag GPS spikes. These are not
# performance judgements, they are sanity bounds.
MAX_SPEED_KMH = {
    "run": 32.0,
    "bike": 90.0,
    "swim": 10.0,
    "walk": 12.0,
    "other": 90.0,
    "strength": 5.0,
}


@dataclass
class Validation:
    is_valid: bool
    reason: str | None
    warnings: list[str]


def validate_activity(
    sport: str,
    duration_s: int | None,
    elapsed_s: int | None,
    distance_m: float | None,
    max_speed_kmh: float | None = None,
    avg_hr: int | None = None,
    max_hr_setting: int | None = None,
) -> Validation:
    """Decide whether an activity row should count toward load.

    is_valid False means it is excluded from TSS and the load series. Warnings
    do not exclude it but are surfaced on the activity.
    """
    hard: list[str] = []
    warn: list[str] = []

    if duration_s is None or duration_s < MIN_DURATION_S:
        hard.append(f"moving time {duration_s}s below {MIN_DURATION_S}s floor")

    if duration_s and elapsed_s and duration_s > 0:
        ratio = elapsed_s / duration_s
        if ratio > MAX_ELAPSED_TO_MOVING:
            # Not fatal: TSS uses moving time anyway. But a 48h elapsed row
            # breaks any chart drawn on elapsed, so it is worth saying.
            warn.append(
                f"elapsed {elapsed_s}s is {ratio:.1f}x moving time {duration_s}s, "
                "likely a timer left running"
            )

    if max_speed_kmh is not None:
        ceiling = MAX_SPEED_KMH.get(sport, MAX_SPEED_KMH["other"])
        avg_kmh = None
        if duration_s and duration_s > 0 and distance_m:
            avg_kmh = (distance_m / 1000.0) / (duration_s / 3600.0)

        over_ceiling = max_speed_kmh > ceiling
        over_ratio = bool(avg_kmh and avg_kmh > 0 and max_speed_kmh / avg_kmh > MAX_SPEED_TO_AVG)

        if over_ceiling or over_ratio:
            how = (f"exceeds the {ceiling} km/h ceiling for {sport}" if over_ceiling
                   else f"is {max_speed_kmh / avg_kmh:.1f}x the {avg_kmh:.1f} km/h session average")
            warn.append(
                f"max speed {max_speed_kmh:.1f} km/h {how}, "
                "treat as GPS spike and do not use for best efforts"
            )

    if avg_hr is not None:
        if avg_hr < 30 or avg_hr > 240:
            hard.append(f"avg HR {avg_hr} outside 30-240")
        elif max_hr_setting and avg_hr > max_hr_setting:
            warn.append(f"avg HR {avg_hr} above configured max HR {max_hr_setting}")

    if distance_m is not None and distance_m < 0:
        hard.append(f"negative distance {distance_m}")

    return Validation(not hard, "; ".join(hard) or None, warn)
