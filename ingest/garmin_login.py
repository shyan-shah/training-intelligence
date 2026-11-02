"""Garmin ingest via the login route, using the `garminconnect` library.

This is the PRIMARY Garmin source. It signs in with the same email and
password as the Garmin Connect app and reads everything the app can see:
sleep, HRV, resting HR, body battery, stress, steps, body composition,
activities, and the training metrics the official Personal tier does not
expose at all (readiness, training status, acute and chronic load, VO2max).

Why this rather than the official Personal API:

  * It needs no developer account, no key approval, and no endpoint guessing.
    The official Health API spec sits behind the developer portal, so those
    paths cannot be verified until a key is issued.
  * It covers strictly more fields. Readiness, training status and VO2max are
    not available on the Personal tier at all.

What it costs:

  * It is unofficial. Garmin can change it, and there is nobody to ask.
  * Repeated logins from a CI address can trigger an MFA or captcha
    challenge, which cannot be answered headlessly. If that happens the run
    fails loudly, sync_status records it, and the page shows the source as
    stale rather than quietly serving old numbers.
  * Your password lives in GitHub Actions secrets.

`ingest/garmin_personal.py` remains as the official alternative. Set
GARMIN_PERSONAL_TOKEN and it runs as well; leave it unset and this is the
only Garmin source.

Response shapes are not a stable contract, so every field is pulled with a
tolerant walker rather than a fixed path, and one failing endpoint never
abandons the rest of the day.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from engine.ti.config import Config
from engine.ti.db import Db
from engine.ti.validate import validate_activity

from . import sports

log = logging.getLogger(__name__)


class LoginRouteUnavailable(RuntimeError):
    """Raised when the login route cannot be used at all."""


def client(cfg: Config):
    if not (cfg.garmin_email and cfg.garmin_password):
        raise LoginRouteUnavailable("GARMIN_EMAIL / GARMIN_PASSWORD not set")
    try:
        from garminconnect import Garmin
    except ImportError as e:
        raise LoginRouteUnavailable("garminconnect is not installed") from e

    try:
        api = Garmin(cfg.garmin_email, cfg.garmin_password)
        api.login()
        return api
    except Exception as e:                      # the library raises many types
        raise LoginRouteUnavailable(
            f"login failed ({type(e).__name__}). If Garmin is asking for MFA or a "
            "captcha, that cannot be answered from CI."
        ) from e


# ---------------------------------------------------------------------------
# Tolerant extraction
# ---------------------------------------------------------------------------
def _first(raw: object, *keys: str) -> Any:
    """First non-null value for any of `keys`, anywhere in the structure.

    The login route's payloads nest differently between endpoints and change
    shape between library versions, so this walks rather than assumes.
    """
    for key in keys:
        found = _walk(raw, key)
        if found is not None:
            return found
    return None


def _walk(raw: object, key: str) -> Any:
    if isinstance(raw, dict):
        if raw.get(key) is not None:
            return raw[key]
        for value in raw.values():
            found = _walk(value, key)
            if found is not None:
                return found
    elif isinstance(raw, list):
        for item in raw:
            found = _walk(item, key)
            if found is not None:
                return found
    return None


def _try(label: str, day: str, fn: Callable[[], Any]) -> Any:
    """Call one endpoint, swallowing its failure.

    A missing HRV reading on one night must not cost that night's sleep data.
    """
    try:
        return fn()
    except Exception as e:
        log.debug("%s unavailable for %s: %s", label, day, type(e).__name__)
        return None


def _mins(seconds: Any) -> int | None:
    return None if seconds is None else int(seconds) // 60


def _int(v: Any) -> int | None:
    try:
        return None if v is None else int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _num(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _onset_minutes(sleep: Any) -> int | None:
    """Sleep onset as minutes past midnight local, for the regularity SD."""
    ts = _first(sleep, "sleepStartTimestampLocal", "sleepStartTimestampGMT")
    if ts is None:
        return None
    try:
        # The library returns milliseconds since epoch.
        when = datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
    return when.hour * 60 + when.minute


# ---------------------------------------------------------------------------
# Daily wellness
# ---------------------------------------------------------------------------
def fetch_daily(api, days: int = 90) -> list[dict]:
    """One `garmin_daily` row per day, with everything the app can see."""
    rows: list[dict] = []

    for offset in range(days):
        day = date.today() - timedelta(days=offset)
        iso = day.isoformat()
        values: dict[str, Any] = {"day": day, "source": "garmin_login"}

        stats = _try("stats", iso, lambda: api.get_stats(iso))
        if stats:
            values.update({
                "steps": _int(_first(stats, "totalSteps", "steps")),
                "rhr": _int(_first(stats, "restingHeartRate")),
                "stress_avg": _int(_first(stats, "averageStressLevel")),
                "body_battery_max": _int(_first(stats, "bodyBatteryHighestValue",
                                                "bodyBatteryMostRecentValue")),
                "body_battery_min": _int(_first(stats, "bodyBatteryLowestValue")),
            })

        sleep = _try("sleep", iso, lambda: api.get_sleep_data(iso))
        if sleep:
            values.update({
                "sleep_score": _int(_first(sleep, "overallSleepScore", "sleepScore", "value")),
                "sleep_total_min": _mins(_first(sleep, "sleepTimeSeconds")),
                "sleep_deep_min": _mins(_first(sleep, "deepSleepSeconds")),
                "sleep_rem_min": _mins(_first(sleep, "remSleepSeconds")),
                "sleep_onset_min": _onset_minutes(sleep),
            })

        hrv = _try("hrv", iso, lambda: api.get_hrv_data(iso))
        if hrv:
            values.update({
                "hrv_night": _num(_first(hrv, "lastNightAvg", "lastNight5MinHigh")),
                "hrv_7d": _num(_first(hrv, "weeklyAvg")),
            })

        # Fields the official Personal tier does not expose at all.
        readiness = _try("readiness", iso, lambda: api.get_training_readiness(iso))
        if readiness:
            values["readiness"] = _int(_first(readiness, "score"))

        status = _try("training status", iso, lambda: api.get_training_status(iso))
        if status:
            values.update({
                "training_status": _first(status, "trainingStatus", "trainingStatusKey"),
                "acute_load": _num(_first(status, "acuteTrainingLoad")),
                "chronic_load": _num(_first(status, "chronicTrainingLoad",
                                            "dailyTrainingLoadChronic")),
            })

        vo2 = _try("vo2max", iso, lambda: api.get_max_metrics(iso))
        if vo2:
            values.update({
                "vo2max_run": _num(_first(vo2, "vo2MaxValue", "vo2MaxPreciseValue")),
                "vo2max_bike": _num(_first(vo2, "cyclingVo2Max")),
            })

        # Only keep a day that actually carries something.
        if len([k for k in values if k not in ("day", "source")]) > 0:
            rows.append({k: v for k, v in values.items()
                         if v is not None or k in ("day", "source")})

    return rows


# ---------------------------------------------------------------------------
# Body composition
# ---------------------------------------------------------------------------
def fetch_body(api, days: int = 90) -> list[dict]:
    end = date.today()
    start = end - timedelta(days=days)
    raw = _try("body composition", start.isoformat(),
               lambda: api.get_body_composition(start.isoformat(), end.isoformat()))
    if not raw:
        return []

    entries = raw.get("dateWeightList") if isinstance(raw, dict) else None
    if not entries:
        return []

    rows: list[dict] = []
    for e in entries:
        ts = _first(e, "date", "timestampGMT")
        weight_g = _first(e, "weight")
        if ts is None or weight_g is None:
            continue
        try:
            measured = datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            continue
        rows.append({
            "measured_at": measured,
            "weight_kg": round(float(weight_g) / 1000.0, 2),
            "body_fat_pct": _num(_first(e, "bodyFat")),
            "muscle_mass_kg": (round(float(_first(e, "muscleMass")) / 1000.0, 2)
                               if _first(e, "muscleMass") else None),
            "source": "garmin",
        })
    return rows


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------
def fetch_activities(api, days: int = 90) -> list[dict]:
    end = date.today()
    start = end - timedelta(days=days)
    raw = _try("activities", start.isoformat(),
               lambda: api.get_activities_by_date(start.isoformat(), end.isoformat()))
    if not raw:
        return []

    rows: list[dict] = []
    for a in raw:
        activity_id = _first(a, "activityId")
        started = _first(a, "startTimeLocal", "startTimeGMT")
        if activity_id is None or not started:
            continue

        type_key = _first(a, "typeKey") or ""
        sport = sports.from_garmin(type_key)
        moving = _int(_first(a, "movingDuration")) or _int(_first(a, "duration")) or 0
        elapsed = _int(_first(a, "elapsedDuration", "duration")) or moving
        distance = _num(_first(a, "distance"))
        max_speed = _num(_first(a, "maxSpeed"))

        v = validate_activity(
            sport=sport,
            duration_s=moving,
            elapsed_s=elapsed,
            distance_m=distance,
            max_speed_kmh=(max_speed * 3.6) if max_speed else None,
            avg_hr=_int(_first(a, "averageHR")),
        )
        reason = "; ".join(filter(None, [v.reason, *v.warnings])) or None

        rows.append({
            "source": "garmin",
            "source_id": str(activity_id),
            "sport": sport,
            "sport_raw": type_key,
            "start_at": str(started).replace(" ", "T"),
            "duration_s": moving,
            "elapsed_s": elapsed,
            "distance_m": distance,
            "avg_hr": _int(_first(a, "averageHR")),
            "max_hr": _int(_first(a, "maxHR")),
            "avg_power": _num(_first(a, "avgPower", "averagePower")),
            "np": _num(_first(a, "normPower", "normalizedPower")),
            "elevation_m": _num(_first(a, "elevationGain")),
            "is_valid": v.is_valid,
            "invalid_reason": reason,
        })
    return rows


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def ingest(cfg: Config, db: Db, days: int = 90, strict: bool = True) -> dict[str, int]:
    """Pull everything the login route can see.

    `strict` False keeps the old top-up behaviour: a failure is recorded and
    swallowed, which is what you want when the Personal API is the backbone
    and this only fills five columns. With the login route as the primary
    source, a silent failure would leave the page quietly empty, so the
    default raises.
    """
    try:
        api = client(cfg)
    except LoginRouteUnavailable as e:
        db.mark_sync("garmin_login", ok=False, error=str(e))
        if strict:
            raise
        log.warning("garmin login route unavailable: %s", e)
        return {}

    try:
        counts = {
            "garmin_daily": db.upsert("garmin_daily", fetch_daily(api, days),
                                      on_conflict="user_id,day"),
            "garmin_body": db.upsert("garmin_body", fetch_body(api, days),
                                     on_conflict="user_id,measured_at,source"),
            "activities": db.upsert("activities", fetch_activities(api, days),
                                    on_conflict="user_id,source,source_id"),
        }
    except Exception as e:
        db.mark_sync("garmin_login", ok=False, error=f"{type(e).__name__}: {e}"[:400])
        raise

    db.mark_sync("garmin_login", ok=True)
    log.info("garmin login route: %s", counts)
    return counts
