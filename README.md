# Training Intelligence

Readiness, training load, recovery, body composition and habit streaks for one
athlete, in one place, with every number traceable to a formula.

Built from the Nov 2026 build brief. This repo is self-contained: schema,
analytics engine, ingest, the `/training` page, the chat tools and the
scheduled jobs.

---

## Read this first: what the live data says

Before writing any code I audited the sources that were reachable (Strava and
the Vault, both live). Seven findings changed the design. They are not
blockers, but several of them mean the page will be emptier than the brief
assumes for a while.

### 1. There is one Evolt scan on record, not a series

The Vault holds a single scan, 13 Sep 2026 (66.7kg, 14.1% body fat, 32.0kg
skeletal muscle, BMR 1607, TEE 2474, bio age 19, BWI 8.6). Its own note says
"weekly scans, next due 20 September". None followed.

Everything in the brief's body-composition section needs two or three scans:
the rolling 3-scan average, gain quality over 4 weeks, the weekly rate. All of
it returns an explicit reason instead of a number until the scans exist. **The
Body tab is the emptiest part of the app and will stay that way until scanning
resumes.** The code is written and tested; it is waiting on data.

### 2. Training volume is well below what the analytics assume

Approximate counts over the audited 90 days (3 Aug to 1 Nov 2026):

| Sport | Sessions | Note |
|---|---|---|
| Strength | 14 | about 1.2/week against a 4/week target |
| Run | 9 | longest 12.5km; last one 11 Oct, 21 days before the audit |
| Bike | 7 | includes 2 Zwift |
| Swim | 2 | 1,020m and a 160m sea swim |
| Walk | 19 | recorded, but carries no TSS |

Consequences, all of them deliberate in the code rather than hidden:

- The insight engine needs n >= 14. Run efficiency needs 12 sessions. **Most
  insights will show nothing at first**, and the Insights tab says so.
- CTL will be low and TSB mostly positive, so the `TSB < -30` back-off rule
  will effectively never fire at this volume.
- The gym streak calendar will be mostly red against a 4/week target.
- Against an Ironman in Oct 2027 the current base is close to zero. That is a
  planning input, not a code problem.

### 3. The 2-minute dedupe window is too tight

Two tempo runs on 2026-08-27 start at 11:21:23 and 11:23:59. That is **2m36s
apart** and they are plainly the same session (10.3km/3982s and
12.5km/4550s, both exported from the same training plan). A 2-minute window
misses them.

The window is now 300s and start time alone is not enough: a pair must also
agree on duration, and on distance where both have one. The genuinely separate
rides on 2026-10-28 (12:43 and 12:59, 1.25km and 16.1km) stay separate. Both
cases are pinned by tests in `engine/tests/test_dedupe.py`.

### 4. The activity feed contains rows that would poison the maths

The brief specified range checks for Evolt scans but not for activities. Real
examples found:

| Record | Problem |
|---|---|
| "Night Workout" 2026-10-09 | 4 seconds elapsed, zero distance |
| "Night Workout" 2026-09-22 | 175,726s elapsed (48.8h) against 4,678s moving |
| "Afternoon Walk" 2026-09-26 | max speed 48.9 km/h |
| "Lunch Ride" 2026-08-15 | max speed 81.0 km/h while averaging 11.3 km/h |

So: TSS is computed on **moving** time, never elapsed; sessions under 60s are
rejected; and GPS spikes are flagged both by an absolute per-sport ceiling and
by a ratio to the session average. The ratio matters: 81 km/h sits under the
90 km/h bike ceiling, so only the ratio check catches it. Rows are flagged,
never deleted, so a rejection stays auditable.

### 5. ACWR as defined in the brief is not the one the thresholds belong to

The brief defines ACWR as ATL/CTL. That is a 7:42 exponential ratio. The
0.8-1.3 band and the 1.5 back-off threshold come from the literature on the
**7:28 rolling** form, and the two are not interchangeable.

Both are computed. `acwr` (7-day total over the 28-day weekly average) drives
the verdict; `acwr_ewma` (ATL/CTL) is stored alongside so the old definition
stays visible. `acwr` is left null until there are 28 days of history, because
a partial chronic window reads high and would fire a false back-off in week
one.

