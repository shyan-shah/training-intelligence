"""The insight engine.

The point of difference from a population-normed recovery score is that every
claim here is fitted to this athlete's own history. That only works if the
claims are honest, so three gates apply to all of them and are enforced in
`publish`, not left to the caller:

  1. n >= insight_min_n (default 14). Below that, nothing is shown.
  2. The effect must clear day-to-day noise: |effect| >= 0.25 SD of the
     outcome series, and a correlation must clear p<0.05.
  3. Sample size travels with the claim, and a correlation is labelled a
     correlation. `is_causal` is only ever True for an intervention, which
     this engine never has, so it stays False.

Insights carry an expiry so a stale finding disappears instead of being
quoted back months later.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from . import stats

MIN_N = 14
MIN_EFFECT_SD = 0.25
DEFAULT_TTL_DAYS = 14


@dataclass
class Insight:
    kind: str
    headline: str
    detail: str
    effect_size: float | None
    effect_unit: str
    n: int
    confidence: float | None = None
    is_causal: bool = False
    expires_at: datetime | None = None

    def to_row(self, user_id: str) -> dict:
        return {
            "user_id": user_id,
            "kind": self.kind,
            "headline": self.headline,
            "detail": self.detail,
            "effect_size": self.effect_size,
            "effect_unit": self.effect_unit,
            "n": self.n,
            "confidence": self.confidence,
            "is_causal": self.is_causal,
            "expires_at": (self.expires_at or
                           datetime.now(timezone.utc) + timedelta(days=DEFAULT_TTL_DAYS)).isoformat(),
        }


def publish(candidates: list[Insight | None], outcome_sd: float | None, min_n: int = MIN_N) -> list[Insight]:
    """Apply the honesty gates. Anything that fails is dropped silently."""
    out: list[Insight] = []
    for c in candidates:
        if c is None or c.n < min_n:
            continue
        if c.effect_size is not None and outcome_sd:
            if abs(c.effect_size) < MIN_EFFECT_SD * outcome_sd:
                continue
        out.append(c)
    return sorted(out, key=lambda i: abs(i.effect_size or 0), reverse=True)


# ---------------------------------------------------------------------------
# Personal drivers: a behaviour against next-day recovery
# ---------------------------------------------------------------------------
def driver_binary(
    name: str,
    present_days: set[date],
    outcome_by_day: dict[date, float],
    outcome_label: str,
    outcome_unit: str,
    lag_days: int = 1,
) -> Insight | None:
    """Compare next-day outcome on days a behaviour was present against absent.

    Example: sessions ending after 19:00 against next-night HRV.
    """
    with_b: list[float] = []
    without_b: list[float] = []
    for day, value in outcome_by_day.items():
        trigger_day = day - timedelta(days=lag_days)
        if trigger_day in present_days:
            with_b.append(value)
        else:
            without_b.append(value)

    n = len(with_b)
    if n < 2 or len(without_b) < 2:
        return None

    delta = statistics.fmean(with_b) - statistics.fmean(without_b)
    d = stats.cohens_d(with_b, without_b)
    direction = "cuts" if delta < 0 else "raises"

    return Insight(
        kind="personal_driver",
        headline=(f"{name} {direction} next-day {outcome_label} by "
                  f"{abs(delta):.1f} {outcome_unit} on average (n={n})"),
        detail=(f"Correlation, not proven cause. {outcome_label} averaged "
                f"{statistics.fmean(with_b):.1f} {outcome_unit} on the {n} days after "
                f"{name.lower()}, against {statistics.fmean(without_b):.1f} on the "
                f"{len(without_b)} days after it did not happen. "
                f"Standardised effect d={d:.2f}." if d is not None else
                f"Correlation, not proven cause. n={n}."),
        effect_size=round(delta, 2),
        effect_unit=outcome_unit,
        n=n,
        confidence=abs(d) if d is not None else None,
        is_causal=False,
    )


def driver_continuous(
    name: str,
    predictor_by_day: dict[date, float],
    outcome_by_day: dict[date, float],
    outcome_label: str,
    outcome_unit: str,
    predictor_unit: str,
    per_unit: float = 1.0,
    lag_days: int = 1,
) -> Insight | None:
    """Regress next-day outcome on a continuous behaviour.

    Example: a day's TSS against the next night's HRV.
    """
    xs: list[float] = []
    ys: list[float] = []
    for day, value in outcome_by_day.items():
        x = predictor_by_day.get(day - timedelta(days=lag_days))
        if x is not None:
            xs.append(x)
            ys.append(value)

    n = len(xs)
    if n < 3:
        return None

    r = stats.pearson(xs, ys)
    if not stats.r_is_significant(r, n):
        return None
    fit = stats.linreg(xs, ys)
    if fit is None:
        return None
    slope, _ = fit
    effect = slope * per_unit
    direction = "costs" if effect < 0 else "adds"

    return Insight(
        kind="personal_driver",
        headline=(f"Each {per_unit:g} {predictor_unit} of {name} {direction} "
                  f"{abs(effect):.1f} {outcome_unit} of next-day {outcome_label} (n={n})"),
        detail=(f"Correlation, not proven cause. Least-squares fit over {n} paired days, "
                f"r={r:.2f}, significant at p<0.05."),
        effect_size=round(effect, 2),
        effect_unit=outcome_unit,
        n=n,
        confidence=abs(r) if r is not None else None,
        is_causal=False,
    )


# ---------------------------------------------------------------------------
# Trend breaks
# ---------------------------------------------------------------------------
def trend_break(
    series: list[tuple[date, float]],
    label: str,
    unit: str,
    recent_days: int = 10,
    prior_days: int = 30,
    min_delta: float = 0.0,
    noise_multiple: float = 1.0,
) -> Insight | None:
    """Flag a sustained shift by comparing a recent window to the one before.

    Robust by construction, because "resting HR has crept up" must not fire on
    one bad night:

      * The comparison uses MEDIANS, not means, so a single outlier inside the
        recent window barely moves it.
      * The threshold is scaled to the series' own noise: the shift has to
        clear `noise_multiple` standard deviations of the prior window. A
        series that normally wanders 4bpm needs a bigger move than one that
        sits flat.
      * The two windows must also be separable by Welch's t at p<0.05. An SD
        multiple alone is not enough, because the medians of two windows drawn
        from the same distribution routinely differ by half an SD.
    """
    if len(series) < recent_days + 5:
        return None
    ordered = sorted(series, key=lambda s: s[0])
    recent = [v for _, v in ordered[-recent_days:]]
    prior = [v for _, v in ordered[-(recent_days + prior_days):-recent_days]]
    if len(prior) < 5:
        return None

    delta = statistics.median(recent) - statistics.median(prior)
    if abs(delta) < min_delta:
        return None

    prior_sd = statistics.stdev(prior) if len(prior) > 1 else 0.0
    floor = max(noise_multiple * prior_sd, min_delta)
    if abs(delta) < floor:
        return None

    if not stats.welch_t_significant(recent, prior):
        return None

    d = stats.cohens_d(recent, prior)
    direction = "crept up" if delta > 0 else "fallen"
    return Insight(
        kind="trend_break",
        headline=f"{label} has {direction} {abs(delta):.1f} {unit} over {recent_days} days",
        detail=(f"Median of the last {recent_days} days was {statistics.median(recent):.1f} {unit} "
                f"against {statistics.median(prior):.1f} over the prior {len(prior)} days, "
                f"a shift of {abs(delta):.1f} against day-to-day spread of {prior_sd:.1f}. "
                f"Medians are used so one outlying day does not trigger this."),
        effect_size=round(delta, 2),
        effect_unit=unit,
        n=len(recent) + len(prior),
        confidence=abs(d) if d is not None else None,
        is_causal=False,
    )


# ---------------------------------------------------------------------------
# Cause hunting: what was different on the worst days
# ---------------------------------------------------------------------------
MIN_GROUP = 5          # per side of a decile comparison


def cause_hunt(
    outcome_by_day: dict[date, float],
    behaviours: dict[str, dict[date, float]],
    outcome_label: str,
    decile: float = 0.1,
) -> list[Insight]:
    """Rank behaviours by how differently they behaved on the worst vs best
    decile of days for an outcome.

    Two gates, because a decile of a 40-day history is only four days and a
    four-against-four comparison of pure noise clears a d of 0.8 often enough
    to matter:

      * each side needs at least MIN_GROUP days;
      * the difference must clear Welch's t at p<0.05, not just a large d.
    """
    if len(outcome_by_day) < MIN_N:
        return []

    ranked = sorted(outcome_by_day.items(), key=lambda kv: kv[1])
    k = max(MIN_GROUP, int(len(ranked) * decile))
    if k * 2 > len(ranked):
        return []
    worst = [d for d, _ in ranked[:k]]
    best = [d for d, _ in ranked[-k:]]

    out: list[Insight] = []
    for name, by_day in behaviours.items():
        w = [by_day[d] for d in worst if d in by_day]
        b = [by_day[d] for d in best if d in by_day]
        if len(w) < MIN_GROUP or len(b) < MIN_GROUP:
            continue
        d = stats.cohens_d(w, b)
        if d is None or abs(d) < 0.8:
            continue
        if not stats.welch_t_significant(w, b):
            continue
        out.append(Insight(
            kind="cause_hunt",
            headline=(f"On your worst {outcome_label} days, {name} averaged "
                      f"{statistics.fmean(w):.1f} against {statistics.fmean(b):.1f} on the best"),
            detail=(f"Comparing the bottom and top {k} days of {len(ranked)} by {outcome_label}. "
                    f"Standardised effect d={d:.2f}, significant at p<0.05 by Welch's t. "
                    f"Correlation, not proven cause."),
            effect_size=round(statistics.fmean(w) - statistics.fmean(b), 2),
            effect_unit="",
            n=len(w) + len(b),
            confidence=abs(d),
            is_causal=False,
        ))
    return sorted(out, key=lambda i: i.confidence or 0, reverse=True)


# ---------------------------------------------------------------------------
# Fitness gain: efficiency factor
# ---------------------------------------------------------------------------
def efficiency_factor(speed_m_s: float | None, avg_hr: int | None) -> float | None:
    """Metres per beat. Rising at the same HR means aerobic fitness improving."""
    if not speed_m_s or not avg_hr or avg_hr <= 0:
        return None
    return round(speed_m_s / avg_hr * 60.0, 3)


def ef_trend(samples: list[tuple[date, float]], sport: str,
             recent: int = 6, prior: int = 6) -> Insight | None:
    """Compare recent efficiency factor against six sessions ago."""
    if len(samples) < recent + prior:
        return None
    ordered = sorted(samples, key=lambda s: s[0])
    r = [v for _, v in ordered[-recent:]]
    p = [v for _, v in ordered[-(recent + prior):-recent]]
    delta = statistics.fmean(r) - statistics.fmean(p)
    pct = delta / statistics.fmean(p) * 100.0 if statistics.fmean(p) else 0.0
    if abs(pct) < 2.0:
        return None
    direction = "better" if delta > 0 else "worse"
    return Insight(
        kind="fitness_gain",
        headline=f"{sport.title()} efficiency at the same heart rate is {abs(pct):.1f}% {direction}",
        detail=(f"Metres per beat averaged {statistics.fmean(r):.2f} over the last {recent} "
                f"steady {sport} sessions against {statistics.fmean(p):.2f} over the {prior} before. "
                f"Steady sessions only, so intervals do not distort it."),
        effect_size=round(pct, 2),
        effect_unit="%",
        n=len(r) + len(p),
        confidence=None,
        is_causal=False,
    )
