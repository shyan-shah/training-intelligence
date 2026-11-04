import { supabaseServer } from "./supabase";
import type {
  Activity, Checkin, DailyLoad, DailyReadiness, EvoltScan, Gear, GarminDaily,
  Insight, Nutrition, Scorecard, Settings, SyncStatus, WeeklyReport,
} from "./types";

/**
 * Retries a query that failed with a transient auth error.
 *
 * Supabase mints a new JWT on refresh, and for a moment afterwards a request
 * can land on a node whose clock is a fraction behind the auth server's and
 * be rejected with "JWT issued at future". Observed in production: a token
 * refresh at 21:51:34, then thirteen queries fired in parallel two seconds
 * later, of which twelve returned 200 and one returned 401. One failure in
 * 5,504 requests over 24 hours.
 *
 * Firing the whole page's queries in parallel right after a refresh is what
 * maximises the exposure, so the fix is to retry rather than to surface a
 * one-off as a red banner. A refreshed token is accepted within a second.
 */
const TRANSIENT_AUTH = /jwt|PGRST301|issued at future/i;

async function retrying<T>(
  run: () => PromiseLike<{ data: T | null; error: { message: string; code?: string } | null }>,
  attempts = 3,
): Promise<{ data: T | null; error: { message: string; code?: string } | null }> {
  let last = await run();
  for (let i = 1; i < attempts; i++) {
    if (!last.error) return last;
    if (!TRANSIENT_AUTH.test(`${last.error.code ?? ""} ${last.error.message}`)) return last;
    await new Promise((r) => setTimeout(r, 150 * i));
    last = await run();
  }
  return last;
}

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

/**
 * One round trip for the whole page. Every table is RLS-scoped to the session
 * user, so none of these need an explicit user filter.
 *
 * A failed query returns an empty list rather than throwing: a page that
 * renders with one source missing and says so beats a page that 500s.
 */
export async function loadTrainingData(rangeDays: number) {
  const sb = await supabaseServer();
  const since = isoDaysAgo(Math.max(rangeDays, 90)); // charts need baseline history
  const loadSince = isoDaysAgo(Math.max(rangeDays, 180));

  const [
    loads, readiness, daily, scans, activities, weekly, insights, sync,
    checkins, nutrition, settings, gear, scorecard,
  ] = await Promise.all([
    retrying(() => sb.from("daily_load").select("*").gte("day", loadSince).order("day")),
    retrying(() => sb.from("daily_readiness").select("*").gte("day", since).order("day")),
    retrying(() => sb.from("garmin_daily").select("*").gte("day", since).order("day")),
    retrying(() => sb.from("evolt_scans").select("*").order("scanned_at")),
    retrying(() => sb.from("activities").select("*").gte("start_at", since)
      .order("start_at", { ascending: false })),
    retrying(() => sb.from("weekly_reports").select("*").order("iso_year", { ascending: false })
      .order("iso_week", { ascending: false }).limit(12)),
    retrying(() => sb.from("insights").select("*").order("computed_at", { ascending: false })),
    retrying(() => sb.from("sync_status").select("*")),
    retrying(() => sb.from("daily_checkin").select("*").gte("day", since).order("day")),
    retrying(() => sb.from("nutrition_daily").select("*").gte("day", since).order("day")),
    retrying(() => sb.from("athlete_settings").select("*").maybeSingle()),
    retrying(() => sb.from("gear").select("*").eq("retired", false)),
    retrying(() => sb.from("daily_scorecard").select("*").gte("day", since).order("day")),
  ]);

  return {
    loads: (loads.data ?? []) as DailyLoad[],
    readiness: (readiness.data ?? []) as DailyReadiness[],
    daily: (daily.data ?? []) as GarminDaily[],
    scans: (scans.data ?? []) as EvoltScan[],
    activities: (activities.data ?? []) as Activity[],
    weekly: (weekly.data ?? []) as WeeklyReport[],
    insights: (insights.data ?? []) as Insight[],
    sync: (sync.data ?? []) as SyncStatus[],
    checkins: (checkins.data ?? []) as Checkin[],
    nutrition: (nutrition.data ?? []) as Nutrition[],
    settings: (settings.data ?? null) as Settings | null,
    gear: (gear.data ?? []) as Gear[],
    scorecard: (scorecard.data ?? []) as Scorecard[],
    errors: [
      ["load", loads.error], ["readiness", readiness.error], ["wellness", daily.error],
      ["scans", scans.error], ["activities", activities.error], ["weekly", weekly.error],
      ["insights", insights.error], ["sync", sync.error], ["settings", settings.error],
      ["scorecard", scorecard.error],
    ]
      .filter(([, e]) => e)
      .map(([name, e]) => `${name}: ${(e as { message: string }).message}`),
  };
}

export type TrainingData = Awaited<ReturnType<typeof loadTrainingData>>;
