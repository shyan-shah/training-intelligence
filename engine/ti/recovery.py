"""Recovery signals and the readiness score.

The readiness score is the one number the Today tab leads with, so it carries
two rules the brief did not specify but which real data forces:

  * Cold start. The TSB component needs ~42 days of load history to mean
    anything. Before that the component is dropped and the remaining weights
    are renormalised, and the row is marked cold_start so the page can say so
    instead of quietly reporting a confident number built on nothing.
  * Missing inputs are dropped, not zeroed. A night with no HRV reading would
    otherwise score 0 on 35% of the total and render as "red" when the truth
    is "unknown".
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

DEFAULT_WEIGHTS = {"hrv": 0.35, "sleep": 0.25, "rhr": 0.15, "tsb": 0.15, "checkin": 0.10}
MIN_DAYS_FOR_TSB = 42
MIN_BASELINE_N = 14          # below this an HRV baseline is not a baseline


@dataclass(frozen=True)
class Baseline:
    mean: float | None
    sd: float | None
    n: int

    @property
    def usable(self) -> bool:
        return self.mean is not None and self.sd is not None and self.n >= MIN_BASELINE_N

    def band(self) -> tuple[float, float] | None:
        if not self.usable:
            return None
        return (self.mean - self.sd, self.mean + self.sd)


def baseline(values: list[float | None], days: int) -> Baseline:
    """Mean and SD of the last `days` non-null values."""
    clean = [v for v in values[-days:] if v is not None]
    if len(clean) < 2:
        return Baseline(None, None, len(clean))
    return Baseline(statistics.fmean(clean), statistics.stdev(clean), len(clean))


def rolling_mean(values: list[float | None], days: int) -> float | None:
    clean = [v for v in values[-days:] if v is not None]
    return statistics.fmean(clean) if clean else None


# ---------------------------------------------------------------------------
# HRV
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HrvState:
    rolling_7d: float | None
    baseline_mean: float | None
    baseline_sd: float | None
    band: tuple[float, float] | None
    position: str          # below | inside | above | unknown
    flag: str | None       # strain | saturation | None


def hrv_state(nightly: list[float | None], rolling_days: int = 7, baseline_days: int = 60) -> HrvState:
    """7-day rolling HRV mean against a 60-day baseline mean +/- 1 SD.

    Below the band reads as strain. Above it is flagged too: a sharp rise can
    be parasympathetic saturation rather than good news, so both ends are
    surfaced and neither is silently treated as fine.
    """
    r7 = rolling_mean(nightly, rolling_days)
    base = baseline(nightly, baseline_days)
    band = base.band()

    if r7 is None or band is None:
        return HrvState(r7, base.mean, base.sd, band, "unknown", None)

    lo, hi = band
    if r7 < lo:
        return HrvState(r7, base.mean, base.sd, band, "below", "strain")
    if r7 > hi:
        return HrvState(r7, base.mean, base.sd, band, "above", "saturation")
    return HrvState(r7, base.mean, base.sd, band, "inside", None)


def hrv_days_below_band(nightly: list[float | None], band: tuple[float, float] | None, window: int = 7) -> int:
    """Count of the last `window` nights whose single-night HRV sat below the band."""
    if band is None:
        return 0
    lo, _ = band
    return sum(1 for v in nightly[-window:] if v is not None and v < lo)


# ---------------------------------------------------------------------------
# Resting heart rate
# ---------------------------------------------------------------------------
def rhr_flagged(rhr: list[int | None], baseline_days: int = 30, threshold_bpm: float = 5.0) -> bool:
    """True when today's RHR sits threshold_bpm or more above its 30-day mean."""
    if not rhr or rhr[-1] is None:
        return False
    base = rolling_mean([float(v) if v is not None else None for v in rhr[:-1]], baseline_days)
    if base is None:
        return False
    return (rhr[-1] - base) >= threshold_bpm


def rhr_flag_days(rhr: list[int | None], window: int = 7, baseline_days: int = 30, threshold_bpm: float = 5.0) -> int:
    """How many of the last `window` days carried an RHR flag."""
    count = 0
    for i in range(len(rhr) - window, len(rhr)):
        if i < 1:
            continue
        if rhr_flagged(rhr[: i + 1], baseline_days, threshold_bpm):
            count += 1
    return count


