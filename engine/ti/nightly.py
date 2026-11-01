"""Nightly compute. Runs in GitHub Actions after ingest.

Order matters: dedupe before load, because counting the same session twice
inflates CTL; load before readiness, because readiness reads TSB.

Nothing here calls an LLM. Every value written is produced by a formula in
this package.
"""
from __future__ import annotations

import argparse
import logging
import statistics
from datetime import date, datetime, timedelta

from . import body as body_mod
from . import insights as insight_mod
from . import load as load_mod
from . import recovery as rec
from . import streaks as streak_mod
from .config import Config
from .db import Db
from .dedupe import Candidate, group

log = logging.getLogger(__name__)
LOAD_BEARING = {"swim", "bike", "run", "strength"}


def _settings(raw: dict) -> tuple[load_mod.Settings, dict, dict]:
    cfg = load_mod.Settings(
        ftp_w=raw.get("ftp_w"),
        threshold_pace=raw.get("threshold_pace"),
        css_swim=raw.get("css_swim"),
        lthr=raw.get("lthr"),
    )
    return cfg, (raw.get("targets") or {}), (raw.get("thresholds") or {})


def run(cfg: Config, db: Db, days: int = 180) -> dict:
    raw = db.settings()
    load_cfg, targets, thresholds = _settings(raw)

    start = date.today() - timedelta(days=days)
    end = date.today()

    # ---- 1. activities, deduped ------------------------------------------
    acts = db.select(
        "activities",
        columns="id,source,source_id,sport,start_at,duration_s,distance_m,avg_hr,np,avg_power,avg_pace,sport_raw,is_valid",
        order="start_at.asc",
        **{"start_at": f"gte.{start.isoformat()}"},
    )

    cands = [
        Candidate(
            key=f"{a['source']}:{a['source_id']}",
            source=a["source"],
            sport=a["sport"],
            start_at=datetime.fromisoformat(a["start_at"].replace("Z", "+00:00")),
            duration_s=int(a["duration_s"] or 0),
            distance_m=float(a["distance_m"]) if a.get("distance_m") else None,
        )
        for a in acts
    ]
    winners = group(cands, window_s=int(thresholds.get("dedupe_window_s", 300)))

    # Record the dedupe decision so the page can show which rows were folded.
    for a in acts:
        key = f"{a['source']}:{a['source_id']}"
        db.update(
            "activities",
            {"is_primary": winners.get(key) == key},
            **{"source": f"eq.{a['source']}", "source_id": f"eq.{a['source_id']}"},
        )

    # ---- 2. per-session TSS ----------------------------------------------
    sessions: list[load_mod.Session] = []
    for a in acts:
        key = f"{a['source']}:{a['source_id']}"
        if winners.get(key) != key:
            continue                                  # folded duplicate
        if not a.get("is_valid", True):
            continue                                  # failed validation
        if a["sport"] not in LOAD_BEARING:
            continue                                  # walks etc carry no TSS

        started = datetime.fromisoformat(a["start_at"].replace("Z", "+00:00"))
        sessions.append(load_mod.Session(
            start_at=started.date(),
            sport=a["sport"],
            duration_s=int(a["duration_s"] or 0),
            distance_m=float(a["distance_m"]) if a.get("distance_m") else None,
            avg_hr=a.get("avg_hr"),
            np=float(a["np"]) if a.get("np") else None,
            avg_power=float(a["avg_power"]) if a.get("avg_power") else None,
            avg_pace=float(a["avg_pace"]) if a.get("avg_pace") else None,
            label=None,
        ))

    # Persist the TSS and method on each activity so a number on the page can
    # be traced back to the session that produced it.
    for a in acts:
        key = f"{a['source']}:{a['source_id']}"
        if winners.get(key) != key or a["sport"] not in LOAD_BEARING:
            continue
        started = datetime.fromisoformat(a["start_at"].replace("Z", "+00:00"))
        s = load_mod.Session(
            start_at=started.date(), sport=a["sport"], duration_s=int(a["duration_s"] or 0),
            distance_m=float(a["distance_m"]) if a.get("distance_m") else None,
            avg_hr=a.get("avg_hr"),
            np=float(a["np"]) if a.get("np") else None,
            avg_power=float(a["avg_power"]) if a.get("avg_power") else None,
            avg_pace=float(a["avg_pace"]) if a.get("avg_pace") else None,
        )
        res = load_mod.session_tss(s, load_cfg)
        db.update("activities", {"tss": round(res.tss, 2), "tss_method": res.method},
                  **{"source": f"eq.{a['source']}", "source_id": f"eq.{a['source_id']}"})

    # ---- 3. load series ---------------------------------------------------
    tss_by_day = load_mod.daily_tss(sessions, load_cfg)
    by_sport = load_mod.daily_tss_by_sport(sessions, load_cfg)
    series = load_mod.load_series(tss_by_day, start, end)

    db.upsert("daily_load", [
        {
            "day": p.day,
            "tss": round(p.tss, 2),
            "ctl": round(p.ctl, 3),
            "atl": round(p.atl, 3),
            "tsb": round(p.tsb, 3),
            "acwr": p.acwr,
            "acwr_ewma": p.acwr_ewma,
            "ctl_ramp_7d": p.ctl_ramp_7d,
            "by_sport": {k: round(v, 2) for k, v in by_sport.get(p.day, {}).items()},
        }
        for p in series
    ], on_conflict="user_id,day")

    # ---- 4. recovery and readiness ---------------------------------------
    daily = db.select(
        "garmin_daily",
        columns="day,hrv_night,sleep_score,sleep_total_min,sleep_onset_min,rhr",
        order="day.asc",
        **{"day": f"gte.{start.isoformat()}"},
    )
    checkins = {
        c["day"]: c for c in db.select("daily_checkin", order="day.asc",
                                       **{"day": f"gte.{start.isoformat()}"})
    }

    hrv = [_f(d.get("hrv_night")) for d in daily]
    sleep = [_f(d.get("sleep_score")) for d in daily]
    rhr = [_i(d.get("rhr")) for d in daily]
    tsb_by_day = {p.day: p.tsb for p in series}
    load_days = len([p for p in series if p.tss > 0])

    readiness_rows = []
    for i, d in enumerate(daily):
        day = date.fromisoformat(d["day"])
        c = checkins.get(d["day"], {})
        r = rec.readiness(
            hrv_nightly=hrv[: i + 1],
            sleep_scores=sleep[: i + 1],
            rhr=rhr[: i + 1],
            tsb=tsb_by_day.get(day),
            checkin=(c.get("soreness"), c.get("energy"), c.get("mood")),
            weights=(thresholds.get("readiness_weights") or rec.DEFAULT_WEIGHTS),
            load_history_days=load_days,
        )
        readiness_rows.append({
            "day": day, "score": r.score, "band": r.band,
            "components": r.components, "drivers": r.drivers,
            "cold_start": r.cold_start,
        })
    db.upsert("daily_readiness", readiness_rows, on_conflict="user_id,day")

    # ---- 5. habit scorecard ----------------------------------------------
    _write_scorecard(db, start, end, targets, daily, checkins, acts, winners)

    # ---- 6. insights ------------------------------------------------------
    written = _compute_insights(db, daily, series, by_sport, thresholds)

    db.mark_sync("engine", ok=True)
    return {
        "activities": len(acts),
        "sessions_counted": len(sessions),
        "duplicates_folded": sum(1 for k, v in winners.items() if k != v),
        "load_days": len(series),
        "readiness_days": len(readiness_rows),
        "insights": written,
    }


