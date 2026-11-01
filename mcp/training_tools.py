"""The four training tools for `vault-mcp`.

These let any Claude chat read the same computed numbers the page shows, and
log a scan or a check-in, so a scan logged in chat appears on the page with no
extra sync.

Two rules hold throughout:

  * Read tools return COMPUTED values only, never raw Garmin payloads, and
    they answer the range asked for. They do not stream history into a chat
    for an agent to keep. See the Garmin terms note in the README: until the
    Personal tier terms are confirmed, Garmin-sourced data must not be used to
    build or maintain an AI knowledge base, and that constraint bites here,
    not only on AI-written narrative.
  * Write tools apply exactly the same validation as the in-app path, so a
    scan logged from chat cannot bypass the range checks.

Mount into vault-mcp with `register(mcp)`, or run standalone for testing.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from engine.ti import recovery as rec
from engine.ti.body import Scan, gain_quality, validate_scan
from engine.ti.config import Config
from engine.ti.db import Db

log = logging.getLogger(__name__)
MAX_RANGE_DAYS = 180


def _db() -> Db:
    return Db(Config.from_env())


def _clamp_range(start: str | None, end: str | None) -> tuple[date, date]:
    end_d = date.fromisoformat(end) if end else date.today()
    start_d = date.fromisoformat(start) if start else end_d - timedelta(days=30)
    if start_d > end_d:
        start_d, end_d = end_d, start_d
    if (end_d - start_d).days > MAX_RANGE_DAYS:
        start_d = end_d - timedelta(days=MAX_RANGE_DAYS)
    return start_d, end_d


# ---------------------------------------------------------------------------
# training_summary
# ---------------------------------------------------------------------------
def training_summary(start: str | None = None, end: str | None = None) -> dict:
    """Readiness, load, recovery and body trend for a date range.

    Returns computed values only. Does not return raw wellness records.
    """
    start_d, end_d = _clamp_range(start, end)
    with _db() as db:
        loads = db.select("daily_load", columns="day,tss,ctl,atl,tsb,acwr",
                          order="day.asc",
                          **{"day": f"gte.{start_d}", "and": f"(day.lte.{end_d})"})
        ready = db.select("daily_readiness", columns="day,score,band,cold_start",
                          order="day.asc",
                          **{"day": f"gte.{start_d}", "and": f"(day.lte.{end_d})"})
        daily = db.select("garmin_daily", columns="day,hrv_night,sleep_score,rhr",
                          order="day.asc", **{"day": f"gte.{start_d - timedelta(days=60)}"})
        scans = db.select("evolt_scans",
                          columns="scanned_at,weight_kg,body_fat_pct,skeletal_muscle_kg",
                          order="scanned_at.asc")
        sync = db.select("sync_status", columns="source,last_success,token_expires_at")

    hrv = [float(d["hrv_night"]) if d.get("hrv_night") is not None else None for d in daily]
    sleep = [float(d["sleep_score"]) if d.get("sleep_score") is not None else None for d in daily]
    state = rec.hrv_state(hrv)
    latest_load = loads[-1] if loads else {}
    latest_ready = ready[-1] if ready else {}

    gq = gain_quality([
        Scan(scanned_at=datetime.fromisoformat(s["scanned_at"].replace("Z", "+00:00")).date(),
             weight_kg=_f(s.get("weight_kg")),
             skeletal_muscle_kg=_f(s.get("skeletal_muscle_kg")))
        for s in scans
    ])

    return {
        "range": {"start": start_d.isoformat(), "end": end_d.isoformat()},
        "readiness": {
            "latest": latest_ready.get("score"),
            "band": latest_ready.get("band"),
            "cold_start": latest_ready.get("cold_start"),
        },
        "load": {
            "ctl": _f(latest_load.get("ctl")),
            "atl": _f(latest_load.get("atl")),
            "tsb": _f(latest_load.get("tsb")),
            "acwr": _f(latest_load.get("acwr")),
            "range_tss": round(sum(float(d["tss"] or 0) for d in loads), 1),
        },
        "recovery": {
            "hrv_7d": state.rolling_7d,
            "hrv_baseline": state.baseline_mean,
            "hrv_position": state.position,
            "hrv_flag": state.flag,
            "sleep_7d": rec.rolling_mean(sleep, 7),
        },
        "body": {
            "scans_on_record": len(scans),
            "latest_weight_kg": _f(scans[-1].get("weight_kg")) if scans else None,
            "latest_body_fat_pct": _f(scans[-1].get("body_fat_pct")) if scans else None,
            "gain_quality": gq.value,
            "gain_quality_note": gq.reason,
        },
        "freshness": {
            s["source"]: {"last_success": s.get("last_success"),
                          "token_expires_at": s.get("token_expires_at")}
            for s in sync
        },
    }


# ---------------------------------------------------------------------------
# training_week
# ---------------------------------------------------------------------------
def training_week(iso_year: int | None = None, iso_week: int | None = None) -> dict:
    """The weekly verdict, the numbers behind it, and the watch flags."""
    if iso_year is None or iso_week is None:
        y, w, _ = date.today().isocalendar()
        iso_year, iso_week = iso_year or y, iso_week or w

    with _db() as db:
        row = db.one("weekly_reports",
                     iso_year=f"eq.{iso_year}", iso_week=f"eq.{iso_week}")

    if not row:
        return {"found": False, "iso_year": iso_year, "iso_week": iso_week,
                "note": "No report for that week yet. The job runs Sunday 18:31 Europe/London."}
    return {
        "found": True,
        "iso_year": row["iso_year"],
        "iso_week": row["iso_week"],
        "verdict": row["verdict"],
        "narrative": row["narrative"],
        "metrics": row["metrics"],
        "watch_flags": row["watch_flags"],
    }


# ---------------------------------------------------------------------------
# body_scan_log
# ---------------------------------------------------------------------------
def body_scan_log(
    scanned_at: str,
    weight_kg: float | None = None,
    body_fat_pct: float | None = None,
    skeletal_muscle_kg: float | None = None,
    lean_mass_kg: float | None = None,
    fat_mass_kg: float | None = None,
    bmr_kcal: int | None = None,
    tee_kcal: int | None = None,
    bio_age: float | None = None,
    bwi: float | None = None,
    conditions: dict | None = None,
) -> dict:
    """Write one Evolt scan. Same range validation as the in-app parser.

    A scan that fails validation is still stored, flagged for review, so it is
    never silently lost and never silently trusted.
    """
    values = {k: v for k, v in {
        "weight_kg": weight_kg, "body_fat_pct": body_fat_pct,
        "skeletal_muscle_kg": skeletal_muscle_kg, "lean_mass_kg": lean_mass_kg,
        "fat_mass_kg": fat_mass_kg, "bmr_kcal": bmr_kcal, "tee_kcal": tee_kcal,
        "bio_age": bio_age, "bwi": bwi,
    }.items() if v is not None}

    ok, reason = validate_scan(values)
    row = {
        **values,
        "scanned_at": scanned_at,
        "conditions": conditions or {},
        "parse_method": "manual",
        "needs_review": not ok,
        "review_reason": reason,
    }
    with _db() as db:
        db.upsert("evolt_scans", [row], on_conflict="user_id,scanned_at")

    return {"written": True, "scanned_at": scanned_at,
            "needs_review": not ok, "review_reason": reason,
            "note": ("Stored and flagged for review." if not ok
                     else "Stored. It will appear on the Body tab after tonight's compute.")}


# ---------------------------------------------------------------------------
# checkin_log
# ---------------------------------------------------------------------------
def checkin_log(
    day: str | None = None,
    soreness: int | None = None,
    energy: int | None = None,
    mood: int | None = None,
    niggle_area: str | None = None,
    niggle_pain: int | None = None,
    notes: str | None = None,
) -> dict:
    """Write a daily check-in from chat. Feeds the readiness score."""
    for name, value, lo, hi in (("soreness", soreness, 1, 5), ("energy", energy, 1, 5),
                                ("mood", mood, 1, 5), ("niggle_pain", niggle_pain, 0, 10)):
        if value is not None and not (lo <= value <= hi):
            return {"written": False, "error": f"{name} must be between {lo} and {hi}, got {value}"}

    row = {k: v for k, v in {
        "day": day or date.today().isoformat(),
        "soreness": soreness, "energy": energy, "mood": mood,
        "niggle_area": niggle_area, "niggle_pain": niggle_pain, "notes": notes,
    }.items() if v is not None}

    with _db() as db:
        db.upsert("daily_checkin", [row], on_conflict="user_id,day")
    return {"written": True, "day": row["day"]}


def _f(v) -> float | None:
    return None if v is None else float(v)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
TOOLS = {
    "training_summary": training_summary,
    "training_week": training_week,
    "body_scan_log": body_scan_log,
    "checkin_log": checkin_log,
}


def register(mcp) -> None:
    """Attach these tools to an existing FastMCP instance (vault-mcp)."""
    for name, fn in TOOLS.items():
        mcp.tool(name=name)(fn)


if __name__ == "__main__":
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("training-intelligence")
    register(server)
    server.run()
