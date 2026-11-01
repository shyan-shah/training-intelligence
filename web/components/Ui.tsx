"use client";

import type { ReactNode } from "react";

import { ReadinessGauge } from "./Gauge";
import { Sparkline } from "./Sparkline";
import { CountUp, useMounted } from "./Motion";
import { IconAlert, IconCheck, IconDown, IconUp } from "./Icons";
import { STATUS, habitColor } from "@/lib/palette";
import { DASH, daysUntil, shortDate, since } from "@/lib/format";
import type { SyncStatus } from "@/lib/types";

export function Card({
  title, subtitle, children, action, className = "", pad = true,
}: {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
  pad?: boolean;
}) {
  return (
    <section className={`panel ${pad ? "p-4" : ""} ${className}`}>
      {(title || action) && (
        <header className="mb-3 flex items-start justify-between gap-2">
          <div>
            {title && <h3 className="text-sm font-semibold tracking-tight">{title}</h3>}
            {subtitle && (
              <p className="mt-0.5 text-xs" style={{ color: "var(--text-secondary)" }}>
                {subtitle}
              </p>
            )}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

/** A delta chip. Direction is carried by an arrow as well as colour, so it
 *  never relies on red/green alone. */
export function Delta({
  value, unit = "", dp = 1, goodWhen = "up",
}: {
  value: number | null;
  unit?: string;
  dp?: number;
  goodWhen?: "up" | "down" | "neither";
}) {
  if (value === null || Number.isNaN(value)) return null;
  const up = value > 0;
  const flat = Math.abs(value) < 0.05;
  const good =
    goodWhen === "neither" ? null : goodWhen === "up" ? up : !up;
  const colour = flat || good === null
    ? "var(--text-muted)"
    : good ? STATUS.good : STATUS.critical;

  return (
    <span
      className="inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[11px] font-semibold tabular"
      style={{ color: colour, background: "var(--surface-sunken)" }}
    >
      {!flat && (up ? <IconUp size={11} /> : <IconDown size={11} />)}
      {up && !flat ? "+" : ""}
      {value.toFixed(dp)}
      {unit}
    </span>
  );
}

/** Stat tile. A number, its label, and optionally the shape behind it. */
export function Stat({
  label, value, unit, sub, color, spark, sparkColor, delta, animate = false, dp = 0,
  sparkPosition = "side",
}: {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  color?: string;
  spark?: (number | null)[];
  sparkColor?: string;
  delta?: ReactNode;
  animate?: false | number | null;
  dp?: number;
  /** "below" for three-up rows, where a 26px number and a sparkline side by
   *  side overflow a 115px column on a 390px screen. */
  sparkPosition?: "side" | "below";
}) {
  const hasSpark = spark && spark.length > 1;
  const sideSpark = hasSpark && sparkPosition === "side";
  const belowSpark = hasSpark && sparkPosition === "below";

  return (
    <div className="panel-flat overflow-hidden p-3">
      <div className="eyebrow">{label}</div>
      {/* The value and the sparkline share a row; the sub line sits under
          both and gets the full tile width, so it is not squeezed into a
          truncating column. */}
      <div className="mt-1.5 flex items-center justify-between gap-2">
        <div
          className="truncate text-[26px] font-semibold leading-none tracking-tight"
          style={{ color: color ?? "var(--text-primary)" }}
        >
          {animate !== false && animate !== null
            ? <CountUp value={animate} dp={dp} />
            : value}
          {unit && (
            <span
              className="ml-1 text-[13px] font-medium"
              style={{ color: "var(--text-secondary)" }}
            >
              {unit}
            </span>
          )}
        </div>
        {sideSpark && (
          <Sparkline values={spark!} colour={sparkColor ?? "var(--series-1)"} width={64} />
        )}
      </div>
      {belowSpark && (
        <div className="-mb-1 mt-1.5">
          {/* 84px fits a three-up column on a 390px screen: (390 - 32 page
              padding - 20 gaps) / 3 = 112, less 24 of tile padding = 88. */}
          <Sparkline
            values={spark!}
            colour={sparkColor ?? "var(--series-1)"}
            width={84}
            height={24}
          />
        </div>
      )}
      {sub && (
        <div className="mt-1.5 text-[11px] leading-snug" style={{ color: "var(--text-secondary)" }}>
          {sub}
        </div>
      )}
      {delta && <div className="mt-2">{delta}</div>}
    </div>
  );
}

const DRIVER_LABELS: Record<string, string> = {
  hrv: "HRV",
  sleep: "Sleep",
  rhr: "Resting HR",
  tsb: "Form",
  checkin: "Check-in",
};

export function ReadinessHero({
  score, band, drivers, coldStart, garminReadiness, colour,
}: {
  score: number | null;
  band: string;
  drivers: { component: string; subscore: number; contribution: number }[];
  coldStart: boolean;
  garminReadiness: number | null;
  colour: string;
}) {
  return (
    <section
      className="panel relative overflow-hidden p-5"
      style={{
        background:
          "radial-gradient(120% 90% at 50% -20%, var(--accent-wash), transparent 70%), var(--surface-1)",
      }}
    >
      <div className="flex flex-col items-center">
        <ReadinessGauge score={score} band={band} colour={colour} />
      </div>

      {garminReadiness !== null && (
        <div
          className="absolute right-4 top-4 rounded-lg px-2 py-1.5 text-right"
          style={{ background: "var(--surface-sunken)" }}
        >
          <div className="eyebrow">Garmin</div>
          <div className="tabular text-lg font-semibold leading-none">{garminReadiness}</div>
        </div>
      )}

      {coldStart && (
        <p
          className="mt-4 flex items-start gap-1.5 rounded-lg px-2.5 py-2 text-[11px]"
          style={{ background: "var(--surface-sunken)", color: "var(--text-secondary)" }}
        >
          <span style={{ color: STATUS.warning }}>
            <IconAlert />
          </span>
          Form is excluded until there are 42 days of load history. The other
          inputs are reweighted to cover it.
        </p>
      )}

      {drivers.length > 0 && (
        <div className="mt-5">
          <div className="eyebrow mb-2">Pulling it most</div>
          <ul className="space-y-2">
            {drivers.map((d) => {
              const good = d.contribution >= 0;
              const width =
                Math.round(Math.min(Math.abs(d.contribution) * 4.5, 50) * 1000) / 1000;
              return (
                <li key={d.component} className="flex items-center gap-2.5 text-xs">
                  <span className="w-[76px] shrink-0" style={{ color: "var(--text-secondary)" }}>
                    {DRIVER_LABELS[d.component] ?? d.component}
                  </span>
                  {/* Diverging bar from a centre line: left is a drag, right
                      is a lift. The sign is also printed, so the direction
                      never rests on position alone. */}
                  <span
                    className="relative h-1.5 flex-1 rounded-full"
                    style={{ background: "var(--surface-sunken)" }}
                  >
                    <span
                      className="absolute inset-y-0 w-px"
                      style={{ left: "50%", background: "var(--axis)" }}
                    />
                    <span
                      className="absolute inset-y-0 rounded-full"
                      style={{
                        background: good ? STATUS.good : STATUS.critical,
                        width: `${width}%`,
                        left: good ? "50%" : `${50 - width}%`,
                      }}
                    />
                  </span>
                  <span className="w-10 shrink-0 text-right tabular font-semibold">
                    {d.contribution > 0 ? "+" : ""}
                    {d.contribution.toFixed(1)}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

const SOURCE_NAMES: Record<string, string> = {
  garmin_personal: "Garmin API",
  garmin_login: "Garmin login",
  strava: "Strava",
  engine: "Analytics",
  evolt: "Evolt",
};

export function SyncStamps({ sync }: { sync: SyncStatus[] }) {
  // "7 hours ago" and the token countdown are both clock-derived, so they
  // wait for mount rather than hydrating against the server's clock.
  const mounted = useMounted();

  if (sync.length === 0) {
    return (
      <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
        No sync has run yet
      </p>
    );
  }

  return (
    <ul className="no-scrollbar -mx-4 flex gap-1.5 overflow-x-auto px-4">
      {sync.map((s) => {
        const stale = mounted && s.last_success
          ? Date.now() - new Date(s.last_success).getTime() > 36 * 3600 * 1000
          : !s.last_success;
        const tokenDays = mounted ? daysUntil(s.token_expires_at) : null;
        const tokenWarn = tokenDays !== null && tokenDays <= 5;
        return (
          <li
            key={s.source}
            className="flex shrink-0 items-center gap-1.5 rounded-full py-1 pl-2 pr-2.5 text-[11px]"
            style={{ background: "var(--surface-1)", border: "1px solid var(--border-hairline)" }}
            title={s.last_error ?? undefined}
          >
            <span
              aria-hidden
              className={`inline-block h-1.5 w-1.5 rounded-full ${stale ? "" : "live-dot"}`}
              style={{ background: stale ? STATUS.critical : STATUS.good }}
            />
            <span style={{ color: "var(--text-secondary)" }}>
              {SOURCE_NAMES[s.source] ?? s.source}
            </span>
            <span className="tabular" style={{ color: "var(--text-muted)" }}>
              {mounted ? since(s.last_success) : ""}
            </span>
            {tokenWarn && (
              <span className="tabular font-semibold" style={{ color: STATUS.critical }}>
                {tokenDays}d
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

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
  // Columns of seven, Monday at the top, so a column is a week.
  const weeks: { day: string; state: string }[][] = [];
  days.forEach((d) => {
    const dow = (new Date(d.day).getUTCDay() + 6) % 7;
    if (dow === 0 || weeks.length === 0) weeks.push([]);
    weeks[weeks.length - 1].push(d);
  });

  // A month label above the first column that starts a new month.
  const monthLabels = weeks.map((w, i) => {
    if (!w.length) return null;
    const m = new Date(w[0].day).getUTCMonth();
    const prev = i > 0 && weeks[i - 1].length
      ? new Date(weeks[i - 1][0].day).getUTCMonth()
      : -1;
    return m !== prev ? MONTHS[m] : null;
  });

  return (
    <div className="panel-flat p-3.5">
      <div className="mb-2.5 flex items-baseline justify-between gap-2">
        <h4 className="text-xs font-semibold tracking-tight">{label}</h4>
        <span className="tabular text-[11px]" style={{ color: "var(--text-secondary)" }}>
          {weeklyTarget
            ? `${weekHits}/${weeklyTarget} this week`
            : completion !== null
              ? `${Math.round(completion * 100)}% this week`
              : DASH}
        </span>
      </div>

      <div className="no-scrollbar overflow-x-auto pb-1">
        <div className="flex gap-[3px]">
          {weeks.map((week, wi) => (
            <div key={wi} className="flex flex-col gap-[3px]">
              <span className="h-3 text-[9px] leading-3" style={{ color: "var(--text-muted)" }}>
                {monthLabels[wi] ?? ""}
              </span>
              {week.map((d) => (
                <span
                  key={d.day}
                  title={`${shortDate(d.day)}: ${d.state.replace("_", " ")}`}
                  className="block h-[11px] w-[11px] rounded-[3px]"
                  /* No per-cell glow. With seven habits over 120 days that is
                     840 glowing cells, and the grid stops reading as data. */
                  style={{ background: habitColor(d.state) }}
                />
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-2.5 flex gap-4 text-[11px]" style={{ color: "var(--text-secondary)" }}>
        <span className="inline-flex items-center gap-1">
          Current <strong className="tabular text-xs">{currentStreak}</strong>
        </span>
        <span className="inline-flex items-center gap-1">
          Best <strong className="tabular text-xs">{bestStreak}</strong>
        </span>
      </div>
    </div>
  );
}

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
            className="inline-block h-2.5 w-2.5 rounded-[3px]"
            style={{ background: habitColor(state) }}
          />
          <span style={{ color: "var(--text-secondary)" }}>{label}</span>
        </li>
      ))}
    </ul>
  );
}

export function EmptyState({
  title, body, icon,
}: {
  title: string;
  body: string;
  icon?: ReactNode;
}) {
  return (
    <div
      className="rounded-2xl border border-dashed p-8 text-center"
      style={{ borderColor: "var(--border-hairline)" }}
    >
      {icon && (
        <div className="mb-3 flex justify-center" style={{ color: "var(--text-muted)" }}>
          {icon}
        </div>
      )}
      <p className="text-sm font-semibold">{title}</p>
      <p className="mx-auto mt-1.5 max-w-xs text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
        {body}
      </p>
    </div>
  );
}

/** Rule keys come from the engine, where they are identifiers. The page is
 *  read by a person, so they are translated here rather than renamed in the
 *  engine, where the key is part of the stored report. */
export const CHECK_LABELS: Record<string, string> = {
  hrv_inside: "HRV inside band",
  tsb_ok: "Form (TSB)",
  acwr_ok: "Load ratio",
  sleep_ok: "Sleep score",
  hrv_days_below: "Nights HRV below band",
  acwr_high: "Load ratio spike",
  tsb_low: "Form deeply negative",
  rhr_flags: "Resting HR flagged",
};

/** A pass/fail row for a verdict rule. Carries an icon as well as a colour. */
export function CheckRow({
  name, passed, value, threshold,
}: {
  name: string;
  passed: boolean;
  value: string;
  threshold: string;
}) {
  return (
    <li className="flex items-center gap-2 py-1 text-xs">
      <span
        className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full"
        style={{
          background: passed ? `${STATUS.good}22` : `${STATUS.critical}22`,
          color: passed ? STATUS.good : STATUS.critical,
        }}
      >
        {passed ? <IconCheck size={10} /> : <IconAlert size={10} />}
      </span>
      <span className="truncate" style={{ color: "var(--text-secondary)" }}>
        {CHECK_LABELS[name] ?? name}
      </span>
      <span className="ml-auto shrink-0 tabular font-semibold">{value}</span>
      <span
        className="shrink-0 tabular rounded px-1 text-[10px]"
        style={{ background: "var(--surface-sunken)", color: "var(--text-muted)" }}
      >
        {threshold}
      </span>
    </li>
  );
}