# ---------------------------------------------------------------------------
# Sleep
# ---------------------------------------------------------------------------
def bedtime_regularity(onset_minutes: list[float | None], days: int = 14) -> float | None:
    """SD, in minutes, of sleep onset time. Lower is more regular."""
    clean = [v for v in onset_minutes[-days:] if v is not None]
    if len(clean) < 3:
        return None
    return round(statistics.stdev(clean), 1)


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------
def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _hrv_subscore(r7: float | None, base: Baseline) -> float | None:
    """50 at baseline, 100 at +1 SD, 0 at -1 SD."""
    if r7 is None or not base.usable or not base.sd:
        return None
    z = (r7 - base.mean) / base.sd
    return _clamp(50.0 + z * 50.0)


def _sleep_subscore(score_7d: float | None) -> float | None:
    """Garmin sleep score is already 0-100."""
    return None if score_7d is None else _clamp(score_7d)


def _rhr_subscore(today: int | None, base: float | None) -> float | None:
    """50 at baseline; each bpm above costs 10, each below gains 10."""
    if today is None or base is None:
        return None
    return _clamp(50.0 - (today - base) * 10.0)


def _tsb_subscore(tsb: float | None) -> float | None:
    """0 at -30, 50 at -5, 100 at +20. Linear between."""
    if tsb is None:
        return None
    return _clamp((tsb + 30.0) / 50.0 * 100.0)


def _checkin_subscore(soreness: int | None, energy: int | None, mood: int | None) -> float | None:
    """Soreness is inverted (5 = very sore). Each 1-5 scale maps to 0-100."""
    parts: list[float] = []
    if soreness is not None:
        parts.append((5 - soreness) / 4.0 * 100.0)
    if energy is not None:
        parts.append((energy - 1) / 4.0 * 100.0)
    if mood is not None:
        parts.append((mood - 1) / 4.0 * 100.0)
    return statistics.fmean(parts) if parts else None


@dataclass
class Readiness:
    score: float | None
    band: str
    components: dict[str, dict[str, float]] = field(default_factory=dict)
    drivers: list[dict] = field(default_factory=list)
    cold_start: bool = False
    note: str | None = None


def readiness(
    hrv_nightly: list[float | None],
    sleep_scores: list[float | None],
    rhr: list[int | None],
    tsb: float | None,
    checkin: tuple[int | None, int | None, int | None] = (None, None, None),
    weights: dict[str, float] | None = None,
    load_history_days: int = 0,
) -> Readiness:
    """Weighted 0-100 readiness score with the drivers that moved it.

    Returns the weight actually applied to each component, so the page can
    show why a score is what it is rather than asserting a bare number.
    """
    w = dict(weights or DEFAULT_WEIGHTS)
    base_hrv = baseline(hrv_nightly, 60)

    subs: dict[str, float | None] = {
        "hrv": _hrv_subscore(rolling_mean(hrv_nightly, 7), base_hrv),
        "sleep": _sleep_subscore(rolling_mean(sleep_scores, 7)),
        "rhr": _rhr_subscore(rhr[-1] if rhr else None, rolling_mean([float(v) if v is not None else None for v in rhr[:-1]], 30)),
        "tsb": _tsb_subscore(tsb),
        "checkin": _checkin_subscore(*checkin),
    }

    cold_start = load_history_days < MIN_DAYS_FOR_TSB
    note = None
    if cold_start:
        # TSB is not trustworthy yet, so drop it rather than let a seeded
        # CTL of zero read as "well rested".
        subs["tsb"] = None
        note = f"TSB excluded: {load_history_days} of {MIN_DAYS_FOR_TSB} days of load history"

    available = {k: v for k, v in subs.items() if v is not None}
    if not available:
        return Readiness(None, "unknown", {}, [], cold_start, "no inputs available")

    total_w = sum(w[k] for k in available)
    components: dict[str, dict[str, float]] = {}
    score = 0.0
    for k, v in available.items():
        applied = w[k] / total_w          # renormalised over what we actually have
        score += v * applied
        components[k] = {"subscore": round(v, 1), "weight": round(applied, 4)}

    for k in subs:
        if k not in available:
            components[k] = {"subscore": None, "weight": 0.0}

    # Drivers: distance from neutral (50), scaled by the weight applied.
    drivers = sorted(
        (
            {
                "component": k,
                "subscore": round(v, 1),
                "contribution": round((v - 50.0) * (w[k] / total_w), 2),
            }
            for k, v in available.items()
        ),
        key=lambda d: abs(d["contribution"]),
        reverse=True,
    )[:3]

    score = round(score, 1)
    band = "green" if score >= 70 else "amber" if score >= 50 else "red"
    return Readiness(score, band, components, drivers, cold_start, note)
