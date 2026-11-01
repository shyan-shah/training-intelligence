/**
 * Presentation-layer shaping only: joining persisted series into the row
 * shapes the charts want, and the small amount of smoothing that exists purely
 * for a trend line.
 *
 * No thresholds, verdicts or habit rules live here. Those are computed by the
 * Python engine and persisted, so the page cannot drift from it.
 */
import type {
  DailyLoad, DailyReadiness, EvoltScan, GarminDaily, Scorecard, Activity,
} from "./types";

export function clip<T extends { day: string }>(rows: T[], days: number): T[] {
  const cutoff = new Date();
  cutoff.setUTCDate(cutoff.getUTCDate() - days);
  const iso = cutoff.toISOString().slice(0, 10);
  return rows.filter((r) => r.day >= iso);
}

export function loadRows(loads: DailyLoad[]) {
  return loads.map((l) => ({
    day: l.day,
    ctl: l.ctl,
    atl: l.atl,
    tsb: l.tsb,
    tss: l.tss,
    acwr: l.acwr,
    ctl_ramp_7d: l.ctl_ramp_7d,
  }));
}

export function recoveryRows(daily: GarminDaily[]) {
  return daily.map((d) => ({
    day: d.day,
    hrv: d.hrv_night,
    hrv_7d: d.hrv_7d,
    rhr: d.rhr,
    sleep_score: d.sleep_score,
    sleep_hours: d.sleep_total_min === null ? null : +(d.sleep_total_min / 60).toFixed(2),
    deep: d.sleep_deep_min,
    rem: d.sleep_rem_min,
    body_battery_max: d.body_battery_max,
    body_battery_min: d.body_battery_min,
    stress: d.stress_avg,
  }));
}

/** Trailing mean over `window` non-null values. Used for the HRV 7-day line
 *  when the engine has not stored one. */
export function rollingMean<T extends Record<string, unknown>>(
  rows: T[], key: string, window: number, outKey: string,
): (T & Record<string, number | null>)[] {
  return rows.map((row, i) => {
    const slice = rows
      .slice(Math.max(0, i - window + 1), i + 1)
      .map((r) => r[key])
      .filter((v): v is number => typeof v === "number");
    return {
      ...row,
      [outKey]: slice.length
        ? +(slice.reduce((a, b) => a + b, 0) / slice.length).toFixed(1)
        : null,
    } as T & Record<string, number | null>;
  });
}

/** Mean and SD of the last `days` values, for the HRV baseline band. */
export function baselineBand(
  values: (number | null)[], days: number,
): { lo: number; hi: number; mean: number } | null {
  const clean = values.slice(-days).filter((v): v is number => v !== null);
  if (clean.length < 14) return null;         // same floor as the engine
  const mean = clean.reduce((a, b) => a + b, 0) / clean.length;
  const sd = Math.sqrt(clean.reduce((a, b) => a + (b - mean) ** 2, 0) / (clean.length - 1));
  return { lo: +(mean - sd).toFixed(1), hi: +(mean + sd).toFixed(1), mean: +mean.toFixed(1) };
}

/** Exponential moving average for the weight trend line, alpha 0.1, matching
 *  engine/ti/body.py so the chart and the stated rate agree. */
export function weightRows(scans: EvoltScan[], garminWeights: { day: string; weight_kg: number }[]) {
  const points = [
    ...garminWeights.map((w) => ({ day: w.day, weight: w.weight_kg })),
    ...scans
      .filter((s) => s.weight_kg !== null)
      .map((s) => ({ day: s.scanned_at.slice(0, 10), weight: s.weight_kg as number })),
  ].sort((a, b) => a.day.localeCompare(b.day));

  let ema: number | null = null;
  return points.map((p) => {
    ema = ema === null ? p.weight : 0.1 * p.weight + 0.9 * ema;
    return { day: p.day, weight: p.weight, trend: +ema.toFixed(2) };
  });
}

/** Evolt masses, with a trailing 3-scan average as the trend line.
 *  Body fat percent is deliberately NOT included here: it is a different unit
 *  from kilograms and putting both on one chart would need two y-axes. It gets
 *  its own chart. */
