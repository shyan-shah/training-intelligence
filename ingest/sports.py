"""Sport normalisation.

The engine works in five buckets: swim, bike, run, strength, other. Everything
from either source maps into one of those.

The mapping covers the sport types actually present in the audited 90 days of
history (Ride, VirtualRide, WeightTraining, Run, Walk, Hike, Swim, Tennis,
Padel, Workout) and the common endurance types beyond them. An unrecognised
type lands in 'other', which earns no TSS, rather than being guessed into a
bucket where it would distort load.
"""
from __future__ import annotations

SWIM = "swim"
BIKE = "bike"
RUN = "run"
STRENGTH = "strength"
WALK = "walk"
OTHER = "other"

_STRAVA = {
    # bike
    "Ride": BIKE, "VirtualRide": BIKE, "EBikeRide": BIKE, "GravelRide": BIKE,
    "MountainBikeRide": BIKE, "Handcycle": BIKE, "Velomobile": BIKE,
    # run
    "Run": RUN, "VirtualRun": RUN, "TrailRun": RUN,
    # swim
    "Swim": SWIM, "OpenWaterSwim": SWIM,
    # strength
    "WeightTraining": STRENGTH, "Crossfit": STRENGTH,
    # walk: real aerobic time but not a training session, so it is kept
    # separate and excluded from load rather than counted as a run
    "Walk": WALK, "Hike": WALK, "Wheelchair": WALK,
}

_GARMIN = {
    "cycling": BIKE, "road_biking": BIKE, "mountain_biking": BIKE,
    "virtual_ride": BIKE, "indoor_cycling": BIKE, "gravel_cycling": BIKE,
    "running": RUN, "treadmill_running": RUN, "trail_running": RUN,
    "indoor_running": RUN, "track_running": RUN,
    "lap_swimming": SWIM, "open_water_swimming": SWIM, "swimming": SWIM,
    "strength_training": STRENGTH, "indoor_cardio": OTHER,
    "walking": WALK, "hiking": WALK, "casual_walking": WALK, "speed_walking": WALK,
}

# Sports that contribute to training load. Walking and racquet sports are real
# activity but there is no defensible TSS model for them here, so they are
# stored and shown without inflating CTL.
LOAD_BEARING = {SWIM, BIKE, RUN, STRENGTH}


def from_strava(sport_type: str | None) -> str:
    return _STRAVA.get(sport_type or "", OTHER)


def from_garmin(activity_type: str | None) -> str:
    return _GARMIN.get((activity_type or "").lower(), OTHER)


def bears_load(sport: str) -> bool:
    return sport in LOAD_BEARING


def strength_label(name: str | None) -> str | None:
    """Guess a push/pull/legs label from a session title, for the fixed TSS
    estimate. Returns None when the title says nothing useful, which falls
    back to the default estimate rather than a wrong one."""
    if not name:
        return None
    n = name.lower()
    if any(w in n for w in ("leg", "squat", "deadlift", "lower")):
        return "legs"
    if any(w in n for w in ("push", "chest", "shoulder", "press")):
        return "push"
    if any(w in n for w in ("pull", "back", "row", "lat")):
        return "pull"
    if any(w in n for w in ("full body", "fullbody", "full-body")):
        return "full"
    return None