Separately, the brief uses three ACWR numbers in three places: 1.2 (push
ceiling), 1.3 (top of the shaded band) and 1.5 (back off). That is coherent
but looks inconsistent on screen, so the Load tab names each one.

### 6. Two of the configured values have no source, and one is a guess

From the live Strava account:

| Setting | Value | Provenance |
|---|---|---|
| `ftp_w` | 213 | Measured, manually set by you. Trustworthy. |
| `max_hr` | 207 | Implied by the zone 5 floor of 208. |
| `threshold_pace` | 240 s/km | **Estimated** from a measured 18:16 5k. Not tested. |
| `lthr` | not set | **No source.** Strava does not expose it; nor does the Garmin Personal tier. |
| `css_swim` | not set | **No source.** Needs a 400/200 test. |

Because `lthr` is unset, **HR-fallback TSS is disabled**, so a session with
neither power nor pace scores nothing rather than a fabricated number. Because
`css_swim` is unset, swim TSS is disabled too (with 2 swims in 90 days this
costs almost nothing today). Set both and they switch on with no code change.

### 7. Target conflicts, and how they were settled

- **Protein target: settled at 216g.** The Evolt scan prescribes 216-223g/day;
  the Vault's nutrition memory said 150-170g/day. 216 wins, because it is tied
  to the muscle-gain goal and to the 2874-2974 kcal target seeded next to it.
  Worth knowing that 216g vegetarian is a hard daily ask, so expect this to be
  the habit that runs red most often. One value in
  `athlete_settings.targets.protein_g` if the goal changes.
- **Weight.** The Strava profile says 62kg; the Evolt scan says 66.7kg. The
  Strava figure is almost certainly stale. Evolt is treated as the source of
  truth for composition and Garmin for daily weight; Strava's profile weight is
  ignored entirely.

### Open decision, unchanged from the brief: Garmin's terms

A developer quoting Garmin's terms says they prohibit using Garmin-sourced data
to create or maintain an AI system or AI-generated knowledge base. **Read the
Personal tier terms at sign up.**

Until that is confirmed, this repo ships rule-based text only: the weekly
narrative is a template in `engine/ti/verdict.py`, and no LLM touches any
number anywhere.

One point the brief understates. It treats this as a constraint on AI-written
narrative, and waves the chat tools through as "numbers the user asked for".
But `training_summary` returning Garmin-derived figures into a Claude chat is
still Garmin data entering an AI context. The tools are therefore written to
return **computed values only**, scoped to a requested range, capped at 180
days, and never raw wellness records. Confirm the terms before relying on them.

---

## How it fits together

```
Garmin Personal API ─┐
Garmin login route  ─┤
Strava              ─┼─> ingest/ ─> Supabase (the Vault project) ─┬─> /training page
Evolt PDF           ─┤                      ▲                     ├─> Claude chats (vault-mcp)
Daily check-in      ─┘                      │                     └─> Sunday ntfy push
                                    engine/ti/nightly.py
```

Everything lands in one Supabase project, so the page, the chat tools and the
Sunday push read the same rows and cannot disagree.

| Directory | What it holds |
|---|---|
| `supabase/` | Schema, RLS policies, seed data |
| `engine/ti/` | The analytics engine. Pure stdlib maths, no LLM, fully tested |
| `ingest/` | One module per source, plus validation and dedupe |
| `mcp/` | The four tools to mount into `vault-mcp` |
| `web/` | The Next.js `/training` page, installable as a PWA |
| `.github/workflows/` | Ingest, nightly compute, weekly report, CI |

### Why the engine is Python and the page is TypeScript

Every threshold, verdict and habit rule is evaluated once, in Python, and the
result is persisted. The page renders stored rows. Nothing in `web/` decides
whether a habit was hit or whether a week is a push, so the two cannot drift.
`lib/derive.ts` only reshapes series for charts.

---

## Setup

### 1. Database

```bash
psql "$SUPABASE_DB_URL" -f supabase/migrations/0001_init.sql
```

```bash
psql "$SUPABASE_DB_URL" -f supabase/migrations/0002_rls.sql
```

