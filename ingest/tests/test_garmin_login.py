"""Tests for the login-route parsing.

The library's payload shapes are not a stable contract and differ between
endpoints and versions, which is why the module walks the structure rather
than indexing fixed paths. These tests pin that behaviour, using payloads
shaped the way garminconnect actually returns them.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from ingest import garmin_login as gl


# ---------------------------------------------------------------------------
# The tolerant walker
# ---------------------------------------------------------------------------
def test_finds_a_key_at_the_top_level():
    assert gl._first({"score": 72}, "score") == 72


def test_finds_a_key_nested_in_a_wrapper():
    """Several endpoints wrap the payload in a single-key envelope."""
    payload = {"dailySleepDTO": {"sleepTimeSeconds": 27000, "overallSleepScore": 84}}
    assert gl._first(payload, "sleepTimeSeconds") == 27000
    assert gl._first(payload, "overallSleepScore") == 84


def test_finds_a_key_inside_a_list():
    payload = {"items": [{"other": 1}, {"vo2MaxValue": 54.0}]}
    assert gl._first(payload, "vo2MaxValue") == 54.0


def test_tries_alternative_key_names_in_order():
    """Field names drift between versions, so each lookup takes fallbacks."""
    assert gl._first({"sleepScore": 80}, "overallSleepScore", "sleepScore") == 80
    assert gl._first({"overallSleepScore": 90, "sleepScore": 80},
                     "overallSleepScore", "sleepScore") == 90


def test_missing_key_is_none_not_an_error():
    assert gl._first({"a": 1}, "nope") is None
    assert gl._first(None, "nope") is None
    assert gl._first([], "nope") is None


def test_null_values_are_skipped_rather_than_returned():
    """A present-but-null field must not shadow a real one deeper in."""
    payload = {"score": None, "inner": {"score": 61}}
    assert gl._first(payload, "score") == 61


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------
def test_seconds_convert_to_whole_minutes():
    assert gl._mins(27000) == 450          # 7.5 hours
    assert gl._mins(None) is None


def test_numeric_coercion_is_forgiving_but_not_silent():
    assert gl._int("48") == 48
    assert gl._int(48.6) == 49
    assert gl._int(None) is None
    assert gl._int("not a number") is None
    assert gl._num("61.5") == 61.5
    assert gl._num(None) is None


def test_sleep_onset_is_minutes_past_midnight():
    # 2026-11-01 23:15 UTC, in milliseconds as the library returns it.
    ms = int(datetime(2026, 11, 1, 23, 15, tzinfo=timezone.utc).timestamp() * 1000)
    assert gl._onset_minutes({"sleepStartTimestampLocal": ms}) == 23 * 60 + 15


def test_sleep_onset_handles_rubbish():
    assert gl._onset_minutes({}) is None
    assert gl._onset_minutes({"sleepStartTimestampLocal": "nonsense"}) is None


# ---------------------------------------------------------------------------
# One failing endpoint must not cost the rest of the day
# ---------------------------------------------------------------------------
class FakeApi:
    """Stands in for garminconnect. `broken` names endpoints that raise."""

    def __init__(self, broken: set[str] | None = None):
        self.broken = broken or set()

    def _maybe_fail(self, name: str):
        if name in self.broken:
            raise RuntimeError(f"{name} exploded")

    def get_stats(self, d):
        self._maybe_fail("stats")
        return {"totalSteps": 8200, "restingHeartRate": 48, "averageStressLevel": 31,
                "bodyBatteryHighestValue": 82, "bodyBatteryLowestValue": 22}

    def get_sleep_data(self, d):
        self._maybe_fail("sleep")
        return {"dailySleepDTO": {"sleepTimeSeconds": 27000, "deepSleepSeconds": 4200,
                                  "remSleepSeconds": 5700, "overallSleepScore": 84}}

    def get_hrv_data(self, d):
        self._maybe_fail("hrv")
        return {"hrvSummary": {"lastNightAvg": 61, "weeklyAvg": 59}}

    def get_training_readiness(self, d):
        self._maybe_fail("readiness")
        return [{"score": 72}]

    def get_training_status(self, d):
        self._maybe_fail("status")
        return {"trainingStatus": "maintaining", "acuteTrainingLoad": 310,
                "chronicTrainingLoad": 295}

    def get_max_metrics(self, d):
        self._maybe_fail("vo2")
        return [{"generic": {"vo2MaxValue": 54.0}}]


def test_a_full_day_maps_every_field():
    rows = gl.fetch_daily(FakeApi(), days=1)
    assert len(rows) == 1
    row = rows[0]

    assert row["day"] == date.today()
    assert row["source"] == "garmin_login"
    assert row["steps"] == 8200
    assert row["rhr"] == 48
    assert row["stress_avg"] == 31
    assert row["body_battery_max"] == 82
    assert row["body_battery_min"] == 22
    assert row["sleep_total_min"] == 450
    assert row["sleep_deep_min"] == 70
    assert row["sleep_rem_min"] == 95
    assert row["sleep_score"] == 84
    assert row["hrv_night"] == 61
    assert row["hrv_7d"] == 59
    assert row["readiness"] == 72
    assert row["training_status"] == "maintaining"
    assert row["acute_load"] == 310
    assert row["vo2max_run"] == 54.0


def test_the_login_route_covers_what_the_personal_tier_does_not():
    """Readiness, training status, load and VO2max are the whole reason this
    route exists. If these stop being fetched, the Personal API would be
    strictly better and this module would be pointless."""
    row = gl.fetch_daily(FakeApi(), days=1)[0]
    for field in ("readiness", "training_status", "acute_load", "chronic_load",
                  "vo2max_run"):
        assert field in row, f"{field} missing: the Personal tier cannot supply it"


def test_one_broken_endpoint_does_not_lose_the_others():
    """A missing HRV reading must not cost that night's sleep data."""
    rows = gl.fetch_daily(FakeApi(broken={"hrv"}), days=1)
    row = rows[0]
    assert "hrv_night" not in row
    assert row["sleep_score"] == 84
    assert row["steps"] == 8200