def _write_scorecard(db: Db, start: date, end: date, targets: dict,
                     daily: list[dict], checkins: dict, acts: list[dict],
                     winners: dict) -> int:
    """Evaluate every habit for every day and persist the result.

    The browser renders these rows as-is. Keeping the evaluation here means the
    habit rules live in exactly one place.
    """
    wellness = {d["day"]: d for d in daily}

    strength_by_day: dict[str, int] = {}
    scan_weeks: set[tuple[int, int]] = set()
    for a in acts:
        key = f"{a['source']}:{a['source_id']}"
        if winners.get(key) != key or a["sport"] != "strength":
            continue
        day = a["start_at"][:10]
        strength_by_day[day] = strength_by_day.get(day, 0) + 1

    for row in db.select("evolt_scans", columns="scanned_at"):
        y, w, _ = date.fromisoformat(row["scanned_at"][:10]).isocalendar()
        scan_weeks.add((y, w))

    nutrition = {n["day"]: n for n in db.select(
        "nutrition_daily", order="day.asc", **{"day": f"gte.{start.isoformat()}"})}

    day_rows: dict[date, dict] = {}
    cursor = start
    while cursor <= end:
        iso = cursor.isoformat()
        w = wellness.get(iso, {})
        n = nutrition.get(iso, {})
        y, wk, _ = cursor.isocalendar()
        day_rows[cursor] = {
            "protein_g": _f(n.get("protein_g")),
            "kcal": n.get("kcal"),
            "strength_sessions": strength_by_day.get(iso, 0),
            "sleep_total_min": w.get("sleep_total_min"),
            "sleep_score": w.get("sleep_score"),
            "has_checkin": iso in checkins,
            "scan_this_week": (y, wk) in scan_weeks,
        }
        cursor += timedelta(days=1)

    habits = streak_mod.default_habits(targets)
    results = streak_mod.evaluate(habits, day_rows, start, end)

    per_day: dict[date, dict[str, str]] = {}
    for res in results:
        for day, state in res.days.items():
            per_day.setdefault(day, {})[res.key] = state

    return db.upsert(
        "daily_scorecard",
        [{"day": day, "habits": states} for day, states in sorted(per_day.items())],
        on_conflict="user_id,day",
    )


