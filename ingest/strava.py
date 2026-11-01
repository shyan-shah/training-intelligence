"""Strava ingest via OAuth refresh token.

Pulls activities, normalises them, validates them and writes to `activities`.
Also syncs gear so the shoe mileage alert has something to read.

Rate limits: Strava allows 100 requests per 15 minutes and 1000 per day on the
default tier. A 90-day backfill at 200 activities per page is 1-2 requests, so
this stays well inside them, but the page size is kept high deliberately.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from engine.ti.config import Config
from engine.ti.db import Db
from engine.ti.validate import validate_activity

from . import sports

log = logging.getLogger(__name__)

TOKEN_URL = "https://www.strava.com/oauth/token"
API = "https://www.strava.com/api/v3"
PER_PAGE = 200


def _access_token(cfg: Config) -> tuple[str, datetime]:
    r = httpx.post(TOKEN_URL, timeout=30.0, data={
        "client_id": cfg.strava_client_id,
        "client_secret": cfg.strava_client_secret,
        "grant_type": "refresh_token",
        "refresh_token": cfg.strava_refresh_token,
    })
    if r.status_code >= 400:
        raise RuntimeError(f"Strava token refresh failed: HTTP {r.status_code}")
    body = r.json()
    expires = datetime.fromtimestamp(body["expires_at"], tz=timezone.utc)
    return body["access_token"], expires


def _get(token: str, path: str, **params) -> list | dict:
    r = httpx.get(f"{API}{path}", timeout=60.0, params=params,
                  headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 429:
        raise RuntimeError("Strava rate limit hit; back off and retry next run")
    if r.status_code >= 400:
        raise RuntimeError(f"Strava GET {path} failed: HTTP {r.status_code}")
    return r.json()


def _to_row(a: dict) -> dict:
    sport = sports.from_strava(a.get("sport_type") or a.get("type"))
    moving = int(a.get("moving_time") or 0)
    elapsed = int(a.get("elapsed_time") or 0)
    distance = float(a.get("distance") or 0.0) or None

    max_speed_kmh = (float(a["max_speed"]) * 3.6) if a.get("max_speed") else None
    avg_pace = None
    if distance and moving:
        avg_pace = moving / (distance / 1000.0)

    v = validate_activity(
        sport=sport,
        duration_s=moving,
        elapsed_s=elapsed,
        distance_m=distance,
        max_speed_kmh=max_speed_kmh,
        avg_hr=int(a["average_heartrate"]) if a.get("average_heartrate") else None,
    )

    reason = v.reason
    if v.warnings:
        reason = "; ".join(filter(None, [reason, *v.warnings]))

    return {
        "source": "strava",
        "source_id": str(a["id"]),
        "sport": sport,
        "sport_raw": a.get("sport_type") or a.get("type"),
        "start_at": a["start_date"],
        "duration_s": moving,
        "elapsed_s": elapsed,
        "distance_m": distance,
        "avg_hr": int(a["average_heartrate"]) if a.get("average_heartrate") else None,
        "max_hr": int(a["max_heartrate"]) if a.get("max_heartrate") else None,
        "avg_power": float(a["average_watts"]) if a.get("average_watts") else None,
        "np": float(a["weighted_average_watts"]) if a.get("weighted_average_watts") else None,
        "avg_pace": avg_pace,
        "elevation_m": float(a["total_elevation_gain"]) if a.get("total_elevation_gain") else None,
        "is_valid": v.is_valid,
        "invalid_reason": reason,
    }


def ingest_activities(cfg: Config, db: Db, days: int = 90) -> int:
    token, expires = _access_token(cfg)
    after = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    rows: list[dict] = []
    page = 1
    while True:
        batch = _get(token, "/athlete/activities", after=after, per_page=PER_PAGE, page=page)
        if not batch:
            break
        rows.extend(_to_row(a) for a in batch)
        if len(batch) < PER_PAGE:
            break
        page += 1

    n = db.upsert("activities", rows, on_conflict="user_id,source,source_id")
    db.mark_sync("strava", ok=True, token_expires_at=expires)
    log.info("strava: %d activities over %d days", n, days)
    return n


# Replacement thresholds in metres. Carbon-plated racers wear out sooner than
# daily trainers, which is why this is per-model rather than one number.
SHOE_RETIRE_M = {"vaporfly": 350_000, "alphafly": 350_000, "pro": 400_000,
                 "zoom fly": 650_000, "DEFAULT": 700_000}


def _retire_at(model: str | None, name: str | None) -> int:
    hay = f"{model or ''} {name or ''}".lower()
    for key, limit in SHOE_RETIRE_M.items():
        if key != "DEFAULT" and key in hay:
            return limit
    return SHOE_RETIRE_M["DEFAULT"]


def ingest_gear(cfg: Config, db: Db) -> int:
    token, _ = _access_token(cfg)
    athlete = _get(token, "/athlete")
    rows: list[dict] = []
    for kind, items in (("shoe", athlete.get("shoes") or []), ("bike", athlete.get("bikes") or [])):
        for g in items:
            rows.append({
                "source_id": str(g["id"]),
                "gear_type": kind,
                "name": g.get("name"),
                "brand": g.get("brand_name"),
                "model_name": g.get("model_name"),
                "distance_m": float(g.get("distance") or 0.0),
                "retired": bool(g.get("retired")),
                "retire_at_m": _retire_at(g.get("model_name"), g.get("name")) if kind == "shoe" else None,
            })
    return db.upsert("gear", rows, on_conflict="user_id,source_id")
