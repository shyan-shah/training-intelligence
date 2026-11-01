import type { ReactNode } from "react";

import { CHROME, STATUS, habitColor, readinessColor } from "@/lib/palette";
import { DASH, daysUntil, num, shortDate, since } from "@/lib/format";
import type { SyncStatus } from "@/lib/types";

export function Card({
  title, children, action, className = "",
}: {
  title?: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border p-4 ${className}`}
      style={{ background: CHROME.surface, borderColor: "var(--border-hairline)" }}
    >
      {(title || action) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          {title && <h3 className="text-sm font-semibold">{title}</h3>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

/** A stat tile. A single number with its label and an optional sub-line.
 *  No plot, so no hover layer. */
export function Stat({
  label, value, unit, sub, color, tabular = true,
}: {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  color?: string;
  tabular?: boolean;
}) {
  return (
    <div
      className="rounded-lg border p-3"
      style={{ background: CHROME.surface, borderColor: "var(--border-hairline)" }}
    >
      <div className="text-[11px] uppercase tracking-wide" style={{ color: CHROME.muted }}>
        {label}
      </div>
      <div
        className={`mt-1 text-2xl font-semibold leading-none ${tabular ? "" : ""}`}
        style={{ color: color ?? CHROME.ink }}
      >
        {value}
        {unit && (
          <span className="ml-1 text-sm font-normal" style={{ color: CHROME.inkSecondary }}>
            {unit}
          </span>
        )}
      </div>
      {sub && (
        <div className="mt-1 text-xs" style={{ color: CHROME.inkSecondary }}>
          {sub}
        </div>
      )}
    </div>
  );
}

/** The hero figure on the Today tab. Readiness is the one number the page
 *  leads with, so it gets the largest type and its drivers beneath it. */
export function ReadinessHero({
  score, band, drivers, coldStart, garminReadiness,
}: {
  score: number | null;
  band: string;
  drivers: { component: string; subscore: number; contribution: number }[];
  coldStart: boolean;
  garminReadiness: number | null;
}) {
  const colour = readinessColor(band);
  const LABELS: Record<string, string> = {
    hrv: "HRV", sleep: "Sleep", rhr: "Resting HR", tsb: "Form (TSB)", checkin: "Check-in",
  };

  return (
    <Card>
      <div className="flex items-start gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-wide" style={{ color: CHROME.muted }}>
            Readiness
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-5xl font-semibold leading-none" style={{ color: colour }}>
              {score === null ? DASH : Math.round(score)}
            </span>
            <span className="text-sm" style={{ color: CHROME.inkSecondary }}>
              / 100
            </span>
          </div>
          {/* Status colour never carries meaning alone: the band is also named. */}
          <div className="mt-1 flex items-center gap-1.5 text-xs font-medium">
            <span
              aria-hidden
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: colour }}
            />
            <span style={{ color: CHROME.ink }}>
              {band === "unknown" ? "Not enough data" : band[0].toUpperCase() + band.slice(1)}
            </span>
          </div>
        </div>

        {garminReadiness !== null && (
          <div className="ml-auto text-right">
            <div className="text-[11px] uppercase tracking-wide" style={{ color: CHROME.muted }}>
              Garmin's own
            </div>
            <div className="text-2xl font-semibold leading-none">{garminReadiness}</div>
            <div className="text-[11px]" style={{ color: CHROME.muted }}>
              for comparison
            </div>
          </div>
        )}
      </div>

      {coldStart && (
        <p
          className="mt-3 rounded-md px-2 py-1.5 text-[11px]"
          style={{ background: "var(--band-fill)", color: CHROME.inkSecondary }}
        >
          Form is excluded until there are 42 days of load history. The remaining
          inputs are reweighted to fill the gap.
        </p>
      )}

      {drivers.length > 0 && (
        <div className="mt-3">
          <div className="mb-1.5 text-[11px] uppercase tracking-wide" style={{ color: CHROME.muted }}>
            Pulling it most
          </div>
          <ul className="space-y-1.5">
            {drivers.map((d) => {
              const good = d.contribution >= 0;
              return (
                <li key={d.component} className="flex items-center gap-2 text-xs">
                  <span className="w-24 shrink-0" style={{ color: CHROME.inkSecondary }}>
                    {LABELS[d.component] ?? d.component}
                  </span>
                  <span className="relative h-1.5 flex-1 overflow-hidden rounded-full"
                        style={{ background: "var(--gridline)" }}>
                    <span
                      className="absolute inset-y-0 rounded-full"
                      style={{
                        background: good ? STATUS.good : STATUS.critical,
                        width: `${Math.min(Math.abs(d.contribution) * 4, 100)}%`,
                        left: good ? "50%" : undefined,
                        right: good ? undefined : "50%",
                      }}
                    />
                  </span>
                  <span className="w-12 shrink-0 text-right tabular font-medium">
                    {d.contribution > 0 ? "+" : ""}
                    {d.contribution.toFixed(1)}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Card>
  );
}

/** Per-source freshness. A visible stamp beats silently old numbers. */
export function SyncStamps({ sync }: { sync: SyncStatus[] }) {
  const NAMES: Record<string, string> = {
    garmin_personal: "Garmin (API)",
    garmin_login: "Garmin (login)",
    strava: "Strava",
    engine: "Analytics",
    evolt: "Evolt",
  };
  if (sync.length === 0) {
    return (
      <p className="text-xs" style={{ color: CHROME.muted }}>
        No sync has run yet.
      </p>
    );
  }
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-[11px]">
      {sync.map((s) => {
        const stale = s.last_success
          ? Date.now() - new Date(s.last_success).getTime() > 36 * 3600 * 1000
          : true;
        const tokenDays = daysUntil(s.token_expires_at);
        const tokenWarn = tokenDays !== null && tokenDays <= 5;
        return (
          <li key={s.source} className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: stale ? STATUS.critical : STATUS.good }}
            />
            <span style={{ color: CHROME.inkSecondary }}>
              {NAMES[s.source] ?? s.source} {since(s.last_success)}
            </span>
            {tokenDays !== null && (
              <span
                className="rounded px-1 font-medium"
                style={{
                  color: tokenWarn ? STATUS.critical : CHROME.muted,
                  background: tokenWarn ? "rgba(208,59,59,0.12)" : "transparent",
                }}
              >
                token {tokenDays}d
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** GitHub-style habit heatmap. Green hit, red missed, grey no data. */
export function StreakCalendar({
  label, days, currentStreak, bestStreak, completion, weeklyTarget, weekHits,
}: {
  label: string;
  days: { day: string; state: string }[];
  currentStreak: number;
  bestStreak: number;
  completion: number | null;
  weeklyTarget: number | null;
  weekHits: number;
}) {
  // Build columns of 7, Monday at the top, so each column is one week.
  const weeks: { day: string; state: string }[][] = [];
  days.forEach((d) => {
    const dow = (new Date(d.day).getUTCDay() + 6) % 7;
    if (dow === 0 || weeks.length === 0) weeks.push([]);
    weeks[weeks.length - 1].push(d);
  });

  return (
    <div
      className="rounded-lg border p-3"
      style={{ background: CHROME.surface, borderColor: "var(--border-hairline)" }}
    >
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h4 className="text-xs font-semibold">{label}</h4>
        <span className="text-[11px] tabular" style={{ color: CHROME.inkSecondary }}>
          {weeklyTarget
            ? `${weekHits}/${weeklyTarget} this week`
            : completion !== null
              ? `${Math.round(completion * 100)}% this week`
              : DASH}
        </span>
      </div>

      <div className="flex gap-[3px] overflow-x-auto pb-1">
        {weeks.map((week, wi) => (
          <div key={wi} className="flex flex-col gap-[3px]">
            {week.map((d) => (
              <span
                key={d.day}
                title={`${shortDate(d.day)}: ${d.state.replace("_", " ")}`}
                className="block h-[10px] w-[10px] rounded-[2px]"
                style={{ background: habitColor(d.state) }}
              />
            ))}
          </div>
        ))}
      </div>

      <div className="mt-2 flex gap-4 text-[11px]" style={{ color: CHROME.inkSecondary }}>
        <span>
          Current <strong className="tabular">{currentStreak}</strong>
        </span>
        <span>
          Best <strong className="tabular">{bestStreak}</strong>
        </span>
      </div>
    </div>
  );
}

/** Legend for the heatmap states. Identity is never colour-alone. */
export function HabitLegend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
      {[
        ["hit", "Target hit"],
        ["missed", "Missed"],
        ["no_data", "No data"],
      ].map(([state, label]) => (
        <li key={state} className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-2.5 w-2.5 rounded-[2px]"
            style={{ background: habitColor(state) }}
          />
          <span style={{ color: CHROME.inkSecondary }}>{label}</span>
        </li>
      ))}
    </ul>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div
      className="rounded-xl border border-dashed p-6 text-center"
      style={{ borderColor: "var(--border-hairline)" }}
    >
      <p className="text-sm font-medium">{title}</p>
      <p className="mx-auto mt-1 max-w-sm text-xs" style={{ color: CHROME.inkSecondary }}>
        {body}
      </p>
    </div>
  );
}