Then seed the settings and races as the owning user, so `auth.uid()` resolves:

```bash
psql "$SUPABASE_DB_URL" -f supabase/seed/athlete_settings.sql
```

Every table has RLS with `user_id = auth.uid()` and `force row level security`.
The browser only ever holds the anon key; the service key lives in GitHub
Actions and nowhere else.

### 2. Secrets

Copy `.env.example` to `.env` for local work (it is gitignored). In CI, set
each one as a GitHub Actions secret. `TI_USER_ID` is required: server-side
writes pass `user_id` explicitly because the column default is `auth.uid()`,
which is null under the service role.

### 3. Audit before migrating anything

```bash
python -m ingest.run audit
```

This prints row counts, the latest date per table, per-source sync state and
which settings are unset. It changes nothing. Read it before the first
backfill.

### 4. Backfill

```bash
python -m ingest.run strava --days 90
```

```bash
python -m ingest.run garmin-personal --days 90
```

```bash
python -m engine.ti.nightly --days 180
```

### 5. Web

```bash
cd web && npm install && npm run dev
```

Deploys to the existing Vercel project. Set `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` there.

### 6. Chat tools

In `vault-mcp`, import and register:

```python
from mcp.training_tools import register
register(mcp)
```

---

## Getting it on your phone

The app is a PWA, so there is no App Store step and no TestFlight. Deploy it,
sign in once in Safari, add it to the home screen.

### 1. Supabase

Run the two migrations and the seed, then turn on email sign-in.

In the Supabase dashboard, under Authentication:

- **Providers → Email**: enabled, with "Confirm email" on. Magic links need it.
- **URL Configuration → Site URL**: the deployed origin.
- **Redirect URLs**: add `https://<your-domain>/auth/confirm`. The link in the
  email will not work without it.

Create exactly one user, with your own email. Sign-in uses
`shouldCreateUser: false`, so nobody else can make an account by submitting
their address at `/login`. RLS is the second line of defence, not the only one.

### 2. Vercel

Point a Vercel project at this repo with `web` as the root directory. Two
environment variables:

```
NEXT_PUBLIC_SUPABASE_URL=https://drdvfdwxjgbqpnnqfzgg.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key>
```

The anon key is meant to be public. The service key must never appear here: it
bypasses RLS and belongs only in GitHub Actions.

### 3. GitHub Actions

Add every secret from `.env.example` to the repository's Actions secrets. The
ingest workflow runs four times a day, the compute nightly, the report on
Sunday. Until the secrets exist, the workflows fail and the page stays empty.

### 4. Install it

On the iPhone, in **Safari** (not Chrome, which cannot install to the home
screen on iOS):

1. Open the deployed URL and sign in. The magic link opens back in Safari.
2. Share → Add to Home Screen.

It then launches full screen with its own icon, no Safari chrome, and the
session persists so it rarely asks you to sign in again. Sign out lives in the
More sheet.

It works offline to the extent that is safe: see **Offline** below.

### Offline

A service worker caches the app shell, so it opens off disk rather than
re-downloading ~103kB of JS on a slow connection, and shows a real screen
instead of a white page when there is no signal.

It deliberately does **not** cache your numbers. `/training` is server-rendered
with sleep, HRV and body composition inside the HTML, and `next.config.mjs`
already sends `Cache-Control: private, no-store` for it. Writing that same HTML
into Cache Storage would put health data on disk in exactly the place that
header exists to prevent, and would undo it silently. API routes, auth routes
and every Supabase request are left alone for the same reason.

So the trade is explicit: offline you get the app and an honest "no
connection" screen, not yesterday's readiness. A smoke check asserts that
nothing matching `/training`, `/preview`, `/api` or `/auth` ever lands in a
cache.

The worker itself is served `no-cache`. A cached service worker never updates.

## Before the first Garmin run

`ingest/garmin_personal.py` carries endpoint paths and field names that are
**not verified**. Garmin's Health API spec sits behind the developer portal and
is not public. Check the swagger when the Personal key is issued and correct
the `ENDPOINTS` block and the field mappings; everything downstream reads from
that one block.

