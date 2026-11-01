"""Body composition: trends, gain quality, rate against target, projection.

Audit note: at the time of writing there is exactly one Evolt scan on record
(13 Sep 2026). Every function here needs two or three, so each returns an
explicit `reason` when it cannot compute rather than a plausible-looking
number. The Body tab is expected to be mostly empty until scans accumulate.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

# Evolt plausibility ranges. Anything outside goes to manual review instead of
# being stored as truth.
VALID_RANGES = {
    "weight_kg": (50.0, 100.0),
    "body_fat_pct": (3.0, 40.0),
    "skeletal_muscle_kg": (20.0, 55.0),
    "lean_mass_kg": (35.0, 90.0),
}


@dataclass(frozen=True)
class Scan:
    scanned_at: date
    weight_kg: float | None = None
    body_fat_pct: float | None = None
    skeletal_muscle_kg: float | None = None
    lean_mass_kg: float | None = None
    conditions: dict | None = None


@dataclass(frozen=True)
class Weigh:
    day: date
    weight_kg: float


def validate_scan(values: dict) -> tuple[bool, str | None]:
    """Range-check a parsed scan. Returns (ok, reason)."""
    problems = []
    for field_name, (lo, hi) in VALID_RANGES.items():
        v = values.get(field_name)
        if v is None:
            continue
        if not (lo <= float(v) <= hi):
            problems.append(f"{field_name}={v} outside {lo}-{hi}")

    # Internal consistency: lean + fat should land near total weight.
    w, bf = values.get("weight_kg"), values.get("body_fat_pct")
    lean = values.get("lean_mass_kg")
    if w and bf is not None and lean:
        implied_lean = float(w) * (1 - float(bf) / 100.0)
        if abs(implied_lean - float(lean)) > 3.0:
            problems.append(
                f"lean_mass_kg={lean} inconsistent with weight {w} at {bf}% "
                f"(implies {implied_lean:.1f})"
            )

    return (not problems), ("; ".join(problems) or None)


def rolling_scan_average(scans: list[Scan], window: int = 3) -> list[tuple[date, dict[str, float | None]]]:
    """Trailing average of the last `window` scans, emitted per scan date.

    Evolt readings swing with hydration and timing, so the trend line is the
    rolling average and the raw scans are the dots.
    """
    ordered = sorted(scans, key=lambda s: s.scanned_at)
    out: list[tuple[date, dict[str, float | None]]] = []
    for i in range(len(ordered)):
        chunk = ordered[max(0, i - window + 1) : i + 1]
        avg: dict[str, float | None] = {}
        for key in ("weight_kg", "body_fat_pct", "skeletal_muscle_kg", "lean_mass_kg"):
            vals = [getattr(s, key) for s in chunk if getattr(s, key) is not None]
            avg[key] = round(statistics.fmean(vals), 2) if vals else None
        avg["n"] = len(chunk)
        out.append((ordered[i].scanned_at, avg))
    return out


def smoothed_weight(weighs: list[Weigh], alpha: float = 0.1) -> list[tuple[date, float]]:
    """Exponential moving average of daily weight, so one salty day does not
    move the trend line. alpha 0.1 gives roughly a 7-day feel."""
    ordered = sorted(weighs, key=lambda w: w.day)
    out: list[tuple[date, float]] = []
    ema: float | None = None
    for w in ordered:
        ema = w.weight_kg if ema is None else alpha * w.weight_kg + (1 - alpha) * ema
        out.append((w.day, round(ema, 2)))
    return out


@dataclass
class GainQuality:
    value: float | None            # fraction of weight gain that was skeletal muscle
    delta_weight_kg: float | None
    delta_muscle_kg: float | None
    weeks: float | None
    n_scans: int
    reason: str | None = None


def gain_quality(scans: list[Scan], weeks: int = 4) -> GainQuality:
    """Change in skeletal muscle divided by change in weight over `weeks`.

    Answers whether the bulk is lean. Guards the two ways this goes wrong:
    fewer than two scans, and a weight change near zero (where the ratio
    explodes and means nothing).
    """
    usable = sorted(
        [s for s in scans if s.weight_kg is not None and s.skeletal_muscle_kg is not None],
        key=lambda s: s.scanned_at,
    )
    if len(usable) < 2:
        return GainQuality(None, None, None, None, len(usable),
                           f"needs 2 scans with weight and muscle, have {len(usable)}")

    latest = usable[-1]
    cutoff = latest.scanned_at - timedelta(weeks=weeks)
    earlier = [s for s in usable[:-1] if s.scanned_at <= cutoff]
    baseline_scan = earlier[-1] if earlier else usable[0]

    d_weight = latest.weight_kg - baseline_scan.weight_kg
    d_muscle = latest.skeletal_muscle_kg - baseline_scan.skeletal_muscle_kg
    span_weeks = round((latest.scanned_at - baseline_scan.scanned_at).days / 7.0, 1)

    if abs(d_weight) < 0.3:
        return GainQuality(None, round(d_weight, 2), round(d_muscle, 2), span_weeks, len(usable),
                           f"weight change {d_weight:+.2f}kg is inside scan noise, ratio not meaningful")

    return GainQuality(round(d_muscle / d_weight, 3), round(d_weight, 2),
                       round(d_muscle, 2), span_weeks, len(usable))


@dataclass
class RateVsTarget:
    weekly_kg: float | None
    weekly_pct_bw: float | None
    in_band: bool | None
    band_pct: tuple[float, float] | None
    reason: str | None = None


def weekly_rate(weighs: list[Weigh], band_pct: tuple[float, float] = (0.0025, 0.005),
                window_days: int = 28) -> RateVsTarget:
    """Weekly weight change as a fraction of bodyweight, against a target band.

    Computed on the smoothed series over `window_days` so it reflects a trend
    rather than the gap between two arbitrary mornings.
    """
    sm = smoothed_weight(weighs)
    if len(sm) < 2:
        return RateVsTarget(None, None, None, band_pct, "need at least 2 weigh-ins")

    latest_day, latest_w = sm[-1]
    cutoff = latest_day - timedelta(days=window_days)
    earlier = [(d, w) for d, w in sm if d <= cutoff]
    if not earlier:
        earlier = [sm[0]]
    base_day, base_w = earlier[-1]

    days = (latest_day - base_day).days
    if days < 7:
        return RateVsTarget(None, None, None, band_pct,
                            f"only {days} days of span, need 7 or more")

    weekly_kg = (latest_w - base_w) / (days / 7.0)
    weekly_pct = weekly_kg / latest_w
    lo, hi = band_pct
    return RateVsTarget(round(weekly_kg, 3), round(weekly_pct, 5),
                        lo <= weekly_pct <= hi, band_pct)


def project_target_date(weighs: list[Weigh], target_kg: float) -> tuple[date, float] | None:
    """Date the smoothed trend reaches target_kg at the current rate.

    Returns None when the trend is flat or moving away from the target: a
    projection that says "never" is more honest than one that says 2041.
    """
    rate = weekly_rate(weighs)
    if rate.weekly_kg is None or abs(rate.weekly_kg) < 0.01:
        return None
    sm = smoothed_weight(weighs)
    latest_day, latest_w = sm[-1]
    gap = target_kg - latest_w
    if gap == 0:
        return (latest_day, 0.0)
    weeks = gap / rate.weekly_kg
    if weeks < 0:
        return None            # moving the wrong way
    return (latest_day + timedelta(weeks=weeks), round(weeks, 1))


def conditions_mismatch(scans: list[Scan]) -> list[date]:
    """Scan dates whose conditions differ from the modal conditions.

    Hydration and time of day move Evolt readings more than a week of training
    does, so a scan taken under different conditions is flagged rather than
    trended as if it were comparable.
    """
    keyed = [(s.scanned_at, tuple(sorted((s.conditions or {}).items()))) for s in scans]
    present = [k for _, k in keyed if k]
    if len(present) < 2:
        return []
    modal = statistics.mode(present)
    return [d for d, k in keyed if k and k != modal]
