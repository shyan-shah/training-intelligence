-- Training Intelligence :: core schema
-- Grain and key columns follow the build brief. Every table is per-user and
-- RLS-protected in 0002_rls.sql. Nothing here is health-advice logic; this is
-- storage only. All computed values live in 0003_views.sql or are written by
-- the nightly engine.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Athlete settings: the single source of truth for thresholds and targets.
-- Exactly one row. Every threshold the engine uses is read from here so it can
-- be tuned without a deploy.
-- ---------------------------------------------------------------------------
create table if not exists athlete_settings (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null default auth.uid(),
  ftp_w           integer,                 -- cycling FTP, watts
  threshold_pace  numeric,                 -- run threshold, seconds per km
  css_swim        numeric,                 -- critical swim speed, seconds per 100m
  lthr            integer,                 -- lactate threshold HR, bpm
  max_hr          integer,
  zones           jsonb not null default '{}'::jsonb,
  targets         jsonb not null default '{}'::jsonb,
  thresholds      jsonb not null default '{}'::jsonb,
  updated_at      timestamptz not null default now(),
  unique (user_id)
);

-- ---------------------------------------------------------------------------
-- Garmin daily wellness. One row per calendar day.
-- Columns sourced from the login route (readiness, training_status, vo2max,
-- acute_load, chronic_load) are nullable by design: if that token dies these
-- go null and nothing else breaks.
-- ---------------------------------------------------------------------------
create table if not exists garmin_daily (
  user_id           uuid not null default auth.uid(),
  day               date not null,
  sleep_score       integer,
  sleep_total_min   integer,
  sleep_deep_min    integer,
  sleep_rem_min     integer,
  sleep_onset_min   integer,   -- minutes past midnight of sleep onset, for regularity SD
  hrv_night         numeric,
  hrv_7d            numeric,
  rhr               integer,
  body_battery_max  integer,
  body_battery_min  integer,
  stress_avg        integer,
  steps             integer,
  -- login-route only, nullable
  readiness         integer,
  training_status   text,
  vo2max_run        numeric,
  vo2max_bike       numeric,
  acute_load        numeric,
  chronic_load      numeric,
  source            text not null default 'garmin_personal',
  ingested_at       timestamptz not null default now(),
  primary key (user_id, day)
);

-- ---------------------------------------------------------------------------
-- Body weight / composition from Garmin scale or device. One row per weigh-in.
-- ---------------------------------------------------------------------------
create table if not exists garmin_body (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null default auth.uid(),
  measured_at   timestamptz not null,
  weight_kg     numeric,
  body_fat_pct  numeric,
  muscle_mass_kg numeric,
  source        text not null default 'garmin',
  ingested_at   timestamptz not null default now(),
  unique (user_id, measured_at, source)
);

-- ---------------------------------------------------------------------------
-- Activities, one row per session, from Garmin or Strava.
--
-- Audit note: duration_s is MOVING time, not elapsed. Real Strava history
-- contains sessions with elapsed 175,726s against moving 4,678s; TSS computed
-- on elapsed would be nonsense. elapsed_s is kept for the stale-timer check.
--
-- dedupe_group links records judged to be the same real session across
-- sources. is_valid / invalid_reason carry the validation verdict rather than
-- deleting rows, so a rejected session stays auditable.
-- ---------------------------------------------------------------------------
create table if not exists activities (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null default auth.uid(),
  source         text not null,                   -- 'garmin' | 'strava'
  source_id      text not null,                   -- id in that source
  sport          text not null,                   -- normalised: swim|bike|run|strength|other
  sport_raw      text,
  start_at       timestamptz not null,
  duration_s     integer not null,                -- MOVING time
  elapsed_s      integer,
  distance_m     numeric,
  avg_hr         integer,
  max_hr         integer,
  avg_power      numeric,
  np             numeric,
  avg_pace       numeric,                         -- seconds per km
  elevation_m    numeric,
  tss            numeric,
  tss_method     text,                            -- power|pace|hr|swim_css|fixed
  fit_path       text,
  dedupe_group   uuid,
  is_primary     boolean not null default true,   -- false for the losing side of a dedupe
  is_valid       boolean not null default true,
  invalid_reason text,
  ingested_at    timestamptz not null default now(),
  unique (user_id, source, source_id)
);
create index if not exists activities_start_idx on activities (user_id, start_at desc);
create index if not exists activities_sport_idx on activities (user_id, sport, start_at desc);

