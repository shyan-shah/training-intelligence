export type DailyLoad = {
  day: string;
  tss: number | null;
  ctl: number | null;
  atl: number | null;
  tsb: number | null;
  acwr: number | null;
  acwr_ewma: number | null;
  ctl_ramp_7d: number | null;
  by_sport: Record<string, number>;
};

export type DailyReadiness = {
  day: string;
  score: number | null;
  band: string;
  components: Record<string, { subscore: number | null; weight: number }>;
  drivers: { component: string; subscore: number; contribution: number }[];
  cold_start: boolean;
};

export type GarminDaily = {
  day: string;
  sleep_score: number | null;
  sleep_total_min: number | null;
  sleep_deep_min: number | null;
  sleep_rem_min: number | null;
  sleep_onset_min: number | null;
  hrv_night: number | null;
  hrv_7d: number | null;
  rhr: number | null;
  body_battery_max: number | null;
  body_battery_min: number | null;
  stress_avg: number | null;
  steps: number | null;
  readiness: number | null;
  training_status: string | null;
  vo2max_run: number | null;
  vo2max_bike: number | null;
};

export type EvoltScan = {
  scanned_at: string;
  weight_kg: number | null;
  body_fat_pct: number | null;
  skeletal_muscle_kg: number | null;
  lean_mass_kg: number | null;
  fat_mass_kg: number | null;
  bmr_kcal: number | null;
  tee_kcal: number | null;
  bio_age: number | null;
  bwi: number | null;
  conditions: Record<string, unknown>;
  pdf_path: string | null;
  needs_review: boolean;
  review_reason: string | null;
};

export type Activity = {
  id: string;
  source: string;
  sport: string;
  sport_raw: string | null;
  start_at: string;
  duration_s: number;
  distance_m: number | null;
  avg_hr: number | null;
  avg_power: number | null;
  avg_pace: number | null;
  tss: number | null;
  tss_method: string | null;
  is_valid: boolean;
  invalid_reason: string | null;
  is_primary: boolean;
};

export type WeeklyReport = {
  iso_year: number;
  iso_week: number;
  verdict: "push" | "hold" | "back_off";
  metrics: Record<string, unknown>;
  watch_flags: string[];
  narrative: string | null;
};

export type Insight = {
  id: string;
  kind: string;
  headline: string;
  detail: string | null;
  effect_size: number | null;
  effect_unit: string | null;
  n: number;
  confidence: number | null;
  is_causal: boolean;
  computed_at: string;
};

export type SyncStatus = {
  source: string;
  last_success: string | null;
  last_attempt: string | null;
  last_error: string | null;
  token_expires_at: string | null;
};

export type Checkin = {
  day: string;
  soreness: number | null;
  energy: number | null;
  mood: number | null;
  niggle_area: string | null;
  niggle_pain: number | null;
  notes: string | null;
};

export type Nutrition = { day: string; kcal: number | null; protein_g: number | null };

export type Settings = {
  ftp_w: number | null;
  threshold_pace: number | null;
  css_swim: number | null;
  lthr: number | null;
  max_hr: number | null;
  zones: Record<string, unknown>;
  targets: Record<string, any>;
  thresholds: Record<string, any>;
};

export type Gear = {
  source_id: string;
  gear_type: string;
  name: string | null;
  brand: string | null;
  model_name: string | null;
  distance_m: number;
  retire_at_m: number | null;
  retired: boolean;
};

export type Scorecard = {
  day: string;
  habits: Record<string, "hit" | "missed" | "no_data">;
};
