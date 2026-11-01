"""Validation tests built on the junk rows found in the real Strava history."""
from ti.validate import MAX_SPEED_KMH, MIN_DURATION_S, validate_activity


def test_the_audited_four_second_row_is_rejected():
    """Real record: "Night Workout", 2026-10-09, 4s elapsed, zero distance."""
    v = validate_activity("other", duration_s=4, elapsed_s=4, distance_m=0.0)
    assert v.is_valid is False
    assert "below" in (v.reason or "")


def test_the_audited_stuck_timer_is_warned_not_rejected():
    """Real record: "Night Workout", 2026-09-22, elapsed 175,726s against
    moving 4,678s. The session happened, so it counts, but the elapsed figure
    must not be trusted."""
    v = validate_activity("other", duration_s=4678, elapsed_s=175726, distance_m=3434.3)
    assert v.is_valid is True
    assert any("timer left running" in w for w in v.warnings)


def test_the_audited_walk_gps_spike_is_warned():
    """Real record: "Afternoon Walk", 2026-09-26, max speed 48.85 km/h."""
    v = validate_activity("walk", duration_s=1343, elapsed_s=1472,
                          distance_m=1739.8, max_speed_kmh=48.85)
    assert v.is_valid is True
    assert any("GPS spike" in w for w in v.warnings)
    assert any("best efforts" in w for w in v.warnings)


def test_the_audited_ride_gps_spike_is_warned():
    """Real record: "Lunch Ride", 2026-08-15, 9.82km in 3132s (11.3 km/h
    average) with a max speed of 80.98 km/h. That sits under the 90 km/h bike
    ceiling, so only the ratio check catches it."""
    v = validate_activity("bike", duration_s=3132, elapsed_s=3772,
                          distance_m=9819.1, max_speed_kmh=80.98)
    assert v.is_valid is True
    assert any("GPS spike" in w for w in v.warnings)
    assert any("x the" in w for w in v.warnings)


def test_realistic_rides_do_not_trip_the_ratio_check():
    """Audited clean records: a Zwift ride at 26.5 km/h average peaking at
    48.8 (1.8x), and a road ride at 19.8 average peaking at 49.5 (2.5x)."""
    zwift = validate_activity("bike", duration_s=1768, elapsed_s=2894,
                              distance_m=13009.8, max_speed_kmh=48.816)
    road = validate_activity("bike", duration_s=2926, elapsed_s=7271,
                             distance_m=16133.2, max_speed_kmh=49.536)
    assert zwift.warnings == []
    assert road.warnings == []


def test_a_normal_session_passes_clean():
    """Real record: "Lunch Run", 2026-10-11, 8.49km in 2817s moving."""
    v = validate_activity("run", duration_s=2817, elapsed_s=2939,
                          distance_m=8486.2, max_speed_kmh=19.73, avg_hr=150,
                          max_hr_setting=207)
    assert v.is_valid is True
    assert v.warnings == []
    assert v.reason is None


def test_duration_floor_boundary():
    assert validate_activity("run", MIN_DURATION_S - 1, 100, 100.0).is_valid is False
    assert validate_activity("run", MIN_DURATION_S, 100, 100.0).is_valid is True


def test_impossible_heart_rate_is_rejected():
    assert validate_activity("run", 1800, 1800, 5000.0, avg_hr=300).is_valid is False
    assert validate_activity("run", 1800, 1800, 5000.0, avg_hr=10).is_valid is False


def test_avg_hr_above_configured_max_is_a_warning_only():
    v = validate_activity("run", 1800, 1800, 5000.0, avg_hr=210, max_hr_setting=207)
    assert v.is_valid is True
    assert any("above configured max HR" in w for w in v.warnings)


def test_negative_distance_is_rejected():
    assert validate_activity("run", 1800, 1800, -5.0).is_valid is False


def test_missing_duration_is_rejected_not_assumed():
    assert validate_activity("run", None, None, None).is_valid is False


def test_speed_ceilings_differ_by_sport():
    assert MAX_SPEED_KMH["run"] < MAX_SPEED_KMH["bike"]
    v = validate_activity("run", 1800, 1800, 5000.0, max_speed_kmh=40.0)
    assert any("GPS spike" in w for w in v.warnings)
    # 5km in 1800s is 10 km/h, so 40 km/h is 4x the average and trips the
    # ratio check even on a bike. Use a realistic ride to isolate the ceiling.
    v2 = validate_activity("bike", 1800, 1800, 15000.0, max_speed_kmh=40.0)
    assert v2.warnings == []
