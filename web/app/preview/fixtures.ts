/**
 * Fixture data for the design preview route. Never imported by the real page.
 *
 * Shaped to match the audited reality rather than an idealised athlete: one
 * Evolt scan, sparse running, a gym habit running at about one session a week
 * against a target of four, and HRV around a 60ms baseline. If the design only
 * looks right on dense data it is the wrong design.
 */
import type { TrainingData } from "@/lib/queries";

const DAYS = 120;
const END = new Date("2026-11-01T00:00:00Z");

function iso(offset: number): string {
  const d = new Date(END);
  d.setUTCDate(d.getUTCDate() - offset);
  return d.toISOString().slice(0, 10);
}

// Deterministic pseudo-random so the preview is stable across runs.
function rand(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

const daily = Array.from({ length: DAYS }, (_, i) => {
  const offset = DAYS - 1 - i;
  const r = rand(i + 1);
  const r2 = rand(i + 97);
  const drift = Math.sin(i / 17) * 4;
  return {
    day: iso(offset),
    hrv_night: Math.round(60 + drift + (r - 0.5) * 9),
    hrv_7d: null,
    sleep_score: Math.round(74 + Math.sin(i / 9) * 9 + (r2 - 0.5) * 10),
    sleep_total_min: Math.round(430 + Math.sin(i / 11) * 45 + (r - 0.5) * 60),
    sleep_deep_min: Math.round(70 + (r - 0.5) * 24),
    sleep_rem_min: Math.round(95 + (r2 - 0.5) * 30),
    sleep_onset_min: Math.round(1385 + (r - 0.5) * 70),
    rhr: Math.round(49 + Math.sin(i / 23) * 2.5 + (r2 - 0.5) * 3),
    body_battery_max: Math.round(82 + (r - 0.5) * 16),
    body_battery_min: Math.round(22 + (r2 - 0.5) * 14),
    stress_avg: Math.round(31 + (r - 0.5) * 18),
    steps: Math.round(8200 + (r2 - 0.5) * 5000),
    readiness: Math.round(68 + (r - 0.5) * 22),
    training_status: "maintaining",
    vo2max_run: 54 + Math.floor(i / 60) * 0.5,
    vo2max_bike: 49,
  };
});

// Load: realistic sparse sessions, not a daily grind.
let ctl = 22;
let atl = 20;
const loads = Array.from({ length: DAYS }, (_, i) => {
  const offset = DAYS - 1 - i;
  const r = rand(i + 500);
  const trains = r > 0.45;
  const tss = trains ? Math.round(28 + r * 95) : 0;
  const tsb = ctl - atl;
  ctl = ctl + (tss - ctl) / 42;
  atl = atl + (tss - atl) / 7;
  const sport = !trains ? {} :
    r > 0.8 ? { run: tss } :
    r > 0.65 ? { bike: tss } :
    r > 0.6 ? { swim: tss } : { strength: tss };
  return {
    day: iso(offset),
    tss,
    ctl: +ctl.toFixed(2),
    atl: +atl.toFixed(2),
    tsb: +tsb.toFixed(2),
    acwr: i < 28 ? null : +(0.95 + Math.sin(i / 13) * 0.3).toFixed(2),
    acwr_ewma: +(atl / ctl).toFixed(2),
    ctl_ramp_7d: +(Math.sin(i / 19) * 3).toFixed(2),
    by_sport: sport as Record<string, number>,
  };
});

const readiness = daily.map((d, i) => {
  const score = Math.max(28, Math.min(92, 64 + Math.sin(i / 14) * 16 + (rand(i + 11) - 0.5) * 14));
  return {
    day: d.day,
    score: +score.toFixed(1),
    band: score >= 70 ? "green" : score >= 50 ? "amber" : "red",
    components: {
      hrv: { subscore: 62, weight: 0.35 },
      sleep: { subscore: 74, weight: 0.25 },
      rhr: { subscore: 48, weight: 0.15 },
      tsb: { subscore: 58, weight: 0.15 },
      checkin: { subscore: 70, weight: 0.1 },
    },
    drivers: [
      { component: "sleep", subscore: 74, contribution: 6.1 },
      { component: "hrv", subscore: 42, contribution: -2.9 },
      { component: "rhr", subscore: 48, contribution: -0.3 },
    ],
    cold_start: false,
  };
});

const HABITS = ["protein", "kcal", "gym", "sleep_duration", "sleep_quality", "checkin", "evolt"];

const scorecard = daily.map((d, i) => ({
  day: d.day,
  habits: Object.fromEntries(
    HABITS.map((h) => {
      const r = rand(i * 7 + h.length * 31);
      // Gym runs at roughly one session a week against a target of four, which
      // is what the audit actually found.
      const hitRate = h === "gym" ? 0.18 : h === "evolt" ? 0.05 : h === "protein" ? 0.42 : 0.62;
      const state = r < 0.06 ? "no_data" : r < 0.06 + hitRate ? "hit" : "missed";
      return [h, state];
    }),
  ) as Record<string, "hit" | "missed" | "no_data">,
}));

export const FIXTURES: TrainingData = {
  loads,
  readiness,
  daily,
  scorecard,
  scans: [
    {
      scanned_at: "2026-09-13T09:30:00Z",
      weight_kg: 66.7,
      body_fat_pct: 14.1,
      skeletal_muscle_kg: 32.0,
      lean_mass_kg: 57.3,
      fat_mass_kg: 9.4,
      bmr_kcal: 1607,
      tee_kcal: 2474,
      bio_age: 19,
      bwi: 8.6,
      conditions: { time_of_day: "morning", fasted: true },
      pdf_path: "u/scan-2026-09-13.pdf",
      needs_review: false,
      review_reason: null,
    },
  ],
  activities: Array.from({ length: 26 }, (_, i) => {
    const r = rand(i + 3000);
    const sport = r > 0.62 ? "run" : r > 0.4 ? "strength" : r > 0.2 ? "bike" : "walk";
    const dur = Math.round(1800 + r * 2400);
    const dist = sport === "strength" ? null : Math.round(dur * (sport === "bike" ? 5.4 : 3.0));
    return {
      id: `a${i}`,
      source: "strava",
      sport,
      sport_raw: sport,
      start_at: `${iso(i * 4)}T11:20:00Z`,
      duration_s: dur,
      distance_m: dist,
      avg_hr: Math.round(142 + r * 22),
      avg_power: sport === "bike" ? Math.round(170 + r * 40) : null,
      avg_pace: dist ? +(dur / (dist / 1000)).toFixed(1) : null,
      tss: Math.round(30 + r * 70),
      tss_method: sport === "bike" ? "power" : sport === "run" ? "pace" : "fixed",
      is_valid: true,
      invalid_reason: null,
      is_primary: true,
    };
  }),
  weekly: [
    {
      iso_year: 2026,
      iso_week: 44,
      verdict: "hold",
      metrics: {
        acwr: 1.12,
        week_tss_change_pct: -8,
        checks: [
          { name: "hrv_inside", passed: true, value: "inside", threshold: "inside baseline band" },
          { name: "tsb_ok", passed: true, value: -4.2, threshold: "> -10" },
          { name: "acwr_ok", passed: true, value: 1.12, threshold: "<= 1.2" },
          { name: "sleep_ok", passed: false, value: 71.4, threshold: ">= 75" },
        ],
        unavailable: [],
      },
      watch_flags: [
        "HRV dipped below band on 2 of the last 7 nights",
        "Resting HR flagged on 1 of the last 7 days",
      ],
      narrative:
        "Hold. Sleep score 7d mean 71.4 against 75. Everything else is inside its limit.",
    },
  ],
  insights: [
    {
      id: "i1",
      kind: "personal_driver",
      headline: "Each 150 TSS of training load costs 5.8 ms of next-day HRV (n=46)",
      detail:
        "Correlation, not proven cause. Least-squares fit over 46 paired days, r=-0.52, significant at p<0.05.",
      effect_size: -5.8,
      effect_unit: "ms",
      n: 46,
      confidence: 0.52,
      is_causal: false,
      computed_at: "2026-11-01T02:12:00Z",
    },
    {
      id: "i2",
      kind: "trend_break",
      headline: "Resting HR has crept up 3.4 bpm over 10 days",
      detail:
        "Median of the last 10 days was 52.1 bpm against 48.7 over the prior 30 days, a shift of 3.4 against day-to-day spread of 1.6. Medians are used so one outlying day does not trigger this.",
      effect_size: 3.4,
      effect_unit: "bpm",
      n: 40,
      confidence: 1.42,
      is_causal: false,
      computed_at: "2026-11-01T02:12:00Z",
    },
  ],
  sync: [
    { source: "garmin_personal", last_success: "2026-11-01T05:17:00Z", last_attempt: "2026-11-01T05:17:00Z", last_error: null, token_expires_at: null },
    { source: "garmin_login", last_success: "2026-11-01T05:18:00Z", last_attempt: "2026-11-01T05:18:00Z", last_error: null, token_expires_at: "2026-11-05T00:00:00Z" },
    { source: "strava", last_success: "2026-11-01T05:19:00Z", last_attempt: "2026-11-01T05:19:00Z", last_error: null, token_expires_at: null },
    { source: "engine", last_success: "2026-11-01T02:12:00Z", last_attempt: "2026-11-01T02:12:00Z", last_error: null, token_expires_at: null },
  ],
  checkins: [],
  nutrition: [],
  settings: {
    ftp_w: 213,
    threshold_pace: 240,
    css_swim: null,
    lthr: null,
    max_hr: 207,
    zones: {},
    targets: {
      protein_g: 216,
      kcal: 2874,
      gym_per_week: 4,
      sleep_hours: 7.5,
      sleep_score: 75,
      weight_band_kg: [68, 70],
    },
    thresholds: { acwr_band: [0.8, 1.3], ctl_ramp_max: 6 },
  },
  gear: [
    { source_id: "30466854", gear_type: "shoe", name: "Evo SL", brand: "Adidas", model_name: "Evo SL", distance_m: 210124, retire_at_m: 700000, retired: false },
    { source_id: "10316661", gear_type: "shoe", name: "zoom fly 4s", brand: "Nike", model_name: "Zoom Fly 4", distance_m: 505787, retire_at_m: 650000, retired: false },
    { source_id: "10504219", gear_type: "shoe", name: "vaporflys", brand: "Nike", model_name: "Vaporfly", distance_m: 331481, retire_at_m: 350000, retired: false },
  ],
  errors: [],
};
