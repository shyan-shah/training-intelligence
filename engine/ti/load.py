"""Training load: per-session TSS, then the CTL / ATL / TSB / ACWR series.

Session TSS all reduces to the same shape:

    TSS = hours * IF**k * 100

with k = 2 for power, pace and HR, and k = 3 for swim. The power form in the
brief,

    TSS = (t_s * NP * IF) / (FTP * 3600) * 100

is the same thing: (t_s/3600) * (NP/FTP) * IF * 100 = hours * IF**2 * 100.

Two rules that matter for real data:

  * hours comes from MOVING time. Audited Strava history contains a session
    with 175,726s elapsed against 4,678s moving. Elapsed-time TSS would read
    ~1,200 for a walk.
  * IF is capped. A GPS spike or a bad FTP produces an IF of 3+, which would
    otherwise dominate CTL for six weeks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Sequence

# An IF above this is treated as a data error rather than a heroic session.
IF_CAP = 1.60

# Fixed TSS per strength session until a real model exists. Keyed by a coarse
# session label; falls back to DEFAULT. Deliberately conservative: strength
# work does raise fatigue, but attributing 100 TSS to it would swamp the
# endurance signal.
STRENGTH_TSS = {
    "push": 30.0,
    "pull": 30.0,
    "legs": 45.0,
    "full": 40.0,
    "DEFAULT": 35.0,
}

CTL_TAU = 42
ATL_TAU = 7


@dataclass(frozen=True)
class Session:
    """One activity, already normalised and validated."""
    start_at: date
    sport: str                  # swim | bike | run | strength | other
    duration_s: int             # MOVING time
    distance_m: float | None = None
    avg_hr: int | None = None
    np: float | None = None
    avg_power: float | None = None
    avg_pace: float | None = None     # seconds per km
    label: str | None = None          # for strength: push/pull/legs/full


@dataclass(frozen=True)
class Settings:
    ftp_w: int | None = None
    threshold_pace: float | None = None   # seconds per km
    css_swim: float | None = None         # seconds per 100m
    lthr: int | None = None


@dataclass(frozen=True)
class TssResult:
    tss: float
    method: str
    intensity_factor: float | None = None
    capped: bool = False


def _hours(duration_s: int) -> float:
    return max(duration_s, 0) / 3600.0


def _apply_cap(if_raw: float) -> tuple[float, bool]:
    if if_raw > IF_CAP:
        return IF_CAP, True
    return if_raw, False


def session_tss(s: Session, cfg: Settings) -> TssResult:
    """Compute TSS for one session, choosing the best available method.

    Priority is power > pace > HR, because each is a step further from
    measured work. Returns method 'none' when nothing is available, rather
    than guessing a number: a blank is honest, a fabricated 50 is not.
    """
    h = _hours(s.duration_s)
    if h <= 0:
        return TssResult(0.0, "none")

    if s.sport == "strength":
        key = (s.label or "DEFAULT").lower()
        return TssResult(STRENGTH_TSS.get(key, STRENGTH_TSS["DEFAULT"]), "fixed")

    # --- bike: normalised power against FTP -------------------------------
    if s.sport == "bike" and cfg.ftp_w:
        power = s.np if s.np else s.avg_power
        if power:
            if_val, capped = _apply_cap(power / cfg.ftp_w)
            return TssResult(h * if_val**2 * 100.0, "power", if_val, capped)

    # --- run: threshold pace against actual pace --------------------------
    if s.sport == "run" and cfg.threshold_pace:
        pace = s.avg_pace
        if not pace and s.distance_m and s.distance_m > 0:
            pace = s.duration_s / (s.distance_m / 1000.0)
        if pace and pace > 0:
            # Both in seconds per km, so faster (smaller) pace gives IF > 1.
            if_val, capped = _apply_cap(cfg.threshold_pace / pace)
            return TssResult(h * if_val**2 * 100.0, "pace", if_val, capped)

    # --- swim: CSS, cubed ---------------------------------------------------
    if s.sport == "swim" and cfg.css_swim:
        if s.distance_m and s.distance_m > 0:
            pace_100 = s.duration_s / (s.distance_m / 100.0)
            if pace_100 > 0:
                if_val, capped = _apply_cap(cfg.css_swim / pace_100)
                return TssResult(h * if_val**3 * 100.0, "swim_css", if_val, capped)

    # --- fallback: heart rate against LTHR ---------------------------------
    if cfg.lthr and s.avg_hr:
        if_val, capped = _apply_cap(s.avg_hr / cfg.lthr)
        return TssResult(h * if_val**2 * 100.0, "hr", if_val, capped)

    return TssResult(0.0, "none")


def daily_tss(sessions: Iterable[Session], cfg: Settings) -> dict[date, float]:
    """Total TSS per calendar day, and per sport, from a set of sessions."""
    out: dict[date, float] = {}
    for s in sessions:
        out[s.start_at] = out.get(s.start_at, 0.0) + session_tss(s, cfg).tss
    return out


def daily_tss_by_sport(sessions: Iterable[Session], cfg: Settings) -> dict[date, dict[str, float]]:
    out: dict[date, dict[str, float]] = {}
    for s in sessions:
        day = out.setdefault(s.start_at, {})
        day[s.sport] = day.get(s.sport, 0.0) + session_tss(s, cfg).tss
    return out


@dataclass
class LoadPoint:
    day: date
    tss: float
    ctl: float
    atl: float
    tsb: float
    acwr: float | None = None
    acwr_ewma: float | None = None
    ctl_ramp_7d: float | None = None


def load_series(
    tss_by_day: dict[date, float],
    start: date,
    end: date,
    ctl_seed: float = 0.0,
    atl_seed: float = 0.0,
) -> list[LoadPoint]:
    """Walk every calendar day from start to end building the load series.

    Rest days must be present as zeros, which is why this iterates dates
    rather than sessions: skipping a rest day would stop CTL and ATL decaying
    and quietly inflate fitness.

    TSB is yesterday's CTL minus yesterday's ATL, per the brief, so day one
    reports the seed difference rather than a figure that already includes
    today's session.
    """
    points: list[LoadPoint] = []
    ctl, atl = float(ctl_seed), float(atl_seed)

    day = start
    while day <= end:
        tss = float(tss_by_day.get(day, 0.0))

        # TSB uses the PREVIOUS day's values, so capture them before updating.
        tsb = ctl - atl

        ctl = ctl + (tss - ctl) / CTL_TAU
        atl = atl + (tss - atl) / ATL_TAU

        points.append(LoadPoint(day=day, tss=tss, ctl=ctl, atl=atl, tsb=tsb))
        day += timedelta(days=1)

    _attach_acwr(points, tss_by_day)
    _attach_ramp(points)
    return points


def _attach_acwr(points: list[LoadPoint], tss_by_day: dict[date, float]) -> None:
    """Standard ACWR: 7-day total over the 28-day weekly average.

    Audit note: the brief defined ACWR as ATL/CTL. That is a 7:42 exponential
    ratio, and the 0.8-1.3 band and the 1.5 back-off threshold in the
    literature are calibrated for the 7:28 rolling form, so the two are not
    interchangeable. Both are computed: `acwr` drives the verdict, `acwr_ewma`
    is kept so the old definition stays visible for comparison.

    Chronic load needs a full 28 days behind it. Before that the ratio is left
    as None rather than divided by a partial window, which would read high and
    trigger a spurious back-off in week one.
    """
    for p in points:
        acute = sum(tss_by_day.get(p.day - timedelta(days=i), 0.0) for i in range(7))
        chronic_total = sum(tss_by_day.get(p.day - timedelta(days=i), 0.0) for i in range(28))
        chronic_weekly = chronic_total / 4.0

        earliest = min(tss_by_day) if tss_by_day else p.day
        has_28d = (p.day - earliest).days >= 27

        p.acwr = round(acute / chronic_weekly, 3) if (has_28d and chronic_weekly > 0) else None
        p.acwr_ewma = round(p.atl / p.ctl, 3) if p.ctl > 0 else None


def _attach_ramp(points: list[LoadPoint]) -> None:
    by_day = {p.day: p for p in points}
    for p in points:
        prior = by_day.get(p.day - timedelta(days=7))
        p.ctl_ramp_7d = round(p.ctl - prior.ctl, 2) if prior else None