def test_every_endpoint_failing_yields_no_row_rather_than_an_empty_one():
    rows = gl.fetch_daily(
        FakeApi(broken={"stats", "sleep", "hrv", "readiness", "status", "vo2"}),
        days=1,
    )
    assert rows == [] or all(
        set(r) <= {"day", "source"} for r in rows
    )


def test_a_range_of_days_produces_a_row_each():
    rows = gl.fetch_daily(FakeApi(), days=5)
    assert len(rows) == 5
    assert len({r["day"] for r in rows}) == 5
    assert max(r["day"] for r in rows) == date.today()


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------
class ActivityApi:
    def get_activities_by_date(self, start, end):
        return [
            {   # a normal run
                "activityId": 123,
                "activityType": {"typeKey": "running"},
                "startTimeLocal": "2026-10-11 11:11:40",
                "duration": 2939, "movingDuration": 2817,
                "distance": 8486.2, "averageHR": 150, "maxHR": 172,
                "elevationGain": 65, "maxSpeed": 5.48,
            },
            {   # the junk row pattern seen in real data
                "activityId": 456,
                "activityType": {"typeKey": "indoor_cardio"},
                "startTimeLocal": "2026-10-09 23:26:11",
                "duration": 4, "movingDuration": 4, "distance": 0,
            },
            {   # no id, must be dropped
                "activityType": {"typeKey": "running"},
                "startTimeLocal": "2026-10-01 09:00:00",
                "duration": 1800,
            },
        ]


def test_activities_map_and_normalise_sport():
    rows = gl.fetch_activities(ActivityApi(), days=90)
    assert len(rows) == 2                      # the id-less one is dropped

    run = next(r for r in rows if r["source_id"] == "123")
    assert run["sport"] == "run"
    assert run["sport_raw"] == "running"
    assert run["duration_s"] == 2817           # moving, not elapsed
    assert run["elapsed_s"] == 2939
    assert run["distance_m"] == 8486.2
    assert run["avg_hr"] == 150
    assert run["start_at"] == "2026-10-11T11:11:40"
    assert run["is_valid"] is True
    assert run["source"] == "garmin"


def test_a_four_second_activity_is_marked_invalid_not_dropped():
    """Same rule as the Strava path: flagged, so it stays auditable."""
    rows = gl.fetch_activities(ActivityApi(), days=90)
    junk = next(r for r in rows if r["source_id"] == "456")
    assert junk["is_valid"] is False
    assert "below" in junk["invalid_reason"]


def test_no_activities_is_an_empty_list_not_an_error():
    class Empty:
        def get_activities_by_date(self, s, e):
            return []
    assert gl.fetch_activities(Empty(), days=30) == []


# ---------------------------------------------------------------------------
# Body composition
# ---------------------------------------------------------------------------
def test_body_composition_converts_grams_to_kilograms():
    ms = int(datetime(2026, 10, 20, 7, 30, tzinfo=timezone.utc).timestamp() * 1000)

    class BodyApi:
        def get_body_composition(self, s, e):
            return {"dateWeightList": [
                {"date": ms, "weight": 66700, "bodyFat": 14.1, "muscleMass": 32000},
            ]}

    rows = gl.fetch_body(BodyApi(), days=90)
    assert len(rows) == 1
    assert rows[0]["weight_kg"] == 66.7
    assert rows[0]["body_fat_pct"] == 14.1
    assert rows[0]["muscle_mass_kg"] == 32.0
    assert rows[0]["source"] == "garmin"


def test_body_composition_skips_entries_with_no_weight():
    class BodyApi:
        def get_body_composition(self, s, e):
            return {"dateWeightList": [{"date": 1, "bodyFat": 14.1}]}
    assert gl.fetch_body(BodyApi(), days=90) == []


