"""Garmin ingest via the login route. Top-up only.

This fills the five fields the Personal tier does not expose: training
readiness, training status, acute load, chronic load and VO2max. It uses the
unofficial login route through the `garminconnect` library.

Design rule: this module may fail without consequence. Its token dies roughly
every 30 days, and when it does, only those five columns go null. Nothing
calls it on the critical path, the nightly job treats a failure as a warning,
and the page shows how many days of token life are left with a warning at
five. That is the whole point of keeping the Personal API as the backbone.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from engine.ti.config import Config
from engine.ti.db import Db

log = logging.getLogger(__name__)

# Observed lifetime of a login-route session before re-auth is needed.
TOKEN_LIFETIME_DAYS = 30


class LoginRouteUnavailable(RuntimeError):
    """Raised when the login route cannot be used. Always non-fatal."""


def _client(cfg: Config):
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
    except Exception as e:                      # library raises many types
        raise LoginRouteUnavailable(f"login failed: {type(e).__name__}") from e


def fetch_topup(cfg: Config, days: int = 90) -> list[dict]:
    """Return partial `garmin_daily` rows carrying only the top-up columns."""
    api = _client(cfg)
    rows: list[dict] = []

    for offset in range(days):
        day = date.today() - timedelta(days=offset)
        iso = day.isoformat()
        values: dict[str, object] = {"day": day}

        for label, fn in (
            ("readiness", lambda: api.get_training_readiness(iso)),
            ("status", lambda: api.get_training_status(iso)),
            ("vo2", lambda: api.get_max_metrics(iso)),
        ):
            try:
                raw = fn()
            except Exception as e:
                log.debug("login route %s for %s unavailable: %s", label, iso, type(e).__name__)
                continue

            if label == "readiness":
                values["readiness"] = _first(raw, "score")
            elif label == "status":
                values["training_status"] = _first(raw, "trainingStatus")
                values["acute_load"] = _first(raw, "acuteTrainingLoad")
                values["chronic_load"] = _first(raw, "chronicTrainingLoad")
            else:
                values["vo2max_run"] = _first(raw, "vo2MaxValue")
                values["vo2max_bike"] = _first(raw, "cyclingVo2Max")

        if len(values) > 1:
            rows.append(values)

    return rows


def _first(raw: object, key: str):
    """Pull `key` out of whatever shape the library returned.

    The login route's response shapes are not a stable contract, so this walks
    dicts and lists rather than assuming one.
    """
    if isinstance(raw, dict):
        if key in raw:
            return raw[key]
        for v in raw.values():
            found = _first(v, key)
            if found is not None:
                return found
    elif isinstance(raw, list):
        for item in raw:
            found = _first(item, key)
            if found is not None:
                return found
    return None


def ingest(cfg: Config, db: Db, days: int = 90) -> int:
    """Top up garmin_daily. Never raises: returns 0 and records the failure."""
    try:
        rows = fetch_topup(cfg, days)
    except LoginRouteUnavailable as e:
        log.warning("garmin login route unavailable, top-up columns stay null: %s", e)
        db.mark_sync("garmin_login", ok=False, error=str(e))
        return 0

    n = db.upsert("garmin_daily", rows, on_conflict="user_id,day")
    db.mark_sync(
        "garmin_login", ok=True,
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=TOKEN_LIFETIME_DAYS),
    )
    log.info("garmin login route topped up %d days", n)
    return n