def _compute_insights(db: Db, daily: list[dict], series: list, by_sport: dict,
                      thresholds: dict) -> int:
    min_n = int(thresholds.get("insight_min_n", insight_mod.MIN_N))

    hrv_by_day = {date.fromisoformat(d["day"]): _f(d["hrv_night"])
                  for d in daily if d.get("hrv_night") is not None}
    rhr_series = [(date.fromisoformat(d["day"]), _f(d["rhr"]))
                  for d in daily if d.get("rhr") is not None]
    tss_by_day = {p.day: p.tss for p in series}

    candidates: list[insight_mod.Insight | None] = []

    if len(hrv_by_day) >= min_n:
        candidates.append(insight_mod.driver_continuous(
            "training load", tss_by_day, hrv_by_day, "HRV", "ms", "TSS", per_unit=150))

    if len(rhr_series) >= min_n:
        candidates.append(insight_mod.trend_break(rhr_series, "Resting HR", "bpm"))

    hrv_series = sorted(hrv_by_day.items())
    if len(hrv_series) >= min_n:
        candidates.append(insight_mod.trend_break(hrv_series, "HRV", "ms"))

    outcome_sd = (statistics.stdev(list(hrv_by_day.values()))
                  if len(hrv_by_day) > 1 else None)
    published = insight_mod.publish(candidates, outcome_sd, min_n=min_n)

    # Replace rather than accumulate: stale insights must expire, not pile up.
    db.delete("insights", kind="in.(personal_driver,trend_break,fitness_gain,cause_hunt)")
    return db.upsert("insights", [i.to_row(db.cfg.user_id) for i in published])


def _f(v) -> float | None:
    return None if v is None else float(v)


def _i(v) -> int | None:
    return None if v is None else int(v)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Nightly analytics compute")
    ap.add_argument("--days", type=int, default=180)
    args = ap.parse_args()

    cfg = Config.from_env()
    with Db(cfg) as db:
        summary = run(cfg, db, days=args.days)
    log.info("nightly complete: %s", summary)


if __name__ == "__main__":
    main()
