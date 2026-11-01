"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";

import type { SeriesSpec } from "./Charts";

/* Recharts is ~100kB and only the chart tabs need it. Loading it lazily keeps
   it out of the Today bundle, which is the tab that has to open in under two
   seconds on a phone over 4G. Webpack folds these into one shared chunk, so
   the first chart tab pays for it once. */
const chartModule = () => import("./Charts");

const MultiLine = dynamic(() => chartModule().then((m) => m.MultiLine), { ssr: false });
const BandedLine = dynamic(() => chartModule().then((m) => m.BandedLine), { ssr: false });
const TrendWithPoints = dynamic(() => chartModule().then((m) => m.TrendWithPoints), { ssr: false });
const StackedBars = dynamic(() => chartModule().then((m) => m.StackedBars), { ssr: false });
const AcwrChart = dynamic(() => chartModule().then((m) => m.AcwrChart), { ssr: false });
const StatusBars = dynamic(() => chartModule().then((m) => m.StatusBars), { ssr: false });
import { Card, EmptyState, HabitLegend, ReadinessHero, Stat, StreakCalendar, SyncStamps } from "./Ui";
import { CHROME, SERIES, STATUS, habitColor, readinessColor } from "@/lib/palette";
import {
  DASH, VERDICT_LABEL, dayLabel, hours, km, num, pace, shortDate, signed,
} from "@/lib/format";
import {
  HABIT_LABELS, HABIT_WEEKLY_TARGET, baselineBand, bodyFatRows, clip,
  compositionRows, efficiencyRows, habitSeries, loadRows, recoveryRows,
  rollingMean, weeklyBySport, weightRows,
} from "@/lib/derive";
import type { TrainingData } from "@/lib/queries";

const TABS = [
  "Today", "Week", "Streaks", "Body", "Insights", "Load", "Recovery", "Performance",
] as const;
type Tab = (typeof TABS)[number];

const RANGES = [30, 90, 180] as const;

export default function TrainingTabs({ data }: { data: TrainingData }) {
  const [tab, setTab] = useState<Tab>("Today");
  const [range, setRange] = useState<number>(90);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-24 pt-4">
      <header className="mb-4">
        <h1 className="text-xl font-semibold">Training</h1>
        <div className="mt-1.5">
          <SyncStamps sync={data.sync} />
        </div>
        {data.errors.length > 0 && (
          <p
            className="mt-2 rounded-md px-2 py-1.5 text-[11px]"
            style={{ background: "rgba(208,59,59,0.12)", color: STATUS.critical }}
          >
            Some sources could not be read: {data.errors.join("; ")}
          </p>
        )}
      </header>

      {/* Tab nav. Scrolls horizontally on a phone rather than wrapping. */}
      <nav
        className="sticky top-0 z-10 -mx-4 mb-4 flex gap-1 overflow-x-auto px-4 py-2"
        style={{ background: "var(--plane)" }}
        aria-label="Training sections"
      >
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            aria-current={tab === t ? "page" : undefined}
            className="shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition-colors"
            style={{
              background: tab === t ? "var(--series-1)" : "var(--surface-1)",
              color: tab === t ? "#ffffff" : CHROME.inkSecondary,
              border: `1px solid ${tab === t ? "transparent" : "var(--border-hairline)"}`,
            }}
          >
            {t}
          </button>
        ))}
      </nav>

      {/* Date range control: one row above the charts, on the tabs that chart
          over time. */}
      {["Load", "Recovery", "Body", "Performance"].includes(tab) && (
        <div className="mb-4 flex items-center gap-1.5">
          <span className="text-[11px]" style={{ color: CHROME.muted }}>
            Range
          </span>
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRange(r)}
              aria-pressed={range === r}
              className="rounded-md px-2 py-1 text-[11px] font-medium"
              style={{
                background: range === r ? "var(--band-fill)" : "transparent",
                color: range === r ? CHROME.ink : CHROME.inkSecondary,
                border: "1px solid var(--border-hairline)",
              }}
            >
              {r}d
            </button>
          ))}
          <button
            type="button"
            onClick={() => setRange(3650)}
            aria-pressed={range === 3650}
            className="rounded-md px-2 py-1 text-[11px] font-medium"
            style={{
              background: range === 3650 ? "var(--band-fill)" : "transparent",
              color: range === 3650 ? CHROME.ink : CHROME.inkSecondary,
              border: "1px solid var(--border-hairline)",
            }}
          >
            All
          </button>
        </div>
      )}

      {tab === "Today" && <TodayTab data={data} />}
      {tab === "Week" && <WeekTab data={data} />}
      {tab === "Streaks" && <StreaksTab data={data} />}
      {tab === "Body" && <BodyTab data={data} range={range} />}
      {tab === "Insights" && <InsightsTab data={data} />}
      {tab === "Load" && <LoadTab data={data} range={range} />}
      {tab === "Recovery" && <RecoveryTab data={data} range={range} />}
      {tab === "Performance" && <PerformanceTab data={data} range={range} />}
    </div>
  );
}