The swagger also settles two things that affect the workflow but not the
schema: whether the Personal tier offers pull endpoints at all (the Health API
is push-oriented, so this may need a webhook receiver instead of a scheduled
pull), and what the backfill limits are.

---

## Tests

```bash
python -m pytest
```

169 Python tests, plus a 21-case browser smoke test described under
**The page**. The ones worth knowing about:

- **The hand calculation** (`test_load.py`). The acceptance check asks that
  CTL, ATL and TSB match a hand calculation on three sample days. Rather than
  paste float literals, the test re-derives them in exact rational arithmetic
  straight from the recurrences, so it checks the engine rather than echoing
  it. The exact values from zero seeds with TSS 100/0/50 are CTL 50/21, 1025/441,
  64075/18522.
- **Audited real records** (`test_dedupe.py`, `test_validate.py`). The
  duplicate tempo runs, the back-to-back rides, the 4-second row, the stuck
  timer and both GPS spikes are all pinned as fixtures with their real dates
  and values.
- **The Evolt printout** (`ingest/tests/test_evolt.py`). Every printed value
  from the real 13 Sep scan round-trips through the parser.
- **False-positive rates** (`test_insights.py`). The trend-break and
  cause-hunt detectors are run over hundreds of stationary random series and
  asserted to fire rarely, and over real shifts and asserted to catch them.
  This caught two genuine bugs: a single outlier triggering "resting HR has
  crept up", and a 4-vs-4 decile comparison clearing a Cohen's d of 0.8 on pure
  noise. Both are fixed with medians, a noise-scaled floor, a minimum group
  size and a Welch t gate.

For the Evolt acceptance check end to end, drop a real PDF somewhere outside
the repo and run:

```bash
python -c "from ingest.evolt import parse_pdf; print(parse_pdf('/path/to/scan.pdf').values)"
```

---

## The page

Phone first, and built like a phone app rather than a desktop dashboard that
shrank: a bottom navigation bar within thumb reach, a readiness gauge as the
first thing on screen, and the depth behind tabs. Eight tabs will not fit
across a phone, so the four most-used sit in the bar and the rest live behind
More. When a More tab is active the fifth slot takes that tab's name, so the
bar always shows where you are.

Light and dark are both selected sets, not one flipped into the other, and the
toggle cycles system / light / dark. A small inline script applies the saved
choice before first paint so there is no flash of the wrong palette.

### Charts

The palette is the validated reference set, not a taste call. The four
categorical slots clear the colourblindness and contrast gates on the adjacent
pairlist in both modes; the three-series set clears all-pairs. Light mode aqua
(2.74:1) and yellow (2.11:1) sit below 3:1 on the light surface, so every chart
carries direct labels and a table-view toggle as the relief.

Three rules shaped the layout:

- **No dual axes, anywhere.** The brief asks for "skeletal muscle, fat mass and
  body fat % on one timeline". Kilograms and percent cannot share a y-axis, so
  that is two charts. CTL, ATL and TSB are all in TSS units and do share one.
- **Colour follows the entity, not its rank**, so filtering the sport list
  never repaints the survivors.
- **Status colours are reserved.** Green is a hit, red a miss, grey no data,
  amber readiness only. None doubles as a series colour, and each is paired
  with a label or an icon so colour never carries meaning alone.

Recharts is lazy-loaded behind a shimmer placeholder, which keeps the Today
tab's first-load JS at 120kB rather than 225kB, in service of the "Today loads
in under 2 seconds on 4G" check.

Every animation is suppressed under `prefers-reduced-motion`, including the
gauge sweep and the count-up.

### Looking at it without a database

`/preview` renders the real page against fixtures, so the design can be worked
on without Supabase or a signed-in session. It 404s in production unless
`ENABLE_PREVIEW=1`.

```bash
cd web && npm run dev
```

The fixtures deliberately match the audited reality rather than an idealised
athlete: one Evolt scan, sparse running, a gym habit at about one session a
week against a target of four. A design that only looks right on dense data is
the wrong design.

### Visual smoke test

```bash
cd web && npm run build && ENABLE_PREVIEW=1 npm start -- -p 3100
```

