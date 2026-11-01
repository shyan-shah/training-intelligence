"""The weekly verdict: push, hold or back off.

The verdict never ships as a bare label. Every rule that was evaluated comes
back with the number that satisfied or failed it, so the page and the Sunday
push can state why.

Rules, from the brief:
  Push      all of: HRV 7d inside band, TSB > -10, ACWR <= 1.2, sleep 7d >= 75
  Back off  any of: HRV below band on 3+ of last 7 days, ACWR > 1.5,
                    TSB < -30, RHR flagged on 3+ days
  Hold      anything else

Back off is evaluated first: a single hard signal outranks a clean sweep of
the push conditions.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Check:
    name: str
    passed: bool
    value: float | int | str | None
    threshold: str
    detail: str


@dataclass
class Verdict:
    verdict: str                     # push | hold | back_off
    reasons: list[Check] = field(default_factory=list)
    push_checks: list[Check] = field(default_factory=list)
    backoff_checks: list[Check] = field(default_factory=list)
    watch_flags: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)

    def narrative(self) -> str:
        """Rule-based template text. No LLM, per the Garmin terms constraint."""
        head = {
            "push": "Push.",
            "hold": "Hold.",
            "back_off": "Back off.",
        }[self.verdict]
        if self.reasons:
            body = " " + "; ".join(f"{c.detail}" for c in self.reasons) + "."
        else:
            body = " No rule fired either way."
        tail = ""
        if self.unavailable:
            tail = f" Not assessed: {', '.join(self.unavailable)}."
        return head + body + tail


def weekly_verdict(
    hrv_position: str,               # below | inside | above | unknown
    hrv_days_below: int,
    tsb: float | None,
    acwr: float | None,
    sleep_7d: float | None,
    rhr_flag_days: int,
    thresholds: dict | None = None,
) -> Verdict:
    t = {
        "acwr_push_max": 1.2,
        "acwr_backoff": 1.5,
        "tsb_push_min": -10.0,
        "tsb_backoff": -30.0,
        "sleep_push_min": 75.0,
        "hrv_below_days": 3,
        "rhr_flag_days": 3,
        **(thresholds or {}),
    }

    unavailable: list[str] = []
    if hrv_position == "unknown":
        unavailable.append("HRV (no baseline yet)")
    if tsb is None:
        unavailable.append("TSB (insufficient load history)")
    if acwr is None:
        unavailable.append("ACWR (needs 28 days of load)")
    if sleep_7d is None:
        unavailable.append("sleep score")

    # --- back off: any one of these ---------------------------------------
    backoff = [
        Check("hrv_days_below", hrv_days_below >= t["hrv_below_days"], hrv_days_below,
              f">= {t['hrv_below_days']} of last 7",
              f"HRV below baseline band on {hrv_days_below} of the last 7 nights"),
        Check("acwr_high", acwr is not None and acwr > t["acwr_backoff"], acwr,
              f"> {t['acwr_backoff']}",
              f"ACWR {acwr if acwr is not None else 'n/a'} above {t['acwr_backoff']}"),
        Check("tsb_low", tsb is not None and tsb < t["tsb_backoff"], tsb,
              f"< {t['tsb_backoff']}",
              f"TSB {tsb if tsb is not None else 'n/a'} below {t['tsb_backoff']}"),
        Check("rhr_flags", rhr_flag_days >= t["rhr_flag_days"], rhr_flag_days,
              f">= {t['rhr_flag_days']} of last 7",
              f"Resting HR flagged on {rhr_flag_days} of the last 7 days"),
    ]
    fired = [c for c in backoff if c.passed]
    if fired:
        return Verdict("back_off", fired, [], backoff, _watch(backoff, hrv_position), unavailable)

    # --- push: all of these ------------------------------------------------
    push = [
        Check("hrv_inside", hrv_position == "inside", hrv_position, "inside baseline band",
              f"HRV 7d {hrv_position} baseline band"),
        Check("tsb_ok", tsb is not None and tsb > t["tsb_push_min"], tsb,
              f"> {t['tsb_push_min']}",
              f"TSB {tsb if tsb is not None else 'n/a'} against {t['tsb_push_min']} floor"),
        Check("acwr_ok", acwr is not None and acwr <= t["acwr_push_max"], acwr,
              f"<= {t['acwr_push_max']}",
              f"ACWR {acwr if acwr is not None else 'n/a'} against {t['acwr_push_max']} ceiling"),
        Check("sleep_ok", sleep_7d is not None and sleep_7d >= t["sleep_push_min"], sleep_7d,
              f">= {t['sleep_push_min']}",
              f"Sleep score 7d mean {round(sleep_7d, 1) if sleep_7d is not None else 'n/a'} "
              f"against {t['sleep_push_min']}"),
    ]
    if all(c.passed for c in push):
        return Verdict("push", push, push, backoff, _watch(backoff, hrv_position), unavailable)

    failed = [c for c in push if not c.passed]
    return Verdict("hold", failed, push, backoff, _watch(backoff, hrv_position), unavailable)


def _watch(backoff: list[Check], hrv_position: str) -> list[str]:
    """Things not bad enough to change the verdict but worth watching."""
    flags: list[str] = []
    for c in backoff:
        if c.passed:
            continue
        if c.name == "hrv_days_below" and isinstance(c.value, int) and c.value in (1, 2):
            flags.append(f"HRV dipped below band on {c.value} of the last 7 nights")
        if c.name == "rhr_flags" and isinstance(c.value, int) and c.value in (1, 2):
            flags.append(f"Resting HR flagged on {c.value} of the last 7 days")
        if c.name == "acwr_high" and isinstance(c.value, (int, float)) and c.value and c.value > 1.3:
            flags.append(f"ACWR {c.value} above the 1.3 top of band")
    if hrv_position == "above":
        flags.append("HRV above baseline band, check for parasympathetic saturation")
    return flags