-- ---------------------------------------------------------------------------
-- Evolt 360 scans. One row per scan.
-- conditions captures time of day / fasted / hydration so a scan taken under
-- different conditions can be flagged rather than silently trended.
-- ---------------------------------------------------------------------------
create table if not exists evolt_scans (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null default auth.uid(),
  scanned_at          timestamptz not null,
  weight_kg           numeric,
  body_fat_pct        numeric,
  skeletal_muscle_kg  numeric,
  lean_mass_kg        numeric,
  fat_mass_kg         numeric,
  visceral_fat_level  numeric,
  bmr_kcal            integer,
  tee_kcal            integer,
  bio_age             numeric,
  bwi                 numeric,
  segmental           jsonb not null default '{}'::jsonb,
  conditions          jsonb not null default '{}'::jsonb,
  pdf_path            text,
  parse_method        text,              -- 'pdfplumber' | 'vision' | 'manual'
  needs_review        boolean not null default false,
  review_reason       text,
  created_at          timestamptz not null default now(),
  unique (user_id, scanned_at)
);

-- ---------------------------------------------------------------------------
-- Daily subjective check-in. One row per day.
-- ---------------------------------------------------------------------------
create table if not exists daily_checkin (
  user_id      uuid not null default auth.uid(),
  day          date not null,
  soreness     smallint check (soreness between 1 and 5),
  energy       smallint check (energy between 1 and 5),
  mood         smallint check (mood between 1 and 5),
  niggle_area  text,
  niggle_pain  smallint check (niggle_pain between 0 and 10),
  notes        text,
  created_at   timestamptz not null default now(),
  primary key (user_id, day)
);

-- ---------------------------------------------------------------------------
-- Nutrition. One row per day.
-- ---------------------------------------------------------------------------
create table if not exists nutrition_daily (
  user_id    uuid not null default auth.uid(),
  day        date not null,
  kcal       integer,
  protein_g  numeric,
  source     text not null default 'manual',
  created_at timestamptz not null default now(),
  primary key (user_id, day)
);

-- ---------------------------------------------------------------------------
-- Engine outputs. Written nightly, never by hand. Every row carries the
-- inputs that produced it so a number on the page can be traced to a formula.
-- ---------------------------------------------------------------------------
create table if not exists daily_load (
  user_id     uuid not null default auth.uid(),
  day         date not null,
  tss         numeric not null default 0,
  ctl         numeric,
  atl         numeric,
  tsb         numeric,
  acwr        numeric,          -- 7d total / (28d total / 4), the standard form
  acwr_ewma   numeric,          -- atl/ctl, kept for reference only
  ctl_ramp_7d numeric,
  by_sport    jsonb not null default '{}'::jsonb,
  computed_at timestamptz not null default now(),
  primary key (user_id, day)
);

create table if not exists daily_readiness (
  user_id        uuid not null default auth.uid(),
  day            date not null,
  score          numeric,
  band           text,            -- green|amber|red
  components     jsonb not null default '{}'::jsonb,  -- each sub-score + weight actually used
  drivers        jsonb not null default '[]'::jsonb,  -- top 3 contributors, signed
  cold_start     boolean not null default false,
  computed_at    timestamptz not null default now(),
  primary key (user_id, day)
);

-- Per-day habit states, written nightly by engine/ti/streaks.py. Persisted
-- rather than recomputed in the browser so the habit rules have exactly one
-- definition and the page cannot drift from the engine.
-- habits is {habit_key: 'hit' | 'missed' | 'no_data'}.
create table if not exists daily_scorecard (
  user_id     uuid not null default auth.uid(),
  day         date not null,
  habits      jsonb not null default '{}'::jsonb,
  computed_at timestamptz not null default now(),
  primary key (user_id, day)
);

create table if not exists weekly_reports (
  user_id      uuid not null default auth.uid(),
  iso_year     integer not null,
  iso_week     integer not null,
  verdict      text not null,                      -- push|hold|back_off
  metrics      jsonb not null default '{}'::jsonb,
  watch_flags  jsonb not null default '[]'::jsonb,
  narrative    text,                               -- rule-based template text only
  created_at   timestamptz not null default now(),
  primary key (user_id, iso_year, iso_week)
);

create table if not exists insights (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid(),
  kind         text not null,
  headline     text not null,
  detail       text,
  effect_size  numeric,
  effect_unit  text,
  n            integer not null,
  confidence   numeric,
  is_causal    boolean not null default false,
  computed_at  timestamptz not null default now(),
  expires_at   timestamptz
);
create index if not exists insights_live_idx on insights (user_id, expires_at desc);

create table if not exists sync_status (
  user_id      uuid not null default auth.uid(),
  source       text not null,
  last_success timestamptz,
  last_attempt timestamptz,
  last_error   text,
  token_expires_at timestamptz,
  primary key (user_id, source)
);

create table if not exists races (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid(),
  name        text not null,
  race_date   date not null,
  distance    text,
  priority    text,
  target_ctl  numeric,
  notes       text
);

create table if not exists gear (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null default auth.uid(),
  source_id     text not null,
  gear_type     text not null,        -- shoe|bike
  name          text,
  brand         text,
  model_name    text,
  distance_m    numeric not null default 0,
  retire_at_m   numeric,
  retired       boolean not null default false,
  synced_at     timestamptz not null default now(),
  unique (user_id, source_id)
);