```bash
cd web && BASE_URL=http://localhost:3100 npm run smoke
```

Drives all eight tabs in both colour schemes and fails on a console error, a
horizontal overflow, or a tab that renders nothing. It then registers the
service worker, goes offline, and asserts that the offline page is served and
styled and that no page or API response has been written to Cache Storage.
It runs in CI, and it earned its place by catching two real bugs:

- a React hydration mismatch, because `Math.cos` differs in its last bit
  between Node and V8 and the gauge wrote raw floats into SVG attributes
  (`14.33436854000503` against `14.334368540005045`). Every coordinate is
  rounded now;
- the three-up stat row on the Load tab spilling past a 390px screen once
  sparklines sat beside the numbers.

If the machine already has a Chromium, point at it with `CHROMIUM_PATH` instead
of running `playwright install`.

## Acceptance checks

| Check | State |
|---|---|
| Ingest audit delivered before any migration | `python -m ingest.run audit`, plus the findings above |
| 14 consecutive days of every source landing | Not yet. Needs 14 days of live running |
| CTL/ATL/TSB match a hand calculation on 3 days | Passing, re-derived in exact arithmetic |
| A real Evolt PDF parses to the printed values | Text-layer path passing against the real scan's values; run once against the actual PDF |
| Today tab under 2s on iPhone over 4G | 120kB first load, charts lazy-loaded. Measure on the device once deployed |
| Weekly verdict shows its numbers | Passing. Every rule ships its value and threshold |
| Killing the login token leaves the page working | By construction. `garmin_login.ingest` never raises; the five columns go null |

One note on the second check. "Every source landing daily" cannot mean
`activities`, which legitimately has gaps on rest days (there were none between
1 and 9 Oct). It should mean `garmin_daily` and `daily_checkin`, which are
per-day regardless of training.

---

## What is left

### Blocking a working app

1. **Secrets and the database.** Nothing runs until the migrations are applied
   and the Actions secrets are set. This is the only item between here and a
   working page.
2. **Verify the Garmin Personal API endpoints.** `ingest/garmin_personal.py`
   carries unverified paths and field names; the swagger is behind the
   developer portal. Check them when the key is issued and correct the one
   `ENDPOINTS` block. The swagger also decides whether the Personal tier offers
   pull endpoints at all, or whether this needs a webhook receiver instead of a
   scheduled pull.
3. **Set LTHR and CSS**, or accept that HR-fallback TSS and swim TSS stay off.
   A threshold test and a 400/200 CSS test are the inputs.
4. **Settle the Garmin terms question** before relying on the chat tools. Read
   the Personal tier terms at sign up.

### Needed before the numbers mean anything

5. **Resume Evolt scanning.** One scan is on record. Gain quality needs two,
   the rolling average needs three. The Body tab stays mostly empty until then,
   and that is the code being honest rather than broken.
6. **Run it for 14 days** to clear the "every source landing daily" acceptance
   check, and to give the insight engine its minimum of 14 paired days.
7. **Parse one real Evolt PDF end to end** and compare against the printout.
   The text-layer path is tested against the real scan's values, but not yet
   against the actual file.

### Worth building next

8. **Push notifications** for the Sunday verdict, rather than ntfy. iOS
   supports web push for installed PWAs from 16.4, and the service worker that
   would receive them now exists. This is the only reason to consider Expo,
   and it is no longer much of one.
9. **Offline check-in queueing.** The one thing genuinely worth storing on the
   phone is an unsent check-in: it is four small integers, none of them a
   measurement, and losing it to a dead signal is annoying. Background Sync
   would flush it when the connection returns.

### From Phase 5, not built

The race build-phase model with its target CTL ramp plotted against actual, the
strength top-set progression tracker, the IT band injury watch, the uni
deadline overlay on the Load chart, and the scan discipline reminder.

The schema already supports all of them: `races`, `nutrition_daily` and
`daily_checkin.niggle_pain` are in place and seeded.

Built from Phase 5: race targets, the daily check-in, gear mileage with
per-model replacement thresholds, and nutrition against targets.

### Out of scope, per the brief

Pushing workouts to Garmin (the Personal API is read-only), multi-user, and a
native iOS app.