export function compositionRows(scans: EvoltScan[]) {
  const ordered = [...scans].sort((a, b) => a.scanned_at.localeCompare(b.scanned_at));
  return ordered.map((s, i) => {
    const window = ordered.slice(Math.max(0, i - 2), i + 1);
    const avg = (key: keyof EvoltScan) => {
      const vals = window.map((w) => w[key]).filter((v): v is number => typeof v === "number");
      return vals.length ? +(vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2) : null;
    };
    return {
      day: s.scanned_at.slice(0, 10),
      muscle: s.skeletal_muscle_kg,
      fat: s.fat_mass_kg,
      muscle_avg: avg("skeletal_muscle_kg"),
      fat_avg: avg("fat_mass_kg"),
    };
  });
}

export function bodyFatRows(scans: EvoltScan[]) {
  const ordered = [...scans].sort((a, b) => a.scanned_at.localeCompare(b.scanned_at));
  return ordered.map((s, i) => {
    const window = ordered.slice(Math.max(0, i - 2), i + 1)
      .map((w) => w.body_fat_pct)
      .filter((v): v is number => typeof v === "number");
    return {
      day: s.scanned_at.slice(0, 10),
      body_fat_pct: s.body_fat_pct,
      body_fat_avg: window.length
        ? +(window.reduce((a, b) => a + b, 0) / window.length).toFixed(2)
        : null,
    };
  });
}

/** Weekly TSS by sport, for the stacked bars on the Week and Load tabs. */
export function weeklyBySport(loads: DailyLoad[], weeks = 8) {
  const buckets = new Map<string, Record<string, number>>();
  loads.forEach((l) => {
    const d = new Date(l.day);
    const monday = new Date(d);
    monday.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    const key = monday.toISOString().slice(0, 10);
    const bucket = buckets.get(key) ?? { run: 0, bike: 0, swim: 0, strength: 0 };
    Object.entries(l.by_sport ?? {}).forEach(([sport, tss]) => {
      if (sport in bucket) bucket[sport] += Number(tss) || 0;
    });
    buckets.set(key, bucket);
  });

  return [...buckets.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .slice(-weeks)
    .map(([monday, v]) => ({
      label: new Date(monday).toLocaleDateString("en-GB", { day: "numeric", month: "short" }),
      day: monday,
      run: +v.run.toFixed(1),
      bike: +v.bike.toFixed(1),
      swim: +v.swim.toFixed(1),
      strength: +v.strength.toFixed(1),
    }));
}

/** Pivot the persisted scorecard into one series per habit. */
export function habitSeries(scorecard: Scorecard[]) {
  const keys = new Set<string>();
  scorecard.forEach((r) => Object.keys(r.habits ?? {}).forEach((k) => keys.add(k)));

  return [...keys].map((key) => {
    const days = scorecard.map((r) => ({ day: r.day, state: r.habits?.[key] ?? "no_data" }));

    let best = 0;
    let run = 0;
    days.forEach((d) => {
      if (d.state === "hit") { run += 1; best = Math.max(best, run); }
      else if (d.state === "missed") run = 0;
    });

    let current = 0;
    for (let i = days.length - 1; i >= 0; i--) {
      if (days[i].state === "hit") current += 1;
      else if (days[i].state === "missed") break;
    }

    const weekStart = (() => {
      const d = new Date();
      d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
      return d.toISOString().slice(0, 10);
    })();
    const week = days.filter((d) => d.day >= weekStart);
    const weekHits = week.filter((d) => d.state === "hit").length;
    const weekPossible = week.filter((d) => d.state !== "no_data").length;

    return {
      key,
      days,
      currentStreak: current,
      bestStreak: best,
      weekHits,
      completion: weekPossible ? weekHits / weekPossible : null,
    };
  });
}

export const HABIT_LABELS: Record<string, string> = {
  protein: "Protein target",
  kcal: "Calorie target",
  gym: "Gym session",
  sleep_duration: "Sleep 7.5h+",
  sleep_quality: "Sleep score 75+",
  checkin: "Daily check-in",
  evolt: "Weekly Evolt scan",
};

export const HABIT_WEEKLY_TARGET: Record<string, number | null> = {
  gym: 4, evolt: 1,
};

/** Metres per beat on steady sessions, for the Performance tab. */
export function efficiencyRows(activities: Activity[], sport: string) {
  return activities
    .filter((a) => a.sport === sport && a.avg_hr && a.distance_m && a.duration_s && a.is_primary && a.is_valid)
    .map((a) => ({
      day: a.start_at.slice(0, 10),
      ef: +((a.distance_m! / a.duration_s) / a.avg_hr! * 60).toFixed(3),
    }))
    .sort((a, b) => a.day.localeCompare(b.day));
}
