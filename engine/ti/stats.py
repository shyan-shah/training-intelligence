"""Small statistics helpers. Pure stdlib so the engine has no scipy dependency
and the tests run anywhere.
"""
from __future__ import annotations

import math
import statistics

# Two-tailed t critical values at p=0.05, by degrees of freedom. Used to gate
# whether a correlation is worth showing. Approximate above df 30.
_T_CRIT_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056,
    27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def t_crit_95(df: int) -> float:
    if df <= 0:
        return float("inf")
    if df in _T_CRIT_95:
        return _T_CRIT_95[df]
    if df <= 40:
        return 2.021
    if df <= 60:
        return 2.000
    if df <= 120:
        return 1.980
    return 1.960


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson r. None when either series is constant or n < 3."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def r_is_significant(r: float | None, n: int) -> bool:
    """Whether r clears p<0.05 on a two-tailed t test."""
    if r is None or n < 3 or abs(r) >= 1.0:
        return abs(r or 0) >= 1.0 and n >= 3
    df = n - 2
    t = abs(r) * math.sqrt(df / (1 - r * r))
    return t > t_crit_95(df)


def linreg(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """Ordinary least squares, returning (slope, intercept)."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    return slope, my - slope * mx


# Cap for a completely separated comparison. When both groups have zero
# variance the standardised effect is formally infinite; returning None there
# would silently discard a perfect signal, and returning inf would break JSON
# serialisation, so it is capped and signed.
D_CAP = 10.0


def cohens_d(a: list[float], b: list[float]) -> float | None:
    """Standardised difference between two groups.

    Returns None only when a group is too small to have a spread at all. Zero
    pooled variance is handled explicitly: identical means give 0.0, differing
    means give +/- D_CAP.
    """
    if len(a) < 2 or len(b) < 2:
        return None
    sa, sb = statistics.stdev(a), statistics.stdev(b)
    pooled = math.sqrt(((len(a) - 1) * sa**2 + (len(b) - 1) * sb**2) / (len(a) + len(b) - 2))
    diff = statistics.fmean(a) - statistics.fmean(b)
    if pooled == 0:
        if diff == 0:
            return 0.0
        return D_CAP if diff > 0 else -D_CAP
    return diff / pooled


def welch_t_significant(a: list[float], b: list[float]) -> bool:
    """Whether two groups differ at p<0.05 by Welch's t test.

    Used to gate decile comparisons, where group sizes are small enough that a
    large standardised effect can appear from noise alone.
    """
    if len(a) < 2 or len(b) < 2:
        return False
    va, vb = statistics.variance(a), statistics.variance(b)
    na, nb = len(a), len(b)
    se2 = va / na + vb / nb
    if se2 <= 0:
        return statistics.fmean(a) != statistics.fmean(b)
    t = abs(statistics.fmean(a) - statistics.fmean(b)) / math.sqrt(se2)
    num = se2**2
    den = (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)
    df = int(num / den) if den > 0 else min(na, nb) - 1
    return t > t_crit_95(max(df, 1))
