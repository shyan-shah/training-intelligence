-- Seed values. Sourced, with provenance, from live data audited 2026-11-01.
--
--   ftp_w          213   Strava, manually set by athlete (not estimated)
--   max_hr         207   implied by Strava MaxHeartRate zone 5 floor of 208
--   threshold_pace 240   ESTIMATE from a measured 18:16 5k. Replace with a
--                        real threshold test before trusting run TSS.
--   lthr           null  NO SOURCE. Strava does not expose it and the Garmin
--                        Personal tier does not either. HR-fallback TSS stays
--                        disabled until this is set.
--   css_swim       null  NO SOURCE. Needs a 400/200 CSS test. Swim TSS stays
--                        disabled until then (only 2 swims in 90 days anyway).
--
-- targets.protein_g is set to the Evolt scan prescription (216g). Note this
-- conflicts with the 150-170g target recorded in the Vault; see README
-- "Conflicts to resolve".

insert into athlete_settings (user_id, ftp_w, threshold_pace, css_swim, lthr, max_hr, zones, targets, thresholds)
values (
  auth.uid(),
  213,
  240,
  null,
  null,
  207,
  jsonb_build_object(
    'hr',    jsonb_build_array(0, 139, 174, 191, 208),
    'power', jsonb_build_array(0, 118, 161, 193, 225, 257, 321),
    'source', 'strava_2026_11_01'
  ),
  jsonb_build_object(
    'protein_g',        216,
    'kcal',             2874,
    'kcal_max',         2974,
    'gym_per_week',     4,
    'sleep_hours',      7.5,
    'sleep_score',      75,
    'weight_band_kg',   jsonb_build_array(68, 70),
    'weight_band_by',   '2026-12-31',
    'weekly_gain_pct',  jsonb_build_array(0.0025, 0.005)
  ),
  jsonb_build_object(
    'hrv_baseline_days',   60,
    'hrv_rolling_days',    7,
    'rhr_baseline_days',   30,
    'rhr_flag_bpm',        5,
    'acwr_push_max',       1.2,
    'acwr_band',           jsonb_build_array(0.8, 1.3),
    'acwr_backoff',        1.5,
    'tsb_push_min',        -10,
    'tsb_backoff',         -30,
    'sleep_push_min',      75,
    'ctl_ramp_max',        6,
    'dedupe_window_s',     300,
    'insight_min_n',       14,
    'readiness_weights',   jsonb_build_object('hrv',0.35,'sleep',0.25,'rhr',0.15,'tsb',0.15,'checkin',0.10)
  )
)
on conflict (user_id) do update set
  ftp_w = excluded.ftp_w,
  max_hr = excluded.max_hr,
  zones = excluded.zones,
  targets = excluded.targets,
  thresholds = excluded.thresholds,
  updated_at = now();
