"""Weekly report. Runs Sunday 18:31 Europe/London in GitHub Actions.

Writes one `weekly_reports` row and sends an ntfy push carrying only the
verdict word and a link. No health numbers reach the public relay: the whole
point of NTFY_INCLUDE_SENSITIVE defaulting to 0.

The narrative is a rule-based template from verdict.py. No LLM writes it,
pending the Garmin terms question in the README.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta

import httpx

from . import recovery as rec
from .config import Config
from .db import Db
from .verdict import weekly_verdict

log = logging.getLogger(__name__)
PAGE_URL = "https://dashboard-the-vault10.vercel.app/training"


def build(db: Db, on: date | None = None) -> dict:
    on = on or date.today()
    iso_year, iso_week, _ = on.isocalendar()
    start = on - timedelta(days=60)

    raw = db.settings()
    thresholds = raw.get("thresholds") or {}

    daily = db.select("garmin_daily", columns="day,hrv_night,sleep_score,rhr",
                      order="day.asc", **{"day": f"gte.{start.isoformat()}"})
    loads = db.select("daily_load", columns="day,tss,ctl,atl,tsb,acwr,ctl_ramp_7d",
                      order="day.asc", **{"day": f"gte.{start.isoformat()}"})

    hrv = [float(d["hrv_night"]) if d.get("hrv_night") is not None else None for d in daily]
    sleep = [float(d["sleep_score"]) if d.get("sleep_score") is not None else None for d in daily]
    rhr = [int(d["rhr"]) if d.get("rhr") is not None else None for d in daily]

    state = rec.hrv_state(
        hrv,
        rolling_days=int(thresholds.get("hrv_rolling_days", 7)),
        baseline_days=int(thresholds.get("hrv_baseline_days", 60)),
    )
    latest = loads[-1] if loads else {}

    v = weekly_verdict(
        hrv_position=state.position,
        hrv_days_below=rec.hrv_days_below_band(hrv, state.band),
        tsb=_f(latest.get("tsb")),
        acwr=_f(latest.get("acwr")),
        sleep_7d=rec.rolling_mean(sleep, 7),
        rhr_flag_days=rec.rhr_flag_days(
            rhr,
            baseline_days=int(thresholds.get("rhr_baseline_days", 30)),
            threshold_bpm=float(thresholds.get("rhr_flag_bpm", 5)),
        ),
        thresholds=thresholds,
    )

    week_tss = sum(float(d["tss"] or 0) for d in loads[-7:])
    prev_tss = sum(float(d["tss"] or 0) for d in loads[-14:-7])

    metrics = {
        "hrv_7d": state.rolling_7d,
        "hrv_baseline": state.baseline_mean,
        "hrv_band": list(state.band) if state.band else None,
        "hrv_position": state.position,
        "tsb": _f(latest.get("tsb")),
        "ctl": _f(latest.get("ctl")),
        "atl": _f(latest.get("atl")),
        "acwr": _f(latest.get("acwr")),
        "ctl_ramp_7d": _f(latest.get("ctl_ramp_7d")),
        "sleep_7d": rec.rolling_mean(sleep, 7),
        "week_tss": round(week_tss, 1),
        "prev_week_tss": round(prev_tss, 1),
        "week_tss_change_pct": (round((week_tss - prev_tss) / prev_tss * 100, 1)
                                if prev_tss else None),
        "checks": [
            {"name": c.name, "passed": c.passed, "value": c.value, "threshold": c.threshold}
            for c in (v.push_checks + v.backoff_checks)
        ],
        "unavailable": v.unavailable,
    }

    row = {
        "iso_year": iso_year,
        "iso_week": iso_week,
        "verdict": v.verdict,
        "metrics": metrics,
        "watch_flags": v.watch_flags,
        "narrative": v.narrative(),
    }
    db.upsert("weekly_reports", [row], on_conflict="user_id,iso_year,iso_week")
    return row


def notify(cfg: Config, row: dict) -> None:
    """Push the verdict word and a link. Nothing else.

    Guarded twice: the payload is built from the verdict label only, and the
    sensitive flag has to be explicitly on before anything further is added.
    """
    if not cfg.ntfy_topic:
        log.info("no NTFY_TOPIC set, skipping push")
        return

    label = {"push": "Push", "hold": "Hold", "back_off": "Back off"}[row["verdict"]]
    body = f"This week: {label}"
    if cfg.ntfy_include_sensitive:
        body += f"\n{row['narrative']}"
        log.warning("NTFY_INCLUDE_SENSITIVE is on: health detail is going to the relay")

    r = httpx.post(
        f"https://ntfy.sh/{cfg.ntfy_topic}",
        timeout=20.0,
        content=body.encode(),
        headers={
            "Title": "Training week",
            "Click": PAGE_URL,
            "Tags": {"push": "green_circle", "hold": "yellow_circle",
                     "back_off": "red_circle"}[row["verdict"]],
        },
    )
    if r.status_code >= 400:
        log.warning("ntfy push failed: HTTP %s", r.status_code)


def _f(v) -> float | None:
    return None if v is None else float(v)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Weekly report")
    ap.add_argument("--no-notify", action="store_true")
    args = ap.parse_args()

    cfg = Config.from_env()
    with Db(cfg) as db:
        row = build(db)
        if not args.no_notify:
            notify(cfg, row)
    log.info("weekly verdict: %s", row["verdict"])


if __name__ == "__main__":
    main()