# ---------------------------------------------------------------------------
# Gear
# ---------------------------------------------------------------------------
class GearApi:
    """Garmin keeps distance on a separate per-item stats call."""
    profile_id = 12345

    def get_gear_list(self, **kw):
        return [
            {"uuid": "g1", "gearTypeName": "Shoes", "displayName": "vaporflys",
             "makeName": "Nike", "modelName": "Vaporfly", "gearStatusName": "active"},
            {"uuid": "g2", "gearTypeName": "Shoes", "displayName": "Evo SL",
             "makeName": "Adidas", "modelName": "Evo SL", "gearStatusName": "active",
             "maximumMeters": 500000},
            {"uuid": "g3", "gearTypeName": "Bike", "displayName": "Propel",
             "makeName": "Giant", "gearStatusName": "retired"},
            {"uuid": "g4", "gearTypeName": "Other", "displayName": "Ignore me"},
            {"gearTypeName": "Shoes", "displayName": "No uuid"},
        ]

    def get_gear_stats(self, uuid):
        return {"g1": {"totalDistance": 331481.0},
                "g2": {"totalDistance": 210124.0},
                "g3": {"totalDistance": 1204442.0}}.get(uuid, {})


def test_gear_comes_through_with_distance():
    """Garmin tracks gear too, so dropping Strava does not cost shoe mileage."""
    rows = gl.fetch_gear(GearApi())
    by_id = {r["source_id"]: r for r in rows}

    assert set(by_id) == {"g1", "g2", "g3"}      # unknown type and id-less dropped
    assert by_id["g1"]["gear_type"] == "shoe"
    assert by_id["g1"]["distance_m"] == 331481.0
    assert by_id["g1"]["brand"] == "Nike"
    assert by_id["g3"]["gear_type"] == "bike"
    assert by_id["g3"]["retired"] is True


def test_carbon_racers_get_a_shorter_replacement_threshold():
    rows = {r["source_id"]: r for r in gl.fetch_gear(GearApi())}
    assert rows["g1"]["retire_at_m"] == gl.SHOE_RETIRE_M["vaporfly"]
    assert rows["g1"]["retire_at_m"] < gl.SHOE_RETIRE_M["DEFAULT"]


def test_a_limit_set_in_garmin_wins_over_our_default():
    rows = {r["source_id"]: r for r in gl.fetch_gear(GearApi())}
    assert rows["g2"]["retire_at_m"] == 500000


def test_bikes_get_no_replacement_threshold():
    rows = {r["source_id"]: r for r in gl.fetch_gear(GearApi())}
    assert rows["g3"]["retire_at_m"] is None


def test_gear_falls_back_to_the_profile_endpoint():
    """Older library versions expose get_gear(profileNumber) instead."""
    class Fallback:
        profile_id = 999

        def get_gear_list(self, **kw):
            raise RuntimeError("not available")

        def get_gear(self, profile_number):
            assert profile_number == "999"
            return [{"uuid": "x", "gearTypeName": "Shoes", "displayName": "Pegasus"}]

        def get_gear_stats(self, uuid):
            return {"totalDistance": 60825.0}

    rows = gl.fetch_gear(Fallback())
    assert len(rows) == 1
    assert rows[0]["distance_m"] == 60825.0


def test_no_gear_is_an_empty_list():
    class NoGear:
        def get_gear_list(self, **kw):
            return []
    assert gl.fetch_gear(NoGear()) == []


def test_missing_credentials_raise_a_clear_error():
    from engine.ti.config import Config
    cfg = Config(supabase_url="x", supabase_service_key="y", user_id="z")
    with pytest.raises(gl.LoginRouteUnavailable, match="GARMIN_EMAIL"):
        gl.client(cfg)


# ---------------------------------------------------------------------------
# The library surface we depend on
# ---------------------------------------------------------------------------
def test_garminconnect_exposes_every_method_we_call():
    """Pins the library surface.

    garminconnect is unofficial and renames things between releases. Without
    this, a version bump would fail at 02:12 inside a workflow with a
    swallowed AttributeError on one endpoint, which is exactly the kind of
    silent partial failure the fetch loop is designed to tolerate. Better to
    break here.

    Note 0.2.25 was unusable: it pulled withings-sync, which does not build.
    """
    garminconnect = pytest.importorskip("garminconnect")
    Garmin = garminconnect.Garmin

    required = [
        "login",
        "get_stats",                 # steps, resting HR, stress, body battery
        "get_sleep_data",
        "get_hrv_data",
        "get_training_readiness",    # not available on the Personal tier
        "get_training_status",       # not available on the Personal tier
        "get_max_metrics",           # VO2max, not available on the Personal tier
        "get_body_composition",
        "get_activities_by_date",
    ]
    missing = [m for m in required if not hasattr(Garmin, m)]
    assert not missing, f"garminconnect no longer exposes: {missing}"