/* ================================ TODAY ================================ */
function TodayTab({ data }: { data: TrainingData }) {
  const today = data.readiness.at(-1);
  const wellness = data.daily.at(-1);
  const hrvValues = data.daily.map((d) => d.hrv_night);
  const band = baselineBand(hrvValues, 60);
  const scorecardToday = data.scorecard.at(-1);
  const open = Object.entries(scorecardToday?.habits ?? {}).filter(([, s]) => s !== "hit");
  const hasCheckin = data.checkins.some((c) => c.day === new Date().toISOString().slice(0, 10));

  return (
    <div className="space-y-4">
      <ReadinessHero
        score={today?.score ?? null}
        band={today?.band ?? "unknown"}
        drivers={today?.drivers ?? []}
        coldStart={today?.cold_start ?? false}
        garminReadiness={wellness?.readiness ?? null}
      />

      <div className="grid grid-cols-2 gap-3">
        <Stat
          label="Last night HRV"
          value={num(wellness?.hrv_night ?? null, 0)}
          unit="ms"
          sub={band ? `Your band ${band.lo} to ${band.hi}` : "Baseline needs 14 nights"}
          color={
            band && wellness?.hrv_night
              ? wellness.hrv_night < band.lo
                ? STATUS.critical
                : wellness.hrv_night > band.hi
                  ? STATUS.warning
                  : STATUS.good
              : undefined
          }
        />
        <Stat
          label="Sleep"
          value={
            wellness?.sleep_total_min
              ? (wellness.sleep_total_min / 60).toFixed(1)
              : DASH
          }
          unit="h"
          sub={`Score ${num(wellness?.sleep_score ?? null, 0)}`}
        />
        <Stat label="Resting HR" value={num(wellness?.rhr ?? null, 0)} unit="bpm" />
        <Stat
          label="Form (TSB)"
          value={signed(data.loads.at(-1)?.tsb ?? null, 1)}
          sub={`CTL ${num(data.loads.at(-1)?.ctl ?? null, 1)}`}
        />
      </div>

      <Card title="Still open today">
        {open.length === 0 ? (
          <p className="text-xs" style={{ color: CHROME.inkSecondary }}>
            {scorecardToday
              ? "Everything logged for today is hit."
              : "No scorecard for today yet. It is written by tonight's compute."}
          </p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {open.map(([key, state]) => (
              <li
                key={key}
                className="flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px]"
                style={{ border: "1px solid var(--border-hairline)" }}
              >
                <span
                  aria-hidden
                  className="inline-block h-2 w-2 rounded-[2px]"
                  style={{ background: habitColor(state) }}
                />
                <span>{HABIT_LABELS[key] ?? key}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Daily check-in">
        {hasCheckin ? (
          <p className="text-xs" style={{ color: CHROME.inkSecondary }}>
            Logged for today. It feeds 10% of the readiness score.
          </p>
        ) : (
          <CheckinForm />
        )}
      </Card>
    </div>
  );
}

function CheckinForm() {
  const [state, setState] = useState({ soreness: 3, energy: 3, mood: 3, niggle_pain: 0 });
  const [status, setStatus] = useState<"idle" | "saving" | "done" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function submit() {
    setStatus("saving");
    setMessage(null);
    try {
      const res = await fetch("/api/checkin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(state),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? `HTTP ${res.status}`);
      setStatus("done");
    } catch (e) {
      setStatus("error");
      setMessage(e instanceof Error ? e.message : "Could not save");
    }
  }

  if (status === "done") {
    return (
      <p className="text-xs" style={{ color: STATUS.good }}>
        Saved. It will feed tonight's readiness score.
      </p>
    );
  }

  const SLIDERS: [keyof typeof state, string, number, number][] = [
    ["soreness", "Soreness", 1, 5],
    ["energy", "Energy", 1, 5],
    ["mood", "Mood", 1, 5],
    ["niggle_pain", "Niggle pain", 0, 10],
  ];

  return (
    <div className="space-y-3">
      {SLIDERS.map(([key, label, min, max]) => (
        <label key={key} className="block">
          <span className="flex justify-between text-xs">
            <span style={{ color: CHROME.inkSecondary }}>{label}</span>
            <span className="tabular font-medium">{state[key]}</span>
          </span>
          <input
            type="range"
            min={min}
            max={max}
            value={state[key]}
            onChange={(e) => setState({ ...state, [key]: Number(e.target.value) })}
            className="mt-1 w-full"
            style={{ accentColor: "var(--series-1)" }}
          />
        </label>
      ))}
      <button
        type="button"
        onClick={submit}
        disabled={status === "saving"}
        className="w-full rounded-lg px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
        style={{ background: "var(--series-1)" }}
      >
        {status === "saving" ? "Saving" : "Log check-in"}
      </button>
      {message && (
        <p className="text-[11px]" style={{ color: STATUS.critical }}>
          {message}
        </p>
      )}
    </div>
  );
}

/* ================================= WEEK ================================= */
function WeekTab({ data }: { data: TrainingData }) {
  const report = data.weekly.at(0);
  const sportRows = weeklyBySport(data.loads, 8);
  const thisWeek = sportRows.at(-1);
  const lastWeek = sportRows.at(-2);
  const topInsight = data.insights.at(0);

  const sportSeries: SeriesSpec[] = [
    { key: "run", label: "Run", color: SERIES.run, unit: "TSS", dp: 0 },
    { key: "bike", label: "Bike", color: SERIES.bike, unit: "TSS", dp: 0 },
    { key: "swim", label: "Swim", color: SERIES.swim, unit: "TSS", dp: 0 },
    { key: "strength", label: "Strength", color: SERIES.strength, unit: "TSS", dp: 0 },
  ];

  if (!report) {
    return (
      <EmptyState
        title="No weekly report yet"
        body="The weekly job runs Sunday at 18:31 Europe/London and writes the verdict with the numbers behind it."
      />
    );
  }

  const m = report.metrics as Record<string, any>;
  const colour =
    report.verdict === "push" ? STATUS.good
      : report.verdict === "back_off" ? STATUS.critical
        : STATUS.warning;

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className="inline-block h-3 w-3 rounded-full"
            style={{ background: colour }}
          />
          <h2 className="text-2xl font-semibold" style={{ color: colour }}>
            {VERDICT_LABEL[report.verdict]}
          </h2>
          <span className="ml-auto text-[11px]" style={{ color: CHROME.muted }}>
            {report.iso_year} week {report.iso_week}
          </span>
        </div>

        {report.narrative && (
          <p className="mt-2 text-sm" style={{ color: CHROME.inkSecondary }}>
            {report.narrative}
          </p>
        )}

        {/* The verdict never ships as a bare label: every rule shows its
            number and threshold. */}
        {Array.isArray(m.checks) && (
          <ul className="mt-3 space-y-1">
            {m.checks.map((c: any, i: number) => (
              <li key={i} className="flex items-center gap-2 text-xs">
                <span
                  aria-hidden
                  className="inline-block h-1.5 w-1.5 rounded-full"
                  style={{ background: c.passed ? STATUS.good : STATUS.critical }}
                />
                <span style={{ color: CHROME.inkSecondary }}>{c.name}</span>
                <span className="ml-auto tabular">
                  {c.value === null ? DASH : String(c.value)}
                  <span className="ml-1" style={{ color: CHROME.muted }}>
                    ({c.threshold})
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}

        {Array.isArray(m.unavailable) && m.unavailable.length > 0 && (
          <p className="mt-2 text-[11px]" style={{ color: CHROME.muted }}>
            Not assessed: {m.unavailable.join(", ")}
          </p>
        )}
      </Card>

      {report.watch_flags.length > 0 && (
        <Card title="Watch this week">
          <ul className="space-y-1.5">
            {report.watch_flags.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-xs">
                {/* Status colour plus an icon and a label, never colour alone. */}
                <span aria-hidden style={{ color: STATUS.warning }}>!</span>
                <span style={{ color: CHROME.inkSecondary }}>{f}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Stat
          label="Load this week"
          value={num(thisWeek ? thisWeek.run + thisWeek.bike + thisWeek.swim + thisWeek.strength : null, 0)}
          unit="TSS"
          sub={
            m.week_tss_change_pct !== null && m.week_tss_change_pct !== undefined
              ? `${signed(m.week_tss_change_pct, 0)}% on last week`
              : "No prior week"
          }
        />
        <Stat label="ACWR" value={num(m.acwr, 2)} sub="0.8 to 1.3 is the band" />
      </div>

      <StackedBars
        title="Load by sport"
        subtitle="Last 8 weeks, TSS"
        rows={sportRows}
        series={sportSeries}
        note="Walks and racquet sports are recorded but carry no TSS: there is no defensible load model for them here, so they are left out rather than estimated."
      />

      {topInsight && (
        <Card title="This week's top insight">
          <p className="text-sm">{topInsight.headline}</p>
          {topInsight.detail && (
            <p className="mt-1 text-xs" style={{ color: CHROME.inkSecondary }}>
              {topInsight.detail}
            </p>
          )}
        </Card>
      )}
    </div>
  );
}

/* =============================== STREAKS =============================== */
function StreaksTab({ data }: { data: TrainingData }) {
  const series = habitSeries(data.scorecard);

  if (series.length === 0) {
    return (
      <EmptyState
        title="No scorecard yet"
        body="Habit states are written nightly from the same rules the streak engine uses, so this fills in after the first compute run."
      />
    );
  }

  return (
    <div className="space-y-4">
      <HabitLegend />
      <div className="space-y-3">
        {series.map((h) => (
          <StreakCalendar
            key={h.key}
            label={HABIT_LABELS[h.key] ?? h.key}
            days={h.days}
            currentStreak={h.currentStreak}
            bestStreak={h.bestStreak}
            completion={h.completion}
            weeklyTarget={HABIT_WEEKLY_TARGET[h.key] ?? null}
            weekHits={h.weekHits}
          />
        ))}
      </div>
      <p className="text-[11px]" style={{ color: CHROME.muted }}>
        A day with no data is grey and does not break a streak. Only a logged miss does.
      </p>
    </div>
  );
}

/* ================================= BODY ================================= */
function BodyTab({ data, range }: { data: TrainingData; range: number }) {
  const targets = data.settings?.targets ?? {};
  const bandKg: [number, number] = targets.weight_band_kg ?? [68, 70];

  const weights = weightRows(data.scans, []);
  const comp = compositionRows(data.scans);
  const bf = bodyFatRows(data.scans);

  const latest = data.scans.at(-1);
  const first = data.scans.at(0);
  const gainQuality =
    latest && first && latest !== first &&
    latest.weight_kg && first.weight_kg &&
    latest.skeletal_muscle_kg && first.skeletal_muscle_kg &&
    Math.abs(latest.weight_kg - first.weight_kg) >= 0.3
      ? (latest.skeletal_muscle_kg - first.skeletal_muscle_kg) /
        (latest.weight_kg - first.weight_kg)
      : null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Stat
          label="Latest weight"
          value={num(latest?.weight_kg ?? null, 1)}
          unit="kg"
          sub={`Target ${bandKg[0]} to ${bandKg[1]} kg`}
        />
        <Stat label="Body fat" value={num(latest?.body_fat_pct ?? null, 1)} unit="%" />
        <Stat
          label="Skeletal muscle"
          value={num(latest?.skeletal_muscle_kg ?? null, 1)}
          unit="kg"
        />
        <Stat
          label="Gain quality"
          value={gainQuality === null ? DASH : `${Math.round(gainQuality * 100)}%`}
          sub={
            gainQuality === null
              ? `${data.scans.length} scan${data.scans.length === 1 ? "" : "s"} on record, needs 2`
              : "of weight gained was skeletal muscle"
          }
        />
      </div>

      {data.scans.length < 3 && (
        <p
          className="rounded-md px-2 py-1.5 text-[11px]"
          style={{ background: "var(--band-fill)", color: CHROME.inkSecondary }}
        >
          The composition trend uses a rolling 3-scan average. With{" "}
          {data.scans.length} scan{data.scans.length === 1 ? "" : "s"} on record the
          line is the raw reading, which swings with hydration and time of day.
        </p>
      )}

      <TrendWithPoints
        title="Weight"
        subtitle="Every weigh-in, with a smoothed trend and the target band shaded"
        rows={clip(weights, range)}
        pointKey="weight"
        trendKey="trend"
        targetBand={{ lo: bandKg[0], hi: bandKg[1] }}
        unit="kg"
        dp={1}
        note="The trend is an exponential average with alpha 0.1, so one salty day does not move it."
      />

      {/* Masses and percentage are different units, so they get separate
          charts rather than a second y-axis. */}
      <MultiLine
        title="Composition"
        subtitle="Skeletal muscle and fat mass, 3-scan rolling average"
        rows={clip(comp, range)}
        series={[
          { key: "muscle_avg", label: "Skeletal muscle", color: SERIES.ctl, unit: "kg", dp: 1 },
          { key: "fat_avg", label: "Fat mass", color: SERIES.atl, unit: "kg", dp: 1 },
        ]}
      />

      <MultiLine
        title="Body fat percent"
        subtitle="3-scan rolling average"
        rows={clip(bf, range)}
        series={[{ key: "body_fat_avg", label: "Body fat", color: SERIES.tsb, unit: "%", dp: 1 }]}
        note="Shown on its own chart: a percentage and a mass in kilograms cannot share one y-axis."
      />

      <Card title="Scans">
        {data.scans.length === 0 ? (
          <p className="text-xs" style={{ color: CHROME.inkSecondary }}>
            No scans stored yet. Upload a PDF or log one from any Claude chat.
          </p>
        ) : (
          <ul className="space-y-2">
            {[...data.scans].reverse().map((s) => (
              <li key={s.scanned_at} className="flex items-center gap-2 text-xs">
                <span className="tabular" style={{ color: CHROME.inkSecondary }}>
                  {shortDate(s.scanned_at)}
                </span>
                <span className="tabular">
                  {num(s.weight_kg, 1)} kg · {num(s.body_fat_pct, 1)}% ·{" "}
                  {num(s.skeletal_muscle_kg, 1)} kg muscle
                </span>
                {s.needs_review && (
                  <span
                    className="ml-auto rounded px-1.5 py-0.5 text-[10px] font-medium"
                    style={{ background: "rgba(250,178,25,0.18)", color: CHROME.ink }}
                    title={s.review_reason ?? undefined}
                  >
                    needs review
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        <ScanUpload />
      </Card>
    </div>
  );
}

function ScanUpload() {
  const [status, setStatus] = useState<"idle" | "up" | "done" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function upload(file: File) {
    setStatus("up");
    setMessage(null);
    const form = new FormData();
    form.set("file", file);
    try {
      const res = await fetch("/api/evolt", { method: "POST", body: form });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? `HTTP ${res.status}`);
      setStatus("done");
      setMessage(
        body.needs_review
          ? `Stored and flagged for review: ${body.review_reason}`
          : "Stored. It appears on the trend after tonight's compute.",
      );
    } catch (e) {
      setStatus("error");
      setMessage(e instanceof Error ? e.message : "Upload failed");
    }
  }

  return (
    <div className="mt-3">
      <label
        className="flex cursor-pointer items-center justify-center rounded-lg border border-dashed px-3 py-2 text-xs"
        style={{ borderColor: "var(--border-hairline)", color: CHROME.inkSecondary }}
      >
        {status === "up" ? "Uploading" : "Upload an Evolt PDF"}
        <input
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void upload(f);
          }}
        />
      </label>
      {message && (
        <p
          className="mt-1.5 text-[11px]"
          style={{ color: status === "error" ? STATUS.critical : CHROME.inkSecondary }}
        >
          {message}
        </p>
      )}
    </div>
  );
}

/* =============================== INSIGHTS =============================== */
function InsightsTab({ data }: { data: TrainingData }) {
  if (data.insights.length === 0) {
    return (
      <EmptyState
        title="No insights yet"
        body="An insight is only shown once there are 14 or more paired days and the effect clears day-to-day noise. Nothing has cleared both gates yet."
      />
    );
  }

  return (
    <div className="space-y-3">
      {data.insights.map((i) => (
        <Card key={i.id}>
          <p className="text-sm font-medium">{i.headline}</p>
          {i.detail && (
            <p className="mt-1 text-xs" style={{ color: CHROME.inkSecondary }}>
              {i.detail}
            </p>
          )}
          <div
            className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]"
            style={{ color: CHROME.muted }}
          >
            <span className="tabular">n = {i.n}</span>
            {i.effect_size !== null && (
              <span className="tabular">
                effect {signed(i.effect_size, 1)} {i.effect_unit}
              </span>
            )}
            {i.confidence !== null && (
              <span className="tabular">confidence {i.confidence.toFixed(2)}</span>
            )}
            {/* Correlation is labelled as correlation, every time. */}
            <span>{i.is_causal ? "causal" : "correlation, not proven cause"}</span>
          </div>
        </Card>
      ))}
    </div>
  );
}

/* ================================= LOAD ================================= */
function LoadTab({ data, range }: { data: TrainingData; range: number }) {
  const rows = clip(loadRows(data.loads), range);
  const sportRows = weeklyBySport(data.loads, 12);
  const latest = data.loads.at(-1);
  const thresholds = data.settings?.thresholds ?? {};
  const acwrBand: [number, number] = thresholds.acwr_band ?? [0.8, 1.3];
  const rampMax = thresholds.ctl_ramp_max ?? 6;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Fitness (CTL)" value={num(latest?.ctl ?? null, 1)} />
        <Stat label="Fatigue (ATL)" value={num(latest?.atl ?? null, 1)} />
        <Stat label="Form (TSB)" value={signed(latest?.tsb ?? null, 1)} />
      </div>

      <MultiLine
        title="Fitness, fatigue and form"
        subtitle="All three in TSS units, so they share one axis"
        rows={rows}
        series={[
          { key: "ctl", label: "Fitness (CTL)", color: SERIES.ctl, dp: 1 },
          { key: "atl", label: "Fatigue (ATL)", color: SERIES.atl, dp: 1 },
          { key: "tsb", label: "Form (TSB)", color: SERIES.tsb, dp: 1 },
        ]}
        zeroLine
      />

      <AcwrChart
        rows={rows.filter((r) => r.acwr !== null)}
        band={acwrBand}
        note="Seven-day load over the 28-day weekly average. Blank until there are 28 days of history: a partial chronic window reads high and would fire a false back-off. The dashed line is the 1.5 back-off threshold."
      />

      <Stat
        label="CTL ramp, last 7 days"
        value={signed(latest?.ctl_ramp_7d ?? null, 1)}
        sub={`Target is no more than about ${rampMax} points a week`}
        color={
          latest?.ctl_ramp_7d && latest.ctl_ramp_7d > rampMax ? STATUS.warning : undefined
        }
      />

      <StackedBars
        title="Weekly load by sport"
        subtitle="TSS, last 12 weeks"
        rows={sportRows}
        series={[
          { key: "run", label: "Run", color: SERIES.run, dp: 0 },
          { key: "bike", label: "Bike", color: SERIES.bike, dp: 0 },
          { key: "swim", label: "Swim", color: SERIES.swim, dp: 0 },
          { key: "strength", label: "Strength", color: SERIES.strength, dp: 0 },
        ]}
      />

      <StatusBars
        title="Daily load"
        subtitle="TSS per day"
        rows={rows}
        valueKey="tss"
        label="TSS"
        colorFor={(r) => (r.tss > 120 ? STATUS.warning : SERIES.ctl)}
      />
    </div>
  );
}

/* =============================== RECOVERY =============================== */
function RecoveryTab({ data, range }: { data: TrainingData; range: number }) {
  const base = recoveryRows(data.daily);
  const withRolling = rollingMean(base, "hrv", 7, "hrv_roll");
  const rows = clip(withRolling, range);
  const band = baselineBand(data.daily.map((d) => d.hrv_night), 60);
  const latest = data.daily.at(-1);

  const sleepDebt = useMemo(() => {
    const target = (data.settings?.targets?.sleep_hours ?? 7.5) * 60;
    const last7 = data.daily.slice(-7).map((d) => d.sleep_total_min).filter((v): v is number => v !== null);
    if (last7.length === 0) return null;
    return +((last7.reduce((a, b) => a + (b - target), 0)) / 60).toFixed(1);
  }, [data.daily, data.settings]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Stat
          label="HRV 7-day"
          value={num(rows.at(-1)?.hrv_roll ?? null, 0)}
          unit="ms"
          sub={band ? `Band ${band.lo} to ${band.hi}` : "Needs 14 nights"}
        />
        <Stat
          label="Sleep debt, 7 days"
          value={sleepDebt === null ? DASH : signed(sleepDebt, 1)}
          unit="h"
        />
        <Stat label="Resting HR" value={num(latest?.rhr ?? null, 0)} unit="bpm" />
        <Stat label="Stress average" value={num(latest?.stress_avg ?? null, 0)} />
      </div>

      <BandedLine
        title="HRV against your own baseline"
        subtitle="Nightly reading, with the 60-day mean plus or minus one SD shaded"
        rows={rows}
        series={{ key: "hrv", label: "HRV", color: SERIES.primary, unit: "ms", dp: 0 }}
        band={band ? { lo: band.lo, hi: band.hi } : null}
        note="Below the band reads as strain. Above it is flagged too, since a sharp rise can be parasympathetic saturation rather than good news."
      />

      <MultiLine
        title="Resting heart rate"
        rows={rows}
        series={[{ key: "rhr", label: "Resting HR", color: SERIES.atl, unit: "bpm", dp: 0 }]}
      />

      <StatusBars
        title="Sleep score"
        subtitle="Green at or above the 75 target, red below"
        rows={rows}
        valueKey="sleep_score"
        label="Sleep score"
        colorFor={(r) =>
          r.sleep_score === null
            ? STATUS.none
            : r.sleep_score >= (data.settings?.targets?.sleep_score ?? 75)
              ? STATUS.good
              : STATUS.critical
        }
      />

      <MultiLine
        title="Sleep stages"
        subtitle="Minutes of deep and REM"
        rows={rows}
        series={[
          { key: "deep", label: "Deep", color: SERIES.ctl, unit: "min", dp: 0 },
          { key: "rem", label: "REM", color: SERIES.tsb, unit: "min", dp: 0 },
        ]}
      />

      <MultiLine
        title="Body battery"
        rows={rows}
        series={[
          { key: "body_battery_max", label: "Max", color: SERIES.ctl, dp: 0 },
          { key: "body_battery_min", label: "Min", color: SERIES.atl, dp: 0 },
        ]}
      />
    </div>
  );
}

/* ============================= PERFORMANCE ============================= */
function PerformanceTab({ data, range }: { data: TrainingData; range: number }) {
  const latest = data.daily.filter((d) => d.vo2max_run !== null).at(-1);
  const settings = data.settings;
  const runEf = clip(efficiencyRows(data.activities, "run"), range);
  const bikeEf = clip(efficiencyRows(data.activities, "bike"), range);

  const best = useMemo(
    () =>
      [...data.activities]
        .filter((a) => a.sport === "run" && a.distance_m && a.is_primary && a.is_valid)
        .sort((a, b) => (a.avg_pace ?? 1e9) - (b.avg_pace ?? 1e9))
        .slice(0, 5),
    [data.activities],
  );

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Stat label="FTP" value={num(settings?.ftp_w ?? null, 0)} unit="W" />
        <Stat
          label="Threshold pace"
          value={pace(settings?.threshold_pace ?? null)}
          sub={settings?.threshold_pace ? "Estimated from a 5k, not tested" : undefined}
        />
        <Stat
          label="CSS"
          value={
            settings?.css_swim ? `${Math.floor(settings.css_swim / 60)}:${String(Math.round(settings.css_swim % 60)).padStart(2, "0")}/100m` : DASH
          }
          sub={settings?.css_swim ? undefined : "Needs a CSS test"}
        />
        <Stat
          label="VO2max"
          value={num(latest?.vo2max_run ?? null, 1)}
          sub={latest ? "From the Garmin login route" : "Login route not reporting"}
        />
      </div>

      <MultiLine
        title="Run efficiency"
        subtitle="Metres per beat. Rising at the same heart rate means aerobic fitness improving."
        rows={runEf}
        series={[{ key: "ef", label: "Metres per beat", color: SERIES.run, dp: 2 }]}
        note="Every run with a heart rate, not only steady ones, so an interval session will read low. Treat the trend rather than a single point."
      />

      {bikeEf.length > 0 && (
        <MultiLine
          title="Bike efficiency"
          rows={bikeEf}
          series={[{ key: "ef", label: "Metres per beat", color: SERIES.bike, dp: 2 }]}
        />
      )}

      <Card title="Fastest runs in range">
        {best.length === 0 ? (
          <p className="text-xs" style={{ color: CHROME.inkSecondary }}>
            No runs with a pace in this range.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {best.map((a) => (
              <li key={a.id} className="flex items-center gap-2 text-xs tabular">
                <span style={{ color: CHROME.inkSecondary }}>{shortDate(a.start_at)}</span>
                <span>{km(a.distance_m)}</span>
                <span className="ml-auto font-medium">{pace(a.avg_pace)}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-[11px]" style={{ color: CHROME.muted }}>
          Ranked on average pace. Peak speed is deliberately not used: GPS
          spikes make it unreliable.
        </p>
      </Card>

      {data.gear.filter((g) => g.gear_type === "shoe").length > 0 && (
        <Card title="Shoe mileage">
          <ul className="space-y-1.5">
            {data.gear
              .filter((g) => g.gear_type === "shoe")
              .sort((a, b) => b.distance_m - a.distance_m)
              .map((g) => {
                const frac = g.retire_at_m ? g.distance_m / g.retire_at_m : 0;
                const due = frac >= 1;
                const near = frac >= 0.85;
                return (
                  <li key={g.source_id} className="text-xs">
                    <div className="flex items-center gap-2">
                      <span>{g.name ?? g.model_name ?? "Shoe"}</span>
                      <span className="ml-auto tabular" style={{ color: CHROME.inkSecondary }}>
                        {km(g.distance_m, 0)}
                        {g.retire_at_m ? ` / ${km(g.retire_at_m, 0)}` : ""}
                      </span>
                      {(due || near) && (
                        <span
                          className="rounded px-1 text-[10px] font-medium"
                          style={{
                            background: due ? "rgba(208,59,59,0.14)" : "rgba(250,178,25,0.18)",
                            color: CHROME.ink,
                          }}
                        >
                          {due ? "replace" : "nearly due"}
                        </span>
                      )}
                    </div>
                    <span
                      className="mt-1 block h-1 overflow-hidden rounded-full"
                      style={{ background: "var(--gridline)" }}
                    >
                      <span
                        className="block h-full rounded-full"
                        style={{
                          width: `${Math.min(frac * 100, 100)}%`,
                          background: due ? STATUS.critical : near ? STATUS.warning : SERIES.run,
                        }}
                      />
                    </span>
                  </li>
                );
              })}
          </ul>
        </Card>
      )}
    </div>
  );
}
