"""Garmin ingest via the official Health API (Personal tier). The backbone.

IMPORTANT, READ BEFORE FIRST RUN
--------------------------------
The endpoint paths and field names below are NOT verified. Garmin's Health API
spec sits behind the developer portal at

    developer.garmin.com/gc-developer-program/personal/swagger-docs/

and is not public, so the map in ENDPOINTS and the per-summary field mappings
are the shape this code expects, not a confirmed contract. Check each against
the swagger when the Personal key is issued and correct this one block; the
rest of the module and everything downstream reads from it.

Two further things the swagger decides:

  * Push vs pull. The Health API is push-oriented (Garmin POSTs to a webhook).
    If the backfill/pull endpoints are not available on the Personal tier,
    this module needs a webhook receiver instead of a scheduled pull, which
    changes the Actions workflow but not the schema.
  * Rate and backfill limits, which cap how much of the 90-day history can be
    requested in one run.

Fields the Personal tier does NOT expose are handled in garmin_login.py.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from engine.ti.config import Config
from engine.ti.db import Db
from engine.ti.validate import validate_activity

from . import sports

log = logging.getLogger(__name__)

BASE = "https://apis.garmin.com/wellness-api/rest"

# --- TO VERIFY AGAINST THE SWAGGER ----------------------------------------
ENDPOINTS = {
    "sleep": "/sleeps",
    "hrv": "/hrvSummary",
    "daily": "/dailies",
    "stress": "/stressDetails",
    "body": "/bodyComps",
    "activities": "/activities",
}
# Maximum span one request may cover. Garmin typically caps this at 24h for
# summary endpoints; raise it only if the swagger allows.
MAX_SPAN_DAYS = 1
# ---------------------------------------------------------------------------


def _get(cfg: Config, path: str, start: datetime, end: datetime) -> list[dict]:
    r = httpx.get(
        f"{BASE}{path}",
        timeout=60.0,
        headers={"Authorization": f"Bearer {cfg.garmin_personal_token}"},
        params={
            "uploadStartTimeInSeconds": int(start.timestamp()),
            "uploadEndTimeInSeconds": int(end.timestamp()),
        },
    )
    if r.status_code == 401:
        raise RuntimeError("Garmin Personal token rejected (401). Regenerate the key.")
    if r.status_code == 429:
        raise RuntimeError("Garmin rate limit hit; back off and retry next run")
    if r.status_code >= 400:
        raise RuntimeError(f"Garmin GET {path} failed: HTTP {r.status_code}")
    body = r.json()
    return body if isinstance(body, list) else [body]


def _day_of(summary: dict) -> date | None:
    for key in ("calendarDate", "summaryDate"):
        if summary.get(key):
            return date.fromisoformat(summary[key][:10])
    ts = summary.get("startTimeInSeconds")
    if ts:
        return datetime.fromtimestamp(ts, tz=timezone.utc).date()
    return None


def _merge(into: dict[date, dict], day: date | None, values: dict[str, Any]) -> None:
    if day is None:
        return
    row = into.setdefault(day, {"day": day, "source": "garmin_personal"})
    row.update({k: v for k, v in values.items() if v is not None})


def fetch_daily(cfg: Config, days: int = 90) -> list[dict]:
    """Build one `garmin_daily` row per day from the wellness summaries."""
    out: dict[date, dict] = {}
    end = datetime.now(timezone.utc)

    for offset in range(days):
        window_end = end - timedelta(days=offset)
        window_start = window_end - timedelta(days=MAX_SPAN_DAYS)

        for kind in ("sleep", "hrv", "daily"):
            try:
                for s in _get(cfg, ENDPOINTS[kind], window_start, window_end):
                    day = _day_of(s)
                    if kind == "sleep":
                        _merge(out, day, {
                            "sleep_score": _nested(s, "overallSleepScore", "value"),
                            "sleep_total_min": _secs_to_min(s.get("durationInSeconds")),
                            "sleep_deep_min": _secs_to_min(s.get("deepSleepDurationInSeconds")),
                            "sleep_rem_min": _secs_to_min(s.get("remSleepInSeconds")),
                            "sleep_onset_min": _onset_minutes(s),
                        })
                    elif kind == "hrv":
                        _merge(out, day, {
                            "hrv_night": s.get("lastNightAvg") or s.get("weeklyAvg"),
                        })
                    else:
                        _merge(out, day, {
                            "rhr": s.get("restingHeartRateInBeatsPerMinute"),
                            "steps": s.get("steps"),
                            "stress_avg": s.get("averageStressLevel"),
                            "body_battery_max": s.get("bodyBatteryChargedValue"),
                            "body_battery_min": s.get("bodyBatteryDrainedValue"),
                        })
            except RuntimeError as e:
                # One bad window must not abandon the whole backfill.
                log.warning("garmin %s window %s failed: %s", kind, window_end.date(), e)

    return sorted(out.values(), key=lambda r: r["day"])


def _nested(d: dict, *path: str) -> Any:
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def _secs_to_min(v: Any) -> int | None:
    return None if v is None else int(v) // 60


def _onset_minutes(s: dict) -> int | None:
    """Sleep onset as minutes past midnight local, for the regularity SD."""
    ts = s.get("startTimeInSeconds")
    offset = s.get("startTimeOffsetInSeconds") or 0
    if ts is None:
        return None
    local = datetime.fromtimestamp(int(ts) + int(offset), tz=timezone.utc)
    return local.hour * 60 + local.minute


def fetch_body(cfg: Config, days: int = 90) -> list[dict]:
    rows: list[dict] = []
    end = datetime.now(timezone.utc)
    for offset in range(days):
        window_end = end - timedelta(days=offset)
        try:
            for s in _get(cfg, ENDPOINTS["body"], window_end - timedelta(days=1), window_end):
                ts = s.get("measurementTimeInSeconds")
                if not ts:
                    continue
                rows.append({
                    "measured_at": datetime.fromtimestamp(ts, tz=timezone.utc),
                    "weight_kg": _grams_to_kg(s.get("weightInGrams")),
                    "body_fat_pct": s.get("bodyFatInPercent"),
                    "muscle_mass_kg": _grams_to_kg(s.get("muscleMassInGrams")),
                    "source": "garmin",
                })
        except RuntimeError as e:
            log.warning("garmin body window %s failed: %s", window_end.date(), e)
    return rows


def _grams_to_kg(v: Any) -> float | None:
    return None if v is None else round(float(v) / 1000.0, 2)


def fetch_activities(cfg: Config, days: int = 90) -> list[dict]:
    rows: list[dict] = []
    end = datetime.now(timezone.utc)
    for offset in range(days):
        window_end = end - timedelta(days=offset)
        try:
            batch = _get(cfg, ENDPOINTS["activities"], window_end - timedelta(days=1), window_end)
        except RuntimeError as e:
            log.warning("garmin activities window %s failed: %s", window_end.date(), e)
            continue

        for a in batch:
            sport = sports.from_garmin(a.get("activityType"))
            moving = int(a.get("durationInSeconds") or 0)
            distance = a.get("distanceInMeters")
            max_speed_kmh = (float(a["maxSpeedInMetersPerSecond"]) * 3.6
                             if a.get("maxSpeedInMetersPerSecond") else None)
            v = validate_activity(sport, moving, moving, distance, max_speed_kmh,
                                  a.get("averageHeartRateInBeatsPerMinute"))
            reason = "; ".join(filter(None, [v.reason, *v.warnings])) or None
            start_ts = a.get("startTimeInSeconds")
            rows.append({
                "source": "garmin",
                "source_id": str(a.get("summaryId") or a.get("activityId")),
                "sport": sport,
                "sport_raw": a.get("activityType"),
                "start_at": datetime.fromtimestamp(int(start_ts), tz=timezone.utc) if start_ts else None,
                "duration_s": moving,
                "elapsed_s": moving,
                "distance_m": distance,
                "avg_hr": a.get("averageHeartRateInBeatsPerMinute"),
                "max_hr": a.get("maxHeartRateInBeatsPerMinute"),
                "avg_power": a.get("averagePowerInWatts"),
                "np": a.get("normalizedPowerInWatts"),
                "elevation_m": a.get("totalElevationGainInMeters"),
                "is_valid": v.is_valid,
                "invalid_reason": reason,
            })
    return [r for r in rows if r["start_at"] and r["source_id"]]


def ingest(cfg: Config, db: Db, days: int = 90) -> dict[str, int]:
    if not cfg.garmin_personal_token:
        raise RuntimeError("GARMIN_PERSONAL_TOKEN is not set")
    counts = {
        "garmin_daily": db.upsert("garmin_daily", fetch_daily(cfg, days), on_conflict="user_id,day"),
        "garmin_body": db.upsert("garmin_body", fetch_body(cfg, days),
                                 on_conflict="user_id,measured_at,source"),
        "activities": db.upsert("activities", fetch_activities(cfg, days),
                                on_conflict="user_id,source,source_id"),
    }
    db.mark_sync("garmin_personal", ok=True)
    return counts
